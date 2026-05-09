"""Day 7. Tests for claims.extract (quantitative claim regex)."""
from __future__ import annotations

from claims import extract, summarise_by_role
from transcript_schema import SpeakerTurn


def _t(text: str, role: str = "CEO") -> SpeakerTurn:
    return SpeakerTurn(speaker="X", role=role, firm=None, text=text, minute=0)


def test_extracts_currency_with_billion_suffix():
    claims = extract([_t("Revenue was $24.8 billion, up 7 percent.")])
    ccy = [c for c in claims if c.unit == "USD"]
    assert ccy
    # 24.8 * 1bn = 24,800,000,000
    assert any(abs(c.value_low - 24_800_000_000) < 1 for c in ccy)


def test_extracts_percent_claim():
    claims = extract([_t("Gross margin was 18.2 percent.")])
    pcts = [c for c in claims if c.unit == "%"]
    assert any(abs(c.value_low - 18.2) < 0.01 for c in pcts)


def test_extracts_range_percent():
    claims = extract([_t("We expect margin in the 22 to 24 percent range.")])
    pcts = [c for c in claims if c.kind == "range_percent"]
    assert any(c.value_low == 22.0 and c.value_high == 24.0 for c in pcts)


def test_extracts_gbp_and_eur():
    claims = extract([_t("Capex was GBP 1.2 billion. EUR 450 million was deployed.")])
    units = {c.unit for c in claims}
    assert "GBP" in units
    assert "EUR" in units


def test_summarises_by_role():
    turns = [
        _t("Revenue was $5 billion.", role="CEO"),
        _t("Operating margin was 18%.", role="CFO"),
        _t("Cash was $1.2 billion.", role="CFO"),
    ]
    claims = extract(turns)
    s = summarise_by_role(claims)
    assert s.get("CEO", 0) >= 1
    assert s.get("CFO", 0) >= 2


def test_does_not_match_implausible_percent():
    claims = extract([_t("The year is 2025 and we have 9999 percent... not really.")])
    # 9999 percent is filtered (over 1000)
    assert not any(c.value_low == 9999 for c in claims)
