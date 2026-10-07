from pathlib import Path

import pytest

from actor_success.analysis import AnalysisConfig, _wilson_lower, analyze
from actor_success.cli import build_parser
from actor_success.demo import create_demo_data
from actor_success.plots import _read_rows, _sensitivity_data


def test_wilson_lower_rewards_evidence() -> None:
    assert _wilson_lower(50, 100, 1.96) > _wilson_lower(1, 2, 1.96)
    assert _wilson_lower(0, 0, 1.96) == 0.0


def test_demo_pipeline(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "results"
    create_demo_data(data_dir)

    summary = analyze(
        data_dir,
        output_dir,
        AnalysisConfig(min_votes=100, major_cast_size=3, top_n=4, min_movies=1),
        memory_limit="1GB",
    )

    assert summary["people_analyzed"] == 4
    assert summary["eligible_movie_count"] == 5
    assert summary["raw_percentage_winner"]["name"] == "Cleo Gamma"
    assert summary["confidence_adjusted_winner"]["name"] == "Cleo Gamma"
    assert summary["raw_percentage_winner"]["major_high_rated_movies"] == 4
    assert (output_dir / "leaderboard.csv").is_file()
    assert (output_dir / "movie_credits.csv").is_file()
    assert (output_dir / "report.md").is_file()
    assert (output_dir / "summary.json").is_file()

    leaderboard = _read_rows(output_dir / "leaderboard.csv")
    credits = _read_rows(output_dir / "movie_credits.csv")
    thresholds, actors, counts, totals = _sensitivity_data(
        leaderboard,
        credits,
        {"rating_threshold": 7.0, "major_cast_size": 3},
        limit=4,
    )
    cleo = next(index for index, actor in enumerate(actors) if actor["name"] == "Cleo Gamma")
    assert thresholds == (6.5, 7.0, 7.5, 8.0)
    assert counts[cleo] == [4, 4, 2, 2]
    assert totals[cleo] == 4
    assert counts[cleo][1] == int(actors[cleo]["major_high_rated_movies"])


@pytest.mark.parametrize("cutoff", [8.0, None])
def test_alternative_cutoffs(tmp_path: Path, cutoff: float | None) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "results"
    create_demo_data(data_dir)

    summary = analyze(
        data_dir,
        output_dir,
        AnalysisConfig(rating_threshold=cutoff, min_votes=100, top_n=4, min_movies=1),
        memory_limit="1GB",
    )
    rows = _read_rows(output_dir / "leaderboard.csv")
    credits = _read_rows(output_dir / "movie_credits.csv")
    assert summary["config"]["rating_threshold"] == cutoff
    assert summary["people_analyzed"] == 4
    thresholds, actors, counts, totals = _sensitivity_data(
        rows, credits, {"rating_threshold": cutoff, "major_cast_size": 3}, limit=4
    )
    assert counts[0][thresholds.index(cutoff)] == int(actors[0]["major_high_rated_movies"])
    assert totals[0] == int(actors[0]["eligible_movies"])
    if cutoff is None:
        assert thresholds == (None, 6.5, 7.0, 8.0)
        assert all(row["high_rated_movies"] == row["eligible_movies"] for row in rows)
        assert all(row["major_high_rated_movies"] == row["major_roles"] for row in rows)
        assert all(credit["is_high_rated"] == "True" for credit in credits)
        assert "none (all rated eligible movies)" in (output_dir / "report.md").read_text()
    else:
        assert thresholds == (7.5, 8.0, 8.5, 9.0)


def test_cli_accepts_no_rating_cutoff() -> None:
    args = build_parser().parse_args(["analyze", "--rating-threshold", "none"])
    assert args.rating_threshold is None

