"""Portable May formulation and electrical-context loader."""

from __future__ import annotations

import os
from pathlib import Path

from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.formulation import materialize_formulation_data

from dayahead.v36.context import install_exact_source_lookup
from .contracts import CACHE_ROOT, SOURCE_DATA_REPOSITORY


def load_day_context(repo: Path, day: str):
    install_exact_source_lookup()
    previous = Path.cwd()
    try:
        data = materialize_formulation_data(
            SOURCE_DATA_REPOSITORY, day, disable_legacy_mess_source=True,
        )
        cache = repo / CACHE_ROOT / "electrical" / day
        try:
            electrical = build_electrical_context(SOURCE_DATA_REPOSITORY, data, cache)
        except RuntimeError as error:
            if not str(error).startswith("V28R2_D1_ELECTRICAL_CACHE_MISSING:"):
                raise
            electrical = prepare_electrical_context(SOURCE_DATA_REPOSITORY, data, cache)
        return data, electrical
    finally:
        os.chdir(previous)
