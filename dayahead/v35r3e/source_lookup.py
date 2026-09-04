"""Science-neutral resilient lookup for disappearing raw-cache directories."""

from __future__ import annotations

import os
from pathlib import Path

from dayahead.authority import sha256_file
from dayahead.v28r2 import source_labels


def install_missing_directory_tolerant_lookup() -> None:
    """Preserve exact-SHA authority while ignoring vanished walk branches."""

    def find_exact(root: Path, filename: str, expected_sha256: str) -> Path:
        matches = []
        for directory, names, files in os.walk(
            root, topdown=True, onerror=lambda _error: None,
        ):
            names.sort()
            files.sort()
            if filename not in files:
                continue
            candidate = Path(directory) / filename
            try:
                if candidate.is_file() and sha256_file(candidate) == expected_sha256:
                    matches.append(candidate)
            except FileNotFoundError:
                continue
        if not matches:
            raise FileNotFoundError(f"V28R2_EXACT_SOURCE_NOT_FOUND:{filename}")
        return sorted(matches)[0]

    source_labels._find_exact = find_exact
