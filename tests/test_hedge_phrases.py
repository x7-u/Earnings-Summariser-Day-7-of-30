"""Day 7. Tests for hedge_phrases (rule-based tone signal detector)."""
from __future__ import annotations

from hedge_phrases import (
    confidence_score,
    detect_signals,
    signal_summary,
)
from transcript_schema import SpeakerTurn


def _t(text: str, role: str = "CEO") -> SpeakerTurn:
    return SpeakerTurn(speaker="X", role=role, firm=None, text=text, minute=0)


def test_detects_hedge_phrases():
    hits = detect_signals([_t("We expect Q2 to be approximately flat.")])
    assert any(h.bucket == "hedge" and "we expect" in h.phrase.lower() for h in hits)
    assert any(h.bucket == "hedge" and "approximately" in h.phrase.lower() for h in hits)


def test_detects_certainty_phrases():
    hits = detect_signals([_t("We are committed to delivering record results.")])
    assert any(h.bucket == "certainty" and "we are committed" in h.phrase.lower() for h in hits)
    assert any(h.bucket == "certainty" and "record" in h.phrase.lower() for h in hits)


def test_detects_deflection_phrases():
    hits = detect_signals([_t("We don't break that out forward looking.")])
    assert any(h.bucket == "deflection" for h in hits)


def test_skips_analyst_speakers():
    hits = detect_signals([_t("We expect a tough quarter.", role="ANALYST")])
    assert hits == []


def test_summary_and_confidence_scoring():
    hits = detect_signals([
        _t("We are confident. We will deliver. We are committed."),
        _t("We expect approximately. We anticipate."),
        _t("We don't disclose."),
    ])
    s = signal_summary(hits)
    cs = confidence_score(s)
    assert s["certainty"] >= 2
    assert s["hedge"] >= 2
    assert s["deflection"] >= 1
    assert 0.0 <= cs <= 1.0
