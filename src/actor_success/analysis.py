from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


REQUIRED_FILES = (
    "name.basics.tsv.gz",
    "title.basics.tsv.gz",
    "title.principals.tsv.gz",
    "title.ratings.tsv.gz",
)
ATTRIBUTION = "Information courtesy of\nIMDb\n(https://www.imdb.com).\nUsed with permission."


@dataclass(frozen=True)
class AnalysisConfig:
    rating_threshold: float = 7.0
    min_votes: int = 10_000
    major_cast_size: int = 3
    top_n: int = 100
    min_movies: int = 5
    confidence_z: float = 1.96


def _sql_path(path: Path) -> str:
    """Return a safely quoted path literal for DuckDB SQL."""
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _validate_inputs(data_dir: Path) -> dict[str, Path]:
    files = {name: data_dir / name for name in REQUIRED_FILES}
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        joined = "\n  - ".join(missing)
        raise FileNotFoundError(f"Missing IMDb dataset files:\n  - {joined}")
    return files


def _wilson_lower(successes: int, total: int, z: float) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    center = p + z2 / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total)
    return max(0.0, (center - margin) / denominator)


def _write_csv(path: Path, headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def analyze(
    data_dir: Path,
    output_dir: Path,
    config: AnalysisConfig,
    people_csv: Path | None = None,
    memory_limit: str = "4GB",
) -> dict[str, Any]:
    """Run the analysis and write a leaderboard, film-level audit, and summary."""
    files = _validate_inputs(data_dir)
    if people_csv is not None and not people_csv.is_file():
        raise FileNotFoundError(f"People CSV not found: {people_csv}")
    if config.top_n < 1 or config.min_movies < 1 or config.major_cast_size < 1:
        raise ValueError("top_n, min_movies, and major_cast_size must be positive")
    if config.min_votes < 0 or not 0 <= config.rating_threshold <= 10:
        raise ValueError("min_votes must be non-negative and rating_threshold must be 0-10")

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / ".duckdb-temp"
    temp_dir.mkdir(exist_ok=True)

    con = duckdb.connect()
    try:
        con.execute("SET preserve_insertion_order = false")
        con.execute(f"SET memory_limit = '{memory_limit.replace(chr(39), '')}'")
        con.execute(f"SET temp_directory = {_sql_path(temp_dir)}")

        basics = _sql_path(files["title.basics.tsv.gz"])
        ratings = _sql_path(files["title.ratings.tsv.gz"])
        principals = _sql_path(files["title.principals.tsv.gz"])
        names = _sql_path(files["name.basics.tsv.gz"])

        con.execute(
            f"""
            CREATE TEMP TABLE eligible_movies AS
            SELECT
                b.tconst,
                b.primaryTitle AS title,
                try_cast(b.startYear AS INTEGER) AS year,
                r.averageRating AS rating,
                r.numVotes AS votes
            FROM read_csv(
                {basics}, delim='\t', header=true, nullstr='\\N', quote='',
                columns={{
                    'tconst':'VARCHAR', 'titleType':'VARCHAR', 'primaryTitle':'VARCHAR',
                    'originalTitle':'VARCHAR', 'isAdult':'VARCHAR', 'startYear':'VARCHAR',
                    'endYear':'VARCHAR', 'runtimeMinutes':'VARCHAR', 'genres':'VARCHAR'
                }}
            ) AS b
            JOIN read_csv(
                {ratings}, delim='\t', header=true, nullstr='\\N', quote='',
                columns={{'tconst':'VARCHAR', 'averageRating':'DOUBLE', 'numVotes':'BIGINT'}}
            ) AS r USING (tconst)
            WHERE b.titleType = 'movie'
              AND b.isAdult = '0'
              AND r.numVotes >= ?
            """,
            [config.min_votes],
        )

        con.execute(
            f"""
            CREATE TEMP TABLE cast_credits AS
            WITH movie_cast AS (
                SELECT
                    p.tconst,
                    p.nconst,
                    p.ordering,
                    row_number() OVER (
                        PARTITION BY p.tconst ORDER BY p.ordering, p.nconst
                    ) AS cast_rank
                FROM read_csv(
                    {principals}, delim='\t', header=true, nullstr='\\N', quote='',
                    columns={{
                        'tconst':'VARCHAR', 'ordering':'INTEGER', 'nconst':'VARCHAR',
                        'category':'VARCHAR', 'job':'VARCHAR', 'characters':'VARCHAR'
                    }}
                ) AS p
                SEMI JOIN eligible_movies AS e USING (tconst)
                WHERE p.category IN ('actor', 'actress')
            )
            SELECT
                c.nconst,
                c.tconst,
                c.cast_rank,
                e.title,
                e.year,
                e.rating,
                e.votes
            FROM movie_cast AS c
            JOIN eligible_movies AS e USING (tconst)
            """
        )

        if people_csv is None:
            con.execute(
                """
                CREATE TEMP TABLE selected_people AS
                SELECT
                    nconst,
                    row_number() OVER (
                        ORDER BY sum(votes) DESC, count(*) DESC, nconst
                    ) AS source_rank,
                    sum(votes) AS audience_exposure
                FROM cast_credits
                GROUP BY nconst
                HAVING count(*) >= ?
                QUALIFY source_rank <= ?
                """,
                [config.min_movies, config.top_n],
            )
            cohort_method = "top actors by summed IMDb votes across eligible principal-cast movie credits"
        else:
            people = _sql_path(people_csv)
            con.execute(
                f"""
                CREATE TEMP TABLE selected_people AS
                SELECT
                    trim(nconst) AS nconst,
                    coalesce(try_cast(rank AS INTEGER), row_number() OVER ()) AS source_rank,
                    NULL::HUGEINT AS audience_exposure
                FROM read_csv({people}, header=true, all_varchar=true)
                WHERE nconst IS NOT NULL AND trim(nconst) != ''
                ORDER BY source_rank
                LIMIT ?
                """,
                [config.top_n],
            )
            cohort_method = f"user-supplied people list: {people_csv.name}"

        query = con.execute(
            f"""
            WITH person_names AS (
                SELECT n.nconst, n.primaryName
                FROM read_csv(
                    {names}, delim='\t', header=true, nullstr='\\N', quote='',
                    columns={{
                        'nconst':'VARCHAR', 'primaryName':'VARCHAR', 'birthYear':'VARCHAR',
                        'deathYear':'VARCHAR', 'primaryProfession':'VARCHAR',
                        'knownForTitles':'VARCHAR'
                    }}
                ) AS n
                SEMI JOIN selected_people AS s USING (nconst)
            ), aggregate_stats AS (
                SELECT
                    s.source_rank,
                    s.audience_exposure,
                    s.nconst,
                    coalesce(any_value(n.primaryName), s.nconst) AS name,
                    count(c.tconst) AS eligible_movies,
                    count(c.tconst) FILTER (WHERE c.rating >= ?) AS high_rated_movies,
                    count(c.tconst) FILTER (WHERE c.cast_rank <= ?) AS major_roles,
                    count(c.tconst) FILTER (
                        WHERE c.cast_rank <= ? AND c.rating >= ?
                    ) AS major_high_rated_movies,
                    round(avg(c.rating), 2) AS average_rating,
                    round(avg(c.rating) FILTER (WHERE c.cast_rank <= ?), 2) AS average_rating_as_major
                FROM selected_people AS s
                LEFT JOIN cast_credits AS c USING (nconst)
                LEFT JOIN person_names AS n USING (nconst)
                GROUP BY s.source_rank, s.audience_exposure, s.nconst
            )
            SELECT
                source_rank,
                nconst,
                name,
                eligible_movies,
                high_rated_movies,
                major_roles,
                major_high_rated_movies,
                round(100.0 * major_high_rated_movies / nullif(eligible_movies, 0), 2)
                    AS success_rate_pct,
                round(100.0 * major_high_rated_movies / nullif(major_roles, 0), 2)
                    AS major_role_hit_rate_pct,
                round(100.0 * major_high_rated_movies / nullif(high_rated_movies, 0), 2)
                    AS high_rated_major_share_pct,
                average_rating,
                average_rating_as_major,
                audience_exposure
            FROM aggregate_stats
            """,
            [
                config.rating_threshold,
                config.major_cast_size,
                config.major_cast_size,
                config.rating_threshold,
                config.major_cast_size,
            ],
        )
        headers = [item[0] for item in query.description]
        raw_rows = query.fetchall()

        records: list[dict[str, Any]] = []
        for raw in raw_rows:
            record = dict(zip(headers, raw, strict=True))
            lower = _wilson_lower(
                int(record["major_high_rated_movies"]),
                int(record["eligible_movies"]),
                config.confidence_z,
            )
            record["wilson_lower_pct"] = round(100 * lower, 2)
            records.append(record)

        raw_order = sorted(
            records,
            key=lambda row: (
                -(row["success_rate_pct"] or 0),
                -row["eligible_movies"],
                row["name"],
            ),
        )
        for raw_rank, record in enumerate(raw_order, start=1):
            record["raw_rank"] = raw_rank

        records.sort(
            key=lambda row: (
                -row["wilson_lower_pct"],
                -(row["success_rate_pct"] or 0),
                -row["eligible_movies"],
                row["name"],
            )
        )
        for confidence_rank, record in enumerate(records, start=1):
            record["confidence_rank"] = confidence_rank

        ordered_headers = [
            "confidence_rank",
            "raw_rank",
            "source_rank",
            "nconst",
            "name",
            "eligible_movies",
            "high_rated_movies",
            "major_roles",
            "major_high_rated_movies",
            "success_rate_pct",
            "wilson_lower_pct",
            "major_role_hit_rate_pct",
            "high_rated_major_share_pct",
            "average_rating",
            "average_rating_as_major",
            "audience_exposure",
        ]
        leaderboard_rows = [tuple(record.get(key) for key in ordered_headers) for record in records]
        leaderboard_path = output_dir / "leaderboard.csv"
        _write_csv(leaderboard_path, ordered_headers, leaderboard_rows)

        credits_query = con.execute(
            """
            SELECT
                s.source_rank,
                s.nconst,
                c.tconst,
                c.title,
                c.year,
                c.rating,
                c.votes,
                c.cast_rank,
                c.cast_rank <= ? AS is_major,
                c.rating >= ? AS is_high_rated,
                c.cast_rank <= ? AND c.rating >= ? AS is_success
            FROM selected_people AS s
            JOIN cast_credits AS c USING (nconst)
            ORDER BY s.source_rank, c.year NULLS LAST, c.title, c.tconst
            """,
            [
                config.major_cast_size,
                config.rating_threshold,
                config.major_cast_size,
                config.rating_threshold,
            ],
        )
        credits_headers = [item[0] for item in credits_query.description]
        credits_rows = credits_query.fetchall()
        credits_path = output_dir / "movie_credits.csv"
        _write_csv(credits_path, credits_headers, credits_rows)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "IMDb non-commercial datasets",
            "cohort_method": cohort_method,
            "metric": (
                "success_rate_pct = top-billed principal-cast movies rated at or above "
                "the threshold / all eligible principal-cast movies"
            ),
            "ranking": "95% Wilson lower confidence bound on success_rate_pct",
            "config": asdict(config),
            "people_analyzed": len(records),
            "eligible_movie_count": con.execute("SELECT count(*) FROM eligible_movies").fetchone()[0],
            "raw_percentage_winner": raw_order[0] if raw_order else None,
            "confidence_adjusted_winner": records[0] if records else None,
            "input_files": {
                name: {
                    "size_bytes": path.stat().st_size,
                    "modified_at_utc": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
                for name, path in files.items()
            },
            "limitations": [
                "IMDb's non-commercial title.principals dataset contains principal credits, not full filmographies.",
                "Cast rank is derived among actor/actress rows from the principals ordering field; it is a proxy for role size.",
                "The default cohort is an exposure-based reproducible proxy, not the proprietary IMDbPro STARmeter ranking.",
                "IMDb ratings and vote counts change over time, so record the dataset download date when comparing runs.",
            ],
            "attribution": ATTRIBUTION,
        }
        summary_path = output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        raw_winner = summary["raw_percentage_winner"]
        confidence_winner = summary["confidence_adjusted_winner"]
        report_lines = [
            "# IMDb Actor Success Results",
            "",
            f"Generated {summary['generated_at_utc']} from IMDb's non-commercial datasets.",
            "",
        ]
        if raw_winner and confidence_winner:
            report_lines.extend(
                [
                    "## Answer",
                    "",
                    (
                        f"**Highest raw percentage: {raw_winner['name']} — "
                        f"{raw_winner['success_rate_pct']:.2f}% "
                        f"({raw_winner['major_high_rated_movies']} of "
                        f"{raw_winner['eligible_movies']} eligible movies).**"
                    ),
                    "",
                    (
                        f"**Strongest confidence-adjusted result: {confidence_winner['name']} — "
                        f"{confidence_winner['success_rate_pct']:.2f}% raw, "
                        f"{confidence_winner['wilson_lower_pct']:.2f}% Wilson lower bound "
                        f"({confidence_winner['major_high_rated_movies']} of "
                        f"{confidence_winner['eligible_movies']}).**"
                    ),
                    "",
                ]
            )
        report_lines.extend(
            [
                "## Confidence-adjusted leaderboard",
                "",
                "| Rank | Raw rank | Actor | Eligible movies | Successful movies | Raw success | Wilson lower bound |",
                "|---:|---:|---|---:|---:|---:|---:|",
            ]
        )
        for record in records[:20]:
            safe_name = str(record["name"]).replace("|", "\\|")
            actor_link = f"[{safe_name}](https://www.imdb.com/name/{record['nconst']}/)"
            report_lines.append(
                f"| {record['confidence_rank']} | {record['raw_rank']} | {actor_link} | "
                f"{record['eligible_movies']} | {record['major_high_rated_movies']} | "
                f"{record['success_rate_pct']:.2f}% | {record['wilson_lower_pct']:.2f}% |"
            )
        report_lines.extend(
            [
                "",
                "## Settings",
                "",
                f"- Rating threshold: **{config.rating_threshold:.1f}+**",
                f"- Minimum votes per movie: **{config.min_votes:,}**",
                f"- Major role proxy: **top {config.major_cast_size} cast positions**",
                f"- Cohort size: **{len(records)}**",
                f"- Cohort method: {cohort_method}",
                "",
                "See `leaderboard.csv` for all actors, `movie_credits.csv` for the underlying film rows, "
                "and `summary.json` for machine-readable settings and limitations.",
                "",
                *ATTRIBUTION.splitlines(),
                "",
            ]
        )
        (output_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
        return summary
    finally:
        con.close()

