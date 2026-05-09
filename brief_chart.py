"""Day 7. Charts for BRIEF.

  - render_tone_curve_png: management tone over the call (per turn).
  - render_speaker_breakdown_png: pie of word share by role.
  - render_tone_curve_svg: inline SVG for the live UI.

Bloomberg-terminal palette: navy ground, cream foreground, orange accent.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt

NAVY    = "#0A1628"
CREAM   = "#F4F1EA"
ORANGE  = "#FF6B00"
CYAN    = "#06B6D4"
GREY    = "#6B7280"
GREEN   = "#10B981"
RED     = "#EF4444"


def render_tone_curve_png(tone_points: list, *,
                          title: str = "Management tone curve",
                          out_path: Path | None = None) -> bytes:
    fig, ax = plt.subplots(figsize=(10, 3.6), dpi=120)
    fig.patch.set_facecolor(NAVY)
    ax.set_facecolor(NAVY)
    if not tone_points:
        ax.text(0.5, 0.5, "no tone signal", ha="center", va="center",
                color=CREAM, fontsize=12, transform=ax.transAxes)
        return _flush(fig, out_path)
    xs = list(range(len(tone_points)))
    ys = [p.tone for p in tone_points]
    # Zero baseline
    ax.axhline(0, color=GREY, linewidth=0.8, linestyle=":")
    # Fill positive in cyan, negative in orange
    ax.fill_between(xs, ys, 0, where=[y >= 0 for y in ys],
                    color=CYAN, alpha=0.30, interpolate=True)
    ax.fill_between(xs, ys, 0, where=[y < 0 for y in ys],
                    color=ORANGE, alpha=0.30, interpolate=True)
    ax.plot(xs, ys, color=CREAM, linewidth=2.0)
    # Mark turn boundaries by speaker role colour
    role_colour = {
        "CEO": "#FFD166", "CFO": CYAN, "EXEC": "#A78BFA",
        "ANALYST": ORANGE, "OPERATOR": GREY, "OTHER": GREY,
        "COO": "#34D399",
    }
    for i, p in enumerate(tone_points):
        ax.scatter(i, p.tone, color=role_colour.get(p.speaker_role, GREY),
                   s=14, zorder=4, edgecolors=CREAM, linewidths=0.4)
    ax.set_ylim(-1.05, 1.05)
    ax.set_xlabel("Turn (left = earliest)", color=CREAM, fontsize=10)
    ax.set_ylabel("Tone", color=CREAM, fontsize=10)
    ax.tick_params(colors=CREAM, labelsize=9)
    ax.set_title(title, color=CREAM, fontsize=12, pad=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(GREY)
    fig.tight_layout()
    return _flush(fig, out_path)


def render_speaker_breakdown_png(role_share: dict[str, float], *,
                                 title: str = "Word share by role",
                                 out_path: Path | None = None) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 3.8), dpi=120)
    fig.patch.set_facecolor(NAVY)
    ax.set_facecolor(NAVY)
    if not role_share:
        ax.text(0.5, 0.5, "no speakers", ha="center", va="center",
                color=CREAM, transform=ax.transAxes)
        return _flush(fig, out_path)
    labels = list(role_share.keys())
    sizes = [role_share[r] for r in labels]
    colours = []
    palette = {
        "CEO": "#FFD166", "CFO": CYAN, "EXEC": "#A78BFA",
        "ANALYST": ORANGE, "OPERATOR": GREY, "OTHER": "#94A3B8",
        "COO": "#34D399",
    }
    for r in labels:
        colours.append(palette.get(r, "#94A3B8"))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colours,
        autopct="%1.0f%%", startangle=140,
        wedgeprops={"edgecolor": NAVY, "linewidth": 1.5},
        textprops={"color": CREAM, "fontsize": 9},
    )
    for at in autotexts:
        at.set_color(NAVY)
        at.set_fontweight("bold")
    ax.set_title(title, color=CREAM, fontsize=12, pad=10)
    fig.tight_layout()
    return _flush(fig, out_path)


def render_tone_curve_svg(tone_points: list, *, width: int = 920,
                          height: int = 240, pad: int = 40) -> str:
    """Inline SVG with the same shape as the PNG. Used by the live UI."""
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="{height}">')
    parts.append(f'<rect width="{width}" height="{height}" fill="{NAVY}"/>')
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    if not tone_points:
        parts.append(f'<text x="{width/2:.0f}" y="{height/2:.0f}" fill="{CREAM}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="12" text-anchor="middle">no tone signal</text>')
        parts.append("</svg>")
        return "".join(parts)
    n = len(tone_points)
    def x_at(i: int) -> float:
        return pad + (i / max(1, n - 1)) * inner_w
    def y_at(t: float) -> float:
        return pad + (1 - (t + 1) / 2) * inner_h
    # Zero line
    y0 = y_at(0)
    parts.append(f'<line x1="{pad}" y1="{y0:.1f}" x2="{pad + inner_w}" y2="{y0:.1f}" stroke="{GREY}" stroke-width="0.6" stroke-dasharray="2 4"/>')
    # Fills
    pts = [(x_at(i), y_at(p.tone)) for i, p in enumerate(tone_points)]
    # Polyline
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    parts.append(f'<polyline points="{poly}" fill="none" stroke="{CREAM}" stroke-width="2"/>')
    # Per-point dots colour-coded by role
    role_colour = {
        "CEO": "#FFD166", "CFO": CYAN, "EXEC": "#A78BFA",
        "ANALYST": ORANGE, "OPERATOR": GREY, "OTHER": GREY,
        "COO": "#34D399",
    }
    for i, p in enumerate(tone_points):
        x, y = pts[i]
        c = role_colour.get(p.speaker_role, GREY)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{c}" stroke="{CREAM}" stroke-width="0.6"/>')
    parts.append(f'<text x="{pad}" y="{pad - 8}" fill="{CREAM}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="10">+1 confident</text>')
    parts.append(f'<text x="{pad}" y="{pad + inner_h + 18}" fill="{CREAM}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="10">-1 defensive</text>')
    parts.append("</svg>")
    return "".join(parts)


def _flush(fig, out_path: Path | None) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    data = buf.getvalue()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
    return data
