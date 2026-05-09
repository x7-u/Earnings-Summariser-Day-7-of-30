"""Day 7. Rule-based detector for management tone signals.

Three buckets, each a curated phrase list. Matches are case-insensitive
substring matches on word boundaries. The AI extraction adds context;
this module is the cheap deterministic floor.

Buckets:
  - hedge:      'we expect to', 'should', 'roughly', 'modestly', 'on track'
  - certainty:  'we will', 'committed', 'confident', 'guaranteed'
  - deflection: 'we don't break that out', 'as we mentioned', 'I will let X address'
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- Phrase lists (curated; add freely) ----------------------------

HEDGE_PHRASES = [
    "we expect", "we anticipate", "we believe", "we are confident in",
    "should be", "should see", "should result", "should benefit",
    "could see", "could be", "may see", "may result",
    "approximately", "roughly", "broadly", "modestly", "in the range of",
    "north of", "south of", "around", "give or take",
    "all else equal", "absent any", "barring any",
    "assuming current", "assuming a", "tracking towards",
    "broadly in line", "slightly above", "slightly below",
    "we are working to", "we are working on", "we plan to", "we are planning",
    "on track for", "on track to",
    "we feel good about", "we are pleased with",
    "expect to deliver", "expect to see", "expect to drive",
]

CERTAINTY_PHRASES = [
    "we will", "we are committed", "we have committed",
    "we are confident", "we are certain", "we know",
    "we delivered", "we achieved", "we hit", "we beat",
    "we exceeded", "we surpassed", "record", "all-time high",
    "best ever", "strongest ever", "guaranteed",
    "no question", "no doubt", "without question",
    "this year we will", "this quarter we will",
    "we are reaffirming", "we are raising", "we are increasing",
]

DEFLECTION_PHRASES = [
    "we don't break that out", "we do not break that out",
    "we don't disclose", "we do not disclose",
    "we don't comment", "we do not comment", "we won't comment",
    "we won't be commenting", "we are not going to comment",
    "we don't typically", "we do not typically",
    "as we mentioned", "as we discussed",
    "as I mentioned earlier", "as I said earlier",
    "i'd refer you to", "i would refer you to", "let me refer you",
    "i'll let", "let me hand it to", "i'll hand it over",
    "for competitive reasons", "for competitive purposes",
    "we're not in a position to", "we are not in a position to",
    "more colour at", "more color at",
    "we don't guide to", "we do not guide to",
]


@dataclass
class PhraseHit:
    bucket: str             # "hedge" / "certainty" / "deflection"
    phrase: str
    speaker: str
    role: str
    minute: int
    context: str            # ~80 chars of surrounding text


def _compile(phrases: list[str]) -> list[re.Pattern]:
    return [
        re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)
        for p in phrases
    ]


_HEDGE_RE      = _compile(HEDGE_PHRASES)
_CERTAINTY_RE  = _compile(CERTAINTY_PHRASES)
_DEFLECTION_RE = _compile(DEFLECTION_PHRASES)


def detect_signals(turns: list) -> list[PhraseHit]:
    """Walk every turn from CEO/CFO/EXEC and tag tone signals."""
    out: list[PhraseHit] = []
    for t in turns:
        if t.role not in ("CEO", "CFO", "COO", "EXEC"):
            continue
        text = t.text
        for bucket, patterns in (
            ("hedge", _HEDGE_RE),
            ("certainty", _CERTAINTY_RE),
            ("deflection", _DEFLECTION_RE),
        ):
            for pat in patterns:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 30)
                    end = min(len(text), m.end() + 50)
                    out.append(PhraseHit(
                        bucket=bucket,
                        phrase=m.group(0),
                        speaker=t.speaker,
                        role=t.role,
                        minute=t.minute,
                        context="..." + text[start:end].strip() + "...",
                    ))
    return out


def signal_summary(hits: list[PhraseHit]) -> dict[str, int]:
    """Bucket counts."""
    out = {"hedge": 0, "certainty": 0, "deflection": 0}
    for h in hits:
        out[h.bucket] = out.get(h.bucket, 0) + 1
    return out


def confidence_score(summary: dict[str, int]) -> float:
    """A simple management-confidence score in [0,1]:
    certainty / (certainty + hedge + 2*deflection + 1)
    """
    cert = summary.get("certainty", 0)
    hedge = summary.get("hedge", 0)
    deflect = summary.get("deflection", 0)
    denom = cert + hedge + 2 * deflect + 1
    if denom <= 0:
        return 0.5
    return cert / denom
