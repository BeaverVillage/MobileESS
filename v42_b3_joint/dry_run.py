"""Small 96-slot synthetic interfaces. Never use these as paper results."""
from dataclasses import replace
import json
from .contracts import (Authority, AIDCDecision, MESSDecision, Certificate,
                        PhysicalReceipt, StageResult, canonical, digest, require)
from .budget import MockNativeBudget


def fixture_authority(day="2025-05-23"):
    from datetime import date, timedelta
    preceding = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    hashes = {name: digest({"synthetic_only": name, "day": day}) for name in
              ("input_sha", "grid_sha", "pcc_mapping_sha", "physical_domain_sha", "forecast_sha", "runtime_sha", "source_sha")}
    return Authority(day=day, **hashes, planning_cutoff=preceding + "T18:00:00+09:00",
                     forecast_available_at=preceding + "T17:00:00+09:00",
                     pcc_ids=tuple("PCC" + str(i) for i in range(12)),
                     mess_ids=tuple("MESS" + str(i) for i in range(4)))


def zeros(rows, cols, value=0.0):
    return tuple(tuple(value for _ in range(cols)) for _ in range(rows))


def fixture_aidc(marker=1):
    return AIDCDecision(
        jobs_json=canonical({"known_job_actions": [{"synthetic_job": "J1", "slot": marker, "migration": marker % 2}],
                             "unknown_arrival_policy": {"interface": "v42_native.actual.unknown_arrival", "synthetic_only": True}}),
        it_power=zeros(12, 96, float(marker)), pcc_p=zeros(12, 96, float(marker)), pcc_q=zeros(12, 96),
        gpu_runtime_json=canonical({"gpu": {"synthetic_marker": marker}, "rack": {}, "wan": {}, "qos": {}, "runtime": {}}),
        variables_json=canonical({"synthetic_only": True, "schedule": marker, "migration": marker % 2}))


def fixture_mess(marker=1):
    return MESSDecision(routes=tuple(("STATION0", "STATION" + str(marker)) for _ in range(4)),
                        location=zeros(4, 96, "STATION" + str(marker)),
                        charge_p=zeros(4, 96, marker / 10), discharge_p=zeros(4, 96), q=zeros(4, 96, marker / 20),
                        soc=zeros(4, 97, 0.5), initial_final_json=canonical({"initial": [0.5] * 4, "final": [0.5] * 4}),
                        move_energy=zeros(4, 96, marker / 100),
                        variables_json=canonical({"movement": marker, "charge_mode": 1, "route": marker,
                                                  "P": marker / 10, "Q": marker / 20, "SOC": 0.5, "synthetic_only": True}))


def make_result(request, budget, aidc, mess):
    require(isinstance(budget, MockNativeBudget) and budget.stage == request.stage, "MOCK_STAGE_BUDGET_REQUIRED")
    budget.bind(request)
    decision_sha = digest({"aidc": aidc.to_dict() if aidc else None, "mess": mess.to_dict() if mess else None})
    # These numbers exercise 0.5% versus 3% software acceptance only. There was
    # no optimization, original physics replay or independent scientific proof.
    lower = "199/200" if request.stage.startswith("A") else "97/100"
    verifier = digest({"synthetic_mock_verifier": "v1"})
    model_sha = digest({"synthetic_original_model": request.stage, "fixed_input_sha": request.fixed_input_sha})
    certificate = Certificate(request.stage, request.authority.sha, request.fixed_input_sha, decision_sha,
                              lower, "1", request.authority.physical_domain_sha, verifier, True, "MOCK",
                              original_model_sha=model_sha)
    physical = PhysicalReceipt(request.stage, request.authority.sha, request.fixed_input_sha, decision_sha,
                               digest({"synthetic_replay": decision_sha}), verifier, True, "MOCK", original_model_sha=model_sha)
    return StageResult(request.stage, request.authority, aidc, mess, certificate, physical,
                       budget.sealed_receipt(), request.fixed_input_sha)


class FakeBackend:
    def __init__(self, faults=None):
        self.calls = []
        faults = dict(faults or {})
        require(all(stage in ("A1", "M1", "A2", "M2") and value in
                    ("MISSING_LB", "P2", "MUTATE_AIDC", "MUTATE_MESS", "MISSING_PHYSICAL")
                    for stage, value in faults.items()), "BUILTIN_MOCK_FAULT_REQUIRED")
        self._faults_json = canonical(faults)

    def execute(self, request, budget):
        self.calls.append(request.stage)
        budget.bind(request)
        budget.record_non_native("MODEL_BUILD", 6000)  # Mock wall > 90 min is allowed.
        budget.simulate(2.0, kind="LP")
        budget.simulate(3.0, kind="PRICING")
        budget.simulate(4.0, kind="MILP")
        budget.record_non_native("CERTIFICATION", 1)
        if request.stage.startswith("A"):
            aidc = fixture_aidc(1 if request.stage == "A1" else 2)
            mess = request.fixed_mess
        else:
            aidc = request.fixed_aidc
            mess = fixture_mess(1 if request.stage == "M1" else 2)
        fault = json.loads(self._faults_json).get(request.stage)
        if fault == "MUTATE_AIDC":
            aidc = fixture_aidc(99)
        if fault == "MUTATE_MESS":
            mess = fixture_mess(99)
        result = make_result(request, budget, aidc, mess)
        if fault == "MISSING_LB":
            result = replace(result, certificate=replace(result.certificate, lower_bound=None))
        elif fault == "P2":
            result = replace(result, certificate=replace(result.certificate, p2_calls=1))
        elif fault == "MISSING_PHYSICAL":
            result = replace(result, physical=replace(result.physical, original_integer_physical_verified=False))
        return result


def dry_run():
    from .pipeline import MockPipeline
    result = MockPipeline().execute_mock(fixture_authority())
    return {"schema": "V42_B3_DRY_RUN_V1", "states": list(result.states),
            "mock_status": "MOCK_TEST_PASS", "synthetic_only": True,
            "real_native_optimize_calls": 0, "real_OpenDSS_calls": 0, "real_FULL_model_builds": 0,
            "simulated_native_runtime_by_stage": {b["stage"]: b["simulated_native_runtime"] for b in result.ledgers},
            "simulated_P2_calls": 0, "planning_sha": result.frozen.sha,
            "scientific_certified": False, "production_authorized": False}


if __name__ == "__main__":
    print(canonical(dry_run()))
