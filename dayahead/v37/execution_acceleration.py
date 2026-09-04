"""Science-neutral, fingerprinted execution caches for V37-P1."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pickle
import uuid
from typing import Any, Mapping, Sequence


COMPATIBILITY_VERSION = "V37_P1_EXECUTION_CACHE_V1"
FALLBACK_POLICY = (200, 400, 800, "FULL")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fallback_levels(move_candidate_count: int) -> tuple[int, ...]:
    """Return the unchanged 200 -> 400 -> 800 -> FULL logical widths."""

    total = max(0, int(move_candidate_count))
    values = [value for value in (200, 400, 800) if value <= total]
    if total not in values:
        values.append(total)
    return tuple(values)


def cumulative_missing_ids(
    selected_ids: Sequence[str], completed_ids: Sequence[str],
) -> tuple[str, ...]:
    """Preserve rank order while returning only previously unsolved IDs."""

    completed = set(map(str, completed_ids))
    return tuple(candidate_id for candidate_id in map(str, selected_ids) if candidate_id not in completed)


class CandidateResultCache:
    """Atomic exact-context cache for one restricted beam-parent search."""

    def __init__(self, root: Path, context: Mapping[str, Any]):
        self.root = Path(root)
        self.context = dict(context)
        self.context_sha256 = canonical_sha256(self.context)

    def specification(self, candidate_id: str, candidate_rank: int) -> dict[str, Any]:
        identity = {
            **self.context,
            "candidate_id": str(candidate_id),
            "candidate_rank": int(candidate_rank),
            "solve_type": "RESTRICTED",
        }
        token = canonical_sha256(identity)
        return {
            # Keep well below the legacy Windows MAX_PATH boundary while the
            # full 256-bit digests remain inside the validated payload.
            "path": str(
                self.root / self.context_sha256[:24] / f"{token[:32]}.pkl"
            ),
            "identity": identity,
            "identity_sha256": token,
        }

    @staticmethod
    def load(specification: Mapping[str, Any]) -> Any | None:
        path = Path(str(specification["path"]))
        if not path.is_file():
            return None
        try:
            with path.open("rb") as stream:
                payload = pickle.load(stream)
            if payload.get("identity_sha256") != specification["identity_sha256"]:
                return None
            if payload.get("identity") != specification["identity"]:
                return None
            return payload["result"]
        except (OSError, EOFError, pickle.PickleError, AttributeError, KeyError, TypeError):
            return None

    @staticmethod
    def store(specification: Mapping[str, Any], result: Any) -> dict[str, Any]:
        path = Path(str(specification["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(
            f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
        )
        payload = {
            "artifact_id": "V37_P1_RESTRICTED_CANDIDATE_CACHE_V1",
            "identity": dict(specification["identity"]),
            "identity_sha256": str(specification["identity_sha256"]),
            "result": result,
        }
        with temporary.open("wb") as stream:
            pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        return {
            "path": str(path),
            "sha256": file_sha256(path),
            "identity_sha256": str(specification["identity_sha256"]),
        }


def full_child_identity(
    execution_context: Mapping[str, Any], *, parent_state_sha256: str,
    fixed_trajectory_sha256: str, mess_step: int, candidate_id: str,
    seed_trajectory_sha256: str,
) -> dict[str, Any]:
    return {
        **dict(execution_context),
        "solve_type": "FULL",
        "MESS_step": int(mess_step),
        "beam_parent_fingerprint": str(parent_state_sha256),
        "fixed_previous_MESS_trajectory_SHA": str(fixed_trajectory_sha256),
        "candidate_id": str(candidate_id),
        "seed_trajectory_SHA": str(seed_trajectory_sha256),
    }
