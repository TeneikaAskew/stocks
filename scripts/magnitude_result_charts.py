#!/usr/bin/env python3
"""Small-multiples charts for magnitude experiment results.

Renders a grid of panels (by ticker OR timeframe), one line per prediction
target/series, with end-of-line value labels and a base-rate reference — the
house style for reviewing EXPLOSIVE precision (or lift) curves at a glance.

Programmatic use::

    from scripts.magnitude_result_charts import small_multiples
    small_multiples(
        panels={"IWM": {"body": [.1,.2,.3], "30-min range": [.5,.55,.6]}, ...},
        series_order=["body", "30-min range"],
        x=[0.25, 0.45, 0.65],
        out_path="chart.png",
        title="Magnitude — EXPLOSIVE precision by prediction target",
        subtitle="...", xlabel="confidence (p_EXPLOSIVE >=)", ylabel="precision",
        pct=True, base_rate=0.05)

CLI use (reads a JSON of {panel: {series: [y...]}}):

    python -m scripts.magnitude_result_charts \\
        --data results.json --x 0.25,0.35,0.45,0.55,0.65 \\
        --series "single-bar body,30-min range" \\
        --out chart.png --title "..." --ylabel precision --pct

`panels` values must each be a list of len(x) numbers (None allowed for gaps).
Colours are assigned per series name from a colourblind-safe palette; unknown
series fall back to a stable cycling colour.
"""
from __future__ import annotations
import argparse
import itertools
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

# Okabe-Ito colourblind-safe palette; named keys for the common magnitude series.
PALETTE = {
    "single-bar body": "#999999",
    "body": "#999999",
    "30-min range": "#0072B2",
    "30-min up-excursion": "#009E73",
    "30-min down-excursion": "#D55E00",
    "range": "#0072B2",
    "up": "#009E73",
    "down": "#D55E00",
}
_FALLBACK = itertools.cycle(["#CC79A7", "#56B4E9", "#E69F00", "#000000", "#0072B2"])
_BG = "#FBFBFB"


def _colour(series, assigned):
    if series in PALETTE:
        return PALETTE[series]
    if series not in assigned:
        assigned[series] = next(_FALLBACK)
    return assigned[series]


def small_multiples(panels, series_order, x, out_path, *, title="", subtitle="",
                    xlabel="", ylabel="", pct=True, base_rate=None,
                    ncols=None, figsize=None):
    """Render a small-multiples line chart; return out_path.

    Raises ValueError on empty panels or a series whose y-length != len(x).
    """
    if not panels:
        raise ValueError("panels is empty — nothing to plot")
    x = list(x)
    for pname, series in panels.items():
        for sname, ys in series.items():
            if len(ys) != len(x):
                raise ValueError(
                    f"panel {pname!r} series {sname!r} has {len(ys)} values "
                    f"but x has {len(x)}")

    names = list(panels.keys())
    n = len(names)
    ncols = ncols or (2 if n > 3 else n)
    nrows = int(np.ceil(n / ncols))
    reserve = 1.5  # inches at top for title + subtitle + legend
    fw = (figsize[0] if figsize else 6.2 * ncols)
    fh = (figsize[1] if figsize else 4.7 * nrows) + reserve
    fig, axes = plt.subplots(nrows, ncols, figsize=(fw, fh), squeeze=False)
    fig.patch.set_facecolor("white")

    vals = [v for p in panels.values() for s in p.values() for v in s if v is not None]
    ymax = (max(vals + ([base_rate] if base_rate else [1e-9]))) * (1.18 if pct else 1.15)
    assigned = {}

    for i, name in enumerate(names):
        ax = axes[i // ncols][i % ncols]
        ax.set_facecolor(_BG)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color("#CCCCCC")
        ax.grid(axis="y", color="#E6E6E6", linewidth=0.9)
        ax.set_axisbelow(True)
        ax.set_ylim(0, ymax)
        ax.set_xlim(min(x) - 0.02, max(x) + 0.10)
        ax.set_title(name, loc="left", fontsize=15, fontweight="bold", pad=8)
        if base_rate is not None:
            ax.axhline(base_rate, color="#BBBBBB", ls=(0, (4, 3)), lw=1.1)
            ax.text(max(x) + 0.005, base_rate, "base rate", va="center",
                    ha="left", fontsize=8.5, color="#999999")
        for s in series_order:
            if s not in panels[name]:
                continue
            y = panels[name][s]
            c = _colour(s, assigned)
            ax.plot(x, y, color=c, lw=2.4, marker="o", ms=4.5,
                    solid_capstyle="round")
            if y[-1] is not None:
                lbl = f"{y[-1] * 100:.0f}%" if pct else f"{y[-1]:.2f}"
                ax.text(x[-1] + 0.012, y[-1], lbl, va="center", ha="left",
                        fontsize=10.5, fontweight="bold", color=c)
        if pct:
            ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
        ax.set_xlabel(xlabel, fontsize=10.5)
        if i % ncols == 0:
            ax.set_ylabel(ylabel, fontsize=10.5)
        ax.tick_params(labelsize=9.5, color="#CCCCCC")

    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    top = 1 - reserve / fh
    fig.tight_layout(rect=[0, 0, 1, top])
    fig.text(0.008, 1 - 0.33 / fh, title, ha="left", va="top",
             fontsize=17, fontweight="bold")
    if subtitle:
        fig.text(0.008, 1 - 0.80 / fh, subtitle, ha="left", va="top",
                 fontsize=10.5, color="#555555")
    handles = [plt.Line2D([0], [0], color=_colour(s, assigned), lw=2.6, marker="o", ms=5)
               for s in series_order]
    fig.legend(handles, series_order, loc="upper right", frameon=False,
               fontsize=10.5, ncol=len(series_order),
               bbox_to_anchor=(0.995, 1 - 0.42 / fh))
    fig.savefig(out_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, help="JSON: {panel: {series: [y...]}}")
    p.add_argument("--x", required=True, help="comma-separated x positions")
    p.add_argument("--series", default="", help="comma-separated series draw order (default: keys of first panel)")
    p.add_argument("--out", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--subtitle", default="")
    p.add_argument("--xlabel", default="")
    p.add_argument("--ylabel", default="precision")
    p.add_argument("--pct", action="store_true", help="format y-axis as percent")
    p.add_argument("--base-rate", type=float, default=None)
    p.add_argument("--ncols", type=int, default=None)
    a = p.parse_args(argv)
    panels = json.load(open(a.data))
    x = [float(v) for v in a.x.split(",")]
    series = a.series.split(",") if a.series else list(next(iter(panels.values())).keys())
    out = small_multiples(panels, series, x, a.out, title=a.title, subtitle=a.subtitle,
                          xlabel=a.xlabel, ylabel=a.ylabel, pct=a.pct,
                          base_rate=a.base_rate, ncols=a.ncols)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
