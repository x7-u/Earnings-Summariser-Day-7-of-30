"""Day 7. Flat Q&A + Guidance CSVs.

Two CSVs per run:
  - <slug>_qa.csv           : every analyst Q&A exchange.
  - <slug>_guidance.csv     : every forward-guidance line item.

utf-8-sig encoding so Excel auto-detects.
"""
from __future__ import annotations

import csv
from pathlib import Path

from analysis import CallAnalysis

QA_COLUMNS = (
    "company", "ticker", "fiscal_period",
    "analyst_name", "analyst_firm",
    "question_summary", "answer_summary",
    "tension", "management_clarity",
)

GUIDANCE_COLUMNS = (
    "company", "ticker", "fiscal_period",
    "metric", "period", "direction",
    "range_low", "range_high", "unit", "quote", "prior",
)


def write_qa_csv(call: CallAnalysis, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = call.transcript.metadata
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(QA_COLUMNS)
        for q in call.qa:
            w.writerow([
                md.company, md.ticker, md.fiscal_period,
                q.analyst_name, q.analyst_firm,
                q.question_summary, q.answer_summary,
                q.tension, q.management_clarity,
            ])
    return out_path


def write_guidance_csv(call: CallAnalysis, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = call.transcript.metadata
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(GUIDANCE_COLUMNS)
        for g in call.guidance:
            w.writerow([
                md.company, md.ticker, md.fiscal_period,
                g.metric, g.period, g.direction,
                "" if g.range_low is None else f"{g.range_low:.4f}",
                "" if g.range_high is None else f"{g.range_high:.4f}",
                g.unit, g.quote, g.prior,
            ])
    return out_path
