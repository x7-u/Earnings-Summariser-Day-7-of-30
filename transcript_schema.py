"""Day 7. Transcript ingestion + speaker-turn detection.

Inputs: a TXT, a PDF (via PyMuPDF if available, fallback to pdfplumber-style
re-flow), or pasted raw text. Plus an optional metadata header (a small
key/value block at the top with company / ticker / fiscal_period / call_date).

Output: TranscriptDoc with metadata + a list of SpeakerTurn objects, each
labelled with a role (CEO / CFO / EXEC / ANALYST / OPERATOR / OTHER) inferred
from speaker tags or context.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---- Dataclasses ---------------------------------------------------

@dataclass
class TranscriptMetadata:
    company: str = ""
    ticker: str = ""
    fiscal_period: str = ""        # e.g. "Q1 FY2026"
    call_date: str = ""            # ISO yyyy-mm-dd
    word_count: int = 0
    source_filename: str = ""


@dataclass
class SpeakerTurn:
    """One contiguous block of speech from one named speaker."""
    speaker: str                   # name as it appears in the transcript
    role: str                      # CEO / CFO / EXEC / ANALYST / OPERATOR / OTHER
    firm: str | None               # for analysts ("Morgan Stanley")
    text: str                      # the words spoken
    minute: int                    # approx position in the call (0-based)


@dataclass
class TranscriptDoc:
    metadata: TranscriptMetadata
    turns: list[SpeakerTurn] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---- Speaker / role inference -------------------------------------

# A speaker line typically looks like:
#   "Tim Cook -- Chief Executive Officer"
#   "Tim Cook (CEO):"
#   "Tim Cook, Apple Inc.:"
#   "Operator:"
#   "John Smith - Morgan Stanley:"
#   "Tim Cook:"
# We treat anything followed by ":" or " --" (followed by capitalised words)
# at the start of a line as a candidate speaker line, then split off the
# role / firm portion if present.
_SPEAKER_RE = re.compile(
    r"^\s*"
    r"(?P<head>[A-Z][A-Za-z'.\- ]{1,80}?)"     # name (allow hyphens, apostrophes)
    r"(?:"
    r"\s*[-,]+\s*(?P<tail>[^:()]+)"             # -- Role / , Firm form
    r"|"
    r"\s*\((?P<tail2>[^)]+)\)"                  # (Role) parens form
    r")?"
    r"\s*:\s*"                                  # required colon
    r"(?P<rest>.*)$"
)

_ROLE_HINTS = {
    "CEO":      ["chief executive", "ceo", "executive officer"],
    "CFO":      ["chief financial", "cfo", "finance officer", "financial officer"],
    "COO":      ["chief operating", "coo", "operating officer"],
    "OPERATOR": ["operator"],
    "EXEC":     ["chairman", "president", "head of", "vp ", "vice president",
                 "chief", "investor relations", "ir "],
    "ANALYST":  ["analyst", "research", "morgan stanley", "goldman", "jpm",
                 "jpmorgan", "j.p. morgan", "barclays", "ubs", "citi",
                 "evercore", "wedbush", "piper", "raymond james", "bernstein",
                 "bofa", "credit suisse", "deutsche", "rbc", "hsbc",
                 "wells fargo", "stifel", "wolfe", "cowen", "bairn"],
}

# Known analyst firm strings to extract from the role/firm tail. Lowercased keys.
_KNOWN_FIRMS = {
    "morgan stanley":   "Morgan Stanley",
    "goldman sachs":    "Goldman Sachs",
    "goldman":          "Goldman Sachs",
    "j.p. morgan":      "JPMorgan",
    "jpmorgan":         "JPMorgan",
    "jpm":              "JPMorgan",
    "barclays":         "Barclays",
    "bank of america":  "Bank of America",
    "bofa":             "Bank of America",
    "ubs":              "UBS",
    "citi":             "Citi",
    "citigroup":        "Citi",
    "evercore":         "Evercore ISI",
    "wedbush":          "Wedbush",
    "piper sandler":    "Piper Sandler",
    "raymond james":    "Raymond James",
    "bernstein":        "Bernstein",
    "credit suisse":    "Credit Suisse",
    "deutsche bank":    "Deutsche Bank",
    "rbc":              "RBC Capital Markets",
    "rbc capital":      "RBC Capital Markets",
    "hsbc":             "HSBC",
    "wells fargo":      "Wells Fargo",
    "stifel":           "Stifel",
    "wolfe research":   "Wolfe Research",
    "cowen":            "Cowen",
    "baird":            "Baird",
}


def infer_role(speaker: str, tail: str) -> str:
    """Pick a role label given the speaker name and the role/firm tail."""
    haystack = (tail or "").lower() + " " + (speaker or "").lower()
    if any(h in haystack for h in _ROLE_HINTS["OPERATOR"]):
        return "OPERATOR"
    if any(h in haystack for h in _ROLE_HINTS["CEO"]):
        return "CEO"
    if any(h in haystack for h in _ROLE_HINTS["CFO"]):
        return "CFO"
    if any(h in haystack for h in _ROLE_HINTS["COO"]):
        return "COO"
    if any(h in haystack for h in _ROLE_HINTS["ANALYST"]):
        return "ANALYST"
    if any(h in haystack for h in _ROLE_HINTS["EXEC"]):
        return "EXEC"
    return "OTHER"


def extract_firm(tail: str) -> str | None:
    """Find the analyst firm name in the role/firm tail."""
    if not tail:
        return None
    low = tail.lower()
    for needle, label in _KNOWN_FIRMS.items():
        if needle in low:
            return label
    return None


# ---- Main parser --------------------------------------------------

def _read_text(*, file_bytes: bytes | None = None,
               path: Path | str | None = None,
               text: str | None = None,
               source_filename: str = "") -> tuple[str, str]:
    """Return (raw_text, source_filename)."""
    if text is not None:
        return text, source_filename or "pasted.txt"
    if file_bytes is None and path is None:
        raise ValueError("parse_transcript() needs file_bytes, path, or text.")
    if path is not None:
        p = Path(path)
        source_filename = source_filename or p.name
        ext = p.suffix.lower()
        if ext == ".txt":
            return p.read_text(encoding="utf-8", errors="replace"), source_filename
        if ext == ".pdf":
            return _pdf_to_text(p.read_bytes()), source_filename
        # default: try utf-8 text
        return p.read_text(encoding="utf-8", errors="replace"), source_filename
    # file_bytes path
    sf = source_filename or "upload.txt"
    if sf.lower().endswith(".pdf"):
        return _pdf_to_text(file_bytes), sf
    try:
        return file_bytes.decode("utf-8"), sf
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="replace"), sf


def _pdf_to_text(data: bytes) -> str:
    """Extract text from a PDF. PyMuPDF preferred; raises if neither library."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        try:
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in r.pages)
        except Exception as e:
            raise ValueError(
                f"PDF parsing requires PyMuPDF (fitz) or pypdf: {e}"
            ) from e
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def _parse_metadata_block(lines: list[str]) -> tuple[TranscriptMetadata, int]:
    """If the transcript begins with a small key/value block, parse it.
    Returns the metadata + the line index where the block ended."""
    md = TranscriptMetadata()
    end = 0
    for i, line in enumerate(lines[:30]):
        s = line.strip()
        if not s:
            if md.company or md.ticker or md.fiscal_period:
                end = i
                break
            continue
        if ":" not in s:
            continue
        key, _, val = s.partition(":")
        k = key.strip().lower()
        v = val.strip()
        if k in {"company"}:
            md.company = v
        elif k == "ticker":
            md.ticker = v.upper()
        elif k in {"fiscal period", "fiscal_period", "period", "quarter"}:
            md.fiscal_period = v
        elif k in {"call date", "call_date", "date"}:
            md.call_date = v
        else:
            # Stop parsing the metadata block on the first line that looks
            # like dialogue (a known role tag etc).
            if k in {"operator", "analyst"}:
                end = i
                break
    if end == 0 and (md.company or md.ticker):
        end = 6
    return md, end


def parse_transcript(*, file_bytes: bytes | None = None,
                     path: Path | str | None = None,
                     text: str | None = None,
                     source_filename: str = "") -> TranscriptDoc:
    raw, source_filename = _read_text(
        file_bytes=file_bytes, path=path, text=text, source_filename=source_filename,
    )
    if not raw or not raw.strip():
        raise ValueError("Transcript is empty.")

    # Normalise whitespace, strip page numbers / repeated headers a PDF often
    # leaves behind.
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*$", "", raw, flags=re.IGNORECASE | re.MULTILINE)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = raw.split("\n")

    md, body_start = _parse_metadata_block(lines, )
    md.source_filename = source_filename
    body_lines = lines[body_start:]

    turns = _split_into_turns(body_lines)
    word_count = sum(len(t.text.split()) for t in turns)
    md.word_count = word_count

    warnings: list[str] = []
    if not turns:
        warnings.append("No speaker turns detected. Provide a transcript "
                        "with 'Speaker:' tags at the start of each turn.")
    elif word_count < 200:
        warnings.append(f"Short transcript ({word_count} words). "
                        "AI extraction quality may suffer.")
    if md.fiscal_period == "":
        warnings.append("No fiscal_period in the metadata header; charts and exports will use 'Unknown period'.")

    return TranscriptDoc(metadata=md, turns=turns, warnings=warnings)


def _split_into_turns(lines: list[str]) -> list[SpeakerTurn]:
    turns: list[SpeakerTurn] = []
    current_speaker: str | None = None
    current_role: str = "OTHER"
    current_firm: str | None = None
    current_text: list[str] = []
    minute_counter = 0

    def flush():
        nonlocal current_text
        if current_speaker is None:
            return
        text = " ".join(s.strip() for s in current_text if s.strip()).strip()
        if not text:
            current_text = []
            return
        turns.append(SpeakerTurn(
            speaker=current_speaker,
            role=current_role,
            firm=current_firm,
            text=text,
            minute=minute_counter,
        ))
        current_text = []

    for line in lines:
        m = _SPEAKER_RE.match(line)
        if m and _looks_like_speaker_line(m, line):
            flush()
            current_speaker = m.group("head").strip().rstrip(",")
            tail = (m.group("tail") or m.group("tail2") or "").strip()
            current_role = infer_role(current_speaker, tail)
            current_firm = extract_firm(tail)
            rest = (m.group("rest") or "").strip()
            if rest:
                current_text = [rest]
            else:
                current_text = []
            # Crude minute estimate: approx 150 words per minute
            minute_counter = sum(len(t.text.split()) for t in turns) // 150
        else:
            current_text.append(line)
    flush()
    return turns


_SENTENCE_STARTERS = {
    "however", "additionally", "moreover", "in fact", "of course",
    "for example", "in summary", "first", "second", "third", "fourth",
    "in conclusion", "today", "this morning", "good morning", "good afternoon",
    "and", "but", "so", "then", "now", "next", "still", "yet",
    "this", "that", "these", "those", "we", "i",
    "first quarter", "second quarter", "third quarter", "fourth quarter",
    "q1", "q2", "q3", "q4", "h1", "h2",
    "at", "in", "on", "for", "with", "as", "before", "after", "during",
    "regarding", "lastly", "again", "also", "looking", "summary", "overall", "yes", "no",
}


def _looks_like_speaker_line(m: re.Match, line: str) -> bool:
    """Heuristics to reject false positives where a sentence inside a
    paragraph happens to contain a 'Word: ...' colon pattern.

    A real speaker line in an earnings call almost always has either:
      - a multi-word head (e.g. 'Tim Cook')
      - a single-word head that is in a small allow-list (Operator)
      - any head with an explicit role/firm tail (' -- CEO:', '(Morgan Stanley):')
    """
    head = m.group("head").strip()
    if len(head) < 2 or len(head) > 80:
        return False
    if line.startswith(" ") and not line.lstrip().startswith(head):
        return False

    # Reject if the head looks like a sentence opener.
    if head.lower() in _SENTENCE_STARTERS:
        return False

    # Has an explicit role/firm tail? Trust it.
    has_tail = bool((m.group("tail") or "").strip()
                    or (m.group("tail2") or "").strip())
    if has_tail:
        return True

    # No tail. Require either:
    #  - multi-word head with each word capitalised (a name), OR
    #  - a single-word head that is in the small allow-list.
    single_word_allow = {"operator", "moderator", "host"}
    words = head.split()
    if len(words) == 1:
        return head.lower() in single_word_allow
    # Multi-word: each token should start with a capital letter (allow
    # apostrophes and hyphens in names).
    for w in words:
        if not w:
            return False
        if not w[0].isupper():
            return False
    return True


def role_summary(turns: list[SpeakerTurn]) -> dict[str, int]:
    """Count of words per role (CEO / CFO / ANALYST / etc)."""
    out: dict[str, int] = {}
    for t in turns:
        out[t.role] = out.get(t.role, 0) + len(t.text.split())
    return out
