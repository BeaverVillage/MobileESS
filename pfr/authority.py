"""Machine-readable PFR0 authority loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT_PATH = Path(__file__).with_name("contracts") / "SCIENTIFIC_REBASE_AUTHORITY.json"
EXPECTED_PR5_HEAD = "f728d4635922c02f08c1f146ced7c932a866d5df"
EXPECTED_PR5_BRANCH = "agent/post-stage15-runtime-acceleration"
EXPECTED_REBASE_BRANCH = "agent/pfr-ai-training-scientific-rebase"


def load_scientific_rebase_authority(
    path: Path = CONTRACT_PATH,
) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        authority = json.load(handle)
    validate_scientific_rebase_authority(authority)
    return authority


def validate_scientific_rebase_authority(authority: Mapping[str, Any]) -> None:
    inherited = authority.get("inherited_checkpoint", {})
    if inherited.get("head_sha") != EXPECTED_PR5_HEAD:
        raise ValueError("PFR authority does not inherit the recorded PR #5 head")
    if inherited.get("branch") != EXPECTED_PR5_BRANCH:
        raise ValueError("PFR authority does not inherit the PR #5 branch")
    if authority.get("rebase_branch") != EXPECTED_REBASE_BRANCH:
        raise ValueError("unexpected PFR rebase branch")
    if authority.get("main_scientific_campaign_started") is not False:
        raise ValueError("PFR0-PFR2 cannot authorize a scientific campaign")
    if authority.get("long_run_authorized") is not False:
        raise ValueError("PFR0-PFR2 cannot authorize a long run")
    legacy = authority.get("legacy_authority", {})
    if legacy.get("M1_M4") != "HISTORICAL_SUPERSEDED_MAIN_METHOD":
        raise ValueError("legacy M1-M4 status is not sealed")
    if legacy.get("Local_Repair") != "HISTORICAL_SUPERSEDED_MAIN_METHOD":
        raise ValueError("legacy Local Repair status is not sealed")
