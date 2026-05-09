"""Day 7. Analysis dataclasses + tone-curve assembly.

The AI extraction call (see pipeline.py) produces a JSON document. We
deserialise it into the dataclasses below, then enrich with the
deterministic outputs from hedge_phrases / numbers / transcript_schema.

This module is pure: no IO, no AI, no Flask.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from claims import NumberClaim
from hedge_phrases import PhraseHit, confidence_score, signal_summary
from transcript_schema import SpeakerTurn, TranscriptDoc

# ---- AI-produced dataclasses ---------------------------------------

@dataclass
class GuidanceItem:
    metric: str               # "revenue", "gross_margin", "capex", "eps", "fcf"
    period: str               # e.g. "Q2 FY2026", "FY2026"
    direction: str            # "up", "down", "flat", "withdrawn", "raised"
    range_low: float | None
    range_high: float | None
    unit: str                 # "USD bn", "%", "USD"
    quote: str
    prior: str = ""           # prior guidance for this metric, if mentioned


@dataclass
class ThemeCard:
    name: str
    weight: float             # 0..1 narrative weight
    sentiment: str            # bullish / neutral / bearish
    key_quotes: list[str] = field(default_factory=list)


@dataclass
class QAExchange:
    analyst_name: str
    analyst_firm: str
    question_summary: str
    answer_summary: str
    tension: str              # "cooperative" / "probing" / "hostile"
    management_clarity: str   # "clear" / "hedged" / "deflected"


@dataclass
class RiskFlag:
    category: str             # "demand", "regulation", "fx", "supply", "competition", "macro"
    severity: str             # "high" / "medium" / "low"
    quote: str


@dataclass
class ExecSummary:
    headline: str             # one sentence verdict
    bull_case: str
    bear_case: str
    actions: list[str] = field(default_factory=list)


@dataclass
class HeadlineStats:
    overall_tone: str         # "confident" / "cautious" / "defensive"
    confidence_score: float   # 0..1
    hedge_count: int
    certainty_count: int
    deflection_count: int
    quantitative_claims: int
    minutes: int
    word_count: int
    analyst_count: int
    role_word_share: dict[str, float] = field(default_factory=dict)


@dataclass
class TonePoint:
    minute: int
    tone: float               # -1 .. 1
    speaker_role: str
    word_count: int


@dataclass
class CallAnalysis:
    transcript: TranscriptDoc
    headline: HeadlineStats
    guidance: list[GuidanceItem] = field(default_factory=list)
    themes: list[ThemeCard] = field(default_factory=list)
    qa: list[QAExchange] = field(default_factory=list)
    risks: list[RiskFlag] = field(default_factory=list)
    exec_summary: ExecSummary | None = None
    tone_curve: list[TonePoint] = field(default_factory=list)
    phrase_hits: list[PhraseHit] = field(default_factory=list)
    number_claims: list[NumberClaim] = field(default_factory=list)


# ---- Tone curve ---------------------------------------------------

def compute_tone_curve(turns: list[SpeakerTurn],
                       hits: list[PhraseHit]) -> list[TonePoint]:
    """Build a per-minute management tone curve.

    Tone for a turn = (cert_count - hedge_count - 2*deflect_count) /
                      max(1, total_signal_count). Plus a 0.05 baseline-shift
                      for whether the turn is explicitly bullish or bearish
                      based on simple keyword count (record/strong/grew vs
                      weak/declined/headwinds).

    Output is a list of points, one per turn, with the running minute index.
    """
    # For each turn we count hits whose minute equals the turn's minute
    # and whose speaker matches.
    out: list[TonePoint] = []
    if not turns:
        return out
    for t in turns:
        text = t.text.lower()
        bull = sum(text.count(w) for w in ("record", "strong", "exceeded", "beat",
                                           "grew", "growth", "all-time", "robust",
                                           "outperformed", "ahead of"))
        bear = sum(text.count(w) for w in ("weak", "weakness", "declined", "decline",
                                           "softness", "soft", "headwind", "headwinds",
                                           "missed", "below", "challenging", "pressure"))
        cert = sum(1 for h in hits
                   if h.bucket == "certainty"
                   and h.speaker == t.speaker
                   and h.minute == t.minute)
        hedge = sum(1 for h in hits
                    if h.bucket == "hedge"
                    and h.speaker == t.speaker
                    and h.minute == t.minute)
        deflect = sum(1 for h in hits
                      if h.bucket == "deflection"
                      and h.speaker == t.speaker
                      and h.minute == t.minute)
        total_signals = max(1, cert + hedge + 2 * deflect)
        sig_score = (cert - hedge - 2 * deflect) / total_signals
        word_score = (bull - bear) / max(1, bull + bear)
        # 60% signal, 40% keyword
        tone = 0.6 * sig_score + 0.4 * word_score
        tone = max(-1.0, min(1.0, tone))
        out.append(TonePoint(
            minute=t.minute,
            tone=round(tone, 4),
            speaker_role=t.role,
            word_count=len(t.text.split()),
        ))
    return out


# ---- Headline stats ----------------------------------------------

def compute_headline_stats(transcript: TranscriptDoc,
                           hits: list[PhraseHit],
                           claims: list[NumberClaim]) -> HeadlineStats:
    """Aggregate everything for the hero KPI strip."""
    summ = signal_summary(hits)
    cs = confidence_score(summ)

    # Words by role
    role_words: dict[str, int] = {}
    for t in transcript.turns:
        role_words[t.role] = role_words.get(t.role, 0) + len(t.text.split())
    total_words = sum(role_words.values()) or 1
    share = {r: round(w / total_words, 4) for r, w in role_words.items()}

    minutes = (transcript.metadata.word_count or total_words) // 150
    # Distinct analysts (by name)
    distinct = len({t.speaker for t in transcript.turns if t.role == "ANALYST"})

    total_signals = (summ.get("hedge", 0) + summ.get("certainty", 0)
                     + summ.get("deflection", 0))
    if total_signals == 0 and total_words < 50:
        tone = "unknown"
    elif cs >= 0.55:
        tone = "confident"
    elif cs <= 0.30:
        tone = "defensive"
    else:
        tone = "cautious"

    return HeadlineStats(
        overall_tone=tone,
        confidence_score=round(cs, 4),
        hedge_count=summ.get("hedge", 0),
        certainty_count=summ.get("certainty", 0),
        deflection_count=summ.get("deflection", 0),
        quantitative_claims=len(claims),
        minutes=minutes,
        word_count=total_words,
        analyst_count=distinct,
        role_word_share=share,
    )


# ---- Multi-quarter compose ----------------------------------------

@dataclass
class MultiQuarterCell:
    period: str
    overall_tone: str
    confidence_score: float
    hedge_count: int
    certainty_count: int
    deflection_count: int
    revenue_guidance_low: float | None
    revenue_guidance_high: float | None
    revenue_unit: str


def compose_multiquarter(analyses: list[CallAnalysis]) -> list[MultiQuarterCell]:
    """One row per call, in the order supplied. Pulls the most-recent
    revenue guidance item out of each call for trend tracking."""
    out: list[MultiQuarterCell] = []
    for a in analyses:
        rev = next((g for g in a.guidance if "revenue" in g.metric.lower()), None)
        out.append(MultiQuarterCell(
            period=a.transcript.metadata.fiscal_period or "?",
            overall_tone=a.headline.overall_tone,
            confidence_score=a.headline.confidence_score,
            hedge_count=a.headline.hedge_count,
            certainty_count=a.headline.certainty_count,
            deflection_count=a.headline.deflection_count,
            revenue_guidance_low=(rev.range_low if rev else None),
            revenue_guidance_high=(rev.range_high if rev else None),
            revenue_unit=(rev.unit if rev else ""),
        ))
    return out
