from __future__ import annotations

import csv
import gzip
from pathlib import Path


def _write_gzip_tsv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)


def create_demo_data(data_dir: Path) -> None:
    """Create a tiny, fictional IMDb-shaped dataset for a fast end-to-end demo."""
    names = [
        ["nm0000001", "Ada Alpha", "1980", r"\N", "actress", "tt0000001"],
        ["nm0000002", "Ben Beta", "1975", r"\N", "actor", "tt0000001"],
        ["nm0000003", "Cleo Gamma", "1990", r"\N", "actress", "tt0000002"],
        ["nm0000004", "Dev Delta", "1985", r"\N", "actor", "tt0000004"],
    ]
    movies = [
        ["tt0000001", "movie", "North Star", "North Star", "0", "2018", r"\N", "110", "Drama"],
        ["tt0000002", "movie", "Second Light", "Second Light", "0", "2019", r"\N", "105", "Drama"],
        ["tt0000003", "movie", "Low Tide", "Low Tide", "0", "2020", r"\N", "99", "Comedy"],
        ["tt0000004", "movie", "High Road", "High Road", "0", "2021", r"\N", "121", "Thriller"],
        ["tt0000005", "movie", "Last Turn", "Last Turn", "0", "2022", r"\N", "115", "Drama"],
        ["tt0000006", "tvseries", "Not a Movie", "Not a Movie", "0", "2022", r"\N", "45", "Drama"],
    ]
    ratings = [
        ["tt0000001", "8.2", "120000"],
        ["tt0000002", "7.4", "90000"],
        ["tt0000003", "6.3", "70000"],
        ["tt0000004", "8.0", "50000"],
        ["tt0000005", "7.1", "20000"],
        ["tt0000006", "9.0", "200000"],
    ]
    principals = [
        ["tt0000001", "1", "nm0000001", "actress", r"\N", '["Lead"]'],
        ["tt0000001", "2", "nm0000002", "actor", r"\N", '["Friend"]'],
        ["tt0000001", "3", "nm0000003", "actress", r"\N", '["Neighbor"]'],
        ["tt0000001", "4", "nm0000004", "actor", r"\N", '["Doctor"]'],
        ["tt0000001", "5", "nm9999999", "director", r"\N", r"\N"],
        ["tt0000002", "1", "nm0000002", "actor", r"\N", '["Lead"]'],
        ["tt0000002", "2", "nm0000001", "actress", r"\N", '["Partner"]'],
        ["tt0000002", "3", "nm0000003", "actress", r"\N", '["Boss"]'],
        ["tt0000003", "1", "nm0000001", "actress", r"\N", '["Lead"]'],
        ["tt0000003", "2", "nm0000002", "actor", r"\N", '["Partner"]'],
        ["tt0000004", "1", "nm0000003", "actress", r"\N", '["Lead"]'],
        ["tt0000004", "2", "nm0000004", "actor", r"\N", '["Partner"]'],
        ["tt0000005", "1", "nm0000004", "actor", r"\N", '["Lead"]'],
        ["tt0000005", "2", "nm0000003", "actress", r"\N", '["Partner"]'],
        ["tt0000006", "1", "nm0000001", "actress", r"\N", '["TV Lead"]'],
    ]

    _write_gzip_tsv(
        data_dir / "name.basics.tsv.gz",
        ["nconst", "primaryName", "birthYear", "deathYear", "primaryProfession", "knownForTitles"],
        names,
    )
    _write_gzip_tsv(
        data_dir / "title.basics.tsv.gz",
        [
            "tconst", "titleType", "primaryTitle", "originalTitle", "isAdult",
            "startYear", "endYear", "runtimeMinutes", "genres",
        ],
        movies,
    )
    _write_gzip_tsv(
        data_dir / "title.ratings.tsv.gz",
        ["tconst", "averageRating", "numVotes"],
        ratings,
    )
    _write_gzip_tsv(
        data_dir / "title.principals.tsv.gz",
        ["tconst", "ordering", "nconst", "category", "job", "characters"],
        principals,
    )

