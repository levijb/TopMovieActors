from pathlib import Path

from actor_success.analysis import AnalysisConfig, _wilson_lower, analyze
from actor_success.demo import create_demo_data


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

