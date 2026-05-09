"""Day 7. Pipeline integration tests (skip_ai mode against bundled samples)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pipeline import analyse, to_dict

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE.parent / "sample_data"
SAMPLES = ["sample_tsla_q1_2026.txt", "sample_aapl_q4_2025.txt", "sample_jpm_q1_2026.txt"]


@pytest.mark.parametrize("fname", SAMPLES)
def test_each_sample_runs_skip_ai(fname):
    p = SAMPLE_DIR / fname
    if not p.exists():
        pytest.skip(f"missing sample {fname}")
    res = analyse(path=p, source_filename=fname, skip_ai=True)
    d = to_dict(res)
    assert d["metadata"]["company"]
    assert d["metadata"]["word_count"] > 200
    assert d["headline"]["analyst_count"] >= 4
    assert d["headline"]["hedge_count"] >= 0
    assert d["headline"]["certainty_count"] >= 0
    # Tone curve has one point per turn
    assert len(d["tone_curve"]) > 0
    # Number claims found
    assert d["headline"]["quantitative_claims"] >= 2
    # JSON-serialisable
    import json
    json.dumps(d)


def test_skip_ai_does_not_call_provider():
    p = SAMPLE_DIR / "sample_tsla_q1_2026.txt"
    if not p.exists():
        pytest.skip("missing sample")
    res = analyse(path=p, source_filename=p.name, skip_ai=True)
    assert res.ai_stats.skipped is True
    assert res.ai_stats.cost_usd == 0.0
    assert res.total_cost_usd == 0.0


def test_estimate_cost_grows_with_word_count():
    from pipeline import estimate_cost
    a = estimate_cost(500)
    b = estimate_cost(5000)
    assert b > a > 0


def test_pipeline_handles_text_input():
    res = analyse(text="""\
Company: Demo
Ticker: DEMO
Fiscal Period: Q1 FY2026
Call Date: 2026-01-01

Operator: Welcome.

Tim Cook -- CEO: We are confident in our record results. Revenue was $5 billion.

Operator: Question from John of Morgan Stanley.

John Smith -- Morgan Stanley: Thanks.

Tim Cook -- CEO: We expect approximately flat margins.
""", skip_ai=True)
    d = to_dict(res)
    assert d["metadata"]["ticker"] == "DEMO"
    assert d["headline"]["analyst_count"] >= 1
