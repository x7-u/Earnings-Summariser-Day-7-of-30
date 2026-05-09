"""Day 7. CLI entry for BRIEF (earnings call summariser).

Usage:
  python main.py path/to/transcript.txt
  python main.py --sample tsla
  python main.py --sample aapl --no-ai
  python main.py path/to/transcript.pdf --model deepseek-chat --max-cost 0.02
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE / "sample_data"
OUTPUTS = HERE / "outputs"

SAMPLES = {
    "tsla": "sample_tsla_q1_2026.txt",
    "aapl": "sample_aapl_q4_2025.txt",
    "jpm":  "sample_jpm_q1_2026.txt",
}


def main():
    p = argparse.ArgumentParser(description="Day 7 BRIEF earnings call analyser (CLI).")
    p.add_argument("transcript", nargs="?", help="path to .txt or .pdf transcript")
    p.add_argument("--sample", choices=sorted(SAMPLES.keys()),
                   help="Use a bundled sample.")
    p.add_argument("--no-ai", action="store_true", help="Skip the DeepSeek call.")
    p.add_argument("--model", default=None, help="Override model.")
    p.add_argument("--api-key", default=None, help="Override DeepSeek API key.")
    p.add_argument("--max-cost", type=float, default=None,
                   help="USD guardrail; raise this to allow pricier runs.")
    p.add_argument("--self-consistency", type=int, default=1, choices=[1, 2, 3],
                   help="Run extraction N times for stability.")
    args = p.parse_args()

    from csv_writer import write_guidance_csv, write_qa_csv
    from excel_writer import write_workbook
    from pipeline import analyse

    if args.sample:
        path = SAMPLE_DIR / SAMPLES[args.sample]
    elif args.transcript:
        path = Path(args.transcript)
    else:
        p.error("Provide a transcript path or --sample.")
        return

    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    try:
        result = analyse(
            path=path, source_filename=path.name,
            skip_ai=args.no_ai, model=args.model, api_key=args.api_key,
            max_cost_usd=args.max_cost,
            self_consistency=args.self_consistency,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    md = result.call.transcript.metadata
    h = result.call.headline
    es = result.call.exec_summary
    print(f"\n  BRIEF | {md.company} ({md.ticker}) | {md.fiscal_period}")
    print(f"  Words           : {md.word_count:>8,}")
    print(f"  Approx minutes  : {h.minutes:>8}")
    print(f"  Distinct analysts: {h.analyst_count:>7}")
    print(f"  Overall tone    : {h.overall_tone:>8}")
    print(f"  Confidence      : {h.confidence_score:>8.3f}")
    print(f"  Hedge phrases   : {h.hedge_count:>8}")
    print(f"  Certainty       : {h.certainty_count:>8}")
    print(f"  Deflections     : {h.deflection_count:>8}")
    print(f"  Quant claims    : {h.quantitative_claims:>8}")
    print(f"  Guidance items  : {len(result.call.guidance):>8}")
    print(f"  Themes          : {len(result.call.themes):>8}")
    print(f"  Q&A exchanges   : {len(result.call.qa):>8}")
    if es and es.headline:
        print(f"\n  Verdict: {es.headline}")
    if not result.ai_stats.skipped and not result.ai_stats.error:
        print(f"  AI cost (USD)   : {result.ai_stats.cost_usd:>8.5f}")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M")
    slug = "".join(ch if ch.isalnum() else "_" for ch in md.company.lower())[:32].strip("_")
    xlsx = OUTPUTS / f"brief_{slug}_{ts}.xlsx"
    qa_csv = OUTPUTS / f"brief_{slug}_{ts}_qa.csv"
    g_csv = OUTPUTS / f"brief_{slug}_{ts}_guidance.csv"
    write_workbook(result.call, xlsx)
    write_qa_csv(result.call, qa_csv)
    write_guidance_csv(result.call, g_csv)
    print()
    print(f"  Wrote: {xlsx.relative_to(HERE)}")
    print(f"  Wrote: {qa_csv.relative_to(HERE)}")
    print(f"  Wrote: {g_csv.relative_to(HERE)}")


if __name__ == "__main__":
    main()
