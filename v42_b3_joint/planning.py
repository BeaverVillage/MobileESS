"""Mock final freeze and immutable Actual interfaces; OpenDSS is never called."""
from dataclasses import asdict, dataclass
import json
from .contracts import canonical, digest, require, require_sha, request_from_dict, result_from_dict
from .validation import verify_stage


@dataclass(frozen=True)
class FrozenPlan:
    canonical_json: str

    def __post_init__(self):
        self.verify()

    @property
    def document(self):
        return json.loads(self.canonical_json)

    @property
    def sha(self):
        return self.document["plan_sha"]

    @property
    def authority_sha(self):
        return self.document["plan"]["authority_sha"]

    @property
    def aidc_sha(self):
        return self.document["plan"]["aidc_sha"]

    @property
    def mess_sha(self):
        return self.document["plan"]["mess_sha"]

    def verify(self):
        doc = self.document
        require(set(doc) == {"schema", "plan", "plan_sha", "evidence_kind"} and doc["schema"] == "V42_B3_MOCK_FREEZE_V1",
                "B3_MOCK_FREEZE_SCHEMA_REQUIRED")
        require(doc["evidence_kind"] == "MOCK" and doc["plan_sha"] == digest(doc["plan"]), "FROZEN_PLAN_SHA_DRIFT")
        plan = doc["plan"]
        require(plan["authority_sha"] == digest(plan["authority"]) and plan["aidc_sha"] == digest(plan["aidc"])
                and plan["mess_sha"] == digest(plan["mess"]), "FINAL_COMPONENT_SHA_DRIFT")
        require(plan["stage_order"] == ["A1", "M1", "A2", "M2"], "ALL_FOUR_STAGE_ACCEPTANCES_REQUIRED")
        require(plan["AIDC_source_stage"] == "A2" and plan["MESS_source_stage"] == "M2", "FINAL_A2_M2_COMPONENTS_REQUIRED")
        require(plan["joint_global_optimality_claim"] is False, "JOINT_GLOBAL_CERTIFICATION_FORBIDDEN")
        records = plan["stage_records"]
        require(isinstance(records, list) and len(records) == 4 and digest(records) == plan["source_receipts_sha"], "FROZEN_STAGE_RECEIPTS_REQUIRED")
        requests = tuple(request_from_dict(row["request"]) for row in records)
        results = tuple(result_from_dict(row["result"]) for row in records)
        require(tuple(r.stage for r in requests) == tuple(r.stage for r in results) == ("A1", "M1", "A2", "M2"), "FROZEN_STAGE_ORDER_DRIFT")
        for request, result in zip(requests, results):
            require(request.authority.sha == plan["authority_sha"], "FROZEN_STAGE_AUTHORITY_DRIFT")
            verify_stage(request, result)
        require(requests[1].fixed_aidc == results[0].aidc and requests[2].fixed_mess == results[1].mess
                and requests[3].fixed_aidc == results[2].aidc, "FROZEN_STAGE_CHAIN_DRIFT")
        require(results[2].aidc.sha == plan["aidc_sha"] and results[3].mess.sha == plan["mess_sha"], "FROZEN_FINAL_SOURCE_DRIFT")
        for value in (plan["authority_sha"], plan["aidc_sha"], plan["mess_sha"], plan["source_receipts_sha"]):
            require_sha(value)
        return True


def freeze_mock_plan(requests, results):
    require(len(requests) == len(results) == 4, "ALL_FOUR_STAGE_ACCEPTANCES_REQUIRED")
    require(tuple(r.stage for r in requests) == tuple(r.stage for r in results) == ("A1", "M1", "A2", "M2"), "STAGE_ORDER_REQUIRED")
    authority = requests[0].authority
    for request, result in zip(requests, results):
        require(request.authority == authority, "FINAL_DATE_INPUT_MAPPING_AUTHORITY_DRIFT")
        verify_stage(request, result)
    a1, m1, a2, m2 = results
    require(requests[1].fixed_aidc == a1.aidc and requests[2].fixed_mess == m1.mess
            and requests[3].fixed_aidc == a2.aidc, "FINAL_HANDOFF_CHAIN_DRIFT")
    require(a2.mess == m1.mess and m2.aidc == a2.aidc, "FINAL_FIXED_COMPONENT_DRIFT")
    # Every original state (including full auxiliaries) stays in the seal. This
    # is a mock software freeze, never a production scientific acceptance.
    records = [{"request": asdict(request), "result": asdict(result)} for request, result in zip(requests, results)]
    plan = {"authority": authority.to_dict(), "authority_sha": authority.sha,
            "aidc": a2.aidc.to_dict(), "aidc_sha": a2.aidc.sha,
            "mess": m2.mess.to_dict(), "mess_sha": m2.mess.sha,
            "AIDC_source_stage": "A2", "MESS_source_stage": "M2",
            "stage_order": ["A1", "M1", "A2", "M2"],
            "source_receipts_sha": digest(records), "stage_records": records,
            "joint_global_optimality_claim": False}
    return FrozenPlan(canonical({"schema": "V42_B3_MOCK_FREEZE_V1", "plan": plan,
                                 "plan_sha": digest(plan), "evidence_kind": "MOCK"}))


def mock_actual(frozen, *, replay_plan=None, local_p_repair=False, local_q_repair=False, full_reoptimization=False):
    require(isinstance(frozen, FrozenPlan), "VERIFIED_B3_FREEZE_REQUIRED")
    frozen.verify()
    require(local_p_repair is False and local_q_repair is False and full_reoptimization is False, "ACTUAL_REPAIR_REOPTIMIZATION_FORBIDDEN")
    plan = frozen.document["plan"]
    replay = plan if replay_plan is None else replay_plan
    require(digest(replay) == frozen.sha, "ACTUAL_FROZEN_DECISIONS_CHANGED")
    return canonical({"stage": "ACTUAL", "evidence_kind": "MOCK", "plan_sha": frozen.sha,
                      "authority_sha": frozen.authority_sha, "aidc_sha": frozen.aidc_sha,
                      "mess_sha": frozen.mess_sha, "global_MILP_calls": 0,
                      "local_p_repair": False, "local_q_repair": False,
                      "full_reoptimization": False, "actual_physics_executed": False,
                      "status": "MOCK_INTERFACE_ONLY"})


def require_mock_actual(frozen, actual_json):
    actual = json.loads(actual_json)
    expected = json.loads(mock_actual(frozen))
    require(actual == expected, "ACTUAL_RECEIPT_OR_FROZEN_PLAN_DRIFT")
    return actual


def mock_fresh_ac(frozen, actual_json):
    require_mock_actual(frozen, actual_json)
    return canonical({"stage": "FRESH_AC", "evidence_kind": "MOCK", "plan_sha": frozen.sha,
                      "actual_sha": digest(json.loads(actual_json)), "OpenDSS_calls": 0,
                      "fresh_AC_executed": False, "status": "NOT_RUN_MOCK_INTERFACE_ONLY",
                      "source_api": "v42_native.actual.run_dday_actual -> ActualBackend.fresh_ac"})


def mock_validation(frozen, actual_json, fresh_json):
    require_mock_actual(frozen, actual_json)
    require(json.loads(fresh_json) == json.loads(mock_fresh_ac(frozen, actual_json)), "FRESH_RECEIPT_DRIFT")
    return canonical({"stage": "VALIDATION", "evidence_kind": "MOCK", "plan_sha": frozen.sha,
                      "static_contract_status": "STATIC_CONTRACT_PASS", "mock_status": "MOCK_TEST_PASS",
                      "scientific_certified": False, "actual_fresh_ac_status": "ACTUAL_FRESH_AC_NOT_RUN"})
