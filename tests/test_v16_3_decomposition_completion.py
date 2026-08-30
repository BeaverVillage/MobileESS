import json
from pathlib import Path

from dayahead.authority import sha256_file

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"dayahead/artifacts/v16_3_decomposition_completion"


def load(name):return json.loads((OUT/name).read_text(encoding="utf-8"))


def test_historical_final_science_is_byte_immutable():
    contract=load("V16_3_DECOMPOSITION_EXECUTOR_CONTRACT.json");final=ROOT/"dayahead/artifacts/v16_3_final"
    assert contract["final_science_manifest_sha256"]=="abe8dae43ed31c96b20a530421fa88a76d0a1e3a03dd7e4a9a7a9d4b1e980798"
    assert all(sha256_file(final/name)==digest for name,digest in contract["historical_final_artifact_sha256"].items())


def test_may02_exact_equivalence_passes():
    value=load("V16_3_MAY02_DECOMPOSITION_EQUIVALENCE.json")
    assert value["status"]=="PASS"
    assert max(value["relative_objective_difference"].values())<=1e-3
    assert value["same_hard_feasibility_status"]
    assert value["ORIGINAL_JUNE_BENCHMARK_STATUS"]=="NOT_TESTABLE_REFERENCE_CONSTRUCTION_INFEASIBLE"


def test_iteration_certificates_use_all_96_and_real_duals():
    for name in ("V16_3_MAY02_STANDARD_BD_COMPLETION.json","V16_3_MAY02_CL_MC_BD_COMPLETION.json"):
        value=load(name);assert value["status"]=="OPTIMAL_CERTIFIED" and value["LB_monotone"] and value["UB_nonincreasing"] and value["UB_only_from_all_96_feasible"]
        assert all(len(row["subproblem_statuses"])==96 and len(row["dual_sha256_by_slot"])==96 for row in value["iteration_log"])
        assert value["OpenDSS_calls_inside_Benders"]==0
        assert value["coefficient_identity"]["actual_Pi_nonzero_total"]>0


def test_frozen_supplementary_contract_has_all_41_days():
    value=load("V16_3_POSTHOC_SUPPLEMENTARY_DECOMPOSITION_CONTRACT.json")
    assert value["status"]=="FROZEN_AFTER_MAY02_EQUIVALENCE_BEFORE_ALL41_EXECUTION"
    assert len(value["days"])==41 and len(set(value["days"]))==41
    assert value["gamma_crit"]==.98 and value["scientific_authority_changes"]==0


def test_reference_coherence_forensic_rules_out_implementation_provenance_defects():
    value=load("V16_3_AIDC_REFERENCE_COHERENCE_FORENSIC.json")
    assert value["failure_day_count"]==13
    assert value["classification"]=="A_EXPECTED_CROSS_HEAD_FORECAST_INCOHERENCE"
    assert not value["provenance_defect_found"]
    assert all(row["G_RES_SYS_statistics"]["negative_slot_count"]>0 for row in value["per_day"])
    assert all(max(row["beta_scaling_identity"].values())<=1e-9 for row in value["per_day"])
    assert all(row["V3_reference_trace"]["nodeh_to_GPU_conversion_max_abs_error"]<=1e-9 for row in value["per_day"])


def test_critical_current_attribution_is_read_only_and_closes_component_identity():
    value=load("V16_3_CRITICAL_CUT_ATTRIBUTION_DIAGNOSTIC.json")
    assert value["common_feasible_day_count"]==21
    assert value["hypothesis_supported"]
    assert value["aggregate"]["AIDC_redistribution_nonzero_day_count"]==21
    assert value["aggregate"]["component_sum_identity_max_abs_error_pu"]<=1e-12
    assert value["aggregate"]["median_abs_Delta_I_crit_from_MESS_total_pu"]>value["aggregate"]["median_abs_Delta_I_crit_from_AIDC_pu"]
    assert value["counters"]["solver_calls"]==value["counters"]["OpenDSS_calls"]==0


def test_full_lp_farkas_logs_record_bound_aware_violation():
    standard=load("V16_3_MAY02_STANDARD_BD_COMPLETION.json")
    assert standard["farkas_cut_count"]>=1
    certificates=[certificate for row in standard["iteration_log"] for certificate in row["Farkas_certificates"]]
    assert certificates
    assert all(row["Gurobi_FarkasProof"]>0 and row["bound_aware_cut_violation"]>0 for row in certificates)
    assert all(row["cut_origin"]=="ACTUAL_GUROBI_FARKASDUAL_FULL_LP" for row in certificates)
