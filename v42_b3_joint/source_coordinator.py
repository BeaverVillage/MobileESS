"""Sequential source execution with independently verified persistent resume."""
from dataclasses import asdict
from fractions import Fraction
import json
import math
from pathlib import Path

from .contracts import (AIDCDecision, MESSDecision, StageRequest, canonical,
                        digest, require, require_sha, request_from_dict)
from .native_ledger import SourceStageLedger
from .policy import gap_target
from .source_runtime import SourceStageOutput, jsonable

ORDER = ("A1", "M1", "A2", "M2")


def output_document(output):
    return json.loads(canonical(jsonable(asdict(output))))


def output_from_document(document):
    value = dict(document)
    value["request"] = request_from_dict(value["request"])
    value["aidc"] = AIDCDecision(**value["aidc"])
    value["mess"] = MESSDecision(**value["mess"]) if value["mess"] else None
    return SourceStageOutput(**value)


def verify_output(context, output, bridge, ledger):
    """Re-run source verifiers; producer PASS flags never admit a handoff."""
    registry, request = context.source_registry, context.request
    registry.admit(context, "COORDINATOR_INDEPENDENT_ACCEPTANCE")
    require(isinstance(output, SourceStageOutput) and output.request == request,
            "SOURCE_COORDINATOR_REQUEST_DRIFT")
    require(output.evidence_kind == registry.evidence_kind, "FAKE_SOURCE_REAL_PROMOTION_FORBIDDEN")
    before = output.sha
    if request.fixed_aidc is not None:
        require(output.aidc == request.fixed_aidc, "FULL_FIXED_AIDC_DRIFT")
    if request.stage == "A1":
        require(output.mess is None, "A1_MESS_OPTIMIZATION_OFF")
    if request.fixed_mess is not None:
        require(output.mess == request.fixed_mess, "FULL_FIXED_MESS_DRIFT")
    if request.stage.startswith("M"):
        require(isinstance(output.mess, MESSDecision), "M_FULL_MESS_DECISION_REQUIRED")
    receipt = json.loads(output.ledger_receipt)
    actual = ledger.receipt()
    require(receipt == actual, "SOURCE_LEDGER_RECEIPT_CHANGED_OR_RESET")
    require(receipt.get("evidence_kind") == registry.evidence_kind
            and receipt.get("stage") == request.stage
            and receipt.get("request_sha") == request.request_sha
            and receipt.get("fixed_input_sha") == request.fixed_input_sha
            and receipt.get("source_sha") == request.authority.source_sha
            and receipt.get("authority_sha") == request.authority.sha,
            "SOURCE_LEDGER_SCIENTIFIC_IDENTITY_DRIFT")
    require(receipt.get("quarantined") is False and receipt.get("P2_calls") == 0
            and receipt.get("Threads") == 1 and receipt.get("native_limit_seconds") == 5400
            and receipt.get("wall_limit_seconds") is None
            and type(receipt.get("measured_native_runtime")) in (int, float)
            and math.isfinite(receipt["measured_native_runtime"])
            and 0 <= receipt["measured_native_runtime"] <= 5400,
            "SOURCE_LEDGER_NOT_ACCEPTED")
    proof = bridge.verify(context, output)
    require(proof.get("PASS") is True and proof.get("evidence_kind") == registry.evidence_kind
            and proof.get("original_model_sha") == output.model_sha, "SOURCE_REPLAY_FAILED")
    for key, claimed in (("physical", output.physical_evidence), ("global", output.global_evidence)):
        evidence = proof.get(key)
        require(isinstance(evidence, dict) and evidence == claimed,
                "INDEPENDENT_SOURCE_EVIDENCE_DRIFT:" + key)
        require(all(evidence.get(name) == value for name, value in output.identity.items()),
                "SOURCE_PROOF_IDENTITY_DRIFT:" + key)
        require_sha(evidence.get("verifier_source_sha"))
    physical, bounds = proof["physical"], proof["global"]
    require(physical.get("original_integer_physical_verified") is True,
            "ORIGINAL_INTEGER_PHYSICAL_REPLAY_REQUIRED")
    require_sha(physical.get("replay_sha"))
    require(bounds.get("original_global_bound_verified") is True
            and bounds.get("bound_scope") == "STAGE_FIXED_INPUT_GLOBAL"
            and bounds.get("global_domain_sha") == request.authority.physical_domain_sha
            and bounds.get("joint_global_optimality_claim") is False,
            "INDEPENDENT_STAGE_GLOBAL_SCOPE_REQUIRED")
    lower, upper = Fraction(bounds["exact_LB"]), Fraction(bounds["exact_UB"])
    require(0 <= lower <= upper and (upper == 0 or (upper - lower) / upper <= gap_target(request.stage)),
            "EXACT_SOURCE_GLOBAL_GAP_NOT_ACCEPTED")
    require(output.sha == before, "SOURCE_VERIFIER_MUTATED_OUTPUT")
    return proof


class SourceCoordinator:
    def __init__(self, root, context_factory, a_bridge, m_bridge, *, ledger_factory=SourceStageLedger,
                 a1_bridge=None):
        self.root = Path(root).resolve()
        self.context_factory, self.a_bridge, self.m_bridge = context_factory, a_bridge, m_bridge
        self.ledger_factory = ledger_factory
        self.a1_bridge = a1_bridge or a_bridge
        self.contexts, self.outputs, self.ledgers = {}, {}, {}

    def _save(self, path, value):
        require(path.resolve().is_relative_to(self.root), "COORDINATOR_PATH_ESCAPE")
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(canonical(value) + "\n", encoding="utf-8")
        from v42_pr134_b1.common import replace_file
        replace_file(temporary, path)

    def run(self, authority, *, operations_factory=None, realized_inputs=None, actual_backend=None, progress=None):
        request = StageRequest("A1", authority)
        first = self.context_factory(request, {}, self.root / "A1")
        first.source_registry.admit(first, "COORDINATOR")  # Before any write or original import.
        require(first.output == self.root / "A1", "COORDINATOR_CONTEXT_OUTPUT_DRIFT")
        identity = {"schema": "B3_SOURCE_COORDINATOR_V1", "authority_sha": authority.sha,
                    "source_sha": authority.source_sha, "day": authority.day, "run_id": first.run_id,
                    "evidence_kind": first.source_registry.evidence_kind, "stage_order": list(ORDER)}
        state_path = self.root / "B3_SOURCE_CHECKPOINT.json"
        if self.root.exists():
            require(state_path.exists(), "PARTIAL_SOURCE_COORDINATOR_QUARANTINE")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            require(state["identity"] == identity, "SOURCE_COORDINATOR_RESTART_IDENTITY_DRIFT")
            require(state["inflight"] is None and state["status"] not in ("QUARANTINED", "FAILED"),
                    "INTERRUPTED_SOURCE_STAGE_QUARANTINE")
            require(state["completed"] == list(ORDER[:len(state["completed"])]),
                    "SOURCE_COORDINATOR_PREFIX_REQUIRED")
        else:
            self.root.mkdir(parents=True, exist_ok=False)
            state = {"identity": identity, "completed": [], "inflight": None, "status": "READY",
                     "result_shas": {}, "planning_sha": None}
            self._save(state_path, state)
        packets, requests, outputs = {}, [], []
        try:
            for stage in ORDER:
                if stage == "M1":
                    request = StageRequest(stage, authority, fixed_aidc=outputs[0].aidc)
                    packets = {"fixed_aidc": output_document(outputs[0])["source_packet"]}
                elif stage == "A2":
                    request = StageRequest(stage, authority, fixed_mess=outputs[1].mess)
                    packets = {"fixed_mess": output_document(outputs[1])["source_packet"],
                               "a1": output_document(outputs[0])["source_packet"]}
                elif stage == "M2":
                    request = StageRequest(stage, authority, fixed_aidc=outputs[2].aidc)
                    packets = {"fixed_aidc": output_document(outputs[2])["source_packet"],
                               "warm_mess": output_document(outputs[1])["source_packet"]}
                context = self.context_factory(request, packets, self.root / stage)
                require(context.output == self.root / stage and context.run_id == first.run_id
                        and context.source_registry is first.source_registry
                        and context.input_folder == first.input_folder
                        and context.original_bundle_json == first.original_bundle_json
                        and context.grid_authority is first.grid_authority, "SOURCE_COORDINATOR_CONTEXT_DRIFT")
                bridge = self.a1_bridge if stage == "A1" else self.a_bridge if stage.startswith("A") else self.m_bridge
                completed = stage in state["completed"]
                result_path = context.output / "B3_SOURCE_STAGE_OUTPUT.json"
                if not completed:
                    require(not context.output.exists(), "UNCOMPLETED_SOURCE_OUTPUT_QUARANTINE")
                    state.update(inflight=stage, status="RUNNING")
                    self._save(state_path, state)
                    if progress:
                        progress({"stage": stage, "phase": stage + "_SOURCE_ADMISSION"})
                ledger = self.ledger_factory(context)
                if completed:
                    require(result_path.exists(), "COMPLETED_SOURCE_RESULT_MISSING")
                    output = output_from_document(json.loads(result_path.read_text(encoding="utf-8")))
                    require(output.sha == state["result_shas"][stage], "SOURCE_RESULT_PERSISTENCE_SHA_DRIFT")
                else:
                    stage_progress = (lambda value, current=stage: progress(dict(value, stage=current))) if progress else None
                    output = bridge.execute(context, ledger, stage_progress)
                verify_output(context, output, bridge, ledger)
                if not completed:
                    require(not result_path.exists(), "SOURCE_RESULT_EXCLUSIVE_PUBLICATION_REQUIRED")
                    with result_path.open("x", encoding="utf-8") as stream:
                        stream.write(canonical(output_document(output)) + "\n")
                    state["completed"].append(stage)
                    state["result_shas"][stage] = output.sha
                    state.update(inflight=None, status="STAGES_COMPLETE" if stage == "M2" else "READY")
                    self._save(state_path, state)
                requests.append(request); outputs.append(output)
                self.contexts[stage], self.outputs[stage], self.ledgers[stage] = context, output, ledger
            result = {"requests": requests, "outputs": outputs, "status": "STAGES_COMPLETE",
                      "evidence_kind": first.source_registry.evidence_kind}
            if operations_factory is not None:
                operations = operations_factory(self.contexts["M2"])
                def validator(req, out):
                    bridge = self.a1_bridge if req.stage == "A1" else self.a_bridge if req.stage.startswith("A") else self.m_bridge
                    return verify_output(self.contexts[req.stage], out, bridge, self.ledgers[req.stage])
                if state["planning_sha"]:
                    frozen = operations.load_freeze(verify_stage=validator, requests=requests, outputs=outputs)
                    require(frozen.sha == state["planning_sha"], "SOURCE_PLANNING_RESTART_SHA_DRIFT")
                else:
                    state.update(inflight="PLANNING_FREEZE", status="RUNNING")
                    self._save(state_path, state)
                    if progress:
                        progress({"stage": "PLANNING_FREEZE", "phase": "PLANNING_FREEZE"})
                    frozen = operations.freeze(requests, outputs, verify_stage=validator)
                    state.update(inflight=None, status="PLANNING_COMPLETE", planning_sha=frozen.sha)
                    self._save(state_path, state)
                result.update(frozen=frozen, status="PLANNING_COMPLETE")
                if state["status"] == "COMPLETE":
                    actual = json.loads((self.root / "B3_SOURCE_ACTUAL_RESULT.json").read_text(encoding="utf-8"))
                    require(digest(actual) == state["actual_result_sha"], "SOURCE_ACTUAL_RESULT_RESTART_SHA_DRIFT")
                    validation = operations.validate_actual(frozen, actual)
                    require(digest(validation) == state["validation_sha"], "SOURCE_VALIDATION_RESTART_SHA_DRIFT")
                    result.update(actual=actual, validation=validation, status="COMPLETE")
                elif realized_inputs is not None:
                    state.update(inflight="ACTUAL_FRESH_AC", status="RUNNING")
                    self._save(state_path, state)
                    if progress:
                        progress({"stage": "ACTUAL", "phase": "ACTUAL_FRESH_AC"})
                    inputs = realized_inputs(operations, frozen) if callable(realized_inputs) else realized_inputs
                    actual = operations.actual(frozen, inputs, backend=actual_backend)
                    self._save(self.root / "B3_SOURCE_ACTUAL_RESULT.json", jsonable(actual))
                    state.update(inflight="VALIDATION")
                    self._save(state_path, state)
                    if progress:
                        progress({"stage": "VALIDATION", "phase": "VALIDATION"})
                    validator(requests[3], outputs[3])
                    validation = operations.validate_actual(frozen, actual)
                    self._save(self.root / "B3_SOURCE_VALIDATION.json", jsonable(validation))
                    state.update(inflight=None, status="COMPLETE", actual_result_sha=digest(jsonable(actual)),
                                 validation_sha=digest(jsonable(validation)))
                    self._save(state_path, state)
                    result.update(actual=actual, validation=validation, status="COMPLETE")
            return result
        except Exception as error:
            state.update(status="QUARANTINED", reason=type(error).__name__ + ":" + str(error))
            self._save(state_path, state)
            raise

    @staticmethod
    def campaign(authorities, coordinator_factory, **kwargs):
        results = []
        seen = set()
        for authority in authorities:
            require(authority.day not in seen, "CAMPAIGN_DUPLICATE_DAY_FORBIDDEN")
            seen.add(authority.day)
            results.append(coordinator_factory(authority).run(authority, **kwargs))
        return results
