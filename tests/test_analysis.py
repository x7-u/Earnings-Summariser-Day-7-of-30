"""Day 7. Tests for analysis.compute_headline_stats and compute_tone_curve."""
from __future__ import annotations

import math

from analysis import (
    compose_multiquarter,
    compute_headline_stats,
    compute_tone_curve,
)
from claims import extract
from hedge_phrases import detect_signals
from transcript_schema import SpeakerTurn, TranscriptDoc, TranscriptMetadata


def _doc(turns):
    md = TranscriptMetadata(
        company="X", ticker="X", fiscal_period="Q1", call_date="2026-01-01",
        word_count=sum(len(t.text.split()) for t in turns),
    )
    return TranscriptDoc(metadata=md, turns=turns)


def test_compute_headline_stats_confident_tone():
    turns = [
        SpeakerTurn("CEO", "CEO", None,
                    "We are confident. We delivered a record. We will execute. " * 6, 0),
        SpeakerTurn("CFO", "CFO", None,
                    "We will deliver. Strong growth ahead.", 1),
    ]
    doc = _doc(turns)
    hits = detect_signals(turns)
    claims = extract(turns)
    h = compute_headline_stats(doc, hits, claims)
    assert h.overall_tone == "confident"
    assert h.confidence_score > 0.55


def test_compute_headline_stats_unknown_when_no_signal():
    """A near-empty transcript should report 'unknown' tone, not 'defensive'."""
    md = TranscriptMetadata(company="X", ticker="X", fiscal_period="Q1",
                            call_date="2026-01-01", word_count=0)
    doc = TranscriptDoc(metadata=md, turns=[])
    h = compute_headline_stats(doc, [], [])
    assert h.overall_tone == "unknown"


def test_compute_headline_stats_defensive_tone():
    turns = [
        SpeakerTurn("CEO", "CEO", None,
                    "We don't break that out. We don't disclose. " * 4, 0),
    ]
    doc = _doc(turns)
    hits = detect_signals(turns)
    claims = extract(turns)
    h = compute_headline_stats(doc, hits, claims)
    assert h.overall_tone == "defensive"
    assert h.confidence_score <= 0.30


def test_tone_curve_returns_one_point_per_turn():
    turns = [
        SpeakerTurn("A", "CEO", None, "We are confident in our growth.", 0),
        SpeakerTurn("B", "CFO", None, "We expect approximately flat margins.", 1),
        SpeakerTurn("C", "ANALYST", None, "Question on demand.", 2),
    ]
    hits = detect_signals(turns)
    pts = compute_tone_curve(turns, hits)
    assert len(pts) == len(turns)
    for p in pts:
        assert -1 <= p.tone <= 1


def test_tone_curve_empty_when_no_turns():
    assert compute_tone_curve([], []) == []


def test_compose_multiquarter_picks_revenue_guidance():
    from analysis import (
        CallAnalysis,
        ExecSummary,
        GuidanceItem,
        HeadlineStats,
    )
    md_a = TranscriptMetadata(company="A", ticker="A", fiscal_period="Q1", call_date="")
    md_b = TranscriptMetadata(company="A", ticker="A", fiscal_period="Q2", call_date="")
    h = HeadlineStats(overall_tone="confident", confidence_score=0.6,
                     hedge_count=0, certainty_count=0, deflection_count=0,
                     quantitative_claims=0, minutes=0, word_count=0, analyst_count=0)
    g = GuidanceItem(metric="revenue", period="FY2026", direction="raised",
                    range_low=100.0, range_high=110.0, unit="USD bn",
                    quote="we are raising")
    a = CallAnalysis(transcript=TranscriptDoc(md_a, []), headline=h, guidance=[g])
    b = CallAnalysis(transcript=TranscriptDoc(md_b, []), headline=h, guidance=[g])
    cells = compose_multiquarter([a, b])
    assert len(cells) == 2
    assert cells[0].revenue_guidance_low == 100
    assert cells[1].revenue_guidance_high == 110
    assert cells[0].revenue_unit == "USD bn"
