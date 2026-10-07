"""Publishable summary figures from the locally generated analysis tables."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

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
    rows: list[dict[str, str]], config: dict[str, Any], limit: int, destination: Path
) -> None:
    plt = _setup_figure()
    leaders = rows[:limit][::-1]
    fig, ax = plt.subplots(figsize=(11.5, 2.7 + 0.39 * len(leaders)), layout="constrained")
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
    ax.set_xlim(0, max(raw) + 12)
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
    ax.set_title("Who combines strong films with substantial roles?", loc="left", pad=38)
    ax.text(
        0,
        1.015,
        f"Top {len(leaders)} by evidence-adjusted score · dark segment is the conservative lower bound",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.legend(loc="lower right", frameon=False, ncol=2, fontsize=9)
    _save_svg(fig, plt, destination)


def _short_actor_label(name: str) -> str:
    if name.endswith(" Jr."):
        return " ".join(name.split()[-2:])
    if " De Niro" in name:
        return "De Niro"
    return name.split()[-1]


def _sample_size_panel(
    ax,
    rows: list[dict[str, str]],
    highlighted: list[dict[str, str]],
    short_names: bool = False,
) -> None:
    from adjustText import adjust_text

    ax.scatter(
        [int(row["eligible_movies"]) for row in rows],
        [float(row["success_rate_pct"]) for row in rows],
        s=28,
        color=GRID,
        edgecolors=MUTED,
        linewidths=0.35,
        alpha=0.65,
        label="Other actors",
    )
    ax.scatter(
        [int(row["eligible_movies"]) for row in highlighted],
        [float(row["success_rate_pct"]) for row in highlighted],
        s=65,
        color=CORAL,
        edgecolors="white",
        linewidths=0.7,
        zorder=4,
        label="Labeled actors",
    )
    ax.set_xlim(0, max(int(row["eligible_movies"]) for row in rows) + 20)
    ax.set_ylim(0, min(105, max(float(row["success_rate_pct"]) for row in rows) + 13))
    texts = []
    shortened = [_short_actor_label(row["name"]) for row in highlighted]
    shortened_counts = Counter(shortened)
    for row in highlighted:
        candidate = _short_actor_label(row["name"])
        label = candidate if short_names and shortened_counts[candidate] == 1 else row["name"]
        texts.append(
            ax.text(
                int(row["eligible_movies"]) + 0.7,
                float(row["success_rate_pct"]) + 0.4,
                label,
                fontsize=9,
                color=INK,
                zorder=5,
            )
        )
    adjust_text(
        texts,
        x=[int(row["eligible_movies"]) for row in highlighted],
        y=[float(row["success_rate_pct"]) for row in highlighted],
        ax=ax,
        ensure_inside_axes=True,
        expand=(1.16, 1.36),
        force_text=(0.4, 0.6),
        force_static=(0.25, 0.4),
        iter_lim=500,
        arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.55},
    )
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _sample_size_plot(rows: list[dict[str, str]], limit: int, destination: Path) -> None:
    plt = _setup_figure()
    if limit <= 10:
        fig, ax = plt.subplots(figsize=(12.5, 7.6), layout="constrained")
        _sample_size_panel(ax, rows, rows[:limit])
        ax.set_xlabel("Eligible movies in principal-cast filmography")
        ax.set_ylabel("Observed success rate (%)")
        ax.set_title("Similar percentages carry different evidence", loc="left", pad=38)
        ax.text(
            0,
            1.015,
            f"All {len(rows)} actors appear as dots; the top {limit} are named",
            transform=ax.transAxes,
            color=MUTED,
            fontsize=10,
        )
    else:
        fig, axes = plt.subplots(3, 1, figsize=(13.5, 15), sharex=True, sharey=True, layout="constrained")
        boundaries = (0, 9, 17, limit)
        for ax, start, end in zip(axes, boundaries[:-1], boundaries[1:], strict=True):
            _sample_size_panel(ax, rows, rows[start:end], short_names=True)
            ax.set_title(f"Adjusted ranks {start + 1}–{end}", loc="left", pad=10, color=MUTED)
            ax.set_ylabel("Observed success rate (%)")
        axes[-1].set_xlabel("Eligible movies in principal-cast filmography")
        fig.suptitle(
            f"Top {limit} actors, labeled across three matched views",
            x=0.08,
            ha="left",
            fontsize=18,
            fontweight="bold",
        )
        ax = axes[-1]
    ax.legend(loc="lower right", frameon=False)
    _save_svg(fig, plt, destination)


def _outcome_mix_plot(
    rows: list[dict[str, str]],
    credits: list[dict[str, str]],
    config: dict[str, Any],
    limit: int,
    destination: Path,
) -> None:
    plt = _setup_figure()
    top = rows[:limit][::-1]
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

    fig, ax = plt.subplots(figsize=(11, 2.6 + 0.37 * len(top)), layout="constrained")
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
    ax.set_title("What makes up each actor’s filmography?", loc="left", pad=38)
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


def _sensitivity_data(
    rows: list[dict[str, str]],
    credits: list[dict[str, str]],
    config: dict[str, Any],
    limit: int,
) -> tuple[tuple[float, ...], list[dict[str, str]], list[list[int]], list[int]]:
    """Count qualifying movies per actor at each rating cutoff."""
    baseline = float(config["rating_threshold"])
    thresholds = tuple(
        threshold for threshold in (baseline - 0.5, baseline, baseline + 0.5, baseline + 1.0)
        if 0 <= threshold <= 10
    )
    by_actor: dict[str, list[dict[str, str]]] = defaultdict(list)
    for credit in credits:
        by_actor[credit["nconst"]].append(credit)

    actors = rows[:limit]
    totals = [len(by_actor[row["nconst"]]) for row in actors]
    counts = [
        [
            sum(
                int(credit["cast_rank"]) <= config["major_cast_size"]
                and float(credit["rating"]) >= threshold
                for credit in by_actor[row["nconst"]]
            )
            for threshold in thresholds
        ]
        for row in actors
    ]
    return thresholds, actors, counts, totals


def _sensitivity_plot(
    rows: list[dict[str, str]],
    credits: list[dict[str, str]],
    config: dict[str, Any],
    limit: int,
    destination: Path,
) -> None:
    plt = _setup_figure()
    import matplotlib.colors as colors

    thresholds, actors, counts, totals = _sensitivity_data(rows, credits, config, limit)
    rates = [
        [100 * count / total if total else 0 for count in actor_counts]
        for actor_counts, total in zip(counts, totals, strict=True)
    ]
    cmap = colors.LinearSegmentedColormap.from_list("share", [PALE, PALE_TEAL, TEAL])
    fig, ax = plt.subplots(figsize=(10, 2.6 + 0.38 * len(actors)), layout="constrained")
    image = ax.imshow(rates, cmap=cmap, norm=colors.Normalize(vmin=0, vmax=100), aspect="auto")
    ax.set_xticks(range(len(thresholds)), [f"{threshold:.1f}+" for threshold in thresholds])
    ax.set_yticks(range(len(actors)), [row["name"] for row in actors])
    ax.tick_params(length=0)
    ax.set_xlabel("IMDb rating threshold")
    ax.set_title("How many major-role films clear each rating cutoff?", loc="left", pad=38)
    ax.text(
        0,
        1.015,
        (
            f"Top {len(actors)} at the baseline cutoff · each cell is qualifying / eligible films; "
            "darker color means a higher share"
        ),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    for y, actor_counts in enumerate(counts):
        for x, count in enumerate(actor_counts):
            ax.text(
                x,
                y,
                f"{count}/{totals[y]}",
                ha="center",
                va="center",
                color="white" if rates[y][x] >= 63 else INK,
                fontsize=9.5 if limit <= 10 else 8.6,
            )
    colorbar = fig.colorbar(image, ax=ax, orientation="horizontal", pad=0.09, fraction=0.035)
    colorbar.set_label("Share of eligible films that qualify (%)")
    colorbar.set_ticks([0, 25, 50, 75, 100])
    colorbar.outline.set_visible(False)
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
    if len(rows) < 10:
        raise ValueError("At least 10 actors are needed to create the top-10 figures")
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = []
    for limit in (10, 25):
        if len(rows) < limit:
            continue
        specs.extend(
            [
                (f"leaderboard-top{limit}.svg", lambda path, n=limit: _leaderboard_plot(rows, config, n, path)),
                (f"sample-size-top{limit}.svg", lambda path, n=limit: _sample_size_plot(rows, n, path)),
                (f"outcome-mix-top{limit}.svg", lambda path, n=limit: _outcome_mix_plot(rows, credits, config, n, path)),
                (f"rating-sensitivity-top{limit}.svg", lambda path, n=limit: _sensitivity_plot(rows, credits, config, n, path)),
            ]
        )
    paths = []
    for filename, render in specs:
        path = output_dir / filename
        render(path)
        paths.append(path)
    return paths
