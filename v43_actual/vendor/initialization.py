"""Explicit synthetic initial placement of already-observed RUNNING gangs.

This is a new case-study assumption, never a Kestrel geolocation recovery. The
210 frozen placements are immutable. Original PR79 capacity/rack/whole-interval
primitives are reused, without promoting its failed full ReferenceBuilder.
Only current issue observations and approved model compatibility enter choices.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import math
from pathlib import Path

from .policy import digest
from .m_engine import file_record, _write
from . import pr79_reference


POLICY_ID = "SYNTHETIC_PREDAY_RUNNING_INITIALIZATION_V1"
PR79_HELPER_SHA = "9aadfbb991c59cfd0357b861576638cbc117370c5e1e3549bf5903183d9cf555"
COMPARISON_ARMS = ("B0", "B1", "B2", "B3")


@dataclass(frozen=True)
class InitialRunningJob:
    uid: str
    episode_id: str
    submit_seconds: float
    known_start_seconds: float
    gpu: int
    compatible_sites: tuple
    observation_source_sha: str
    compatibility_source_sha: str
    state: str = "RUNNING"
    origin_unknown: bool = False
    gpu_type: str | None = None
    qos: str | None = None

    def validate(self, issue_seconds):
        if not self.uid or not self.episode_id or self.state != "RUNNING" or self.origin_unknown:
            raise ValueError("INITIAL_RUNNING_KNOWN_EPISODE_REQUIRED")
        if type(self.gpu) is not int or self.gpu <= 0:
            raise ValueError("WHOLE_GANG_GPU_REQUIRED")
        if not all(math.isfinite(float(v)) for v in (self.submit_seconds, self.known_start_seconds, issue_seconds)):
            raise ValueError("FINITE_ISSUE_OBSERVATION_SECONDS")
        if not self.submit_seconds <= self.known_start_seconds <= issue_seconds:
            raise ValueError("CAUSAL_INITIAL_RUNNING_OBSERVATION")
        if not self.observation_source_sha or not self.compatibility_source_sha or not self.compatible_sites:
            raise ValueError("SOURCE_OBSERVATION_COMPATIBILITY_AUTHORITY_REQUIRED")
        if len(self.compatible_sites) != len(set(self.compatible_sites)):
            raise ValueError("DUPLICATE_COMPATIBLE_SITE")


def verify_receipts(receipts):
    if not receipts:
        raise ValueError("INITIALIZATION_SOURCE_RECEIPTS_REQUIRED")
    for receipt in receipts:
        actual = file_record(receipt["path"])
        if any(actual[k] != receipt[k] for k in ("sha256", "bytes")):
            raise ValueError("INITIALIZATION_FROZEN_SOURCE_BYTES_DRIFT")


def _jobs(values, issue_seconds):
    allowed = {field.name for field in fields(InitialRunningJob)}
    result = []
    for value in values:
        if isinstance(value, InitialRunningJob):
            job = value
        else:
            if set(value)-allowed:
                raise ValueError("INITIALIZATION_NONOBSERVED_OR_FUTURE_INPUT_FIELD:"+
                                 ",".join(sorted(set(value)-allowed)))
            job = InitialRunningJob(**dict(value, compatible_sites=tuple(value["compatible_sites"])))
        job.validate(issue_seconds)
        result.append(job)
    if len({j.uid for j in result}) != len(result) or len({j.episode_id for j in result}) != len(result):
        raise ValueError("DUPLICATE_INITIAL_UID_OR_EPISODE")
    return sorted(result, key=lambda j: j.uid)


def _capacity(capacities, rack_limits):
    if set(capacities) != set(rack_limits):
        raise ValueError("INITIAL_SITE_RACK_AXIS_MISMATCH")
    if any(type(cap) is not int or cap <= 0 for cap in capacities.values()):
        raise ValueError("POSITIVE_INTEGER_SITE_CAPACITY_REQUIRED")
    racks = []
    for site in sorted(capacities):
        for index, limit in enumerate(rack_limits[site]):
            if type(limit) is not int or limit <= 0:
                raise ValueError("POSITIVE_LOGICAL_RACK_GANG_LIMIT_REQUIRED")
            racks.append((site+"_COMPATIBILITY_"+str(index), site, limit))
    # The prior is irrelevant to eligible_racks/fits, the exact primitives used
    # here. Unit weights describe this declared fixed-site-order scenario.
    return pr79_reference.Capacity(tuple(sorted(capacities.items())), tuple(racks),
                                   tuple((site, 1.) for site in sorted(capacities)))


def _eligible(job, capacity, site_gpu_types):
    sites = dict(capacity.sites)
    result = []
    for site in sorted(job.compatible_sites):
        if site not in sites or not capacity.eligible_racks(site, job.gpu):
            continue
        if job.gpu_type is not None:
            if site_gpu_types is None or job.gpu_type not in site_gpu_types.get(site, ()):
                continue
        result.append(site)
    return tuple(result)


def _pin(job, value, issue_seconds, source_receipts):
    required = ("episode_id", "site", "assigned_at_seconds", "known_start_seconds",
                "source_receipt", "policy_independent", "episode_capacity_validated")
    if any(k not in value for k in required):
        raise ValueError("PRIOR_EPISODE_PIN_AUTHORITY_INCOMPLETE")
    if (value["episode_id"] != job.episode_id or value["known_start_seconds"] != job.known_start_seconds
            or value["assigned_at_seconds"] > issue_seconds or value["policy_independent"] is not True
            or value["episode_capacity_validated"] is not True):
        raise ValueError("PRIOR_EPISODE_PIN_CAUSAL_OR_IDENTITY_MISMATCH")
    receipt = value["source_receipt"]
    verify_receipts([receipt])
    if not any(r["sha256"] == receipt["sha256"] for r in source_receipts):
        raise ValueError("PRIOR_EPISODE_PIN_NOT_BOUND_TO_SOURCE")
    return value["site"]


def replay_capacity(jobs, assignments, capacities, rack_limits, *, issue_seconds, site_gpu_types=None):
    """Issue occupancy only: no predicted or realized release grants capacity."""
    capacity = _capacity(capacities, rack_limits)
    use = {site: 0 for site in capacities}
    rows = []
    failures = []
    for job in jobs:
        site = assignments.get(job.uid)
        eligible = _eligible(job, capacity, site_gpu_types)
        valid = site in eligible
        if valid:
            use[site] += job.gpu
        else:
            failures.append(dict(uid=job.uid, gpu=job.gpu, site=site,
                                 reason="UNASSIGNED_OR_SITE_RACK_GPU_TYPE_INCOMPATIBLE"))
        rows.append(dict(uid=job.uid, episode_id=job.episode_id, gpu=job.gpu, site=site,
            gpu_type=job.gpu_type, rack=(capacity.eligible_racks(site,job.gpu)[0] if valid else None),
            compatible=valid, whole_gang=True, state="RUNNING", origin_unknown=False,
            gpu_type_basis="OBSERVED_REQUEST_AND_SITE_TYPE_TABLE" if job.gpu_type is not None
                           else "ORIGINAL_FROZEN_MODEL_COMPATIBLE_SITES_GPU_TYPE_UNCONFIRMED"))
    for site, total in use.items():
        if total > capacities[site]:
            failures.append(dict(site=site, required_gpu=total, capacity_gpu=capacities[site],
                                 reason="INITIAL_SITE_GPU_CAPACITY"))
    return dict(PASS=not failures and len(assignments)==len(jobs), at_seconds=issue_seconds,
        scope="OBSERVED_ISSUE_INSTANT_ONLY; NO_FUTURE_RELEASE_ASSUMPTION",
        input_running_jobs=len(jobs), input_running_GPU=sum(j.gpu for j in jobs),
        assigned_running_jobs=sum(r["site"] is not None for r in rows),
        assigned_running_GPU=sum(r["gpu"] for r in rows if r["site"] is not None),
        use_by_site=use, capacities=deepcopy(capacities), nonadditive_rack_compatibility=True,
        rows=rows, failures=failures, dropped_jobs=0, split_gangs=0, running_reclassified=0)


def exact_feasibility_model(jobs, capacity, pinned, site_gpu_types, *, site_order):
    """Tiny complete binary assignment model, objective zero; not dispatched."""
    import gurobipy as gp
    model = gp.Model(POLICY_ID+"_ASSIGNMENT_FEASIBILITY")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 0
    variables = {}
    pin_use = {s: 0 for s,_ in capacity.sites}
    for job in jobs:
        if job.uid in pinned:
            pin_use[pinned[job.uid]] += job.gpu
            continue
        eligible = set(_eligible(job, capacity, site_gpu_types))
        for site in site_order:
            if site in eligible:
                variables[job.uid,site] = model.addVar(vtype=gp.GRB.BINARY, name="initial_gang["+job.uid+","+site+"]")
        model.addConstr(gp.quicksum(variables[job.uid,s] for s in site_order if (job.uid,s) in variables)==1,
                        name="whole_gang_exactly_one["+job.uid+"]")
    for site, cap in capacity.sites:
        model.addConstr(gp.quicksum(job.gpu*variables[job.uid,site] for job in jobs if (job.uid,site) in variables)
                        <=cap-pin_use[site], name="initial_site_GPU["+site+"]")
    model.setObjective(0., gp.GRB.MINIMIZE)
    model.update()
    return model, variables


def initialize_running(jobs, capacities, rack_limits, frozen_sites, *, issue_seconds,
                       source_receipts, site_gpu_types=None, prior_verified_pins=None,
                       expected_counts=None, source_assessment=None, budget=None,
                       exact_cap_seconds=30., output=None):
    """Bind one shared initialization before all Arm workers consume it.

    Greedy failure is unresolved until a complete binary feasibility call is
    actually made. Providing no budget never enters Optimize. Output retains
    all rows and every original unresolved UID, including an accepted prior pin.
    """
    verify_receipts(source_receipts)
    helper = file_record(pr79_reference.__file__)
    if helper["sha256"] != PR79_HELPER_SHA:
        raise ValueError("PR79_HELPER_EXACT_SOURCE_SHA_DRIFT")
    observed = _jobs(jobs, issue_seconds)
    source_shas={receipt["sha256"] for receipt in source_receipts}
    if any(job.observation_source_sha not in source_shas or job.compatibility_source_sha not in source_shas
           for job in observed):
        raise ValueError("INITIAL_OBSERVATION_COMPATIBILITY_NOT_BOUND_TO_SOURCE_RECEIPT")
    by = {j.uid:j for j in observed}
    fixed = deepcopy(frozen_sites)
    if set(fixed)-set(by):
        raise ValueError("FROZEN_SITE_UID_NOT_INITIAL_RUNNING")
    initially_missing = [j for j in observed if j.uid not in fixed]
    counts = dict(running=len(observed), fixed=len(fixed), unassigned=len(initially_missing),
                  unassigned_GPU=sum(j.gpu for j in initially_missing), total_GPU=sum(j.gpu for j in observed))
    if expected_counts and any(counts.get(k)!=v for k,v in expected_counts.items()):
        raise ValueError("ORIGINAL_INITIAL_RUNNING_POPULATION_COUNTS_CHANGED")
    capacity = _capacity(capacities, rack_limits)
    order = tuple(sorted(capacities))
    pinned = deepcopy(fixed)
    recovered = {}
    for uid, value in (prior_verified_pins or {}).items():
        if uid not in by:
            raise ValueError("PRIOR_PIN_UID_NOT_INITIAL_RUNNING")
        site = _pin(by[uid], value, issue_seconds, source_receipts)
        if uid in fixed and fixed[uid]!=site:
            raise ValueError("FROZEN_210_SITE_PIN_CONFLICT")
        pinned[uid]=site
        recovered[uid]=deepcopy(value)
    intervals = pr79_reference.Reservations()
    failures = []
    for uid, site in sorted(pinned.items()):
        job = by[uid]
        if site not in _eligible(job,capacity,site_gpu_types):
            failures.append(dict(uid=uid,site=site,reason="PINNED_SITE_RACK_GPU_TYPE_INCOMPATIBLE"))
            continue
        if not pr79_reference.fits(intervals,site,0,1,job.gpu,capacity):
            failures.append(dict(uid=uid,site=site,reason="PINNED_INITIAL_CAPACITY_CONFLICT"))
            continue
        intervals.append((0,1,job.gpu,uid,site))
    assignments = deepcopy(pinned)
    greedy_failures = []
    unresolved = [j for j in observed if j.uid not in pinned]
    if not failures:
        for ordinal, job in enumerate(unresolved):
            rotating = order[ordinal%len(order):]+order[:ordinal%len(order)]
            eligible = set(_eligible(job,capacity,site_gpu_types))
            site = next((s for s in rotating if s in eligible and
                pr79_reference.fits(intervals,s,0,1,job.gpu,capacity)),None)
            if site is None:
                greedy_failures.append(dict(uid=job.uid,gpu=job.gpu,eligible_sites=sorted(eligible),
                                            reason="GREEDY_NO_FEASIBLE_INITIAL_SLOT"))
            else:
                assignments[job.uid]=site
                intervals.append((0,1,job.gpu,job.uid,site))
    exact = dict(executed=False, Optimize_calls=0, status="NOT_NEEDED" if not greedy_failures else "NOT_EXECUTED",
                 infeasibility_proven=False)
    if greedy_failures and not failures and budget is not None:
        model, variables = exact_feasibility_model(observed,capacity,pinned,site_gpu_types,site_order=order)
        try:
            call = budget.solve(model,label="SYNTHETIC_INITIAL_RUNNING_EXACT_FEASIBILITY",cap=exact_cap_seconds)
            import gurobipy as gp
            exact.update(executed=True,Optimize_calls=1,status=int(model.Status),call=call,
                         infeasibility_proven=model.Status==gp.GRB.INFEASIBLE)
            if model.SolCount:
                assignments=deepcopy(pinned)
                for job in unresolved:
                    chosen=[site for site in order if (job.uid,site) in variables and variables[job.uid,site].X>.5]
                    if len(chosen)!=1:
                        raise ValueError("EXACT_ASSIGNMENT_WHOLE_GANG_RESTORE_FAILED")
                    assignments[job.uid]=chosen[0]
        finally:
            model.dispose()
    replay = replay_capacity(observed,assignments,capacities,rack_limits,issue_seconds=issue_seconds,
                             site_gpu_types=site_gpu_types)
    original_fixed_changes = [uid for uid,site in fixed.items() if assignments.get(uid)!=site]
    passed = replay["PASS"] and not failures and not original_fixed_changes
    input_identity=dict(policy_id=POLICY_ID,issue_seconds=issue_seconds,jobs=[asdict(j) for j in observed],
        capacities=capacities,rack_limits=rack_limits,site_gpu_types=site_gpu_types,frozen_sites=fixed,
        verified_prior_pins=recovered,rule="UID_ASCENDING_ROTATING_ASCENDING_SITE_PRIORITY",
        source_receipts=source_receipts,PR79_helper=helper)
    policy=dict(policy_id=POLICY_ID,input_sha=digest(input_identity),inputs=input_identity,
        mapping={j.uid:assignments.get(j.uid) for j in observed},per_job=[dict(uid=j.uid,episode_id=j.episode_id,
            gpu=j.gpu,gpu_type=j.gpu_type,source_site=fixed.get(j.uid),initial_site=assignments.get(j.uid),
            disposition="FROZEN_SOURCE_SITE_RETAINED" if j.uid in fixed else "EXACT_PRIOR_SITE_RECOVERED" if j.uid in recovered
                        else "SYNTHETIC_INITIALIZATION_REQUIRED",KESTREL_OBSERVED_SITE=False,
            INITIAL_SITE_SOURCE="FROZEN_INITIAL_MODEL_SITE" if j.uid in fixed else "VERIFIED_PRIOR_REFERENCE_EPISODE_SITE" if j.uid in recovered
                                else "SYNTHETIC_MODEL_ASSUMPTION",state="RUNNING",origin_unknown=False) for j in observed],
        rule="UID_ASCENDING_ROTATING_ASCENDING_SITE_PRIORITY",same_initialization_for_arms=list(COMPARISON_ARMS),
        PR79_reuse=dict(source=helper,original_sha=PR79_HELPER_SHA,exact_bytes=True,
            primitives=["Capacity.eligible_racks","fits","Reservations"],
            full_ReferenceBuilder_called=False,failed_full_reference_promoted=False,
            weighted_episode_site_preference_not_used=True,assessment=source_assessment or {}),
        INPUT_AUTHORITY="ISSUE_OBSERVED_RUNNING_AND_FROZEN_MODEL_COMPATIBILITY_ONLY",
        INITIAL_SITE_SOURCE="SYNTHETIC_MODEL_ASSUMPTION",KESTREL_OBSERVED_SITE=False,
        SOURCE18R_NUMERICALLY_IDENTICAL=False,OLD_PR220_UB_AUTOMATIC_REUSE=False,
        HISTORICAL_B1_RESULT_TRANSFER=False,actual_end_reads=0,future_queue_reads=0,
        grid_reads=0,MESS_result_reads=0,job_drop=0,gang_split=0,running_reclassification=0,
        greedy_failures=greedy_failures,exact_feasibility=exact,
        PASS=passed,status="SYNTHETIC_INITIALIZATION_PASS" if passed else "UNRESOLVED_SOURCE_AUTHORITY")
    policy["initialization_sha"]=digest(policy)
    decision=dict(policy_id=POLICY_ID,initialization_sha=policy["initialization_sha"],input_sha=policy["input_sha"],
        status=policy["status"],PASS=passed,counts=counts,
        fixed_site_changes=len(original_fixed_changes),prior_recovered_jobs=len(recovered),
        prior_recovered_GPU=sum(by[uid].gpu for uid in recovered if uid not in fixed),
        synthetic_assigned_jobs=sum(j.uid in assignments for j in initially_missing if j.uid not in recovered),
        synthetic_assigned_GPU=sum(j.gpu for j in initially_missing if j.uid not in recovered and j.uid in assignments),
        source_failure_reasons=failures,greedy_failure_is_not_infeasibility=True,
        same_initialization_for_arms=list(COMPARISON_ARMS),campaign_HOLD=True,
        SOURCE18R_NUMERICALLY_IDENTICAL=False,KESTREL_OBSERVED_SITE=False,
        OLD_PR220_UB_AUTOMATIC_REUSE=False,HISTORICAL_B1_RESULT_TRANSFER=False)
    verify_receipts(source_receipts)
    if output is not None:
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        for name,value in (("SYNTHETIC_INITIALIZATION_POLICY.json",policy),
                           ("INITIAL_SITE_AUTHORITY_DECISION.json",decision),
                           ("SITE_GPU_CAPACITY_REPLAY.json",replay)):
            path=output/name
            if path.exists():
                raise FileExistsError("INITIALIZATION_ARTIFACT_ALREADY_FROZEN:"+str(path))
            _write(path,value)
    return dict(policy=policy,decision=decision,capacity_replay=replay)


def load_initialization(path, *, arm=None, expected_input_sha=None):
    import json
    policy=json.loads(Path(path).read_text(encoding="utf8"))
    expected=policy.pop("initialization_sha")
    if digest(policy)!=expected or policy["policy_id"]!=POLICY_ID:
        raise ValueError("SYNTHETIC_INITIALIZATION_SHA_MISMATCH")
    policy["initialization_sha"]=expected
    if not policy["PASS"] or policy["status"]!="SYNTHETIC_INITIALIZATION_PASS":
        raise ValueError("INITIALIZATION_NOT_PHYSICALLY_ESTABLISHED")
    if arm is not None and arm not in COMPARISON_ARMS:
        raise ValueError("COMPARISON_ARM_REQUIRED")
    if expected_input_sha is not None and expected_input_sha!=policy["input_sha"]:
        raise ValueError("INITIALIZATION_CASE_INPUT_MISMATCH")
    verify_receipts(policy["inputs"]["source_receipts"])
    return policy
