"""Lossless axes/DTO mapping at the original source API boundary.

These functions transpose existing arrays and preserve source state. They do
not reconstruct electrical powers, routes, job options or battery equations.
"""
from dataclasses import asdict, is_dataclass
import json

from .contracts import AIDCDecision, canonical, digest, require, require_sha
from .source_runtime import jsonable


def transpose_slots(values, rows, *, slots=96, name="SOURCE_ARRAY"):
    values = jsonable(values)
    require(isinstance(values, list) and len(values) == slots and
            all(isinstance(row, list) and len(row) == rows for row in values), name + "_AXIS_DRIFT")
    return tuple(tuple(values[t][i] for t in range(slots)) for i in range(rows))


def verify_planning_arrays(arrays, decision, authority):
    require(tuple(arrays["sites"]) == authority.pcc_ids, "SOURCE_AIDC_PCC_ORDER_DRIFT")
    for key, expected in (("PCC_P_kw", decision.pcc_p), ("PCC_Q_kvar", decision.pcc_q),
                          ("IT_kw", decision.it_power)):
        require(transpose_slots(arrays[key], len(authority.pcc_ids), name=key) == expected,
                "SOURCE_AIDC_DTO_ARRAY_DRIFT:" + key)
    require(transpose_slots(arrays["GPU"], len(authority.pcc_ids), name="GPU") ==
            transpose_slots(json.loads(decision.gpu_runtime_json)["gpu"], len(authority.pcc_ids), name="GPU_STATE"),
            "SOURCE_AIDC_GPU_RUNTIME_DRIFT")
    return True


def aidc_from_source(context, arrays, replay, state):
    authority = context.request.authority
    require(tuple(arrays["sites"]) == authority.pcc_ids, "SOURCE_AIDC_PCC_ORDER_DRIFT")
    require(replay.get("PASS") is True and set(replay["selected_jobs"]) == set(state["data"][1]),
            "SOURCE_COMPLETE_SELECTED_JOB_REPLAY_REQUIRED")
    # The unknown arrivals policy is the existing source operational interface.
    # Its authority is bound to this day's causal forecast/runtime inputs.
    policy = {"interface": "v42_native.actual.unknown_arrival", "authority_sha": authority.sha,
              "forecast_sha": authority.forecast_sha, "runtime_sha": authority.runtime_sha}
    jobs = {"known_job_actions": jsonable(replay["selected_jobs"]), "unknown_arrival_policy": policy}
    resources = state["data"][3]
    resources = jsonable(asdict(resources) if is_dataclass(resources) else resources)
    globals_state = jsonable(replay["globals"])
    runtime = {name: value for name, value in globals_state.items()
               if name.startswith(("RT_", "CC4_", "CC4_reserve_timing"))}
    gpu_runtime = {"gpu": jsonable(arrays["GPU"]), "rack": resources,
                   "wan": {uid: jsonable(option["wan"]) for uid, option in replay["selected_jobs"].items()},
                   "qos": jsonable(state["data"][2]), "runtime": runtime}
    variables = {"selected_jobs": jsonable(replay["selected_jobs"]),
                 "controls": jsonable(replay["controls"]), "globals": globals_state,
                 "original_integer_types_restored": True, "source_stage": context.request.stage}
    decision = AIDCDecision(canonical(jobs),
        transpose_slots(arrays["IT_kw"], len(authority.pcc_ids), name="IT_kw"),
        transpose_slots(arrays["PCC_P_kw"], len(authority.pcc_ids), name="PCC_P_kw"),
        transpose_slots(arrays["PCC_Q_kvar"], len(authority.pcc_ids), name="PCC_Q_kvar"),
        canonical(gpu_runtime), canonical(variables))
    verify_planning_arrays(arrays, decision, authority)
    return decision


def verify_fixed_mess_packet(context, packet):
    decision = context.request.fixed_mess
    require(decision is not None and isinstance(packet, dict), "A2_FIXED_SOURCE_MESS_REQUIRED")
    require(packet.get("source_stage") == "M1" and packet.get("authority_sha") == context.request.authority.sha
            and packet.get("decision_sha") == decision.sha, "A2_FIXED_MESS_SOURCE_IDENTITY_DRIFT")
    require_sha(packet.get("original_model_sha"))
    proof = packet.get("physical_source_evidence", packet.get("physical_evidence", {}))
    require(proof.get("original_integer_physical_verified") is True or proof.get("PASS") is True,
            "A2_FIXED_MESS_ORIGINAL_SOURCE_REPLAY_REQUIRED")
    if context.source_registry.evidence_kind == "SOURCE":
        require(proof.get("PASS") is True and proof.get("original_integer_physical_verified") is True and
                proof.get("original_model_sha") == packet["original_model_sha"] and
                proof.get("authority_sha") == context.request.authority.sha,
                "A2_FIXED_MESS_VERIFIED_ORIGINAL_SOURCE_IDENTITY_REQUIRED")
    plan = packet["mess_plan"]
    require(tuple(plan["unit_ids"]) == context.request.authority.mess_ids, "A2_FIXED_MESS_UNIT_ORDER_DRIFT")
    for key, expected, slots in (("Pch_kw", decision.charge_p, 96), ("Pdis_kw", decision.discharge_p, 96),
                                ("Q_kvar", decision.q, 96), ("SOC_kwh", decision.soc, 97),
                                ("move_energy_kwh", decision.move_energy, 96),
                                ("locations", decision.location, 96)):
        require(transpose_slots(plan[key], len(decision.routes), slots=slots, name=key) == expected,
                "A2_FIXED_MESS_FULL_DTO_DRIFT:" + key)
    require(tuple(tuple(str(k) for k in plan["chosen_arcs"][unit]) for unit in plan["unit_ids"]) == decision.routes,
            "A2_FIXED_MESS_CHOSEN_ROUTE_DTO_DRIFT")
    variables = json.loads(decision.variables_json)
    require(jsonable(plan["routes"]) == variables["movement"] and jsonable(plan["values"]) == variables["original_values"],
            "A2_FIXED_MESS_FULL_SOURCE_STATE_DRIFT")
    require(jsonable(plan["charge_mode"]) == jsonable([list(x) for x in zip(*variables["charge_mode"])]),
            "A2_FIXED_MESS_CHARGE_MODE_DTO_DRIFT")
    require(digest(jsonable(packet["graph"])) == packet.get("graph_sha"), "A2_FIXED_MESS_GRAPH_SHA_DRIFT")
    return True
