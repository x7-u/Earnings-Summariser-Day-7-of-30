"""Day 7. PDF export for BRIEF.

Four A4 landscape pages via matplotlib PdfPages:
  1. Cover with verdict + headline KPIs.
  2. Tone curve full bleed.
  3. Forward guidance table.
  4. Q&A grid.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
from analysis import CallAnalysis
from brief_chart import (
    NAVY,
    ORANGE,
    render_tone_curve_png,
)
from matplotlib.backends.backend_pdf import PdfPages

A4_LANDSCAPE = (11.69, 8.27)
CREAM = "#F4F1EA"
GREY = "#6B7280"
INK = "#0A1628"


def write_pdf(call: CallAnalysis, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = call.transcript.metadata
    h = call.headline
    es = call.exec_summary

    with PdfPages(out_path) as pdf:
        # ---- Page 1: Cover ----
        fig = plt.figure(figsize=A4_LANDSCAPE)
        fig.patch.set_facecolor(NAVY)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor(NAVY)
        ax.axis("off")
        ax.text(0.05, 0.92, "BRIEF", fontsize=28, fontweight="bold", color=ORANGE)
        ax.text(0.05, 0.87, "Day 07 . Earnings Call Summariser", fontsize=11, color=GREY)
        ax.text(0.05, 0.78, f"{md.company} ({md.ticker})", fontsize=24, fontweight="bold", color=CREAM)
        ax.text(0.05, 0.74, f"{md.fiscal_period}  |  {md.call_date}", fontsize=12, color=GREY)
        ax.text(0.05, 0.65,
                f"Tone: {h.overall_tone.upper()}   "
                f"Confidence: {h.confidence_score:.2f}   "
                f"Hedge: {h.hedge_count}   "
                f"Certainty: {h.certainty_count}   "
                f"Deflection: {h.deflection_count}",
                fontsize=12, color=CREAM)
        if es and es.headline:
            ax.text(0.05, 0.55, es.headline, fontsize=14, color=CREAM, wrap=True)
        if es and es.bull_case:
            ax.text(0.05, 0.42, "Bull case:", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.05, 0.38, es.bull_case, fontsize=10, color=CREAM, wrap=True)
        if es and es.bear_case:
            ax.text(0.05, 0.25, "Bear case:", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.05, 0.21, es.bear_case, fontsize=10, color=CREAM, wrap=True)
        if es and es.actions:
            ax.text(0.55, 0.55, "Actions:", fontsize=10, color=ORANGE, fontweight="bold")
            for i, a in enumerate(es.actions[:5]):
                ax.text(0.55, 0.51 - i * 0.04, f"- {a}", fontsize=10, color=CREAM)
        pdf.savefig(fig, bbox_inches="tight", facecolor=NAVY)
        plt.close(fig)

        # ---- Page 2: Tone curve ----
        png = render_tone_curve_png(call.tone_curve, title="Management tone curve")
        fig = _png_page(png)
        pdf.savefig(fig, bbox_inches="tight", facecolor=NAVY)
        plt.close(fig)

        # ---- Page 3: Guidance table ----
        fig = plt.figure(figsize=A4_LANDSCAPE)
        fig.patch.set_facecolor(NAVY)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor(NAVY)
        ax.axis("off")
        ax.text(0.05, 0.92, "Forward guidance", fontsize=20, fontweight="bold", color=CREAM)
        if not call.guidance:
            ax.text(0.05, 0.80, "No forward guidance extracted.", fontsize=12, color=GREY)
        else:
            y = 0.84
            ax.text(0.05, y, "Metric", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.20, y, "Period", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.32, y, "Dir", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.40, y, "Range", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.55, y, "Unit", fontsize=10, color=ORANGE, fontweight="bold")
            ax.text(0.66, y, "Quote", fontsize=10, color=ORANGE, fontweight="bold")
            y -= 0.04
            for g in call.guidance[:14]:
                rng = ""
                if g.range_low is not None and g.range_high is not None:
                    rng = f"{g.range_low:g} to {g.range_high:g}"
                elif g.range_low is not None:
                    rng = f"{g.range_low:g}"
                ax.text(0.05, y, g.metric[:18], fontsize=9, color=CREAM)
                ax.text(0.20, y, g.period[:14], fontsize=9, color=CREAM)
                ax.text(0.32, y, g.direction[:8], fontsize=9, color=CREAM)
                ax.text(0.40, y, rng[:14], fontsize=9, color=CREAM)
                ax.text(0.55, y, g.unit[:12], fontsize=9, color=CREAM)
                ax.text(0.66, y, g.quote[:80], fontsize=9, color=CREAM)
                y -= 0.04
        pdf.savefig(fig, bbox_inches="tight", facecolor=NAVY)
        plt.close(fig)

        # ---- Page 4: Q&A grid ----
        fig = plt.figure(figsize=A4_LANDSCAPE)
        fig.patch.set_facecolor(NAVY)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor(NAVY)
        ax.axis("off")
        ax.text(0.05, 0.92, "Analyst Q & A", fontsize=20, fontweight="bold", color=CREAM)
        if not call.qa:
            ax.text(0.05, 0.80, "No Q&A extracted.", fontsize=12, color=GREY)
        else:
            y = 0.85
            for qx in call.qa[:10]:
                ax.text(0.05, y, f"{qx.analyst_name} ({qx.analyst_firm})",
                        fontsize=10, fontweight="bold", color=ORANGE)
                ax.text(0.45, y, f"tension: {qx.tension}   clarity: {qx.management_clarity}",
                        fontsize=9, color=CREAM)
                y -= 0.025
                ax.text(0.05, y, "Q: " + qx.question_summary[:160],
                        fontsize=9, color=CREAM, wrap=True)
                y -= 0.025
                ax.text(0.05, y, "A: " + qx.answer_summary[:200],
                        fontsize=9, color="#94A3B8", wrap=True)
                y -= 0.05
        pdf.savefig(fig, bbox_inches="tight", facecolor=NAVY)
        plt.close(fig)
    return out_path


def _png_page(png_bytes: bytes):
    from matplotlib.image import imread
    img = imread(BytesIO(png_bytes))
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.patch.set_facecolor(NAVY)
    ax = fig.add_axes([0.04, 0.04, 0.92, 0.92])
    ax.set_facecolor(NAVY)
    ax.imshow(img)
    ax.axis("off")
    return fig
