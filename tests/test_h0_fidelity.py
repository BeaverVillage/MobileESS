from pathlib import Path

import pytest

from pfr.h0_fidelity import (
    H0CandidateScore,
    H0FidelityError,
    audit_h0_candidate_fidelity,
)


def rows(reverse=False):
    result = []
    for state in ("s1", "s2"):
        result.extend(
            (
                H0CandidateScore(state, "reference", 0.8, 0.82, True),
                H0CandidateScore(state, "half", 0.7, 0.75),
                H0CandidateScore(
                    state,
                    "accepted",
                    0.6,
                    0.90 if reverse else 0.65,
                ),
            )
        )
    return result


def test_aligned_h0_gate_passes_direction_and_ranking():
    audit = audit_h0_candidate_fidelity(
        rows(),
        tie_tolerance=1e-4,
        minimum_states=2,
        minimum_sign_agreement=0.9,
        minimum_pairwise_concordance=0.8,
    )
    assert audit["status"] == "PASS"
    assert audit["sign_agreement"] == 1.0
    assert audit["pairwise_concordance"] == 1.0


def test_ranking_reversal_fails_gate():
    audit = audit_h0_candidate_fidelity(
        rows(reverse=True),
        tie_tolerance=1e-4,
        minimum_states=2,
        minimum_sign_agreement=0.9,
        minimum_pairwise_concordance=0.8,
    )
    assert audit["status"] == "FAIL"
    assert audit["sign_agreement"] < 0.9


def test_exactly_one_reference_is_required():
    with pytest.raises(H0FidelityError, match="one reference"):
        audit_h0_candidate_fidelity(
            [
                H0CandidateScore("s", "a", 0.1, 0.1),
                H0CandidateScore("s", "b", 0.2, 0.2),
            ],
            tie_tolerance=0.0,
            minimum_states=1,
            minimum_sign_agreement=0.0,
            minimum_pairwise_concordance=0.0,
        )


def test_full_period_runner_propagates_fixed_h0_sampling_interval():
    repo = Path(__file__).resolve().parents[1]
    runner = (
        repo / "pfr" / "tools" / "run_frozen_rep_week_daily_campaign.py"
    ).read_text(encoding="utf-8")
    wrapper = (
        repo / "pfr" / "tools" / "run_full_february_march_2025_local.sh"
    ).read_text(encoding="utf-8")

    assert '"--h0-fidelity-audit-every-steps"' in runner
    assert "str(args.h0_fidelity_audit_every_steps)" in runner
    assert "--h0-fidelity-audit-every-steps 12" in wrapper
    assert "--phase february" in wrapper
