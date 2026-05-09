"""Day 7. SEC EDGAR helpers.

Resolve a ticker to a CIK and surface the latest 10-Q / 10-K / 8-K filing.
This is best-effort: SEC requires a User-Agent on every request; we obey.

Used by /api/edgar/<ticker> in the Flask app to give the user a fast link
out to the most recent filing for the company they're analysing.

No API key needed.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

import os as _os_for_ua
USER_AGENT = _os_for_ua.getenv(
    "DAY07_EDGAR_UA",
    "Earnings-Brief/1.0 (your-email@example.com)",
)
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


@dataclass
class EdgarFiling:
    form: str               # "10-Q", "10-K", "8-K"
    date: str               # ISO yyyy-mm-dd
    accession: str          # e.g. "0001628280-26-001234"
    primary_document: str   # filename of the primary doc
    url: str                # link to the filing index


@dataclass
class EdgarLookup:
    ticker: str
    cik: str                # zero-padded 10 digits
    company_name: str
    filings: list[EdgarFiling]
    error: str | None = None


def _fetch(url: str, *, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


_TICKER_CACHE: dict[str, tuple[str, str]] | None = None


def _load_ticker_map() -> dict[str, tuple[str, str]]:
    """Fetch and cache the SEC ticker -> (CIK, company name) map."""
    global _TICKER_CACHE
    if _TICKER_CACHE is not None:
        return _TICKER_CACHE
    try:
        raw = _fetch(TICKER_MAP_URL)
    except Exception:
        _TICKER_CACHE = {}
        return _TICKER_CACHE
    data = json.loads(raw)
    out: dict[str, tuple[str, str]] = {}
    for _, row in data.items():
        cik = str(row.get("cik_str", "")).zfill(10)
        ticker = str(row.get("ticker", "")).upper()
        name = str(row.get("title", ""))
        if ticker:
            out[ticker] = (cik, name)
    _TICKER_CACHE = out
    return out


def fetch_filing_text(url: str, *, max_chars: int = 200_000) -> str:
    """Fetch a SEC filing URL and return readable plain text.

    Strips HTML tags, decodes HTML entities, collapses whitespace, and
    truncates at max_chars so we don't blow past the AI context window
    on a 200-page 10-K.

    The User-Agent header is required by SEC.
    """
    import html as _html
    import re as _re
    if not url or not url.startswith("https://www.sec.gov/"):
        raise ValueError("Only SEC.gov URLs are accepted.")
    raw = _fetch(url, timeout=20.0)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    # Strip <script> / <style> blocks first.
    text = _re.sub(r"<script[\s\S]*?</script>", "", text, flags=_re.IGNORECASE)
    text = _re.sub(r"<style[\s\S]*?</style>", "", text, flags=_re.IGNORECASE)
    # Convert <br> / <p> / </p> to newlines so paragraph structure survives.
    text = _re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=_re.IGNORECASE)
    text = _re.sub(r"<\s*/?\s*p\s*[^>]*>", "\n", text, flags=_re.IGNORECASE)
    text = _re.sub(r"<\s*/?\s*div\s*[^>]*>", "\n", text, flags=_re.IGNORECASE)
    # Strip everything else.
    text = _re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text)
    # Collapse runs of whitespace within a line, preserve paragraph breaks.
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...filing truncated for length...]\n"
    return text


def lookup(ticker: str, *, forms: tuple[str, ...] = ("10-Q", "10-K", "8-K"),
           limit: int = 5) -> EdgarLookup:
    t = ticker.strip().upper().replace(".", "-")
    if not t:
        return EdgarLookup(ticker=ticker, cik="", company_name="", filings=[],
                           error="Empty ticker.")
    try:
        ticker_map = _load_ticker_map()
    except Exception as e:
        return EdgarLookup(ticker=t, cik="", company_name="", filings=[],
                           error=f"Could not load ticker map: {e}")
    if t not in ticker_map:
        return EdgarLookup(ticker=t, cik="", company_name="", filings=[],
                           error=f"Ticker {t} not found in SEC ticker map.")
    cik, name = ticker_map[t]
    try:
        sub_raw = _fetch(SUBMISSIONS_URL.format(cik=cik))
    except Exception as e:
        return EdgarLookup(ticker=t, cik=cik, company_name=name, filings=[],
                           error=f"Could not load submissions: {e}")
    try:
        sub = json.loads(sub_raw)
    except json.JSONDecodeError as e:
        return EdgarLookup(ticker=t, cik=cik, company_name=name, filings=[],
                           error=f"Bad JSON from SEC: {e}")
    recent = sub.get("filings", {}).get("recent", {}) or {}
    forms_list = recent.get("form", []) or []
    dates = recent.get("filingDate", []) or []
    accs = recent.get("accessionNumber", []) or []
    primaries = recent.get("primaryDocument", []) or []
    out_filings: list[EdgarFiling] = []
    for f, d, a, p in zip(forms_list, dates, accs, primaries, strict=False):
        if f not in forms:
            continue
        acc_clean = a.replace("-", "")
        url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={int(cik)}&type={urllib.parse.quote(f)}"
            f"&dateb=&owner=include&count=10"
            if not p else
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{p}"
        )
        out_filings.append(EdgarFiling(
            form=f, date=d, accession=a,
            primary_document=p, url=url,
        ))
        if len(out_filings) >= limit:
            break
    return EdgarLookup(ticker=t, cik=cik, company_name=name,
                       filings=out_filings, error=None)
