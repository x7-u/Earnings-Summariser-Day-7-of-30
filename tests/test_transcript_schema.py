"""Day 7. Tests for transcript_schema.parse_transcript."""
from __future__ import annotations

import pytest
from transcript_schema import (
    extract_firm,
    infer_role,
    parse_transcript,
    role_summary,
)


def test_parses_minimal_transcript_with_metadata_block():
    text = """\
Company: Acme Inc.
Ticker: ACME
Fiscal Period: Q1 FY2026
Call Date: 2026-01-15

Operator: Welcome to Acme's first quarter earnings call.

Jane Smith -- Chief Executive Officer: Thanks operator. Q1 was a record quarter. Revenue was $200 million.

Bob Brown -- Chief Financial Officer: Operating margin was 18 percent. We expect Q2 to be in line.

Operator: First question is from John Doe of Morgan Stanley.

John Doe -- Morgan Stanley: Thanks. Question on margin trajectory.

Jane Smith -- CEO: We are confident in the path to 22 percent.
"""
    doc = parse_transcript(text=text, source_filename="acme.txt")
    assert doc.metadata.company.startswith("Acme")
    assert doc.metadata.ticker == "ACME"
    assert doc.metadata.fiscal_period.startswith("Q1")
    assert len(doc.turns) >= 5
    roles = {t.role for t in doc.turns}
    assert "CEO" in roles
    assert "CFO" in roles
    assert "OPERATOR" in roles
    assert "ANALYST" in roles


def test_role_inference_directly():
    assert infer_role("Tim Cook", "Chief Executive Officer") == "CEO"
    assert infer_role("Luca Maestri", "Chief Financial Officer") == "CFO"
    assert infer_role("John Smith", "Morgan Stanley") == "ANALYST"
    assert infer_role("Operator", "") == "OPERATOR"
    assert infer_role("Suhasini", "Vice President of IR") == "EXEC"


def test_extract_firm_finds_known_brokers():
    assert extract_firm("Morgan Stanley") == "Morgan Stanley"
    assert extract_firm("J.P. Morgan") == "JPMorgan"
    assert extract_firm("Goldman Sachs research") == "Goldman Sachs"
    assert extract_firm("not a known firm") is None


def test_metadata_word_count_populated():
    text = """\
Company: X Co
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

Tim Cook -- CEO: Hello. Revenue was up 5 percent. We are confident.
Operator: That was the first turn.
"""
    doc = parse_transcript(text=text)
    assert doc.metadata.word_count > 5


def test_role_summary_counts_words():
    text = """\
Company: X Co
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

Tim Cook -- CEO: One two three four.
Bob -- CFO: Five six.
"""
    doc = parse_transcript(text=text)
    s = role_summary(doc.turns)
    assert s.get("CEO", 0) == 4
    assert s.get("CFO", 0) == 2


def test_empty_transcript_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_transcript(text="")


def test_parses_pasted_text_without_metadata_block():
    text = """\
Operator: Welcome.

Jane Smith -- CEO: We delivered a record quarter. Revenue was $5 billion. We are confident.

Operator: First question is from Adam Jonas of Morgan Stanley.

Adam Jonas -- Morgan Stanley: Thanks for the question.
"""
    doc = parse_transcript(text=text, source_filename="paste.txt")
    assert any(t.role == "CEO" for t in doc.turns)
    assert any(t.role == "ANALYST" for t in doc.turns)


def test_short_transcript_warns():
    text = "Tim Cook -- CEO: Hello world."
    doc = parse_transcript(text=text)
    assert any("Short transcript" in w for w in doc.warnings)


def test_speaker_with_inline_role_after_colon_no_dash():
    text = """\
Company: X
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

Tim Cook (Chief Executive Officer): We are confident.
Bob Smith, Morgan Stanley: Thanks.
"""
    doc = parse_transcript(text=text)
    speakers = {t.speaker for t in doc.turns}
    assert any("Tim Cook" in s for s in speakers)
    # "Bob Smith, Morgan Stanley" matches the speaker-line head; firm extracted
    analyst = next((t for t in doc.turns if "Bob Smith" in t.speaker), None)
    assert analyst is not None
    assert analyst.role == "ANALYST"
    assert analyst.firm == "Morgan Stanley"


def test_rejects_sentence_fragment_colon_lines_as_speaker_lines():
    """Lines like 'And: yes' or 'First quarter: results' must NOT be parsed
    as speaker turns."""
    text = """\
Company: X
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

Tim Cook -- CEO: We delivered a strong quarter.
And: yes we did.
Today: we are confident.
First quarter: results were strong.
However, the macro is uncertain.
"""
    doc = parse_transcript(text=text)
    # Only one speaker turn (Tim Cook), the rest absorbed as continuation.
    assert len(doc.turns) == 1
    assert doc.turns[0].speaker == "Tim Cook"
    # The text must include the non-speaker lines we absorbed.
    body = doc.turns[0].text
    assert "And: yes we did" in body or "and: yes we did" in body.lower()


def test_single_word_head_with_no_tail_is_rejected():
    """'Q1: revenue grew' must not be a speaker turn."""
    text = """\
Company: X
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

Tim Cook -- CEO: We grew.
Q1: was strong.
"""
    doc = parse_transcript(text=text)
    assert len(doc.turns) == 1
    assert doc.turns[0].role == "CEO"


def test_operator_alone_is_accepted():
    text = """\
Company: X
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

Operator: First question please.
Tim Cook -- CEO: Hello.
"""
    doc = parse_transcript(text=text)
    roles = [t.role for t in doc.turns]
    assert "OPERATOR" in roles
    assert "CEO" in roles


def test_no_speaker_lines_returns_empty_turns_with_warning():
    text = """\
Company: X
Ticker: X
Fiscal Period: Q1
Call Date: 2026-01-01

This is a paragraph of prose with no speaker tags. It should produce zero turns.
Even with multiple paragraphs.

Still no speakers detected here.
"""
    doc = parse_transcript(text=text)
    assert doc.turns == []
    assert any("No speaker turns" in w for w in doc.warnings)
