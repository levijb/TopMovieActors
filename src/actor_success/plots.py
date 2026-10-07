"""Publishable summary figures from the locally generated analysis tables."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .analysis import _wilson_lower


INK = "#162533"
MUTED = "#586b79"
GRID = "#dbe4e8"
TEAL = "#0b877c"
PALE_TEAL = "#b8ded8"
CORAL = "#dc6550"
GOLD = "#dfad49"
PALE = "#eef3f5"


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Analysis output not found: {path}; run 'analyze' first")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _setup_figure():
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError("Install plot dependencies with: python -m pip install -e '.[plots]'") from error

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 18,
            "axes.titleweight": "bold",
            "axes.labelcolor": INK,
            "axes.edgecolor": GRID,
            "text.color": INK,
            "xtick.color": MUTED,
            "ytick.color": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "top-movie-actors",
            "savefig.facecolor": "white",
        }
    )
    return plt


def _save_svg(fig, plt, destination: Path) -> None:
    fig.savefig(destination, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    svg = destination.read_text(encoding="utf-8")
    destination.write_text(
        "\n".join(line.rstrip() for line in svg.splitlines()).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _leaderboard_plot(
    rows: list[dict[str, str]], config: dict[str, Any], destination: Path
) -> None:
    plt = _setup_figure()
    leaders = rows[:15][::-1]
    fig, ax = plt.subplots(figsize=(11, 8.1), layout="constrained")
    positions = list(range(len(leaders)))

    lower = [float(row["wilson_lower_pct"]) for row in leaders]
    raw = [float(row["success_rate_pct"]) for row in leaders]
    ax.barh(positions, lower, color=TEAL, height=0.62, label="95% Wilson lower bound")
    ax.barh(
        positions,
        [estimate - bound for estimate, bound in zip(raw, lower, strict=True)],
        left=lower,
        color=PALE_TEAL,
        height=0.62,
        label="Gap to observed rate",
    )
    ax.scatter(raw, positions, color=INK, s=22, zorder=4)
    ax.set_yticks(positions, [row["name"] for row in leaders])
    ax.set_xlim(0, 78)
    ax.set_xlabel(
        f"Share of eligible movies with a major role and rating ≥ {config['rating_threshold']:.1f} (%)"
    )
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    for y, row in enumerate(leaders):
        ax.text(
            float(row["success_rate_pct"]) + 1.1,
            y,
            f"{float(row['success_rate_pct']):.1f}%  ·  {row['major_high_rated_movies']}/{row['eligible_movies']}",
            va="center",
            fontsize=8.7,
            color=INK,
        )
    ax.set_title("Who combines strong films with substantial roles?", loc="left", pad=18)
    ax.text(
        0,
        1.015,
        "Top 15 by evidence-adjusted score · dark segment reflects the conservative lower bound",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.legend(loc="lower right", frameon=False, ncol=2, fontsize=9)
    _save_svg(fig, plt, destination)


def _sample_size_plot(rows: list[dict[str, str]], destination: Path) -> None:
    plt = _setup_figure()
    fig, ax = plt.subplots(figsize=(10.5, 6.7), layout="constrained")
    ordinary = [row for row in rows if int(row["confidence_rank"]) > 4]
    highlighted = [row for row in rows if int(row["confidence_rank"]) <= 4]
    ax.scatter(
        [int(row["eligible_movies"]) for row in ordinary],
        [float(row["success_rate_pct"]) for row in ordinary],
        s=36,
        color=PALE_TEAL,
        edgecolors=TEAL,
        linewidths=0.6,
        alpha=0.9,
        label="Other actors",
    )
    ax.scatter(
        [int(row["eligible_movies"]) for row in highlighted],
        [float(row["success_rate_pct"]) for row in highlighted],
        s=90,
        color=CORAL,
        edgecolors="white",
        linewidths=0.7,
        zorder=4,
        label="Top four by adjusted score",
    )
    offsets = {
        "Leonardo DiCaprio": (8, -20),
        "Brad Pitt": (8, 8),
        "Emma Watson": (8, 5),
        "Tom Cruise": (8, -17),
    }
    for row in highlighted:
        ax.annotate(
            row["name"],
            (int(row["eligible_movies"]), float(row["success_rate_pct"])),
            xytext=offsets.get(row["name"], (8, 8)),
            textcoords="offset points",
            fontsize=9,
            color=INK,
        )
    ax.set_xlim(0, max(int(row["eligible_movies"]) for row in rows) + 13)
    ax.set_ylim(0, min(105, max(float(row["success_rate_pct"]) for row in rows) + 9))
    ax.set_xlabel("Eligible movies in principal-cast filmography")
    ax.set_ylabel("Observed success rate (%)")
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Similar percentages carry different evidence", loc="left", pad=18)
    ax.text(
        0,
        1.015,
        "Each dot is one of the 100 actors · small samples have less stable percentages",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.legend(loc="lower right", frameon=False)
    _save_svg(fig, plt, destination)


def _outcome_mix_plot(
    rows: list[dict[str, str]],
    credits: list[dict[str, str]],
    config: dict[str, Any],
    destination: Path,
) -> None:
    plt = _setup_figure()
    top = rows[:10][::-1]
    by_actor: dict[str, list[dict[str, str]]] = defaultdict(list)
    for credit in credits:
        by_actor[credit["nconst"]].append(credit)

    labels = [row["name"] for row in top]
    groups = []
    for row in top:
        movie_rows = by_actor[row["nconst"]]
        count = len(movie_rows)
        if count == 0:
            groups.append([0.0, 0.0, 0.0, 0.0])
            continue
        groups.append(
            [
                100 * sum(c["is_major"] == "True" and c["is_high_rated"] == "True" for c in movie_rows) / count,
                100 * sum(c["is_major"] == "True" and c["is_high_rated"] == "False" for c in movie_rows) / count,
                100 * sum(c["is_major"] == "False" and c["is_high_rated"] == "True" for c in movie_rows) / count,
                100 * sum(c["is_major"] == "False" and c["is_high_rated"] == "False" for c in movie_rows) / count,
            ]
        )

    fig, ax = plt.subplots(figsize=(10.5, 6.3), layout="constrained")
    positions = list(range(len(labels)))
    left = [0.0] * len(labels)
    for index, (label, color) in enumerate(
        [
            (f"Major role · ≥ {config['rating_threshold']:.1f}", TEAL),
            (f"Major role · < {config['rating_threshold']:.1f}", GOLD),
            (f"Smaller role · ≥ {config['rating_threshold']:.1f}", PALE_TEAL),
            (f"Smaller role · < {config['rating_threshold']:.1f}", PALE),
        ]
    ):
        widths = [group[index] for group in groups]
        ax.barh(positions, widths, left=left, height=0.65, label=label, color=color)
        left = [previous + width for previous, width in zip(left, widths, strict=True)]
    ax.set_yticks(positions, labels)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of eligible principal-cast movie appearances (%)")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_title("What makes up each actor’s filmography?", loc="left", pad=18)
    ax.text(
        0,
        1.015,
        "The teal segment is the numerator of the project’s success rate",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
    _save_svg(fig, plt, destination)


def _sensitivity_plot(
    rows: list[dict[str, str]],
    credits: list[dict[str, str]],
    config: dict[str, Any],
    destination: Path,
) -> None:
    plt = _setup_figure()
    import matplotlib.colors as colors

    baseline = float(config["rating_threshold"])
    thresholds = tuple(
        threshold for threshold in (baseline - 0.5, baseline, baseline + 0.5, baseline + 1.0)
        if 0 <= threshold <= 10
    )
    by_actor: dict[str, list[dict[str, str]]] = defaultdict(list)
    for credit in credits:
        by_actor[credit["nconst"]].append(credit)

    ranks: dict[float, dict[str, int]] = {}
    for threshold in thresholds:
        values = []
        for row in rows:
            movie_rows = by_actor[row["nconst"]]
            hits = sum(
                int(credit["cast_rank"]) <= config["major_cast_size"]
                and float(credit["rating"]) >= threshold
                for credit in movie_rows
            )
            values.append(
                (
                    row["nconst"],
                    _wilson_lower(hits, len(movie_rows), config["confidence_z"]),
                    hits,
                    len(movie_rows),
                    row["name"],
                )
            )
        values.sort(
            key=lambda item: (
                -item[1],
                -(item[2] / item[3] if item[3] else 0),
                -item[3],
                item[4],
            )
        )
        ranks[threshold] = {
            item[0]: rank for rank, item in enumerate(values, 1)
        }
    ranks[baseline] = {
        row["nconst"]: int(row["confidence_rank"]) for row in rows
    }

    actors = rows[:12]
    matrix = [[ranks[threshold][row["nconst"]] for threshold in thresholds] for row in actors]
    cmap = colors.LinearSegmentedColormap.from_list("rank", [TEAL, PALE_TEAL, PALE])
    fig, ax = plt.subplots(figsize=(8.2, 7.0), layout="constrained")
    ax.imshow(matrix, cmap=cmap, norm=colors.Normalize(vmin=1, vmax=35), aspect="auto")
    ax.set_xticks(range(len(thresholds)), [f"{threshold:.1f}+" for threshold in thresholds])
    ax.set_yticks(range(len(actors)), [row["name"] for row in actors])
    ax.tick_params(length=0)
    ax.set_xlabel("IMDb rating threshold")
    ax.set_title(f"How much does the {baseline:.1f} cutoff matter?", loc="left", pad=18)
    ax.text(
        0,
        1.015,
        (
            f"Rank among all {len(rows)} actors · top {config['major_cast_size']} cast positions "
            f"and ≥{config['min_votes']:,} votes throughout"
        ),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    for y, series in enumerate(matrix):
        for x, rank in enumerate(series):
            ax.text(x, y, str(rank), ha="center", va="center", color="white" if rank < 6 else INK, fontsize=10)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _save_svg(fig, plt, destination)


def create_plots(results_dir: Path, output_dir: Path) -> list[Path]:
    """Render all figures from a completed analysis."""
    rows = _read_rows(results_dir / "leaderboard.csv")
    credits = _read_rows(results_dir / "movie_credits.csv")
    summary_path = results_dir / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Analysis output not found: {summary_path}")
    config = json.loads(summary_path.read_text(encoding="utf-8"))["config"]
    if not rows or not credits:
        raise ValueError("Analysis CSV files are empty")
    rows.sort(key=lambda row: int(row["confidence_rank"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("leaderboard.svg", lambda path: _leaderboard_plot(rows, config, path)),
        ("sample-size.svg", lambda path: _sample_size_plot(rows, path)),
        ("outcome-mix.svg", lambda path: _outcome_mix_plot(rows, credits, config, path)),
        ("rating-sensitivity.svg", lambda path: _sensitivity_plot(rows, credits, config, path)),
    ]
    paths = []
    for filename, render in specs:
        path = output_dir / filename
        render(path)
        paths.append(path)
    return paths
