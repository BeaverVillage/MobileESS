"""Contracts for the disposable V33X development experiment."""

from __future__ import annotations


STARTING_HEAD = "0c9ea7ae7e90238c81164d268f941e6b538e6059"
BRANCH = "codex/v33x-fasttrack-grid-deliverable-aidc"
V30_HEAD = "f0fcc1c2835cc90b65aab7b788f1b55af544f6ea"
V30_TREE = "9a33aa0bb56f41df1fdc01e50fbca379b76a8968"
V30_ARTIFACT_SHA = "db57e68d116707d45ec0af4ab111a6e25ce4ee0234d08353e86dc498e7898fcb"
OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
DEVELOPMENT_VARIANTS = ("E0_CURRENT", "E1_FULL_GRID_ENVELOPE", "E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM")
DAY = "2025-04-04"


def experiment_contract() -> dict[str, object]:
    return {
        "artifact_id": "V33X_EXPERIMENT_CONTRACT_V1",
        "status": "DEVELOPMENT_ONLY",
        "day": DAY,
        "official_cases": list(OFFICIAL_CASES),
        "official_case_count": 4,
        "development_variants": list(DEVELOPMENT_VARIANTS),
        "development_variants_are_official_cases": False,
        "independent_validation": False,
        "final_authority": False,
        "Fresh_is_ex_post_only": True,
        "physical_parameter_changes": 0,
        "MESS_reoptimization_calls": 0,
        "continuous_parameters_tuned_on_Apr04": 0,
    }
