"""Immutable contracts shared by every V28R2 heavy-backend step."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Mapping


AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
NATIVE_WINDOWS = os.name == "nt"
DAY_WORKERS = 4
GUROBI_THREADS = 4
SLOTS = 96
RESOLUTION_MINUTES = 15

EXECUTION_STEPS = (
    "01_INPUT_AUTHORITY_CHECK",
    "02_OPTIMIZER_CHANNEL_MATERIALIZATION",
    "03_REFERENCE_COMPUTE_SCHEDULE",
    "04_REFERENCE_DELTA_CLOSURE",
    "05_B0_MONOLITHIC",
    "06_B1_MONOLITHIC",
    "07_B2_MONOLITHIC",
    "08_B3_CL_MC_BD",
    "09_B3_MONOLITHIC",
    "10_B3_STANDARD_BD",
    "11_B3_SOLVER_EQUIVALENCE",
    "12_DAYAHEAD_SCHEDULE_FREEZE",
    "13_DA_B0_FRESH_OPENDSS",
    "14_DA_B1_FRESH_OPENDSS",
    "15_DA_B2_FRESH_OPENDSS",
    "16_DA_B3_FRESH_OPENDSS",
    "17_ACTUAL_NAMESPACE_OPEN",
    "18_ACTUAL_R0_NATURAL",
    "19_ACTUAL_B0_REPLAY",
    "20_ACTUAL_B1_REPLAY",
    "21_ACTUAL_B2_REPLAY",
    "22_ACTUAL_B3_REPLAY",
    "23_ACT_R0_FRESH_OPENDSS",
    "24_ACT_B0_FRESH_OPENDSS",
    "25_ACT_B1_FRESH_OPENDSS",
    "26_ACT_B2_FRESH_OPENDSS",
    "27_ACT_B3_FRESH_OPENDSS",
    "28_PI_B3_CL_MC_BD",
    "29_PI_B3_FRESH_OPENDSS",
    "30_CONSERVATION_FIREWALL_HASH_AUDIT",
)


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fixed_aest_axis(day: str) -> tuple[str, ...]:
    operating = date.fromisoformat(day)
    start = datetime.combine(operating, time.min, AEST)
    return tuple((start + timedelta(minutes=RESOLUTION_MINUTES * slot)).isoformat() for slot in range(SLOTS))


def _run_git_head(repo: Path, git_dir: Path | None = None) -> tuple[str | None, str]:
    command = ["git"]
    if git_dir is not None:
        command.extend((f"--git-dir={git_dir}", f"--work-tree={repo}"))
    command.extend(("rev-parse", "HEAD"))
    completed = subprocess.run(
        command, cwd=repo, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        return value, ""
    return None, completed.stderr.strip()


def _worktree_git_dir(repo: Path) -> Path | None:
    """Resolve a linked-worktree gitdir, including Windows paths under WSL."""
    dot_git = repo / ".git"
    if not dot_git.is_file():
        return None
    marker = dot_git.read_text(encoding="utf-8").strip()
    if not marker.lower().startswith("gitdir:"):
        return None
    raw = marker.split(":", 1)[1].strip()
    if not NATIVE_WINDOWS and re.match(r"^[A-Za-z]:[\\/]", raw):
        converted = subprocess.run(
            ["wslpath", "-u", raw], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        if converted.returncode != 0 or not converted.stdout.strip():
            raise RuntimeError(f"V28R2_GIT_WORKTREE_PATH_TRANSLATION_FAILED: {converted.stderr.strip()}")
        return Path(converted.stdout.strip())
    path = Path(raw)
    return path if path.is_absolute() else (repo / path).resolve()


def git_head(repo: Path) -> str:
    value, first_error = _run_git_head(repo)
    if value is not None:
        return value
    git_dir = _worktree_git_dir(repo)
    if git_dir is not None:
        value, fallback_error = _run_git_head(repo, git_dir)
        if value is not None:
            return value
    else:
        fallback_error = "linked worktree gitdir unavailable"
    raise RuntimeError(
        "V28R2_GIT_HEAD_UNAVAILABLE: "
        f"default={first_error or 'invalid object id'}; "
        f"worktree={fallback_error or 'invalid object id'}"
    )


def code_tree_manifest(repo: Path) -> dict[str, str]:
    roots = (repo / "dayahead/v28r2", repo / "tools/final_campaign")
    files = sorted(
        path for root in roots for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh"}
    )
    return {path.relative_to(repo).as_posix(): sha256_file(path) for path in files}


@dataclass(frozen=True)
class NativeSettings:
    day_workers: int = DAY_WORKERS
    gurobi_threads: int = GUROBI_THREADS
    gurobi_seed: int = 20260828
    feasibility_tolerance: float = 1e-6
    optimality_tolerance: float = 1e-6
    equivalence_tolerance: float = 1e-3
    opendss_slots: int = SLOTS
    opendss_clean_engine_per_trajectory: bool = True
    opendss_native_controls: bool = True

    def validate(self) -> None:
        if self.day_workers != DAY_WORKERS or self.gurobi_threads != GUROBI_THREADS:
            raise ValueError("V28R2_FROZEN_PARALLEL_RESOURCE_CONTRACT")
        if self.opendss_slots != SLOTS or not self.opendss_clean_engine_per_trajectory:
            raise ValueError("V28R2_FROZEN_OPENDSS_CONTRACT")


@dataclass(frozen=True)
class DayRunSpec:
    day: str
    campaign: str
    timestamps_fixed_aest: tuple[str, ...]
    git_head: str
    code_tree_sha256: str
    config_sha256: str
    source_day_sha256: str
    ml_model_sha256: str
    thermal_sha256: str
    scale_sha256: str
    formulation_fingerprint: str
    settings: NativeSettings
    output_roots: Mapping[str, str]

    def validate(self) -> None:
        if self.campaign != "april" or self.timestamps_fixed_aest != fixed_aest_axis(self.day):
            raise ValueError("V28R2_DAY_RUN_SPEC_TIME_OR_CAMPAIGN")
        self.settings.validate()
        if len(self.git_head) not in {40, 64} or any(character not in "0123456789abcdef" for character in self.git_head):
            raise ValueError("V28R2_DAY_RUN_SPEC_GIT_OBJECT_ID_REQUIRED")
        hashes = (
            self.code_tree_sha256, self.config_sha256,
            self.source_day_sha256, self.ml_model_sha256, self.thermal_sha256,
            self.scale_sha256, self.formulation_fingerprint,
        )
        if any(len(value) != 64 or any(character not in "0123456789abcdef" for character in value) for value in hashes):
            raise ValueError("V28R2_DAY_RUN_SPEC_SHA_REQUIRED")
        if set(self.output_roots) != {"frozen_artifacts", "logs", "progress"}:
            raise ValueError("V28R2_DAY_RUN_SPEC_OUTPUT_ROOTS")

    def payload(self) -> dict[str, object]:
        result = asdict(self)
        result["settings"] = asdict(self.settings)
        return result

    @property
    def sha256(self) -> str:
        self.validate()
        return canonical_sha256(self.payload())


def combined_file_sha256(files: Mapping[str, Path]) -> str:
    return canonical_sha256({name: sha256_file(path) for name, path in sorted(files.items())})
