"""Day 7. EDGAR helpers tests (network is mocked)."""
from __future__ import annotations

import json
from unittest.mock import patch

import edgar

_FAKE_TICKER_MAP = json.dumps({
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
})


_FAKE_SUBMISSIONS = json.dumps({
    "filings": {
        "recent": {
            "form": ["10-K", "10-Q", "8-K", "10-Q", "DEF 14A"],
            "filingDate": ["2025-11-01", "2025-08-01", "2025-09-15", "2025-05-01", "2025-12-01"],
            "accessionNumber": [
                "0000320193-25-000123",
                "0000320193-25-000111",
                "0000320193-25-000099",
                "0000320193-25-000080",
                "0000320193-25-000050",
            ],
            "primaryDocument": [
                "aapl-20250930.htm",
                "aapl-20250628.htm",
                "aapl-20250915.htm",
                "aapl-20250329.htm",
                "aapl-def14a.htm",
            ],
        },
    },
})


def test_lookup_resolves_known_ticker():
    edgar._TICKER_CACHE = None
    with patch.object(edgar, "_fetch") as mock_fetch:
        mock_fetch.side_effect = [_FAKE_TICKER_MAP.encode(), _FAKE_SUBMISSIONS.encode()]
        result = edgar.lookup("AAPL")
    assert result.ticker == "AAPL"
    assert result.cik == "0000320193"
    assert result.company_name == "Apple Inc."
    assert len(result.filings) >= 3
    assert any(f.form == "10-Q" for f in result.filings)
    assert any(f.form == "10-K" for f in result.filings)


def test_lookup_unknown_ticker_returns_error():
    edgar._TICKER_CACHE = None
    with patch.object(edgar, "_fetch") as mock_fetch:
        mock_fetch.return_value = _FAKE_TICKER_MAP.encode()
        result = edgar.lookup("NOSUCH")
    assert result.error
    assert "not found" in result.error


def test_lookup_empty_ticker_returns_error():
    result = edgar.lookup("")
    assert result.error == "Empty ticker."


_FAKE_FILING_HTML = b"""\
<!DOCTYPE html>
<html><head>
<title>10-Q Filing</title>
<style>body { font-family: sans; }</style>
<script>document.title = 'set';</script>
</head>
<body>
<h1>Apple Inc. 10-Q</h1>
<p>Total revenue was <b>$94.9 billion</b>, up 6 percent year over year.</p>
<p>Services revenue was &dollar;25.0 billion, an all&#45;time record.</p>
<br><br>
<div>The Company expects gross margin between 46% and 47% in Q1 FY2026.</div>
</body></html>
"""


def test_fetch_filing_text_strips_html_and_decodes_entities():
    with patch.object(edgar, "_fetch", return_value=_FAKE_FILING_HTML):
        text = edgar.fetch_filing_text(
            "https://www.sec.gov/Archives/edgar/data/320193/example.htm"
        )
    assert "Apple Inc. 10-Q" in text
    assert "$94.9 billion" in text
    # HTML entity decoded (&dollar; -> $, &#45; -> -)
    assert "$25.0 billion" in text
    assert "all-time record" in text
    # No tags left
    assert "<" not in text
    assert "</" not in text
    # Script and style content stripped
    assert "set" not in text
    assert "font-family" not in text


def test_fetch_filing_text_rejects_non_sec_urls():
    import pytest
    with pytest.raises(ValueError, match="SEC.gov"):
        edgar.fetch_filing_text("https://evil.example.com/filing.htm")


def test_fetch_filing_text_truncates_at_max_chars():
    huge = b"<p>" + (b"data " * 50_000) + b"</p>"
    with patch.object(edgar, "_fetch", return_value=huge):
        text = edgar.fetch_filing_text(
            "https://www.sec.gov/Archives/edgar/data/320193/x.htm",
            max_chars=1000,
        )
    assert len(text) <= 1100  # 1000 + the truncation note
    assert "truncated" in text


def test_lookup_handles_network_failure():
    edgar._TICKER_CACHE = None
    with patch.object(edgar, "_fetch", side_effect=Exception("network down")):
        result = edgar.lookup("AAPL")
    assert result.error
    assert "ticker map" in result.error.lower()
