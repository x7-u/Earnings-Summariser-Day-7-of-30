"""Day 7. Quantitative claim extractor.

Walks a transcript turn and pulls out every dollar / pound / euro / percent
claim, plus surrounding context. Pure regex, no AI. Used for the 'every
number the company said' deep-dive panel.

Examples we want to catch:
    "$5.5 billion in revenue"
    "8.2 percent gross margin"
    "approximately 12% year over year"
    "GBP 1.2bn in capex"
    "EUR 450 million"
    "around 15 to 20 percent"
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class NumberClaim:
    raw: str               # the matched text e.g. "$5.5 billion"
    kind: str              # "currency" / "percent" / "range_percent" / "range_currency"
    value_low: float       # in base units (USD / %)
    value_high: float | None
    unit: str              # "USD" / "GBP" / "EUR" / "%"
    speaker: str
    role: str
    minute: int
    context: str           # ~80 chars surrounding


# Currency: $5.5bn, USD 5.5 billion, GBP 1.2bn, 5.5 million dollars, etc.
_CCY_PREFIX = {
    "$":   "USD",
    "USD": "USD",
    "US$": "USD",
    "GBP": "GBP",
    "£":   "GBP",
    "EUR": "EUR",
    "EU":  "EUR",
    "€":   "EUR",
}

_MAGNITUDE = {
    "":          1.0,
    "k":         1_000.0,
    "thousand":  1_000.0,
    "m":         1_000_000.0,
    "mn":        1_000_000.0,
    "million":   1_000_000.0,
    "millions":  1_000_000.0,
    "b":         1_000_000_000.0,
    "bn":        1_000_000_000.0,
    "billion":   1_000_000_000.0,
    "billions":  1_000_000_000.0,
    "t":         1_000_000_000_000.0,
    "tn":        1_000_000_000_000.0,
    "trillion":  1_000_000_000_000.0,
}

_CCY_RE = re.compile(
    r"(?P<prefix>\$|USD|US\$|GBP|EUR|EU|£|€)"
    r"\s?(?P<num>\d+(?:[.,]\d+)?)"
    r"(?:\s*to\s*(?P<num2>\d+(?:[.,]\d+)?))?"
    r"\s*(?P<mag>k|m|mn|million|millions|bn|b|billion|billions|tn|t|trillion)?",
    re.IGNORECASE,
)

# Percent: 8.2%, 8.2 percent, 8 to 12 percent, around 15%
_PCT_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)"
    r"(?:\s*(?:to|-)\s*(?P<num2>\d+(?:[.,]\d+)?))?"
    r"\s*(?:%|\bpercent\b|\bpct\b)",
    re.IGNORECASE,
)


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def extract(turns: list) -> list[NumberClaim]:
    """Walk turns, return one claim per matched pattern."""
    out: list[NumberClaim] = []
    for t in turns:
        for m in _CCY_RE.finditer(t.text):
            prefix = m.group("prefix").upper().strip()
            unit = _CCY_PREFIX.get(prefix, prefix)
            mag_str = (m.group("mag") or "").lower()
            scale = _MAGNITUDE.get(mag_str, 1.0)
            v_low = _to_float(m.group("num")) * scale
            v_high = (_to_float(m.group("num2")) * scale) if m.group("num2") else None
            kind = "range_currency" if v_high is not None else "currency"
            start = max(0, m.start() - 30)
            end = min(len(t.text), m.end() + 50)
            out.append(NumberClaim(
                raw=t.text[m.start():m.end()].strip(),
                kind=kind,
                value_low=v_low,
                value_high=v_high,
                unit=unit,
                speaker=t.speaker,
                role=t.role,
                minute=t.minute,
                context="..." + t.text[start:end].strip() + "...",
            ))
        for m in _PCT_RE.finditer(t.text):
            v_low = _to_float(m.group("num"))
            v_high = _to_float(m.group("num2")) if m.group("num2") else None
            # Filter sentence "the year 2024" or "10:30" patterns by ensuring
            # the matched text has a percent indicator.
            matched = t.text[m.start():m.end()]
            if not re.search(r"%|percent|pct", matched, re.IGNORECASE):
                continue
            # Skip implausible percents (over 1000 or below 0)
            if v_low > 1000 or v_low < 0:
                continue
            kind = "range_percent" if v_high is not None else "percent"
            start = max(0, m.start() - 30)
            end = min(len(t.text), m.end() + 50)
            out.append(NumberClaim(
                raw=matched.strip(),
                kind=kind,
                value_low=v_low,
                value_high=v_high,
                unit="%",
                speaker=t.speaker,
                role=t.role,
                minute=t.minute,
                context="..." + t.text[start:end].strip() + "...",
            ))
    return out


def summarise_by_role(claims: list[NumberClaim]) -> dict[str, int]:
    """How many quantitative claims by each speaker role."""
    out: dict[str, int] = {}
    for c in claims:
        out[c.role] = out.get(c.role, 0) + 1
    return out
