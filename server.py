"""Day 7. BRIEF. Local Flask server for the Earnings Call Summariser.

Bound to 127.0.0.1:1007 by default. Day-N port = 1000 + N.

Routes:
  GET  /                            renders index.html, sets CSRF cookie
  POST /api/analyse                 paste/upload transcript, returns JSON
  POST /api/followup                free-text Q&A on a cached run
  POST /api/multiquarter            compare 2-4 transcripts
  GET  /api/edgar/<ticker>          SEC EDGAR 10-Q lookup
  GET  /api/runs                    cost-log entries with cached flag
  GET  /api/runs/<id>               re-open a cached run
  POST /api/runs/<id>/save          add a label to a cached run
  POST /api/compare                 diff two cached runs by id
  GET  /api/status                  env + samples + cost log summary
  GET  /api/download/<filename>     serves a file from outputs/
  POST /api/shutdown                debug-only clean stop
  GET  /favicon.ico
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import edgar
from cost_log import CostLog
from csv_writer import write_guidance_csv, write_qa_csv
from excel_writer import write_workbook
from flask import Flask, abort, jsonify, make_response, render_template, request, send_file
from pdf_writer import write_pdf
from pipeline import (
    analyse,
    analyse_multiquarter,
    followup,
    to_dict,
)
from pptx_writer import is_available as pptx_available
from pptx_writer import write_pptx
from run_cache import RunCache
from werkzeug.utils import safe_join, secure_filename

from shared.config import DEEPSEEK_API_KEY

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE / "sample_data"
OUTPUTS = HERE / "outputs"
UPLOADS = HERE / "uploads"
LOGS = HERE / "logs"

SAMPLES: dict[str, dict] = {
    "tsla": {"filename": "sample_tsla_q1_2026.txt",
             "label": "Tesla Q1 FY2026. Cybertruck ramp commentary, 6 analysts, mixed tone."},
    "aapl": {"filename": "sample_aapl_q4_2025.txt",
             "label": "Apple Q4 FY2025. Services strong, China softness, 6 analysts."},
    "jpm":  {"filename": "sample_jpm_q1_2026.txt",
             "label": "JPMorgan Q1 FY2026. NII guide raised, IB recovering, 6 analysts."},
}

MAX_UPLOAD_BYTES = 8 * 1024 * 1024            # transcripts are larger
ALLOWED_EXTS = {".txt", ".pdf"}
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

app = Flask(
    __name__,
    template_folder=str(HERE / "templates"),
    static_folder=str(HERE / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

_analyse_lock = threading.Lock()
_cost_log = CostLog(OUTPUTS / "runs.jsonl")
_run_cache = RunCache(OUTPUTS / "runs")


# ---- Logging ---------------------------------------------------------

LOGS.mkdir(parents=True, exist_ok=True)
_handler = logging.handlers.RotatingFileHandler(
    LOGS / "server.log", maxBytes=512_000, backupCount=3, encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler, logging.StreamHandler()])
log = logging.getLogger("day07.server")


def _env_key_ok() -> bool:
    return bool(DEEPSEEK_API_KEY) and not DEEPSEEK_API_KEY.startswith("sk-placeholder")


def _ensure_csrf_cookie(resp):
    if not request.cookies.get(CSRF_COOKIE_NAME):
        resp.set_cookie(
            CSRF_COOKIE_NAME, secrets.token_urlsafe(24),
            samesite="Strict", httponly=False, secure=False, max_age=24 * 3600,
        )
    return resp


def _csrf_check() -> bool:
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    header = request.headers.get(CSRF_HEADER_NAME, "")
    return bool(cookie) and secrets.compare_digest(cookie, header)


def _samples_for_template():
    out = []
    for sid, meta in SAMPLES.items():
        if (SAMPLE_DIR / meta["filename"]).exists():
            out.append({"id": sid, "filename": meta["filename"], "label": meta["label"]})
    return out


def _cost_log_dict() -> dict:
    s = _cost_log.summary()
    return {
        "runs": s.runs, "cost_usd_total": s.cost_usd_total,
        "rows_total": s.rows_total, "last_run_at": s.last_run_at,
        "cost_usd_30d": s.cost_usd_30d, "runs_30d": s.runs_30d,
    }


@app.route("/")
def index():
    resp = make_response(render_template(
        "index.html",
        env_key_ok=_env_key_ok(),
        samples=_samples_for_template(),
        max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
    ))
    return _ensure_csrf_cookie(resp)


@app.route("/api/status")
def status():
    return jsonify(
        env_key_ok=_env_key_ok(),
        samples=_samples_for_template(),
        max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
        cost_log=_cost_log_dict(),
        guardrail_usd=float(os.getenv("DAY07_MAX_COST_USD", "0.05")),
    )


@app.route("/api/runs")
def runs_list():
    entries = _cost_log.entries(limit=200)
    out = []
    for e in entries:
        eid = e.get("id")
        cached = bool(eid) and (_run_cache.root / f"{eid}.json").is_file()
        out.append({**e, "cached": cached})
    return jsonify(entries=out, summary=_cost_log_dict())


@app.route("/api/runs/<run_id>")
def run_get(run_id: str):
    if not run_id or len(run_id) > 64 or not run_id.replace("-", "").isalnum():
        return jsonify(error="Invalid run id."), 400
    payload = _run_cache.get(run_id)
    if payload is None:
        return jsonify(error="Run not cached."), 404
    return jsonify(payload)


@app.route("/api/runs/<run_id>/save", methods=["POST"])
def api_run_save(run_id: str):
    if not _csrf_check():
        return jsonify(error="CSRF token missing."), 403
    if not run_id or len(run_id) > 64 or not run_id.replace("-", "").isalnum():
        return jsonify(error="Invalid run id."), 400
    label = (request.form.get("label") or "").strip()[:80]
    payload = _run_cache.get(run_id)
    if payload is None:
        return jsonify(error="Run not cached."), 404
    payload["label"] = label
    try:
        _run_cache.save(run_id, payload)
    except Exception:
        log.exception("save label failed")
        return jsonify(error="Could not save label."), 500
    return jsonify(saved=True, run_id=run_id, label=label)


@app.route("/api/analyse_edgar", methods=["POST"])
def api_analyse_edgar():
    """Fetch a SEC filing by URL and run it through the analyse pipeline.

    SEC blocks browser fetches via CORS, so we proxy through the server
    (with the User-Agent header SEC requires) and feed the cleaned text
    into the same analyse() call used by /api/analyse.

    Note: the AI is tuned for earnings call transcripts, not 10-Q narrative.
    Speaker-turn detection won't fire (no 'Tim Cook -- CEO:' tags in a 10-Q),
    but the AI extraction can still pull guidance, themes, and risks from
    the MD&A and Risk Factors sections.
    """
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    if not _analyse_lock.acquire(blocking=False):
        return jsonify(error="Another analysis is in flight."), 429

    started = time.time()
    try:
        url = (request.form.get("url") or "").strip()
        ticker_hint = (request.form.get("ticker") or "").strip().upper()
        form_label = (request.form.get("form") or "").strip()
        date_label = (request.form.get("date") or "").strip()
        skip_ai = request.form.get("skip_ai") == "true"
        api_key_override = (request.form.get("api_key") or "").strip() or None
        model_choice = (request.form.get("model") or "").strip() or None

        if not url:
            return jsonify(error="url is required."), 400
        try:
            filing_text = edgar.fetch_filing_text(url)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            log.exception("EDGAR fetch failed")
            return jsonify(error=f"Could not fetch filing: {e}"), 502
        if not filing_text or len(filing_text) < 200:
            return jsonify(error="Fetched filing is empty or too short."), 422

        # Synthesise a metadata header so the parser's metadata block picks
        # up company / ticker / period without requiring the user to format
        # the SEC document.
        header = (
            f"Company: {ticker_hint or 'SEC filing'}\n"
            f"Ticker: {ticker_hint}\n"
            f"Fiscal Period: {form_label or 'SEC filing'}\n"
            f"Call Date: {date_label}\n"
            f"---\n"
        )
        text_with_header = header + filing_text

        try:
            result = analyse(
                text=text_with_header,
                source_filename=f"edgar_{ticker_hint}_{form_label}_{date_label}.txt",
                skip_ai=skip_ai, model=model_choice, api_key=api_key_override,
                mode="filing",
            )
        except ValueError as e:
            return jsonify(error=str(e)), 400

        # Suppress the 'no speaker turns' warning for SEC filings - it is
        # always true and not actionable. Replace with a clear filing-mode
        # note instead.
        result.warnings = [
            w for w in result.warnings if "speaker turns" not in w.lower()
        ]
        result.warnings.insert(
            0,
            f"Filing-mode analysis of {ticker_hint} {form_label} ({date_label}) "
            f"from SEC EDGAR. Speaker-turn detection skipped (not a transcript). "
            f"AI extraction tuned for SEC filing narrative.",
        )

        # Reuse the same export pipeline as /api/analyse.
        slug = _slug(result.call.transcript.metadata.company,
                     result.call.transcript.metadata.fiscal_period or form_label)
        ts = time.strftime("%Y%m%d-%H%M")
        xlsx_path = OUTPUTS / f"brief_{slug}_{ts}.xlsx"
        qa_csv = OUTPUTS / f"brief_{slug}_{ts}_qa.csv"
        guide_csv = OUTPUTS / f"brief_{slug}_{ts}_guidance.csv"
        write_workbook(result.call, xlsx_path)
        write_qa_csv(result.call, qa_csv)
        write_guidance_csv(result.call, guide_csv)

        pptx_name: str | None = None
        pdf_name: str | None = None
        try:
            if pptx_available():
                pptx_path = OUTPUTS / f"brief_{slug}_{ts}.pptx"
                write_pptx(result.call, pptx_path)
                pptx_name = pptx_path.name
        except Exception:
            log.exception("pptx write failed")
        try:
            pdf_path = OUTPUTS / f"brief_{slug}_{ts}.pdf"
            write_pdf(result.call, pdf_path)
            pdf_name = pdf_path.name
        except Exception:
            log.exception("pdf write failed")

        elapsed_ms = int((time.time() - started) * 1000)
        ai_cost = result.total_cost_usd
        log_entry = _cost_log.append(
            company=f"{ticker_hint} {form_label}",
            period_label=date_label,
            rows=len(result.call.qa),
            cost_usd=ai_cost,
            model=result.ai_stats.model or "(deterministic)",
            skipped=bool(result.ai_stats.skipped),
            elapsed_ms=elapsed_ms,
            source_filename=f"edgar_{ticker_hint}_{form_label}",
            total_variance=result.call.headline.confidence_score,
            total_variance_pct=None,
            rag_red=result.call.headline.deflection_count,
        )
        log.info(
            "analyse_edgar OK ticker=%s form=%s cost_usd=%.5f ms=%d chars=%d",
            ticker_hint, form_label, ai_cost, elapsed_ms, len(filing_text),
        )

        body = to_dict(result)
        body.update(
            xlsx_filename=xlsx_path.name,
            qa_csv_filename=qa_csv.name,
            guidance_csv_filename=guide_csv.name,
            pptx_filename=pptx_name,
            pdf_filename=pdf_name,
            elapsed_ms=elapsed_ms,
            cost_log=_cost_log_dict(),
            run_id=log_entry["id"],
            mode="filing",
            edgar_source={"url": url, "ticker": ticker_hint,
                          "form": form_label, "date": date_label,
                          "fetched_chars": len(filing_text)},
        )
        try:
            _run_cache.save(log_entry["id"], body)
        except Exception:
            log.exception("cache save failed")
        return jsonify(body)
    except Exception:
        log.exception("analyse_edgar unexpected error")
        return jsonify(error="Server error during EDGAR analysis."), 500
    finally:
        _analyse_lock.release()


@app.route("/api/edgar/<ticker>")
def api_edgar(ticker: str):
    safe = ticker.upper().strip()[:10]
    if not safe.replace(".", "").replace("-", "").isalnum():
        return jsonify(error="Invalid ticker."), 400
    try:
        result = edgar.lookup(safe)
    except Exception as e:
        return jsonify(error=f"EDGAR lookup failed: {e}"), 500
    return jsonify(
        ticker=result.ticker, cik=result.cik, company_name=result.company_name,
        error=result.error,
        filings=[
            {"form": f.form, "date": f.date, "accession": f.accession,
             "primary_document": f.primary_document, "url": f.url}
            for f in result.filings
        ],
    )


@app.route("/api/analyse", methods=["POST"])
def api_analyse():
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    if not _analyse_lock.acquire(blocking=False):
        return jsonify(error="Another analysis is in flight."), 429

    started = time.time()
    try:
        use_samples = request.form.get("use_samples") == "true"
        sample_id = (request.form.get("sample_id") or "").strip()
        skip_ai = request.form.get("skip_ai") == "true"
        api_key_override = (request.form.get("api_key") or "").strip() or None
        model_choice = (request.form.get("model") or "").strip() or None
        try:
            self_consistency = max(1, min(3, int(request.form.get("self_consistency") or "1")))
        except ValueError:
            self_consistency = 1
        pasted_text = request.form.get("text") or ""

        file_bytes: bytes | None = None
        text: str | None = None
        display_name = ""

        if use_samples:
            if sample_id not in SAMPLES:
                return jsonify(error=f"Unknown sample id: '{sample_id}'."), 400
            fname = SAMPLES[sample_id]["filename"]
            sample_path = SAMPLE_DIR / fname
            if not sample_path.exists():
                return jsonify(error=f"Sample file missing on disk: {fname}."), 500
            text = sample_path.read_text(encoding="utf-8")
            display_name = fname
        elif pasted_text.strip():
            text = pasted_text
            display_name = "pasted.txt"
        else:
            upload = request.files.get("file")
            if upload is None or not upload.filename:
                return jsonify(error="No transcript provided. Pick a sample, paste text, or upload a file."), 400
            safe_name = secure_filename(upload.filename) or "upload.txt"
            ext = Path(safe_name).suffix.lower()
            if ext not in ALLOWED_EXTS:
                return jsonify(error=f"Unsupported file type: {ext}. Use .txt or .pdf."), 400
            file_bytes = upload.read()
            UPLOADS.mkdir(parents=True, exist_ok=True)
            (UPLOADS / f"{uuid.uuid4().hex[:8]}_{safe_name}").write_bytes(file_bytes)
            display_name = safe_name

        try:
            result = analyse(
                file_bytes=file_bytes, text=text,
                source_filename=display_name,
                skip_ai=skip_ai, model=model_choice, api_key=api_key_override,
                self_consistency=self_consistency,
            )
        except ValueError as e:
            log.warning("analyse validation: %s", e)
            return jsonify(error=str(e)), 400

        slug = _slug(result.call.transcript.metadata.company,
                     result.call.transcript.metadata.fiscal_period)
        ts = time.strftime("%Y%m%d-%H%M")
        xlsx_path = OUTPUTS / f"brief_{slug}_{ts}.xlsx"
        qa_csv = OUTPUTS / f"brief_{slug}_{ts}_qa.csv"
        guide_csv = OUTPUTS / f"brief_{slug}_{ts}_guidance.csv"
        write_workbook(result.call, xlsx_path)
        write_qa_csv(result.call, qa_csv)
        write_guidance_csv(result.call, guide_csv)

        pptx_name: str | None = None
        pdf_name: str | None = None
        try:
            if pptx_available():
                pptx_path = OUTPUTS / f"brief_{slug}_{ts}.pptx"
                write_pptx(result.call, pptx_path)
                pptx_name = pptx_path.name
        except Exception:
            log.exception("pptx write failed")
        try:
            pdf_path = OUTPUTS / f"brief_{slug}_{ts}.pdf"
            write_pdf(result.call, pdf_path)
            pdf_name = pdf_path.name
        except Exception:
            log.exception("pdf write failed")

        elapsed_ms = int((time.time() - started) * 1000)
        ai_cost = result.total_cost_usd
        log_entry = _cost_log.append(
            company=result.call.transcript.metadata.company,
            period_label=result.call.transcript.metadata.fiscal_period,
            rows=len(result.call.qa),
            cost_usd=ai_cost,
            model=result.ai_stats.model or "(deterministic)",
            skipped=bool(result.ai_stats.skipped),
            elapsed_ms=elapsed_ms,
            source_filename=display_name,
            total_variance=result.call.headline.confidence_score,
            total_variance_pct=None,
            rag_red=result.call.headline.deflection_count,
        )
        log.info(
            "analyse OK ticker=%s tone=%s cost_usd=%.5f ms=%d",
            result.call.transcript.metadata.ticker,
            result.call.headline.overall_tone, ai_cost, elapsed_ms,
        )

        body = to_dict(result)
        body.update(
            xlsx_filename=xlsx_path.name,
            qa_csv_filename=qa_csv.name,
            guidance_csv_filename=guide_csv.name,
            pptx_filename=pptx_name,
            pdf_filename=pdf_name,
            elapsed_ms=elapsed_ms,
            cost_log=_cost_log_dict(),
            run_id=log_entry["id"],
        )
        try:
            _run_cache.save(log_entry["id"], body)
        except Exception:
            log.exception("cache save failed")
        return jsonify(body)
    except Exception:
        log.exception("analyse unexpected error")
        return jsonify(error="Server error during analysis. See logs/server.log."), 500
    finally:
        _analyse_lock.release()


@app.route("/api/followup", methods=["POST"])
def api_followup():
    if not _csrf_check():
        return jsonify(error="CSRF token missing."), 403
    run_id = (request.form.get("run_id") or "").strip()
    question = (request.form.get("question") or "").strip()
    if not run_id or not question:
        return jsonify(error="run_id and question required."), 400
    payload = _run_cache.get(run_id)
    if payload is None:
        return jsonify(error="Run not cached. Re-run the analysis."), 404
    api_key = (request.form.get("api_key") or "").strip() or None
    model = (request.form.get("model") or "").strip() or None
    return jsonify(followup(run_payload=payload, question=question,
                            model=model, api_key=api_key))


@app.route("/api/multiquarter", methods=["POST"])
def api_multiquarter():
    if not _csrf_check():
        return jsonify(error="CSRF token missing."), 403
    if not _analyse_lock.acquire(blocking=False):
        return jsonify(error="Another analysis is in flight."), 429
    try:
        skip_ai = request.form.get("skip_ai") == "true"
        sample_ids = (request.form.get("sample_ids") or "").strip()
        if not sample_ids:
            return jsonify(error="sample_ids required (comma-separated)."), 400
        chosen = [s.strip() for s in sample_ids.split(",") if s.strip()][:4]
        transcripts = []
        for sid in chosen:
            if sid not in SAMPLES:
                continue
            sp = SAMPLE_DIR / SAMPLES[sid]["filename"]
            if not sp.exists():
                continue
            transcripts.append({
                "text": sp.read_text(encoding="utf-8"),
                "source_filename": sp.name,
            })
        if not transcripts:
            return jsonify(error="No valid samples selected."), 400
        out = analyse_multiquarter(transcripts, skip_ai=skip_ai)
        return jsonify(out)
    except Exception:
        log.exception("multiquarter failed")
        return jsonify(error="Server error during multi-quarter."), 500
    finally:
        _analyse_lock.release()


@app.route("/api/compare", methods=["POST"])
def api_compare():
    if not _csrf_check():
        return jsonify(error="CSRF token missing."), 403
    a_id = (request.form.get("a") or "").strip()
    b_id = (request.form.get("b") or "").strip()
    if not (a_id and b_id):
        return jsonify(error="Provide both run ids."), 400
    a = _run_cache.get(a_id)
    b = _run_cache.get(b_id)
    if a is None or b is None:
        return jsonify(error="One or both runs not cached."), 404

    def _h(d, k):
        return ((d.get("headline") or {}).get(k))
    keys = [
        "confidence_score", "hedge_count", "certainty_count",
        "deflection_count", "quantitative_claims",
        "minutes", "word_count", "analyst_count",
    ]
    deltas = {}
    for k in keys:
        av, bv = _h(a, k), _h(b, k)
        if av is None or bv is None:
            deltas[k] = {"a": av, "b": bv, "delta": None}
        else:
            deltas[k] = {"a": av, "b": bv, "delta": bv - av}
    return jsonify(
        a_id=a_id, b_id=b_id,
        a_company=(a.get("metadata") or {}).get("company"),
        b_company=(b.get("metadata") or {}).get("company"),
        a_period=(a.get("metadata") or {}).get("fiscal_period"),
        b_period=(b.get("metadata") or {}).get("fiscal_period"),
        deltas=deltas,
    )


@app.errorhandler(413)
def _too_large(_e):
    return jsonify(error=f"Upload exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB limit."), 413


@app.route("/api/download/<path:filename>")
def download(filename: str):
    safe = secure_filename(filename) or ""
    if not safe:
        abort(400)
    full = safe_join(str(OUTPUTS), safe)
    if not full or not Path(full).is_file():
        return jsonify(error=f"Not found: {safe}"), 404
    return send_file(full, as_attachment=True, download_name=safe)


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    if not (app.debug or os.getenv("DAY07_ALLOW_SHUTDOWN") == "1"):
        return jsonify(error="Shutdown not enabled."), 403
    if not _csrf_check():
        return jsonify(error="CSRF token missing."), 403
    threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
    return jsonify(stopped=True)


@app.route("/favicon.ico")
def favicon():
    p = HERE / "static" / "favicon.svg"
    if p.exists():
        return send_file(p)
    return ("", 204)


def _slug(company: str, period: str) -> str:
    out = []
    for ch in f"{company}_{period}".lower():
        out.append(ch if ch.isalnum() else "_")
    s = "".join(out).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s[:48] or "run"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("DAY07_PORT", "1007")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print()
    print("  Day 7. BRIEF . Earnings Call Summariser")
    print(f"  Local URL:  http://{args.host}:{args.port}/")
    print("  Press Ctrl+C to stop.")
    print()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=args.debug)


if __name__ == "__main__":
    main()
