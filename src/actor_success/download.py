from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

from .analysis import REQUIRED_FILES


BASE_URL = "https://datasets.imdbws.com"


def download_datasets(data_dir: Path, force: bool = False) -> list[Path]:
    """Download the official IMDb non-commercial files needed by the analysis."""
    data_dir.mkdir(parents=True, exist_ok=True)
    completed: list[Path] = []
    for filename in REQUIRED_FILES:
        destination = data_dir / filename
        if destination.exists() and not force:
            print(f"Using existing {destination}")
            completed.append(destination)
            continue

        temporary = destination.with_suffix(destination.suffix + ".part")
        request = urllib.request.Request(
            f"{BASE_URL}/{filename}",
            headers={"User-Agent": "imdb-actor-success/0.1 (personal research project)"},
        )
        print(f"Downloading {filename} ...")
        try:
            with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        completed.append(destination)
    return completed

