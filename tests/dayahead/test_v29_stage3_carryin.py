import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "dayahead/artifacts/v29_grid_responsive_aidc"


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_carryin_authority_gate_is_causal_and_ready():
    value = load("V29_CARRYIN_AUTHORITY_DECISION.json")
    assert value["RESULT_CLASSIFICATION"] == "V29_CARRYIN_AUTHORITY_READY"
    assert value["CARRYIN_QUEUE_STATE_OBSERVABLE"] is True
    assert value["CARRYIN_SERVICE_MASS_CAUSAL"] is True
    assert value["CARRYIN_STRICT_FULLNODE_ADMISSION_CAUSAL"] is True
    assert value["PRE_DAY_QUEUE_BRIDGE_READY"] is True
    assert value["APRIL_FIT_ROWS"] == 0
    assert value["POST_CUTOFF_ACTUAL_FEATURE_COUNT"] == 0
    assert value["CARRYIN_AUTHORITY_READY"] is True
    assert value["running_job_preemption"] is False
    assert value["synthetic_deadline_count"] == 0


def test_field_observability_prohibits_ex_post_admission_features():
    audit = load("V29_CUTOFF_FIELD_OBSERVABILITY_AUDIT.json")
    fields = {row["field"]: row for row in audit["fields"]}
    for name in ("partition", "nodes_req", "gpus_requested", "wallclock_req", "submit_time"):
        assert fields[name]["classification"] == "CUTOFF_OBSERVABLE"
        assert fields[name]["used_by_V29_DA"] is True
    for name in ("state_simple", "wallclock_used", "gpu_nodes_occupied", "nodelist", "shared_job_count", "nodes_shared", "jobs_shared"):
        assert fields[name]["classification"] == "POST_CUTOFF_EX_POST_ONLY"
        assert fields[name]["used_by_V29_DA"] is False
    assert fields["start_time"]["classification"] == "RECONSTRUCTED_PAST_STATE"
    assert audit["Day_Ahead_prohibited_field_use_count"] == 0


def test_bridge_and_cohort_mass_conservation():
    decision = load("V29_CARRYIN_AUTHORITY_DECISION.json")
    by_day = {row["day"]: row for row in decision["days"]}
    with (ROOT / "V29_CARRYIN_BY_DAY_COHORT.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for day, summary in by_day.items():
        selected = [row for row in rows if row["day"] == day]
        cutoff = sum(float(row["cutoff_known_queue_nodeh"]) for row in selected)
        served = sum(float(row["bridge_service_nodeh"]) for row in selected)
        carry = sum(float(row["D_day_carryin_nodeh"]) for row in selected)
        assert abs(cutoff - served - carry) <= 1e-9
        assert abs(cutoff - summary["cutoff_known_queue_nodeh"]) <= 1e-9
        assert abs(served - summary["bridge_service_nodeh"]) <= 1e-9
        assert abs(carry - summary["D_day_carryin_nodeh"]) <= 1e-9
        assert summary["post_cutoff_new_arrival_count_in_bridge"] == 0
    assert by_day["2025-04-03"]["D_day_carryin_nodeh"] == 216.0
    assert by_day["2025-04-04"]["D_day_carryin_nodeh"] == 1020.0


def test_source_provenance_opens_all_members_only_for_state_reconstruction():
    provenance = load("V29_CARRYIN_SOURCE_PROVENANCE.json")
    assert provenance["status"] == "PASS"
    assert provenance["all_archive_month_members_opened"] is True
    assert provenance["source_sha256"] == "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
    assert any("month=9" in name and "year=2025" in name for name in provenance["archive_members_opened"])
    assert all(row["future_runtime_feature_count"] == 0 for row in provenance["days"])
    assert all(row["final_state_feature_count"] == 0 for row in provenance["days"])
    assert all(row["allocated_node_feature_count"] == 0 for row in provenance["days"])
    assert all(row["sharing_indicator_feature_count"] == 0 for row in provenance["days"])


def test_pre_day_bridge_is_not_an_extended_optimization_horizon():
    bridge = load("V29_PRE_DAY_QUEUE_BRIDGE_CONTRACT.json")
    assert bridge["optimization_horizon_extended"] is False
    assert bridge["bridge_slots"] == 24
    assert bridge["grid_signal_reads"] == bridge["MESS_signal_reads"] == 0
    assert bridge["post_cutoff_actual_arrivals"] == 0
    assert bridge["future_actual_runtime_reads"] == 0
