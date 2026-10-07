from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import AnalysisConfig, analyze
from .demo import create_demo_data
from .download import download_datasets


def _analysis_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--people-csv",
        type=Path,
        help="Optional CSV with nconst and rank columns; bypasses automatic top-N selection.",
    )
    parser.add_argument("--rating-threshold", type=float, default=7.0)
    parser.add_argument("--min-votes", type=int, default=10_000)
    parser.add_argument("--major-cast-size", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--min-movies", type=int, default=5)
    parser.add_argument("--memory-limit", default="4GB")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imdb-actor-success",
        description="Analyze major roles in highly rated IMDb movies.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download official IMDb datasets.")
    download.add_argument("--data-dir", type=Path, default=Path("data"))
    download.add_argument("--force", action="store_true")

    analysis = subparsers.add_parser("analyze", help="Run the full analysis.")
    _analysis_arguments(analysis)

    demo = subparsers.add_parser("demo", help="Run a tiny fictional end-to-end demo.")
    demo.add_argument("--work-dir", type=Path, default=Path("demo"))
    demo.add_argument("--memory-limit", default="1GB")

    plots = subparsers.add_parser("plots", help="Create SVG figures from analysis CSV files.")
    plots.add_argument("--results-dir", type=Path, default=Path("results"))
    plots.add_argument("--output-dir", type=Path, default=Path("docs/figures"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "download":
        paths = download_datasets(args.data_dir, force=args.force)
        print(f"Ready: {len(paths)} dataset files in {args.data_dir.resolve()}")
        return

    if args.command == "plots":
        from .plots import create_plots

        paths = create_plots(args.results_dir, args.output_dir)
        for path in paths:
            print(path.resolve())
        return

    if args.command == "demo":
        data_dir = args.work_dir / "data"
        output_dir = args.work_dir / "results"
        create_demo_data(data_dir)
        summary = analyze(
            data_dir,
            output_dir,
            AnalysisConfig(min_votes=100, major_cast_size=3, top_n=4, min_movies=1),
            memory_limit=args.memory_limit,
        )
    else:
        config = AnalysisConfig(
            rating_threshold=args.rating_threshold,
            min_votes=args.min_votes,
            major_cast_size=args.major_cast_size,
            top_n=args.top_n,
            min_movies=args.min_movies,
        )
        summary = analyze(
            args.data_dir,
            args.output_dir,
            config,
            people_csv=args.people_csv,
            memory_limit=args.memory_limit,
        )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

