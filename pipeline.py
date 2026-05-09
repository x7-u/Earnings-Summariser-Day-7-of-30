"""Day 7. Orchestrator for BRIEF (earnings call summariser).

analyse():
  1. parse_transcript() reads the transcript.
  2. detect_signals() (rule-based) tags hedge / certainty / deflection phrases.
  3. extract() pulls every quantitative claim ($ / %).
  4. ONE batched DeepSeek V4 call extracts guidance, themes, Q&A, risks, and
     an exec summary into a strict JSON shape.
  5. compute_tone_curve() and compute_headline_stats() roll everything up.

Idempotent: identical inputs short-circuit to the cached AI result via a
content-hash cache.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import (
    CallAnalysis,
    ExecSummary,
    GuidanceItem,
    QAExchange,
    RiskFlag,
    ThemeCard,
    compose_multiquarter,
    compute_headline_stats,
    compute_tone_curve,
)
from claims import extract as extract_claims
from hedge_phrases import detect_signals
from transcript_schema import TranscriptDoc, parse_transcript

from shared.config import DEEPSEEK_MODEL_FAST
from shared.deepseek_client import ask_deepseek_json_with_stats

DEFAULT_COST_GUARDRAIL_USD = float(os.getenv("DAY07_MAX_COST_USD", "0.05"))
TRACE_DIR = Path(__file__).resolve().parent / "outputs" / "traces"
HASH_CACHE_DIR = Path(__file__).resolve().parent / "outputs" / "hash_cache"


# ---- Result wrapper ------------------------------------------------

@dataclass
class AICallStats:
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    model: str = ""
    skipped: bool = False
    error: str | None = None


@dataclass
class AnalysisResult:
    call: CallAnalysis
    ai_stats: AICallStats
    source_filename: str = ""
    elapsed_ms: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        return self.ai_stats.cost_usd or 0.0


# ---- Cost helpers --------------------------------------------------

def estimate_cost(word_count: int) -> float:
    """Rough cost: ~1.3 tokens per word in + ~1500 tokens out at deepseek-chat rates.
    deepseek-chat: $0.27/1M cache miss in, $1.10/1M out.
    """
    in_tokens = int(1.3 * word_count) + 200  # plus system prompt overhead
    out_tokens = 1500
    return (in_tokens * 0.27 + out_tokens * 1.10) / 1_000_000


def _content_hash(transcript: TranscriptDoc) -> str:
    payload = {
        "company": transcript.metadata.company,
        "ticker": transcript.metadata.ticker,
        "fiscal_period": transcript.metadata.fiscal_period,
        "call_date": transcript.metadata.call_date,
        "turns": [f"{t.speaker}|{t.role}|{t.text[:120]}" for t in transcript.turns],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# ---- The AI call ---------------------------------------------------

EXTRACT_SYSTEM_PROMPT = (
    "You are a senior buy-side equity analyst reading an earnings call "
    "transcript. Extract a structured analysis. Be specific: cite quotes, "
    "name analysts and their firms, classify management tone honestly. "
    "When you state a guidance figure, include the exact phrase the company "
    "used. When you score management clarity, ground it in whether they "
    "answered the analyst's question or deflected."
)

EXTRACT_FILING_SYSTEM_PROMPT = (
    "You are a senior buy-side equity analyst reading a SEC filing (10-K, "
    "10-Q, or 8-K) directly from EDGAR. Extract what you can from the "
    "narrative: forward-looking guidance from the MD&A or outlook section, "
    "key business themes from the filing's discussion, named risk factors "
    "with severity, and a bull/bear summary based on the document. Note: "
    "this is a written filing, not a transcript, so the qa array will be "
    "empty (there is no analyst Q&A). For 8-Ks that are just material event "
    "notices (executive change, contract win, etc.) with no financial "
    "outlook, return what you can; some arrays may be empty. Cite the "
    "filing's verbatim phrases in quotes."
)

EXTRACT_SCHEMA = (
    '{\n'
    '  "guidance": [\n'
    '    {\n'
    '      "metric": "revenue|gross_margin|operating_margin|capex|eps|fcf|other",\n'
    '      "period": "Q2 FY2026 etc",\n'
    '      "direction": "up|down|flat|withdrawn|raised|lowered",\n'
    '      "range_low": null,\n'
    '      "range_high": null,\n'
    '      "unit": "USD bn|%|USD|GBP bn",\n'
    '      "quote": "the verbatim phrase",\n'
    '      "prior": "prior guidance phrase if mentioned, else empty"\n'
    '    }\n'
    '  ],\n'
    '  "themes": [\n'
    '    {"name": "AI investment", "weight": 0.0, "sentiment": "bullish|neutral|bearish", "key_quotes": ["..."]}\n'
    '  ],\n'
    '  "qa": [\n'
    '    {\n'
    '      "analyst_name": "...",\n'
    '      "analyst_firm": "...",\n'
    '      "question_summary": "1 sentence",\n'
    '      "answer_summary": "1 to 2 sentences",\n'
    '      "tension": "cooperative|probing|hostile",\n'
    '      "management_clarity": "clear|hedged|deflected"\n'
    '    }\n'
    '  ],\n'
    '  "risks": [\n'
    '    {"category": "demand|regulation|fx|supply|competition|macro|other",\n'
    '     "severity": "high|medium|low", "quote": "..."}\n'
    '  ],\n'
    '  "exec_summary": {\n'
    '    "headline": "1 sentence verdict",\n'
    '    "bull_case": "2 sentences",\n'
    '    "bear_case": "2 sentences",\n'
    '    "actions": ["short imperative for the PM", "..."]\n'
    '  }\n'
    '}'
)


def _build_transcript_digest(transcript: TranscriptDoc, *,
                             max_chars: int = 32_000) -> str:
    """Build the prompt body. Includes a short metadata header + every speaker
    turn labelled by role. Truncates evenly across the call if it would
    exceed max_chars (rare on deepseek-chat's 64k context, but defensive).
    """
    md = transcript.metadata
    header = (
        f"Company: {md.company}\n"
        f"Ticker:  {md.ticker}\n"
        f"Period:  {md.fiscal_period}\n"
        f"Date:    {md.call_date}\n"
        f"Word count: {md.word_count}\n"
        f"---\n"
    )
    body_lines: list[str] = []
    for t in transcript.turns:
        firm = f" ({t.firm})" if t.firm else ""
        body_lines.append(f"[{t.role}] {t.speaker}{firm}: {t.text}")
    body = "\n\n".join(body_lines)
    if len(header) + len(body) > max_chars:
        # Aggressive trim: keep first 60% and last 35% of the body so we hold
        # both the prepared remarks and the Q&A.
        keep = max_chars - len(header) - 200
        head = body[: int(keep * 0.6)]
        tail = body[-int(keep * 0.35):]
        body = head + "\n\n[...transcript truncated for length...]\n\n" + tail
    return header + body


def call_deepseek(transcript: TranscriptDoc, *,
                  model: str | None = None,
                  api_key: str | None = None,
                  self_consistency: int = 1,
                  mode: str = "transcript") -> tuple[dict, AICallStats]:
    digest = _build_transcript_digest(transcript)
    base_prompt = (EXTRACT_FILING_SYSTEM_PROMPT
                   if mode == "filing" else EXTRACT_SYSTEM_PROMPT)
    sys_prompt = base_prompt + "\n\nReply schema:\n" + EXTRACT_SCHEMA
    runs: list[dict] = []
    total_in = 0
    total_out = 0
    total_cost = 0.0
    last_model = ""
    for _i in range(max(1, self_consistency)):
        try:
            data, stats = ask_deepseek_json_with_stats(
                digest, system=sys_prompt, max_tokens=2000,
                model=(model or DEEPSEEK_MODEL_FAST),
                api_key=api_key,
            )
        except Exception as e:
            return {}, AICallStats(error=_scrub(e),
                                   model=model or DEEPSEEK_MODEL_FAST)
        runs.append(data)
        total_in += stats.input_tokens
        total_out += stats.output_tokens
        total_cost += stats.cost_usd
        last_model = stats.model
    merged = _merge_self_consistency(runs)
    return merged, AICallStats(
        cost_usd=total_cost, input_tokens=total_in, output_tokens=total_out,
        cache_hit_tokens=0, model=last_model,
        skipped=False, error=None,
    )


def _merge_self_consistency(runs: list[dict]) -> dict:
    """Merge N self-consistency runs.

    For arrays of dicts (guidance, themes, qa, risks): keep the longest run
    (proxy for richest extraction), but majority-vote on per-item enums where
    possible by joining items with the same key (e.g. analyst_name, metric).

    For the exec_summary: take the first run's free-text fields, but vote on
    nothing (free text doesn't vote cleanly).

    For numeric fields inside guidance items: average across runs that
    matched the same metric+period. Reduces extraction-noise jitter.
    """
    if not runs:
        return {}
    if len(runs) == 1:
        return runs[0]
    base = max(runs, key=lambda r: len(r.get("guidance") or [])
                                  + len(r.get("themes") or [])
                                  + len(r.get("qa") or [])
                                  + len(r.get("risks") or []))
    out = dict(base)

    # Vote / average on guidance items with matching metric+period.
    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in runs:
        for g in (r.get("guidance") or []):
            k = (str(g.get("metric") or ""), str(g.get("period") or ""))
            by_key.setdefault(k, []).append(g)
    merged_guidance = []
    for k, items in by_key.items():
        if len(items) == 1:
            merged_guidance.append(items[0])
            continue
        # Majority direction
        from collections import Counter
        dirs = Counter(str(i.get("direction") or "") for i in items)
        most_dir = dirs.most_common(1)[0][0] if dirs else ""
        # Average ranges where both runs supplied numeric values
        lows = [_safe_num(i.get("range_low")) for i in items]
        lows_n = [x for x in lows if x is not None]
        highs = [_safe_num(i.get("range_high")) for i in items]
        highs_n = [x for x in highs if x is not None]
        merged_guidance.append({
            "metric": k[0],
            "period": k[1],
            "direction": most_dir,
            "range_low": (sum(lows_n) / len(lows_n)) if lows_n else None,
            "range_high": (sum(highs_n) / len(highs_n)) if highs_n else None,
            "unit": items[0].get("unit", ""),
            "quote": items[0].get("quote", ""),
            "prior": items[0].get("prior", ""),
        })
    if merged_guidance:
        out["guidance"] = merged_guidance
    return out


def _safe_num(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---- Deserialise AI JSON into dataclasses --------------------------

def _deserialise_ai(data: dict) -> tuple[list[GuidanceItem], list[ThemeCard],
                                          list[QAExchange], list[RiskFlag],
                                          ExecSummary]:
    g = []
    for item in (data.get("guidance") or []):
        try:
            g.append(GuidanceItem(
                metric=str(item.get("metric") or "other"),
                period=str(item.get("period") or ""),
                direction=str(item.get("direction") or "flat"),
                range_low=_to_float(item.get("range_low")),
                range_high=_to_float(item.get("range_high")),
                unit=str(item.get("unit") or ""),
                quote=str(item.get("quote") or "")[:600],
                prior=str(item.get("prior") or "")[:200],
            ))
        except Exception:
            continue
    th = []
    for item in (data.get("themes") or []):
        try:
            th.append(ThemeCard(
                name=str(item.get("name") or "Theme"),
                weight=max(0.0, min(1.0, float(item.get("weight") or 0))),
                sentiment=str(item.get("sentiment") or "neutral"),
                key_quotes=[str(q)[:300] for q in (item.get("key_quotes") or [])][:5],
            ))
        except Exception:
            continue
    qa = []
    for item in (data.get("qa") or []):
        try:
            qa.append(QAExchange(
                analyst_name=str(item.get("analyst_name") or ""),
                analyst_firm=str(item.get("analyst_firm") or ""),
                question_summary=str(item.get("question_summary") or "")[:500],
                answer_summary=str(item.get("answer_summary") or "")[:800],
                tension=str(item.get("tension") or "cooperative"),
                management_clarity=str(item.get("management_clarity") or "clear"),
            ))
        except Exception:
            continue
    risks = []
    for item in (data.get("risks") or []):
        try:
            risks.append(RiskFlag(
                category=str(item.get("category") or "other"),
                severity=str(item.get("severity") or "medium"),
                quote=str(item.get("quote") or "")[:400],
            ))
        except Exception:
            continue
    es = data.get("exec_summary") or {}
    summary = ExecSummary(
        headline=str(es.get("headline") or "")[:280],
        bull_case=str(es.get("bull_case") or ""),
        bear_case=str(es.get("bear_case") or ""),
        actions=[str(a)[:200] for a in (es.get("actions") or [])][:5],
    )
    return g, th, qa, risks, summary


def _to_float(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---- Main analyse() ------------------------------------------------

def analyse(*,
            file_bytes: bytes | None = None,
            path: Path | str | None = None,
            text: str | None = None,
            source_filename: str = "",
            skip_ai: bool = False,
            model: str | None = None,
            api_key: str | None = None,
            use_cache: bool = True,
            self_consistency: int = 1,
            max_cost_usd: float | None = None,
            mode: str = "transcript") -> AnalysisResult:
    started = _time.time()

    transcript = parse_transcript(
        file_bytes=file_bytes, path=path, text=text,
        source_filename=source_filename,
    )

    hits = detect_signals(transcript.turns)
    claims = extract_claims(transcript.turns)
    headline = compute_headline_stats(transcript, hits, claims)
    tone_curve = compute_tone_curve(transcript.turns, hits)

    if not skip_ai:
        budget = max_cost_usd if max_cost_usd is not None else DEFAULT_COST_GUARDRAIL_USD
        est = estimate_cost(transcript.metadata.word_count) * max(1, self_consistency)
        if budget and est > budget:
            raise ValueError(
                f"Estimated AI cost ${est:.4f} (with {self_consistency}x self-consistency) "
                f"exceeds guardrail ${budget:.4f}. Raise DAY07_MAX_COST_USD."
            )

    chash = _content_hash(transcript)
    chosen_model = model or DEEPSEEK_MODEL_FAST

    if use_cache and not skip_ai:
        cache_path = _hash_cache_path(chash, model=chosen_model,
                                       sc=self_consistency, mode=mode)
        cached = _load_cached_ai(cache_path)
        if cached is not None:
            transcript.warnings.append("Cache hit on transcript hash, AI call skipped (cost saved).")
            g, th, qa, risks, summary = _deserialise_ai(cached["data"])
            ai_stats = AICallStats(
                cost_usd=0.0,
                input_tokens=int(cached["stats"].get("input_tokens", 0)),
                output_tokens=int(cached["stats"].get("output_tokens", 0)),
                model=cached["stats"].get("model", chosen_model),
            )
            call = CallAnalysis(
                transcript=transcript, headline=headline,
                guidance=g, themes=th, qa=qa, risks=risks,
                exec_summary=summary, tone_curve=tone_curve,
                phrase_hits=hits, number_claims=claims,
            )
            elapsed_ms = int((_time.time() - started) * 1000)
            return AnalysisResult(
                call=call, ai_stats=ai_stats,
                source_filename=source_filename,
                elapsed_ms=elapsed_ms,
                warnings=transcript.warnings,
            )

    if skip_ai:
        ai_data: dict = {}
        ai_stats = AICallStats(skipped=True)
    else:
        ai_data, ai_stats = call_deepseek(
            transcript, model=model, api_key=api_key,
            self_consistency=self_consistency,
            mode=mode,
        )

    g, th, qa, risks, summary = _deserialise_ai(ai_data)
    call = CallAnalysis(
        transcript=transcript, headline=headline,
        guidance=g, themes=th, qa=qa, risks=risks,
        exec_summary=summary, tone_curve=tone_curve,
        phrase_hits=hits, number_claims=claims,
    )
    elapsed_ms = int((_time.time() - started) * 1000)
    result = AnalysisResult(
        call=call, ai_stats=ai_stats,
        source_filename=source_filename,
        elapsed_ms=elapsed_ms,
        warnings=transcript.warnings,
    )

    try:
        _write_trace(chash, result)
    except Exception:
        pass
    if use_cache and not skip_ai and not ai_stats.error:
        try:
            _write_cached_ai(
                _hash_cache_path(chash, model=chosen_model,
                                 sc=self_consistency, mode=mode),
                ai_data, ai_stats,
            )
        except Exception:
            pass
    return result


def followup(*, run_payload: dict, question: str,
             model: str | None = None, api_key: str | None = None) -> dict:
    """Free-text follow-up question on a cached run. Single AI call."""
    md = run_payload.get("metadata", {})
    h = run_payload.get("headline", {}) or {}
    summary = (run_payload.get("exec_summary") or {}).get("headline", "")
    digest = (
        f"Subject: {md.get('company','')}  ({md.get('ticker','')})  "
        f"{md.get('fiscal_period','')}\n"
        f"Tone: {h.get('overall_tone','')}  "
        f"confidence={h.get('confidence_score','')}  "
        f"hedge={h.get('hedge_count','')}  "
        f"certainty={h.get('certainty_count','')}  "
        f"deflection={h.get('deflection_count','')}\n"
        f"Verdict: {summary}\n\n"
        f"Question: {question.strip()[:500]}"
    )
    sys_prompt = (
        "You are the same buy-side analyst who summarised this earnings call. "
        "Answer the user's follow-up question in two to three sentences. "
        "Plain language. Cite specific numbers when you have them."
    )
    schema = '{\n  "answer": "2-3 sentences"\n}'
    try:
        data, stats = ask_deepseek_json_with_stats(
            digest, system=sys_prompt + "\n\nReply schema:\n" + schema,
            max_tokens=300, model=(model or DEEPSEEK_MODEL_FAST), api_key=api_key,
        )
    except Exception as e:
        return {"answer": "", "error": _scrub(e),
                "model": model or DEEPSEEK_MODEL_FAST,
                "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
    return {
        "answer": str(data.get("answer") or "").strip(),
        "error": None,
        "model": stats.model,
        "cost_usd": round(stats.cost_usd, 6),
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
    }


# ---- Cache helpers -------------------------------------------------

def _hash_cache_path(content_hash: str, *, model: str, sc: int = 1,
                     mode: str = "transcript") -> Path:
    safe_model = "".join(ch if ch.isalnum() else "_" for ch in model)[:30]
    safe_mode = "".join(ch if ch.isalnum() else "_" for ch in mode)[:16]
    return HASH_CACHE_DIR / f"{content_hash}_{safe_model}_sc{sc}_{safe_mode}.json"


def _load_cached_ai(p: Path) -> dict | None:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cached_ai(p: Path, data: dict, stats: AICallStats) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": data,
        "stats": {
            "input_tokens": stats.input_tokens,
            "output_tokens": stats.output_tokens,
            "model": stats.model,
        },
    }
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_trace(chash: str, result: AnalysisResult) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.UTC).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    md = result.call.transcript.metadata
    rec = {
        "ts": ts, "content_hash": chash,
        "company": md.company, "ticker": md.ticker,
        "fiscal_period": md.fiscal_period,
        "ai_cost_usd": round(result.total_cost_usd, 6),
        "ai_model": result.ai_stats.model,
        "elapsed_ms": result.elapsed_ms,
        "tone": result.call.headline.overall_tone,
        "confidence": result.call.headline.confidence_score,
    }
    (TRACE_DIR / "traces.jsonl").open("a", encoding="utf-8").write(
        json.dumps(rec, ensure_ascii=False) + "\n")


# ---- Multi-quarter ------------------------------------------------

def analyse_multiquarter(transcripts: list[dict[str, Any]], *,
                         skip_ai: bool = False,
                         model: str | None = None,
                         api_key: str | None = None) -> dict[str, Any]:
    """Each transcript dict has 'text' (or 'file_bytes') and 'source_filename'.
    Runs analyse() per transcript and composes a comparison view."""
    analyses: list[CallAnalysis] = []
    per_run: list[AnalysisResult] = []
    for tr in transcripts:
        res = analyse(
            file_bytes=tr.get("file_bytes"),
            path=tr.get("path"),
            text=tr.get("text"),
            source_filename=tr.get("source_filename", ""),
            skip_ai=skip_ai, model=model, api_key=api_key,
        )
        per_run.append(res)
        analyses.append(res.call)
    cells = compose_multiquarter(analyses)
    return {
        "cells": [
            {
                "period": c.period,
                "overall_tone": c.overall_tone,
                "confidence_score": c.confidence_score,
                "hedge_count": c.hedge_count,
                "certainty_count": c.certainty_count,
                "deflection_count": c.deflection_count,
                "revenue_guidance_low": c.revenue_guidance_low,
                "revenue_guidance_high": c.revenue_guidance_high,
                "revenue_unit": c.revenue_unit,
            }
            for c in cells
        ],
        "per_run": [to_dict(r) for r in per_run],
    }


# ---- Serialisation -------------------------------------------------

def to_dict(result: AnalysisResult) -> dict[str, Any]:
    call = result.call
    md = call.transcript.metadata
    h = call.headline
    return {
        "metadata": {
            "company": md.company, "ticker": md.ticker,
            "fiscal_period": md.fiscal_period, "call_date": md.call_date,
            "word_count": md.word_count,
            "source_filename": md.source_filename,
        },
        "headline": {
            "overall_tone": h.overall_tone,
            "confidence_score": h.confidence_score,
            "hedge_count": h.hedge_count,
            "certainty_count": h.certainty_count,
            "deflection_count": h.deflection_count,
            "quantitative_claims": h.quantitative_claims,
            "minutes": h.minutes,
            "word_count": h.word_count,
            "analyst_count": h.analyst_count,
            "role_word_share": dict(h.role_word_share),
        },
        "guidance": [
            {"metric": g.metric, "period": g.period, "direction": g.direction,
             "range_low": g.range_low, "range_high": g.range_high,
             "unit": g.unit, "quote": g.quote, "prior": g.prior}
            for g in call.guidance
        ],
        "themes": [
            {"name": t.name, "weight": t.weight, "sentiment": t.sentiment,
             "key_quotes": list(t.key_quotes)}
            for t in call.themes
        ],
        "qa": [
            {"analyst_name": q.analyst_name, "analyst_firm": q.analyst_firm,
             "question_summary": q.question_summary,
             "answer_summary": q.answer_summary,
             "tension": q.tension, "management_clarity": q.management_clarity}
            for q in call.qa
        ],
        "risks": [
            {"category": r.category, "severity": r.severity, "quote": r.quote}
            for r in call.risks
        ],
        "exec_summary": (None if call.exec_summary is None else {
            "headline": call.exec_summary.headline,
            "bull_case": call.exec_summary.bull_case,
            "bear_case": call.exec_summary.bear_case,
            "actions": list(call.exec_summary.actions),
        }),
        "tone_curve": [
            {"minute": p.minute, "tone": p.tone,
             "speaker_role": p.speaker_role, "word_count": p.word_count}
            for p in call.tone_curve
        ],
        "phrase_hits": [
            {"bucket": h_.bucket, "phrase": h_.phrase, "speaker": h_.speaker,
             "role": h_.role, "minute": h_.minute, "context": h_.context}
            for h_ in call.phrase_hits[:200]
        ],
        "number_claims": [
            {"raw": n.raw, "kind": n.kind, "value_low": n.value_low,
             "value_high": n.value_high, "unit": n.unit, "speaker": n.speaker,
             "role": n.role, "minute": n.minute, "context": n.context}
            for n in call.number_claims
        ],
        "warnings": list(result.warnings),
        "source_filename": result.source_filename,
        "elapsed_ms": result.elapsed_ms,
        "ai_stats": {
            "cost_usd": round(result.ai_stats.cost_usd, 6),
            "input_tokens": result.ai_stats.input_tokens,
            "output_tokens": result.ai_stats.output_tokens,
            "model": result.ai_stats.model,
            "skipped": result.ai_stats.skipped,
            "error": result.ai_stats.error,
        },
        "total_cost_usd": round(result.total_cost_usd, 6),
    }


def _scrub(e: Exception) -> str:
    msg = f"{type(e).__name__}: {e}"
    msg = re.sub(r"/[^\s'\"]+|[A-Z]:\\[^\s'\"]+", "<path>", msg)
    msg = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-***", msg)
    return msg[:300]
