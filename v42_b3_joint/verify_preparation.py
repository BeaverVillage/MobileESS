"""Execute only this preparation's small, sequential stdlib software tests."""
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import ast
import hashlib
import importlib.abc
import importlib.util
import io
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "v42_b3_preparation_20261009"
BASE_SHA = "5ab907e384a5384f1505f851385f4953220f6634"


class PreparationImportFirewall(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.denied = []

    @staticmethod
    def forbidden(fullname):
        top = fullname.split(".")[0]
        return (top in {"gurobipy", "win32com", "pythoncom", "opendssdirect", "dss", "pydss",
                        "pyomo", "pulp", "cvxpy", "scipy", "numpy"}
                or top.startswith("v42_") and top != "v42_b3_joint")

    def find_spec(self, fullname, path=None, target=None):
        if self.forbidden(fullname):
            self.denied.append(fullname)
            raise ImportError("B3_PREPARATION_FORBIDDEN_IMPORT:" + fullname)
        return None


def write_json(name, value):
    destination = DOCS / name
    if not destination.resolve().is_relative_to(DOCS.resolve()):
        raise ValueError("B3_REPORT_OUTPUT_ESCAPE")
    destination.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def handoff_schema():
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    def array(item, count):
        return {"type": "array", "minItems": count, "maxItems": count, "items": item}
    def matrix(rows, cols, strings=False):
        return array(array({"type": "string", "minLength": 1} if strings else {"type": "number"}, cols), rows)
    def obj(properties):
        return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}
    nullable = lambda ref: {"anyOf": [{"$ref": ref}, {"type": "null"}]}
    authority = obj({**{key: sha for key in ("input_sha", "grid_sha", "pcc_mapping_sha", "physical_domain_sha", "forecast_sha", "runtime_sha", "source_sha")},
                     "day": {"type": "string", "format": "date"},
                     "planning_cutoff": {"type": "string", "format": "date-time"},
                     "forecast_available_at": {"type": "string", "format": "date-time"},
                     "pcc_ids": dict(array({"type": "string", "minLength": 1}, 12), uniqueItems=True),
                     "mess_ids": dict(array({"type": "string", "minLength": 1}, 4), uniqueItems=True),
                     "slots": {"const": list(range(96))}, "actual_observations_used": {"const": False}})
    aidc = obj({**{key: {"type": "string", "contentMediaType": "application/json"} for key in
                    ("jobs_json", "gpu_runtime_json", "variables_json")},
                **{key: matrix(12, 96) for key in ("it_power", "pcc_p", "pcc_q")}})
    mess = obj({"routes": array({"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}, 4),
                "location": matrix(4, 96, True), **{key: matrix(4, 96) for key in ("charge_p", "discharge_p", "q", "move_energy")},
                "soc": matrix(4, 97), **{key: {"type": "string", "contentMediaType": "application/json"} for key in ("initial_final_json", "variables_json")}})
    stage = {"enum": ["A1", "M1", "A2", "M2"]}
    common = {"stage": stage, **{key: sha for key in ("authority_sha", "fixed_input_sha", "decision_sha", "verifier_source_sha", "original_model_sha")},
              "evidence_kind": {"const": "MOCK"}}
    cert = obj({**common, "lower_bound": {"type": "string", "minLength": 1}, "upper_bound": {"type": "string", "minLength": 1},
                "global_domain_sha": sha, "original_global_bound_verified": {"const": True},
                "bound_scope": {"const": "STAGE_FIXED_INPUT_GLOBAL"}, "objective": {"const": "min rho_max"}, "p2_calls": {"const": 0}})
    physical = obj({**common, "replay_sha": sha, "original_integer_physical_verified": {"const": True}})
    warm = obj({"authority_sha": sha, "fixed_aidc_sha": sha, "mess": {"$ref": "#/$defs/mess"},
                "eligible": {"type": "boolean"}, "feasibility_verified": {"type": "boolean"}, "reason": {"type": "string", "minLength": 1}})
    request = obj({"stage": stage, "authority": {"$ref": "#/$defs/authority"},
                   "fixed_aidc": nullable("#/$defs/aidc"), "fixed_mess": nullable("#/$defs/mess"), "warm_start": nullable("#/$defs/warm")})
    result = obj({"stage": stage, "authority": {"$ref": "#/$defs/authority"},
                  "aidc": {"$ref": "#/$defs/aidc"}, "mess": nullable("#/$defs/mess"),
                  "certificate": {"$ref": "#/$defs/certificate"}, "physical": {"$ref": "#/$defs/physical"},
                  "native_receipt": {"type": "string", "contentMediaType": "application/json"}, "fixed_input_sha": sha})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:v42:b3:handoff:preparation:v1", "title": "B3 sealed request/result software contract",
            "$comment": "Schema shape validation is necessary only. Python verifies exact gaps, causal KST cutoff, SHA chain, whole frozen decisions, stage order and ledgers. MOCK never certifies science. Source units/mapping/full row coverage require original verifiers.",
            "$defs": {"authority": authority, "aidc": aidc, "mess": mess, "warm": warm, "certificate": cert,
                      "physical": physical, "request": request, "result": result},
            **obj({"request": {"$ref": "#/$defs/request"}, "result": {"$ref": "#/$defs/result"}})}


def verification():
    expected = Path("D:/MobileESS_v42_B3_prep").resolve()
    if ROOT != expected:
        raise PermissionError("VERIFICATION_WRITES_REQUIRE_B3_WORKTREE")
    firewall = PreparationImportFirewall()
    if any(firewall.forbidden(name) for name in sys.modules):
        raise PermissionError("FORBIDDEN_MODULE_ALREADY_LOADED")
    start = perf_counter()
    sys.meta_path.insert(0, firewall)
    try:
        from .adapters import SOURCE_APIS, inspect_source_links, prepare_source_binding
        from .contracts import canonical
        from .dry_run import fixture_authority
        from .pipeline import MockPipeline
        from .policy import STAGES, parameters
        from .readiness import readiness
        from .schema import validate_schema_packet
        files = sorted((ROOT / "v42_b3_joint").glob("*.py")) + [ROOT / "tests/test_v42_b3_joint.py"]
        for path in files:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        source_checks = inspect_source_links()
        schema = handoff_schema()
        spec = importlib.util.spec_from_file_location("b3_preparation_tests", ROOT / "tests/test_v42_b3_joint.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        stream = io.StringIO()
        with ExitStack() as gates:
            gates.enter_context(patch("subprocess.Popen", side_effect=PermissionError("B3_TEST_PROCESS_START_FORBIDDEN")))
            gates.enter_context(patch("os.system", side_effect=PermissionError("B3_TEST_SHELL_START_FORBIDDEN")))
            result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        print(stream.getvalue().strip())
        if not result.wasSuccessful():
            raise RuntimeError("B3_MOCK_TEST_FAILED")
        mock = MockPipeline().execute_mock(fixture_authority())
        schema_count = 0
        for request, stage_result in zip(mock.requests, mock.results):
            packet = json.loads(canonical({"request": asdict(request), "result": asdict(stage_result)}))
            validate_schema_packet(schema, packet)
            schema_count += 1
        DOCS.mkdir(parents=True, exist_ok=True)
        report = {"schema": "V42_B3_NATIVE_ZERO_VERIFICATION_V1", "status": "MOCK_TEST_PASS",
                  "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "test_scope": "ONLY tests/test_v42_b3_joint.py; one process sequential stdlib unittest",
                  "elapsed_wall_seconds": perf_counter() - start, "ast_files_passed": len(files),
                  "static_source_api_signatures_passed": len(source_checks),
                  "json_schema_status": "STATIC_CONTRACT_PASS" if schema_count == 4 else "NOT_RUN",
                  "json_schema_validator_scope": "ONLY_EMITTED_SCHEMA_SUBSET_STDLIB_FAIL_CLOSED",
                  "general_draft_2020_12_validator": False,
                  "json_schema_fixture_packets_passed": schema_count,
                  "real_native_optimize_calls": 0, "real_OpenDSS_calls": 0, "real_FULL_model_builds": 0,
                  "real_physical_domain_builds": 0, "real_pricing_calls": 0, "Gurobi_license_sessions_opened": 0,
                  "native_source_imports": 0, "production_entrypoints_called": 0,
                  "import_firewall_denials": firewall.denied,
                  "simulated_native_runtime_by_stage": {r["stage"]: r["simulated_native_runtime"] for r in mock.ledgers},
                  "simulated_P2_calls": 0, "scientific_certified": False,
                  "evidence_basis": "B3 imports contain no real solver/source execution; native/COM imports blocked; tests cannot start processes; guarded production entries inspected via AST only.",
                  "limits": ["No actual original model/row equivalence tested", "No actual integer/physical replay", "No real Global LB/UB proof", "No actual Runtime/Peak RSS", "No Actual/Fresh AC"]}
        write_json("B3_STAGE_HANDOFF_CONTRACT.json", schema)
        write_json("B3_P1_ONLY_POLICY.json", {"schema": "V42_B3_P1_ONLY_POLICY_V1", "stage_order": list(STAGES),
                    "stage_policy": {stage: parameters(stage) for stage in STAGES[:4]},
                    "objective": "min rho_max", "P2_calls": 0, "acceptance_scope": "STAGE_FIXED_INPUT_GLOBAL",
                    "joint_global_optimality_claim": False, "legacy_unified_acceptance_reused": False,
                    "B3_NATIVE_EXECUTION_AUTHORIZED": False, "B3_PRODUCTION_CAMPAIGN_STARTED": False, "B3_FRESH_AC_EXECUTED": False})
        write_json("B3_NATIVE_ZERO_VERIFICATION.json", report)
        write_json("B3_SOURCE_BINDING_STATIC_VERIFICATION.json", {"schema": "V42_B3_SOURCE_BINDING_STATIC_VERIFICATION_V1",
                    "source_apis": list(source_checks), "stage_bindings": [prepare_source_binding(r).to_dict() for r in mock.requests],
                    "source_imports": 0, "source_invocations": 0, "scientific_certified": False})
        write_json("B3_IMPLEMENTATION_STATUS.json", {**readiness(), "base_git_sha": BASE_SHA,
                    "worktree": str(ROOT), "branch": "codex/v42-b3-preparation",
                    "states": ["CODE_IMPLEMENTED", "STATIC_CONTRACT_PASS", "MOCK_TEST_PASS", "REAL_MODEL_EQUIVALENCE_NOT_RUN",
                               "NATIVE_OPTIMIZATION_NOT_RUN", "ACTUAL_FRESH_AC_NOT_RUN", "PRODUCTION_NOT_AUTHORIZED"],
                    "lightweight_tests_run": result.testsRun, "lightweight_tests_passed": result.wasSuccessful(),
                    "actual_A2_source_builder": "NOT_IMPLEMENTED_FIXED_MESS_ORIGINAL_GRID_MATERIALIZER_BRIDGE",
                    "actual_M2_source_builder": "NOT_IMPLEMENTED_EXPLICIT_STAGE_AND_A2_ORIGINAL_BUNDLE_BRIDGE",
                    "native_ledger_bridge": "MOCK_POLICY_IMPLEMENTED_REAL_SOURCE_LEDGER_BRIDGE_NOT_IMPLEMENTED",
                    "actual_fresh_ac_bridge": "STATIC_ORIGINAL_API_LINKS_ONLY_REAL_PHYSICAL_ADAPTER_NOT_IMPLEMENTED",
                    "counts": {"native_optimize": 0, "OpenDSS": 0, "FULL_model_build": 0}})
        original_files = sorted({api.file for api in SOURCE_APIS})
        source_files = [path.relative_to(ROOT).as_posix() for path in files]
        source_files += original_files
        write_json("B3_SOURCE_SHA_MANIFEST.json", {"schema": "V42_B3_SOURCE_SHA_MANIFEST_V1", "base_git_sha": BASE_SHA,
                    "hash_algorithm": "SHA256", "files": [{"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                        "role": "B3_IMPLEMENTATION_OR_TEST" if path.startswith(("v42_b3_joint/", "tests/")) else "BASE_ORIGINAL_SOURCE_NOT_MODIFIED"} for path in source_files],
                    "active_B1_B2_sha_evidence": "B3_RESOURCE_ISOLATION_AUDIT.json",
                    "actual_original_input_data_loaded": False, "historical_bounds_or_runtime_reused": False,
                    "self_hash_excluded": True})
        print(json.dumps({"tests": result.testsRun, "static_apis": len(source_checks), "schema_packets": schema_count,
                          "native_calls": 0, "OpenDSS_calls": 0, "FULL_builds": 0, "production_authorized": False}))
        return report
    finally:
        sys.meta_path.remove(firewall)


if __name__ == "__main__":
    verification()
