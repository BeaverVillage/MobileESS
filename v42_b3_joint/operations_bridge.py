"""Source-backed A2/M2 freeze, immutable Actual and original Fresh AC bridge.

No engine or source module is imported at module import time. Production
admission precedes resolution and output creation. Another feeder can inject
its source-authorized ActualBackend without changing the native replay API.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .contracts import canonical, digest, require
from .source_runtime import jsonable

SOURCE_COMPANIONS = ("SOURCE/PLANNING_PHYSICAL.npz", "SOURCE/PLANNING_MESS.npz",
    "PLANNING/V42_DAYAHEAD_DECISION_FREEZE.json")


def _companion_receipt(output, relative):
    root = Path(output).resolve()
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and path.is_file(), "SOURCE_COMPANION_FILE_REQUIRED:" + relative)
    with path.open("rb") as stream:
        raw_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=relative, bytes=path.stat().st_size, sha256=raw_sha)


def _verify_companions(output, document):
    receipts = document.get("companion_receipts")
    require(isinstance(receipts, dict) and set(receipts) == set(SOURCE_COMPANIONS),
        "SOURCE_COMPANION_RECEIPT_SCHEMA_REQUIRED")
    for relative in SOURCE_COMPANIONS:
        require(receipts[relative] == _companion_receipt(output, relative),
            "SOURCE_COMPANION_BYTES_OR_SHA_DRIFT:" + relative)


def _verify_source_record(output, record, relative):
    require(isinstance(record, dict) and set(record) == {"path", "bytes", "sha256"},
        "SOURCE_SAVED_ARTIFACT_RECORD_REQUIRED:" + relative)
    raw = _companion_receipt(output, relative)
    require(Path(record["path"]).resolve() == (Path(output).resolve() / relative).resolve()
        and record["sha256"] == raw["sha256"] and record["bytes"] == raw["bytes"],
        "SOURCE_SAVED_ARTIFACT_PATH_OR_RAW_SHA_DRIFT:" + relative)


def _verify_completed_source_records(output, physical, ac):
    _verify_source_record(output, physical["aidc_state"].get("source_receipt_record"),
        "ACTUAL/ACTUAL_FIXED_REPLAY_RECEIPT.json")
    if ac is not None:
        require(isinstance(ac, dict), "SOURCE_FRESH_SAVED_RECEIPT_REQUIRED")
        for key, relative in (("receipt", "FRESH/FRESH_RESULT.json"),
                ("control_log", "FRESH/RAW_CONTROL_LOG.json"),
                ("physical_input_log", "FRESH/RAW_PHYSICAL_INPUT_LOG.json")):
            _verify_source_record(output, ac.get(key), relative)


def _slots(rows):
    return [list(row) for row in zip(*rows)]


def _native_digest(value):
    # Original v42_native.contracts.digest canonicalization (including ASCII
    # escaping) is preserved for the original Actual/Fresh identity boundary.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()


def _require_expected_aidc_state(expected, provided):
    require(jsonable(provided) == expected, "ACTUAL_SOURCE_AIDC_STATE_DRIFT")


def _source_aidc_state(expected, receipt, source_record):
    """Bind reconstructed workload state to the unchanged source Actual policy."""
    require(isinstance(receipt, dict) and receipt.get("PASS") is True
        and receipt.get("policy") == "V39E_FROZEN_DA_FIXED_REPLAY"
        and receipt.get("Actual_reoptimization") == 0
        and receipt.get("local_PQ_repair") == 0 and receipt.get("global_PQ_repair") == 0,
        "ORIGINAL_ACTUAL_AIDC_STATE_AUTHORITY_REQUIRED")
    require(receipt.get("Actual_workload_semantics") ==
        "fixed accepted Planning power/service trajectory; no rescheduling from retrospective outcomes",
        "ORIGINAL_ACTUAL_AIDC_WORKLOAD_SEMANTICS_DRIFT")
    require(isinstance(source_record, dict) and isinstance(source_record.get("sha256"), str)
        and len(source_record["sha256"]) == 64, "ORIGINAL_ACTUAL_AIDC_RECEIPT_SHA_REQUIRED")
    return dict(expected, interface="v42_pr134_b1.replay.actual", source_receipt=receipt,
        source_receipt_record=source_record,
        original_workload_semantics=receipt.get("Actual_workload_semantics"),
        caller_workload_state_used_as_source_authority=False)


@dataclass(frozen=True)
class SourcePlanningFreeze:
    native_freeze: object
    document_json: str
    output: Path
    evidence_kind: str

    @property
    def document(self):
        return json.loads(self.document_json)

    @property
    def sha(self):
        return digest(self.document)

    def verify(self):
        self.native_freeze.verify()
        require(self.document["schema"] == "B3_SOURCE_PLANNING_FREEZE_V1",
            "SOURCE_FREEZE_SCHEMA_REQUIRED")
        require(self.document["native_plan_sha"] == self.native_freeze.plan_sha,
            "SOURCE_NATIVE_FREEZE_SHA_DRIFT")
        require(self.document["evidence_kind"] == self.evidence_kind,
            "SOURCE_FREEZE_EVIDENCE_DRIFT")
        require(self.document["joint_global_optimality_claim"] is False,
            "B3_JOINT_GLOBAL_PROOF_FORBIDDEN")
        plan = self.native_freeze.plan
        require(all(self.document[key] == plan["B3_" + key]
            for key in ("authority_sha", "aidc_sha", "mess_sha", "stage_result_shas", "original_model_shas",
                "companion_receipts")),
            "SOURCE_FREEZE_NATIVE_COMPONENT_OR_PROOF_DRIFT")
        _verify_companions(self.output, self.document)
        return True


class SourceOperationsBridge:
    def __init__(self, context):
        self.context = context
        self.registry = context.source_registry

    def authorize(self, value=None, action=None, **kwargs):
        # Source APIs accept day strings, identity dictionaries or native plans.
        day = value.get("day", self.context.request.authority.day) if isinstance(value, dict) else value
        require(day is None or day == self.context.request.authority.day,
            "B3_OPERATIONS_DATE_DRIFT")
        require(action in ("PLANNING_FREEZE", "ACTUAL", "FRESH_AC"),
            "B3_OPERATIONS_ACTION_REQUIRED")
        self.registry.admit(self.context, action)
        return self.context.request.authority.day

    def _operation(self, symbol, **routing):
        imports = dict(routing.pop("import_replacements", {}), authorize=self.authorize)
        body=self.registry.rebind("v42_may_campaign_native90.operations", symbol,
            import_replacements=imports, **routing)
        from v42_svr11.authority import active
        if active() is not None:
            from v42_svr11.operations import wrapped
            if not hasattr(self,'_svr11_events'):self._svr11_events={}
            return wrapped(symbol,body,self._svr11_events)
        return body

    def _request(self):
        return dict(run_id=self.context.run_id, day=self.context.request.authority.day,
            arm="B3", input_folder=str(self.context.input_folder),
            root=str(Path(self.context.output).resolve()), output=str(Path(self.context.output).resolve()))

    def expected_aidc_state(self, frozen):
        """Source fixed-replay descriptor available before any Actual execution."""
        frozen.verify()
        require(frozen.document["authority_sha"] == self.context.request.authority.sha,
            "SOURCE_ACTUAL_FROZEN_AUTHORITY_DRIFT")
        plan = frozen.native_freeze.plan
        return jsonable(dict(source_semantics="V39E_FROZEN_DA_FIXED_REPLAY",
            aidc_decision_sha=frozen.document["aidc_sha"], aidc_schedule=plan["aidc_schedule"],
            known_job_actions=plan["known_job_actions"], unknown_arrival_policy=plan["unknown_arrival_policy"]))

    def freeze(self, requests, outputs, *, verify_stage):
        self.registry.admit(self.context, "PLANNING_FREEZE")
        self.context.verify_identity()
        require(callable(verify_stage), "INDEPENDENT_SOURCE_STAGE_VALIDATOR_REQUIRED")
        require(len(requests) == len(outputs) == 4, "ALL_FOUR_SOURCE_STAGE_RESULTS_REQUIRED")
        require(tuple(r.stage for r in requests) == ("A1", "M1", "A2", "M2"),
            "SOURCE_FREEZE_STAGE_ORDER")
        authority = self.context.request.authority
        for request, output in zip(requests, outputs):
            require(request.authority == authority and output.request == request,
                "SOURCE_FREEZE_AUTHORITY_OR_REQUEST_DRIFT")
            require(output.evidence_kind == self.registry.evidence_kind,
                "FAKE_SOURCE_RECEIPT_REAL_PROMOTION_FORBIDDEN")
            verify_stage(request, output)
        a1, m1, a2, m2 = outputs
        require(requests[1].fixed_aidc == a1.aidc and requests[2].fixed_mess == m1.mess
            and requests[3].fixed_aidc == a2.aidc, "SOURCE_FREEZE_FIXED_CHAIN_DRIFT")
        require(a2.mess == m1.mess and m2.aidc == a2.aidc,
            "SOURCE_FREEZE_FINAL_FIXED_DECISION_DRIFT")
        aidc, mess = a2.aidc, m2.mess
        planning = jsonable(a2.source_packet["planning_arrays"])
        mess_plan = jsonable(m2.source_packet["mess_plan"])
        expected = dict(PCC_P_kw=_slots(aidc.pcc_p), PCC_Q_kvar=_slots(aidc.pcc_q),
            IT_kw=_slots(aidc.it_power))
        require(all(planning.get(key) == value for key, value in expected.items()),
            "SOURCE_A2_PLANNING_ARRAYS_DRIFT")
        require(planning.get("sites") == list(authority.pcc_ids), "SOURCE_FREEZE_PCC_AXIS_DRIFT")
        require(isinstance(planning.get("GPU"), list) and len(planning["GPU"]) == 96
            and all(isinstance(row, list) and len(row) == len(authority.pcc_ids)
                for row in planning["GPU"]), "SOURCE_FREEZE_GPU_AXIS_REQUIRED")
        require(mess_plan.get("locations") == _slots(mess.location)
            and mess_plan.get("unit_ids") == list(authority.mess_ids)
            and mess_plan.get("Q_kvar") == _slots(mess.q)
            and mess_plan.get("SOC_kwh") == _slots(mess.soc),
            "SOURCE_M2_MESS_ARRAYS_DRIFT")
        jobs = json.loads(aidc.jobs_json)
        variables = json.loads(mess.variables_json)
        require(jsonable(a2.source_packet["selected_jobs"]) == jobs["known_job_actions"],
            "SOURCE_A2_SELECTED_JOB_DRIFT")
        unknown = jobs["unknown_arrival_policy"]
        require(isinstance(unknown, dict) and unknown.get("interface") == "v42_native.actual.unknown_arrival",
            "SOURCE_CAUSAL_POLICY_REQUIRED")
        stage_proofs = [dict(output.identity, result_sha=output.sha,
            source_global_evidence=jsonable(output.global_evidence),
            source_physical_evidence=jsonable(output.physical_evidence)) for output in outputs]
        plan = dict(day=authority.day, arm="B3", stage="M2",
            aidc_schedule=jsonable(a2.source_packet.get("aidc_schedule", jobs)),
            known_job_actions=jobs["known_job_actions"], unknown_arrival_policy=unknown,
            mess_route={"routes": jsonable(mess.routes), "source_routes": mess_plan["routes"]},
            movement=variables["movement"], charge_mode=variables["charge_mode"],
            P={"Pch_kw": _slots(mess.charge_p), "Pdis_kw": _slots(mess.discharge_p),
               "source_P_kw": mess_plan["P_kw"], "move_energy_kwh": _slots(mess.move_energy)},
            Q={"Q_kvar": _slots(mess.q)}, SOC={"SOC_kwh": _slots(mess.soc),
                "initial_final": json.loads(mess.initial_final_json)},
            aidc_electrical_footprint=planning,
            grid_anchor={"grid_sha": authority.grid_sha, "pcc_mapping_sha": authority.pcc_mapping_sha},
            input_authority_hashes=dict(workload=authority.input_sha, placement=aidc.sha,
                runtime=authority.runtime_sha, MESS_PQ=mess.sha, forecast=authority.forecast_sha,
                physical_domain=authority.physical_domain_sha, producer=authority.source_sha),
            source_stage_proofs=stage_proofs, source_stage_order=["A1", "M1", "A2", "M2"],
            AIDC_source_stage="A2", MESS_source_stage="M2", joint_global_optimality_claim=False)
        plan.update(B3_authority_sha=authority.sha, B3_aidc_sha=aidc.sha, B3_mess_sha=mess.sha,
            B3_stage_result_shas=[output.sha for output in outputs],
            B3_original_model_shas=[output.model_sha for output in outputs])
        accepted_source = a2.source_packet.get("accepted_source", a2.source_result.get("freeze"))
        require(isinstance(accepted_source, dict), "SOURCE_A2_ACCEPTED_FILE_RECEIPT_REQUIRED")
        output_root = Path(self.context.output) / "OPERATIONS"
        require(not output_root.exists(), "SOURCE_OPERATIONS_PARTIAL_OR_COMPLETED_NEVER_OVERWRITTEN")
        folders = {key: output_root / key for key in ("SOURCE", "PLANNING", "ACTUAL", "ACTUAL_SOURCE", "FRESH")}
        with self.registry.execution_scope(self.context):
            native_freeze = self.registry.rebind("v42_native.planning", "freeze_day_ahead_plan",
                import_replacements={"require_action_authorized": self.authorize})
            for folder in folders.values():
                folder.mkdir(parents=True, exist_ok=False)
            # Preserve the original source replay schema and equations. This is
            # only materialization of independently validated A2/M2 arrays.
            np = self.registry.resolve("v42_may_campaign_native90.operations").np
            np.savez_compressed(folders["SOURCE"] / "PLANNING_PHYSICAL.npz", **planning)
            mess_arrays = {key: value for key, value in mess_plan.items()
                if key in ("P_kw", "Q_kvar", "locations", "unit_ids", "SOC_kwh")}
            np.savez_compressed(folders["SOURCE"] / "PLANNING_MESS.npz", **mess_arrays)
            accepted = dict(PASS=True, accepted=True, day=authority.day, arm="B3",
                selected_jobs=jobs["known_job_actions"], source_receipt=accepted_source)
            (folders["SOURCE"] / "ACCEPTED_STAGE_RECEIPT.json").write_text(
                canonical({"A2": a2.identity, "M2": m2.identity, "stage_proofs": stage_proofs}) + "\n", encoding="utf-8")
            self._operation("freeze_planning")(self._request(), accepted, mess_plan, folders["PLANNING"])
            companions = {relative: _companion_receipt(output_root, relative)
                for relative in SOURCE_COMPANIONS}
            # Bind consumed source bytes inside the immutable native plan too,
            # so editing the outer B3 receipt cannot relabel a companion file.
            plan["B3_companion_receipts"] = companions
            native = native_freeze(plan, folders["PLANNING"] / "NATIVE", grid_sha=authority.grid_sha)
        document = dict(schema="B3_SOURCE_PLANNING_FREEZE_V1", native_plan_sha=native.plan_sha,
            authority_sha=authority.sha, aidc_sha=aidc.sha, mess_sha=mess.sha,
            stage_result_shas=[output.sha for output in outputs],
            original_model_shas=[output.model_sha for output in outputs],
            output=str(output_root), evidence_kind=self.registry.evidence_kind,
            companion_receipts=companions,
            joint_global_optimality_claim=False)
        frozen = SourcePlanningFreeze(native, canonical(document), output_root, self.registry.evidence_kind)
        frozen.verify()
        (output_root / "B3_SOURCE_FREEZE.json").write_text(canonical(document) + "\n", encoding="utf-8")
        return frozen

    def actual(self, frozen, realized_inputs, *, backend=None):
        self.registry.admit(self.context, "ACTUAL")
        frozen.verify()
        require(frozen.document["authority_sha"] == self.context.request.authority.sha,
            "SOURCE_ACTUAL_FROZEN_AUTHORITY_DRIFT")
        require(frozen.evidence_kind == self.registry.evidence_kind,
            "FAKE_FREEZE_REAL_ACTUAL_PROMOTION_FORBIDDEN")
        if backend is None and self.registry.evidence_kind == "SOURCE":
            _require_expected_aidc_state(self.expected_aidc_state(frozen), realized_inputs.get("aidc_state"))
        physical_backend = backend or OriginalOperationsBackend(self, frozen)
        require(physical_backend.authority_sha == self.context.request.authority.grid_sha,
            "ACTUAL_BACKEND_GRID_AUTHORITY_DRIFT")
        with self.registry.execution_scope(self.context):
            source_actual = self.registry.rebind("v42_native.actual", "run_dday_actual",
                import_replacements={"require_action_authorized": self.authorize})
            result = source_actual(frozen.native_freeze, realized_inputs, physical_backend,
                frozen.output / "NATIVE_ACTUAL", local_p_repair=False,
                local_q_repair=False, full_reoptimization=False)
        return dict(result=result, evidence_kind=self.registry.evidence_kind,
            frozen_sha=frozen.sha, source_api="v42_native.actual.run_dday_actual",
            scientific_certified=self.registry.evidence_kind == "SOURCE" and result.get("PASS") is True)

    def load_freeze(self, verify_stage, requests, outputs):
        """Independently re-admit completed stages and the immutable source freeze."""
        self.registry.admit(self.context, "PLANNING_FREEZE")
        self.context.verify_identity()
        require(callable(verify_stage) and len(requests) == len(outputs) == 4,
            "SOURCE_RESTART_ALL_FOUR_VERIFIERS_REQUIRED")
        require(tuple(request.stage for request in requests) == ("A1", "M1", "A2", "M2"),
            "SOURCE_RESTART_STAGE_ORDER_DRIFT")
        for request, output in zip(requests, outputs):
            require(output.request == request and request.authority == self.context.request.authority
                and output.evidence_kind == self.registry.evidence_kind,
                "SOURCE_RESTART_STAGE_IDENTITY_DRIFT")
            verify_stage(request, output)
        a1, m1, a2, m2 = outputs
        require(requests[1].fixed_aidc == a1.aidc and requests[2].fixed_mess == m1.mess
            and requests[3].fixed_aidc == a2.aidc and a2.mess == m1.mess and m2.aidc == a2.aidc,
            "SOURCE_RESTART_FIXED_CHAIN_DRIFT")
        output_root = Path(self.context.output) / "OPERATIONS"
        document = json.loads((output_root / "B3_SOURCE_FREEZE.json").read_text(encoding="utf-8-sig"))
        require(document["stage_result_shas"] == [output.sha for output in outputs]
            and document["original_model_shas"] == [output.model_sha for output in outputs]
            and document["aidc_sha"] == a2.aidc.sha and document["mess_sha"] == m2.mess.sha
            and Path(document["output"]).resolve() == output_root.resolve(),
            "SOURCE_RESTART_FREEZE_COMPONENT_DRIFT")
        with self.registry.execution_scope(self.context):
            load = self.registry.callable("v42_native/planning.py", "FrozenDayAheadPlan.load")
            native = load(output_root / "PLANNING" / "NATIVE" / "DAYAHEAD_PLANNING_FREEZE.json")
        frozen = SourcePlanningFreeze(native, canonical(document), output_root, self.registry.evidence_kind)
        frozen.verify()
        return frozen

    def validate_actual(self, frozen, actual):
        """Reload original immutable Actual/Fresh artifacts; never execute again."""
        self.registry.admit(self.context, "ACTUAL")
        frozen.verify()
        require(actual["frozen_sha"] == frozen.sha
            and actual["evidence_kind"] == self.registry.evidence_kind,
            "SOURCE_ACTUAL_VALIDATION_IDENTITY_DRIFT")
        folder = frozen.output / "NATIVE_ACTUAL"
        physical = json.loads((folder / "ACTUAL_PHYSICAL_ARRAYS.json").read_text(encoding="utf-8"))
        result = json.loads((folder / "DDAY_ACTUAL_RESULT.json").read_text(encoding="utf-8"))
        require(result == actual["result"] and result["physical_arrays_sha"] == _native_digest(physical)
            and physical["schedule"] == frozen.native_freeze.plan
            and result["DAYAHEAD_PLAN_SHA"] == frozen.native_freeze.plan_sha
            and result["GRID_SHA"] == frozen.native_freeze.grid_sha
            and result["POLICY_SHA"] == frozen.native_freeze.policy_sha,
            "SOURCE_ACTUAL_SAVED_PHYSICAL_OR_FROZEN_DECISION_DRIFT")
        require(result["fresh_ac_calls"] == 1 and result["global_MILP_calls"] == 0
            and result["local_p_repair"] is False and result["local_q_repair"] is False,
            "SOURCE_ACTUAL_EXECUTION_POLICY_DRIFT")
        ac = result["fresh_ac"]
        if self.registry.evidence_kind == "SOURCE":
            require(result["PASS"] is not True or isinstance(ac, dict),
                "SOURCE_FRESH_SAVED_RECEIPT_REQUIRED")
            _verify_completed_source_records(frozen.output, physical, ac)
        if result["PASS"] is True:
            with self.registry.execution_scope(self.context):
                self.registry.callable("v42_native/actual.py", "require_fresh_ac")(
                    ac, frozen.native_freeze.plan_sha, frozen.native_freeze.grid_sha)
            require(ac["physical_arrays_sha"] == result["physical_arrays_sha"]
                and ac["realized_inputs_sha"] == result["realized_inputs_sha"]
                and ac["policy_sha"] == frozen.native_freeze.policy_sha,
                "SOURCE_FRESH_AC_SAVED_IDENTITY_DRIFT")
        return {"stage": "VALIDATION", "PASS": result["PASS"],
                "evidence_kind": self.registry.evidence_kind,
                "scientific_certified": self.registry.evidence_kind == "SOURCE" and result["PASS"] is True,
                "actual_result_sha": digest(result), "frozen_sha": frozen.sha,
                "failure": result.get("failure"), "repeated_Fresh_calls": 0,
                "joint_global_optimality_claim": False}


class OriginalOperationsBackend:
    """Existing 96-slot Actual/Fresh backend with current B3 frozen arrays."""
    def __init__(self, bridge, frozen):
        self.bridge, self.frozen = bridge, frozen
        self.authority_sha = bridge.context.request.authority.grid_sha
        self.source_folder = None

    def reconstruct_physical(self, schedule, realized_inputs):
        from copy import deepcopy
        bridge = self.bridge
        bridge.registry.admit(bridge.context, "ACTUAL")
        self.frozen.verify()
        require(_native_digest(schedule) == self.frozen.native_freeze.plan_sha,
            "SOURCE_ACTUAL_SCHEDULE_MUTATION")
        request, output = bridge._request(), self.frozen.output
        aidc_state = deepcopy(realized_inputs["aidc_state"])
        if bridge.registry.evidence_kind == "SOURCE":
            _require_expected_aidc_state(bridge.expected_aidc_state(self.frozen), aidc_state)
        with bridge.registry.execution_scope(bridge.context):
            # The B2 branch creates source exogenous realizations; the same
            # original branch is required for B3. No data rule is changed.
            self.source_folder = bridge._operation("actual_sources",
                literal_replacements={"B2": "B3"})(request, output / "ACTUAL_SOURCE")
            result = bridge._operation("actual")(request, output / "PLANNING",
                output / "SOURCE", output / "ACTUAL")
            require(result.get("PASS") is True, "ORIGINAL_ACTUAL_FIXED_REPLAY_FAILED")
            if bridge.registry.evidence_kind == "SOURCE":
                # Column projection only: the unchanged Fresh source remains
                # the authority for background allocation and electrical math.
                import pandas as pd
                common = bridge.registry.resolve("v42_may_campaign_native90.common")
                resolver = bridge.registry.callable("v42_capacity/common.py", "resolve")
                provenance = common.read(Path(self.source_folder) / "SOURCE_PROVENANCE.json")
                frame = pd.read_parquet(resolver(provenance["daily_sources"]["aemo_actual.parquet"]))
                require(jsonable(realized_inputs["load"]) == frame.demand_mw.tolist()
                    and jsonable(realized_inputs["pv"]) == frame.rooftop_pv_mw.tolist(),
                    "ACTUAL_SOURCE_REALIZED_ARRAYS_DRIFT")
                # The original source materializes accepted fixed service/power
                # and does not reconstruct arbitrary caller workload state.
                # Record that source authority instead of echoing caller state.
                source_receipt_path = output / "ACTUAL" / "ACTUAL_FIXED_REPLAY_RECEIPT.json"
                require(source_receipt_path.is_file(), "ORIGINAL_ACTUAL_AIDC_RECEIPT_REQUIRED")
                aidc_state = _source_aidc_state(bridge.expected_aidc_state(self.frozen),
                    common.read(source_receipt_path), common.record(source_receipt_path))
        return dict(schedule=deepcopy(schedule), load=deepcopy(realized_inputs["load"]),
            pv=deepcopy(realized_inputs["pv"]), aidc_state=deepcopy(aidc_state),
            execution_controls=dict(local_p_repair=False, local_q_repair=False,
                full_reoptimization=False, global_MILP_calls=0))

    def fresh_ac(self, physical):
        bridge = self.bridge
        bridge.registry.admit(bridge.context, "FRESH_AC")
        self.frozen.verify()
        require(self.source_folder is not None, "ORIGINAL_ACTUAL_SOURCES_REQUIRED_BEFORE_FRESH")
        output = self.frozen.output
        with bridge.registry.execution_scope(bridge.context):
            result = bridge._operation("fresh")(bridge._request(), output / "PLANNING",
                output / "ACTUAL", self.source_folder, output / "FRESH")
        summary = result["summary"]
        # Actual exposures are recorded independently; Planning gap acceptance
        # does not turn physical violations into a Fresh AC PASS.
        return dict(result, engine="OpenDSS", fresh_run=True,
            synthetic=bridge.registry.evidence_kind != "SOURCE",
            schedule_sha=physical["schedule_sha"], grid_sha=physical["grid_sha"],
            policy_sha=physical["policy_sha"], physical_arrays_sha=_native_digest(physical),
            realized_inputs_sha=physical["realized_inputs_sha"], execution_layer="DDAY_ACTUAL",
            voltage_lower_pu=physical["voltage_lower_pu"], voltage_upper_pu=physical["voltage_upper_pu"],
            voltage_violations=summary.get("voltage_violations"),
            line_current_violations=summary.get("line_current_violations"),
            transformer_current_violations=summary.get("transformer_current_violations"),
            transformer_kVA_violations=summary.get("transformer_kVA_violations"),
            original_operations_source="v42_may_campaign_native90.operations.fresh")
