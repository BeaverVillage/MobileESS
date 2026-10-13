"""Isolated small common-core validation; synthetic inputs are labeled fixtures.

Default invocation builds/readbacks models without Optimize. --run explicitly
enters the production coordinator's A1/M1/A2/M2 calls under the durable shared
budget. No historical campaign, monitor, or scientific outcome is replaced.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from .a_engine import ACase, PlanningGridContext, authorized_data, digest
from .actual import JobRequest, FrozenPowerModel
from .budget import IntegrationBudget
from .coordinator import IntegrationCase, run_arm
from .m_engine import (PathGraph, direct_joint, pin_pools, IncumbentBank,
                       _native_joint, file_record, vector_sha, _write)
from .qos import TrainingStatistics, QoSWindowProvider, ObservedJob, CausalReferenceScheduler
from v42_capacity.actual import Environment
from v42_final.workload import ForecastBook


class _Move:
    def __init__(self, source, depart, destination, connect):
        self.source, self.depart, self.destination, self.connect = source, depart, destination, connect
        self.energy_kwh = .01

    def validate(self, horizon):
        if not 0 <= self.depart < self.connect <= horizon:
            raise ValueError("FIXTURE_MOVE_CHRONOLOGY")


def miniature_m(folder, aidc_anchor, *, arm="B3", stage="M1", aidc_peak=.2, qos_sha="fixture-qos"):
    """Four-vehicle, four-slot FULL fixture with explicit mode and SOC rows."""
    units = ["MESS%02d" % u for u in range(1, 5)]
    arcs = [(site, t, site, t+1, None) for site in ("A", "B") for t in range(4)]
    arcs += [("A", 0, "B", 1, _Move("A", 0, "B", 1)),
             ("B", 2, "A", 3, _Move("B", 2, "A", 3))]
    names = ["rho_max"]
    for unit in units:
        names += [f"arc[{unit},{k}]" for k in range(len(arcs))]
        names += [f"node_activity[{unit},{site},{t}]" for site in ("A", "B") for t in range(5)]
        names += [f"{family}[{unit},{t}]" for family in ("charge_mode", "Pch", "Pdis", "Q") for t in range(4)]
        names += [f"SOC[{unit},{t}]" for t in range(5)]
    index = {name: j for j, name in enumerate(names)}
    n = len(names)
    lower, upper, objective = np.zeros(n), np.ones(n), np.zeros(n)
    types = np.array(["B" if name.startswith(("arc[", "node_activity[", "charge_mode[")) else "C" for name in names])
    upper[0], objective[0] = 1., 1.
    for name, j in index.items():
        if name.startswith("SOC["):
            upper[j] = 10.
        elif name.startswith("Q["):
            lower[j] = -1.
    rows, rhs, senses, rownames = [], [], [], []
    def row(name, terms, sense, value):
        rows.append(terms); rhs.append(value); senses.append(sense); rownames.append(name)
    for unit in units:
        for site in ("A", "B"):
            for t in range(4):
                terms = {}
                for k, arc in enumerate(arcs):
                    j = index[f"arc[{unit},{k}]"]
                    if arc[:2] == (site, t): terms[j] = terms.get(j, 0.) + 1.
                    if arc[2:4] == (site, t): terms[j] = terms.get(j, 0.) - 1.
                row(f"flow[{unit},{site},{t}]", terms, "=", 1. if (site, t) == ("A", 0) else 0.)
        for site in ("A", "B"):
            for t in range(5):
                terms = {index[f"node_activity[{unit},{site},{t}]"]: 1.}
                for k, arc in enumerate(arcs):
                    if (arc[:2] if t < 4 else arc[2:4]) == (site, t):
                        terms[index[f"arc[{unit},{k}]"]] = -1.
                row(f"node[{unit},{site},{t}]", terms, "=", 0.)
        row(f"initial_SOC[{unit}]", {index[f"SOC[{unit},0]"]: 1.}, "=", 5.)
        row(f"terminal_SOC[{unit}]", {index[f"SOC[{unit},4]"]: 1.}, "=", 5.)
        for t in range(4):
            mode = index[f"charge_mode[{unit},{t}]"]
            ch, dis = index[f"Pch[{unit},{t}]"], index[f"Pdis[{unit},{t}]"]
            row(f"charge_mode_ch[{unit},{t}]", {ch: 1., mode: -1.}, "<", 0.)
            row(f"charge_mode_dis[{unit},{t}]", {dis: 1., mode: 1.}, "<", 1.)
            terms = {index[f"SOC[{unit},{t+1}]"]: 1., index[f"SOC[{unit},{t}]"]: -1., ch: -.25*.9, dis: .25/.9}
            for k, arc in enumerate(arcs):
                if arc[-1] is not None and arc[1] == t:
                    terms[index[f"arc[{unit},{k}]"]] = arc[-1].energy_kwh
            row(f"SOC_balance[{unit},{t}]", terms, "=", 0.)
    row("fixture_thermal_peak", {0: -1., index["arc[MESS03,0]"]: .2}, "<", -.4-float(aidc_peak)/100.)
    rr, cc, values = [], [], []
    for i, terms in enumerate(rows):
        for j, value in terms.items():
            if value: rr.append(i); cc.append(j); values.append(value)
    A = sparse.csr_matrix((values, (rr, cc)), shape=(len(rows), n))
    d = dict(names=np.array(names), lower=lower, upper=upper, types=types, objective=objective,
             constant=np.array(0.), rhs=np.array(rhs), sense=np.array(senses), row_names=np.array(rownames))
    battery = SimpleNamespace(initial=5., terminal=5., minimum=0., maximum=10., dt_hours=.25,
                              eta_charge=.9, eta_discharge=.9, p_limit=1.)
    identity = dict(arm=arm, stage=stage, aidc_anchor=aidc_anchor, qos_sha=qos_sha,
                    physical_contract_sha="FIXTURE_FOUR_SLOT_SOC_MODE_GANG")
    case = SimpleNamespace(A=A, d=d, original_A=A, original_d=d,
        graph=(["A", "B"], {u: "A" for u in units}, arcs, battery, {}), lift=lambda x: x.copy(),
        case_sha=digest(dict(identity=identity, aidc_peak=aidc_peak)), bundle={"day": "2025-05-01"},
        output=Path(folder), identity=identity, mess_stage_budget_seconds=5.)
    point = np.zeros(n)
    point[0] = .6+float(aidc_peak)/100.
    for unit in units:
        for k in range(4): point[index[f"arc[{unit},{k}]"]] = 1.
        for t in range(5):
            point[index[f"node_activity[{unit},A,{t}]"]] = 1.
            point[index[f"SOC[{unit},{t}]"]] = 5.
    case.strict_validator = fixture_full_validator
    def cold_initializer(current, budget, validator):
        return point.copy(), None, [dict(kind="FIXTURE_ANALYTIC_STAY", optimizer_calls=0,
                                       real_cold_search_performance="NOT_ESTABLISHED")]
    case.cold_initializer = cold_initializer
    graph = PathGraph(case)
    case.candidate_pools = {u: [graph.complete(u), graph.complete(u, [8, 9])] for u in units}
    def exporter(current, x):
        graph = PathGraph(current)
        routes = graph.paths(x)
        # The source fixture has four physical slots. The fixed day anchor
        # extends it by explicit STAY/zero P/Q controls and constant terminal
        # SOC; this is fixture data, not a full96 Source18r result.
        p, q = {s: [0.]*96 for s in ("A", "B")}, {s: [0.]*96 for s in ("A", "B")}
        for unit in units:
            for t in range(4):
                site = next((s for s in ("A", "B") if x[index[f"node_activity[{unit},{s},{t}]"]] == 1.), None)
                if site is not None:
                    p[site][t] += float(x[index[f"Pch[{unit},{t}]"]] - x[index[f"Pdis[{unit},{t}]"]])
                    q[site][t] += float(x[index[f"Q[{unit},{t}]"]])
        plan = dict(routes=routes, P_by_site=p, Q_by_site=q,
            SOC={u: [float(x[index[f"SOC[{u},{t}]"]]) for t in range(5)]+[5.]*92 for u in units},
            Mode={u: [int(x[index[f"charge_mode[{u},{t}]"]]) for t in range(4)]+[0]*92 for u in units},
            source="EXPLICIT_SYNTHETIC_FOUR_SLOT_FULL_FIXTURE", physical_fixture_slots=4,
            extension="DECLARED_STAY_ZERO_PQ_CONSTANT_TERMINAL_SOC")
        return dict(plan, plan_sha=digest(plan))
    case.plan_exporter = exporter
    return case, point


def fixture_full_validator(case, path, evidence=None):
    from v42_m1_research.check_ub import matrix_replay
    with np.load(path, allow_pickle=False) as packet:
        if packet.files != ["point"]: raise ValueError("FIXTURE_RAW_POINT_AXIS")
        point = packet["point"].copy()
    replay = matrix_replay(case.original_A, case.original_d, point)
    if not replay["PASS"] or not replay["integer_pattern_exact"]:
        raise ValueError("FIXTURE_FULL_ORIGINAL_ROW_REPLAY_FAIL")
    return dict(PASS=True, Global_UB=float(point[0]), exact_Global_UB=str(Fraction(float(point[0]))),
        point_vector_sha256=vector_sha(point), evidence_kind="SYNTHETIC_FIXTURE",
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=dict(PASS=True, case_sha=case.case_sha,
            fixture_physical_slots=4, real_96_slot_physical_replay=False))


def build_fixture(folder):
    from v42_job_capability import Job, Resources, ServiceBoundary
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    caps = {"A": 2, "B": 2}
    train = [dict(uid=str(i), submit_seconds=100000., start_seconds=104500., end_seconds=105400.,
        observed_at_seconds=110000., request_provenance="SUBMISSION_VERSION_VERIFIED", qos="normal",
        protected=False, partition="fixture-gpu", gpu=1, requested_walltime_seconds=3600) for i in range(100)]
    statistics = TrainingStatistics.from_records(train, source_sha="FIXTURE_ONLY_TRAIN")
    provider = QoSWindowProvider(statistics, case_sha="fixture-integration", provider_sha="fixture-runtime")
    starts = tuple(range(0, 14401, 900))
    jobs, bounds, receipts, window = {}, {}, {}, {}
    requests = []
    for uid in ("known-a", "known-b"):
        observed = ObservedJob(uid, 0, 0, 0, 900, batch_eligible=True, partition="fixture-gpu",
            representation_starts_seconds=starts, provider_sha="fixture-runtime", reference_sha="fixture-shadow")
        receipts[uid] = provider.issue(observed)
        window[uid] = tuple(24+int(t/900) for t in receipts[uid].allowed_starts_seconds)
        jobs[uid] = Job(uid, "PENDING", 24, 24, 24, "A", 1, 1, initial_sites=("A", "B"),
                        checkpoint_authorized=False, duration_authority="EXPLICIT_SYNTHETIC_FIXTURE")
        bounds[uid] = ServiceBoundary("FIXTURE_REPRESENTATION", True, True, (24,), 132)
        requests.append(JobRequest(uid, 0, 1, ("A", "B"), 900, "A",
            dict(partition="fixture-gpu", batch_eligible=True, representation_starts_seconds=starts,
                 origin_unknown=False, can_prestart_place=True)))
    requests.append(JobRequest("unknown-observed", 900, 1, ("A", "B"), 900, "A",
        dict(partition="fixture-gpu", batch_eligible=True, representation_starts_seconds=starts,
             origin_unknown=True, can_prestart_place=True)))
    resources = Resources(caps, {"A": (2,), "B": (2,)}, {}, {}, 120, 1, {}, {}, {},
                          restart_slots=1, max_active_transfers=1)
    bundle = dict(day="2025-05-01", issue_time="2025-04-30T18:00:00+10:00", capacities=caps,
        C0_Q50=[.5]+[0.]*23, C0_Q90=[.5]+[0.]*23, runtime_reserve_gamma=0.,
        runtime_survival_kernel=[1.], evidence_kind="SYNTHETIC_FIXTURE")
    raw = {u: dict(GPU_gang=1, planning_site="A", reference_end=25,
             risk_nominal_completion_issue_slot=25, duration_authority="EXPLICIT_SYNTHETIC_FIXTURE") for u in jobs}
    data = (bundle, jobs, bounds, resources, raw, {}, {}, {"classes": {"initial": list(jobs)}})
    controls = ("aidc_load_kw[A]", "aidc_load_kw[B]", "mess_p_kw[A]", "mess_q_kvar[A]", "mess_p_kw[B]", "mess_q_kvar[B]")
    coefficients = tuple(SimpleNamespace(slot=t, coefficient_sha256=digest(dict(slot=t, fixture=True)),
        control_names=controls, branch_names=("LINE.FIXTURE::a",), voltage_constant=np.array([1.]),
        voltage_matrix=np.zeros((6, 1)), branch_limits=np.array([100.]),
        flow_p_constant=np.array([10.]), flow_q_constant=np.array([0.]),
        flow_p_matrix=np.array([[1., .1, 1., 0., .1, 0.]]), flow_q_matrix=np.zeros((1, 6)),
        anchor=np.zeros(6), current_constant=np.array([.1]), current_matrix=np.array([[.01], [.001], [.01], [0.], [.001], [0.]]),
        transformer_ratings=(None,)) for t in range(96))
    power = {(s, t): SimpleNamespace(slope=1., intercept_kw=0.) for s in caps for t in range(96)}
    authority = GridAuthority("a"*64, "b"*64, "c"*64, "d"*64, .95**2, 1.05**2, True, Stage.A1)
    def make_a(arm, stage, mess, output):
        grid = PlanningGridContext(coefficients, power, .1, .5, (.5, 1.), (.5, 1.), (.5, .5), authority)
        return ACase(deepcopy(data), grid, output, "fixture-A-"+stage, stage, arm, window, receipts, call_cap=5.)
    def make_m(arm, stage, aidc, output):
        peak = max(sum(aidc["AIDC_P_by_site"][s][t] for s in caps) for t in range(96))
        return miniature_m(output, aidc["aidc_anchor"], arm=arm, stage=stage, aidc_peak=peak, qos_sha=statistics.sha)[0]
    initial_mess = dict(routes={u: ["A"]*97 for u in ("MESS01", "MESS02", "MESS03", "MESS04")},
        P_by_site={s: [0.]*96 for s in caps}, Q_by_site={s: [0.]*96 for s in caps},
        SOC={u: [5.]*97 for u in ("MESS01", "MESS02", "MESS03", "MESS04")},
        Mode={u: [0]*96 for u in ("MESS01", "MESS02", "MESS03", "MESS04")}, source="FIXTURE_MESS_OFF")
    initial_mess["plan_sha"] = digest(initial_mess)
    envelope = [dict(slot_start=t*900., slot_end=(t+1)*900., site=s,
        gpu_capacity=1. if s == "B" and t < 2 else 0., source_variable=f"fixture_reference_anonymous[{s},{t}]",
        carryout_end=86400.) for t in range(96) for s in caps]
    reference_aidc = dict(selected_jobs={u: dict(start_seconds=0., site="A") for u in jobs},
        AIDC_P_by_site={s: [.2]*96 for s in caps}, AIDC_Q_by_site={s: [0.]*96 for s in caps},
        CC4_service={"0,0": .25, "0,1": .25}, CC4_carryout={}, anonymous_resource_envelope=envelope)
    reference_aidc["aidc_anchor"] = digest(reference_aidc)
    physical = FrozenPowerModel(.1, .5, caps, .95, lambda it, w: np.asarray(it)*1.1,
                                "EXPLICIT_SYNTHETIC_C1_FIXTURE")
    source_records = [file_record(Path(__file__)), file_record(Path(__file__).with_name("coordinator.py")),
                      file_record(Path(__file__).with_name("a_engine.py")), file_record(Path(__file__).with_name("m_engine.py")),
                      file_record(Path(__file__).with_name("actual.py")), file_record(Path(__file__).with_name("policy.py")),
                      file_record(Path(__file__).with_name("qos.py"))]
    _write(folder/"FIXTURE_INPUT.json", dict(bundle=bundle, train_source="FIXTURE_ONLY", jobs={u: asdict(j) for u,j in jobs.items()},
        actual_requests=[asdict(r) for r in requests], science="EXPLICIT_SYNTHETIC_FIXTURE", real_May_actions_claimed=False))
    return IntegrationCase("fixture-integration", "FIXTURE_SCIENCE", provider, reference_aidc, initial_mess,
        make_a, make_m, {(s,t*900): [1. if s=="A" else .1] for t in range(96) for s in caps},
        dict(capacities=caps, requests=requests, environment=Environment({"known-a": 1800, "known-b": 900, "unknown-observed": 900}),
             begin=0., end=5400., reference=CausalReferenceScheduler(caps,"fixture-shadow"),
             forecast=ForecastBook(tuple(bundle["C0_Q50"]),tuple(bundle["C0_Q90"]),0),
             power_model=physical, weather=[{}]*6), [file_record(folder/"FIXTURE_INPUT.json")],
        dict(files=source_records, Optimize_calls_before_freeze=0), evidence_kind="SYNTHETIC_FIXTURE")


def native0(output):
    from v42_root.native import build
    from v42_native.voltage import Stage
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    case = build_fixture(output)
    a_case = case.make_a_case("B3", "A1", case.initial_mess, output/"A_NATIVE0")
    a_case.output.mkdir()
    data, domains = authorized_data(a_case)
    class Context:
        folder = a_case.output
        def check(self): pass
        def progress(self, value): pass
    model, units, levels, controls, bindings = build(Context(), data, "F2-CRA", grid_context=a_case.grid, stage=Stage.A1)
    try:
        model.update()
        a_receipt = dict(original_builder="v42_root.native.build", rows=model.NumConstrs,
            columns=model.NumVars, complete_qos_domain=True, classes=len(data[7]["classes"]),
            jobs=len(data[1]), Optimize_calls=0, anonymous_variable_count=len(a_case.grid.planning_arrays["anonymous"]),
            physical_domain_options={u:d.count for u,d in domains.items()})
    finally: model.dispose()
    m_case, point = miniature_m(output/"M_NATIVE0", "NATIVE0_A_ANCHOR")
    m_case.output.mkdir()
    packet = m_case.output/"RAW.npz"
    np.savez_compressed(packet, point=point)
    certificate = fixture_full_validator(m_case, packet)
    bank = IncumbentBank(m_case); bank.offer(point, certificate)
    pools = pin_pools(m_case, point, bank, m_case.candidate_pools)
    transformed = direct_joint(m_case, point, pools)
    # The budget is never consumed on Native0 readback; initialize no ledger.
    call, captures = _native_joint(m_case, None, transformed, m_case.output/"READBACK", 0., native0=True)
    receipt = dict(evidence_kind="SYNTHETIC_FIXTURE", A=a_receipt, M=call,
        direct_proof=transformed[-1], optimizer_calls=0, full_end_to_end="NOT_EXECUTED")
    _write(output/"NATIVE0_FIXTURE_RECEIPT.json", receipt)
    return receipt


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--budget")
    parser.add_argument("--arm", choices=["B0", "B2", "B1", "B3"], default="B3")
    args = parser.parse_args()
    if not args.run:
        receipt = native0(args.output)
    else:
        if not args.budget: raise ValueError("EXISTING_SHARED_INTEGRATION_BUDGET_REQUIRED")
        case = build_fixture(Path(args.output).with_name(Path(args.output).name+"_INPUT"))
        result = run_arm(args.arm, case, IntegrationBudget(args.budget), args.output)
        receipt = dict(evidence_kind="SYNTHETIC_FIXTURE", arm=args.arm,
            stage_calls=list(result["stages"]), Actual=result["actual"]["receipt"],
            campaign_HOLD=True, actual_real_data_actions_claimed=False)
        _write(Path(args.output)/"FIXTURE_EXECUTION_RECEIPT.json", receipt)
    print(json.dumps(receipt, default=str, indent=2))


if __name__ == "__main__": main()
