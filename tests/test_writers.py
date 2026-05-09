"""Day 7. Writers smoke tests (XLSX, CSVs, PDF)."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
from csv_writer import GUIDANCE_COLUMNS, QA_COLUMNS, write_guidance_csv, write_qa_csv
from excel_writer import write_workbook

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE.parent / "sample_data"


def _run(fname):
    from pipeline import analyse
    p = SAMPLE_DIR / fname
    if not p.exists():
        pytest.skip(f"missing sample {fname}")
    return analyse(path=p, source_filename=p.name, skip_ai=True)


def test_excel_six_sheets(tmp_path: Path):
    res = _run("sample_tsla_q1_2026.txt")
    out = tmp_path / "tsla.xlsx"
    write_workbook(res.call, out)
    wb = openpyxl.load_workbook(out)
    expected = {"Summary", "Guidance", "Themes", "QA", "Quotes", "Inputs"}
    assert expected.issubset(set(wb.sheetnames))


def test_qa_csv_header(tmp_path: Path):
    res = _run("sample_tsla_q1_2026.txt")
    out = tmp_path / "qa.csv"
    write_qa_csv(res.call, out)
    text = out.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0].split(",")
    assert tuple(header) == QA_COLUMNS


def test_guidance_csv_header(tmp_path: Path):
    res = _run("sample_tsla_q1_2026.txt")
    out = tmp_path / "guide.csv"
    write_guidance_csv(res.call, out)
    text = out.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0].split(",")
    assert tuple(header) == GUIDANCE_COLUMNS


def test_pdf_writes_non_empty(tmp_path: Path):
    from pdf_writer import write_pdf
    res = _run("sample_tsla_q1_2026.txt")
    out = tmp_path / "tsla.pdf"
    write_pdf(res.call, out)
    assert out.exists()
    assert out.stat().st_size > 5000
    # PDF magic bytes
    assert out.read_bytes()[:4] == b"%PDF"
