"""Courbe de saturation (S5, TP5) : débit et p95 de /v1/predict selon le nombre d'usagers.

Deux graphiques côte à côte plutôt qu'un seul à deux axes : débit et latence n'ont pas la même échelle.
Lit les u<N>_stats.csv de loadtest/paliers.sh, avec le même parseur que loadtest/summary.py.

    python scripts/plot_saturation.py results/w1 --out docs/perf/saturation_w1.png
    python scripts/plot_saturation.py results/w1 results/w2 --out docs/perf/saturation_w1_w2.png
    python scripts/plot_saturation.py w1=results/w1,results/w1_fin --out docs/perf/saturation_w1.png

Une configuration s'écrit [nom=]dossier[,dossier...] : plusieurs dossiers (paliers d'affinage) forment une seule courbe.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loadtest"))
from summary import read_palier  # noqa: E402

SLO_P95_MS = 200
# Palette de référence (ordre catégoriel fixe), encre et surface claires.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def read_config(spec: str) -> tuple[str, list[dict]]:
    name, _, folders = spec.rpartition("=")
    paths = [Path(f) for f in folders.split(",")]
    rows = []
    for path in (p for folder in paths for p in folder.glob("u*_stats.csv")):
        palier = read_palier(path)
        if palier is not None:
            palier["usagers"] = int(re.findall(r"\d+", path.stem)[0])
            rows.append(palier)
    return name or paths[0].name, sorted(rows, key=lambda r: r["usagers"])


def style(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold")
    ax.set_xlabel("usagers simultanés", color=INK_2)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_2, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_ylim(bottom=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("configs", nargs="+", help="une configuration par courbe : [nom=]dossier[,dossier...]")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    configs = dict(read_config(spec) for spec in args.configs)
    if not any(configs.values()):
        print("Aucun palier /v1/predict trouvé", file=sys.stderr)
        return 1

    fig, (ax_debit, ax_p95) = plt.subplots(1, 2, figsize=(11, 4.2), facecolor=SURFACE)
    for color, (name, rows) in zip(SERIES, configs.items(), strict=False):
        x = [r["usagers"] for r in rows]
        for ax, key in ((ax_debit, "debit"), (ax_p95, "p95")):
            ax.plot(x, [r[key] for r in rows], color=color, linewidth=2, marker="o", markersize=7,
                    markeredgecolor=SURFACE, markeredgewidth=2, label=name)
            # Étiquette directe sur le dernier point seulement.
            ax.annotate(name, (x[-1], rows[-1][key]), xytext=(6, 0), textcoords="offset points",
                        va="center", color=INK, fontsize=9)

    style(ax_debit, "Débit de /v1/predict", "req/s")
    style(ax_p95, "p95 de /v1/predict", "ms")
    ax_p95.axhline(SLO_P95_MS, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
    ax_p95.annotate(f"SLO {SLO_P95_MS} ms", (0, SLO_P95_MS), xycoords=("axes fraction", "data"),
                    xytext=(4, 4), textcoords="offset points", color=INK_2, fontsize=9)
    if len(configs) > 1:
        ax_debit.legend(frameon=False, labelcolor=INK)

    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150, facecolor=SURFACE)
    print(f"Courbe écrite dans {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
