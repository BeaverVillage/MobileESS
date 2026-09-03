"""Portable loading of the frozen V28R2 formulation and electrical cache."""

from __future__ import annotations

import os
from pathlib import Path

from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.formulation import materialize_formulation_data

from .contracts import ESIF_PUE_PARQUET, KESTREL_ARCHIVE, SOURCE_DATA_REPOSITORY


def install_exact_source_lookup() -> None:
    """Bypass broken OneDrive descendants while retaining exact source files."""

    import dayahead.v28r2.source_labels as labels

    paths = {
        "esif.influx.buildingData.PUE.combined.parquet": ESIF_PUE_PARQUET,
        "esif.hpc.kestrel.job-anon.zip": KESTREL_ARCHIVE,
    }

    def exact(_root: Path, filename: str, expected_sha256: str) -> Path:
        from dayahead.authority import sha256_file

        path = paths[filename]
        if not path.is_file() or sha256_file(path) != expected_sha256:
            raise RuntimeError(f"V36_EXACT_SOURCE_DRIFT:{filename}")
        return path

    labels._find_exact = exact


def load_day_context(day: str):
    install_exact_source_lookup()
    previous = Path.cwd()
    try:
        data = materialize_formulation_data(
            SOURCE_DATA_REPOSITORY, day, disable_legacy_mess_source=True,
        )
        cache = (
            SOURCE_DATA_REPOSITORY / "frozen_artifacts/v28r2_april_full_month_preflight"
            / day / "dayahead/electrical_cache"
        )
        electrical = build_electrical_context(SOURCE_DATA_REPOSITORY, data, cache)
        return data, electrical
    finally:
        os.chdir(previous)
