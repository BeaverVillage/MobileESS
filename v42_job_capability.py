"""ML-independent capability/domain prototype. No production authority defaults.

ServiceBoundary is an explicit provider result, not a deadline inferred from QoS.
Domain masks describe admissible options; coupled feasibility is certified with
forced-option MILPs before reporting executable masks. No native V42 binding.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil, floor, isfinite
from time import monotonic

SLOT_SECONDS = 900
CHECKPOINT_SECONDS = 1800
EPSILON_RHO = 1e-7
ACTION_CLASSES = ('STAY', 'SHIFT_ONLY', 'PREPLACE_ONLY', 'SHIFT_PREPLACE',
                  'MIGRATE', 'SHIFT_MIGRATE', 'PREPLACE_MIGRATE', 'SHIFT_PREPLACE_MIGRATE')


@dataclass(frozen=True)
class Job:
    uid: str
    state: str
    submit: int
    event: int
    reference_start: int
    reference_site: str
    service_slots: int  # authorized remaining work for RUNNING, total for PENDING
    gpu: int
    qos: str = 'normal'
    protected: bool = False
    admitted: bool = True
    initial_sites: tuple = ()  # explicit residency/pinning-authorized sites
    checkpoint_authorized: bool = False
    elapsed_seconds: float | None = None
    unknown_arrival: bool = False
    duration_authority: str = ''
    migrations_used: int = 0
    standby_candidate_authorized: bool = False

    def __post_init__(self):
        if self.state not in ('PENDING', 'RUNNING'):
            raise ValueError('STATE')
        if any(type(x) is not int for x in (self.submit, self.event, self.reference_start, self.service_slots, self.gpu)):
            raise ValueError('INTEGER_RESOURCE_REQUIRED')
        if self.service_slots <= 0 or self.gpu <= 0 or not self.duration_authority:
            raise ValueError('SERVICE_AUTHORITY_REQUIRED')
        if self.submit > self.event:
            raise ValueError('NOT_YET_SUBMITTED')
        if self.reference_start < max(self.submit, self.event):
            raise ValueError('REFERENCE_BEFORE_CURRENT_BOUNDARY')
        if self.state == 'RUNNING' and self.reference_start != self.event:
            raise ValueError('RUNNING_REMAINING_SERVICE_BEGINS_AT_EVENT')
        if self.elapsed_seconds is not None and (not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError('INVALID_CAUSAL_ELAPSED')
        if self.migrations_used not in (0, 1):
            raise ValueError('ONE_MIGRATION_MAXIMUM')


@dataclass(frozen=True)
class ServiceBoundary:
    """Provider-issued exact finite starts and completion limit, including tails.

    This module does not create this authority from walltime, QoS or future end.
    A finalized native implementation requires a separate reviewed adapter.
    """
    authority_id: str
    finalized: bool
    synthetic: bool
    allowed_starts: tuple
    latest_completion: int

    def require(self):
        if not self.finalized or not self.authority_id:
            raise ValueError('V42_SERVICE_BOUNDARY_NOT_FINALIZED')
        if not self.synthetic:
            raise ValueError('NATIVE_SERVICE_ADAPTER_NOT_BOUND')
        if (not self.allowed_starts or any(type(t) is not int for t in self.allowed_starts)
                or type(self.latest_completion) is not int):
            raise ValueError('FINITE_SERVICE_DOMAIN_REQUIRED')


@dataclass(frozen=True)
class Cohort:
    n: int
    median_seconds: float
    q25_seconds: float


def temporal_candidate(job, rule, cohort=None):
    """Return eligibility, empirical budget (None=provider window), reason."""
    if rule not in ('T0_CURRENT', 'T1_COHORT_MEDIAN', 'T2_CONSERVATIVE_Q25'):
        raise ValueError('RULE')
    if job.state != 'PENDING' or not job.admitted or job.protected or job.qos in ('high', 'urgent'):
        return False, 0, 'STATE_ADMISSION_OR_PROTECTION'
    if job.unknown_arrival:
        return False, 0, 'UNKNOWN_TEMPORAL_MIGRATION_AUTHORITY_MISSING'
    if job.qos == 'standby':
        if not job.standby_candidate_authorized:
            return False, 0, 'FROZEN_STANDBY_CANDIDATE_AUTHORITY_MISSING'
        return True, None, 'STANDBY_CANDIDATE_REQUIRES_SERVICE_WINDOW'
    if rule == 'T0_CURRENT' or cohort is None or cohort.n < 100:
        return False, 0, 'NO_SUPPORTED_COHORT'
    value = cohort.median_seconds if rule == 'T1_COHORT_MEDIAN' else cohort.q25_seconds
    if not isfinite(value) or value < SLOT_SECONDS:
        return False, 0, 'BELOW_ONE_SLOT_PROXY'
    return True, None if rule == 'T1_COHORT_MEDIAN' else floor(value / SLOT_SECONDS), 'TRAIN_PROXY_NOT_SLA'


def legacy_r0_bounds(row):
    """Historical PR75 reproduction only. Never used by the new provider."""
    s, d = int(row['start_slot']), int(row['safe_duration_slots'])
    gate = (row['state_at_issue'] == 'PENDING' and row['qos'] == 'standby'
            and row['RSP_start_slot'] + d <= row['RW_completion_slot'])
    if not gate or row['AIDC_site'] == 'UNASSIGNED' or not 24 <= s < 120:
        return gate, s, s
    lo = max(24, int(row['RSP_start_slot']))
    hi = min(int(row['RW_completion_slot']) - d, 119, 120-d+max(0, s+d-120))
    if not lo <= s <= hi:
        return gate, s, s
    return gate, lo, hi


@dataclass(frozen=True, order=True)
class Option:
    start: int
    initial_site: str
    segments: tuple  # (site, start, end); entire post-H compute retained
    checkpoint: int = -1
    physical_checkpoint_seconds: float = -1
    destination: str = ''
    transfer_start: int = -1
    transfer_end: int = -1
    restart_end: int = -1
    wan: tuple = ()  # (link, slot, bytes), full payload on every path link

    @property
    def migrated(self):
        return self.checkpoint >= 0

    def action(self, job):
        shift = self.start != job.reference_start
        place = self.initial_site != job.reference_site
        return ACTION_CLASSES[int(shift) + 2*int(place) + 4*int(self.migrated)]


@dataclass
class Resources:
    capacities: dict
    rack_limits: dict  # non-additive whole-gang compatibility, not pooled capacity
    wan_capacities: dict
    paths: dict
    control_end: int
    bytes_per_gpu: int
    fixed_gpu: dict
    fixed_wan: dict
    fixed_transfers: dict
    restart_slots: int = 1
    max_active_transfers: int = 1


def checkpoint_records(job, start, end):
    """Same causal elapsed/ceil semantics as inherited V42 checkpoint adapter."""
    if job.state == 'RUNNING':
        if job.elapsed_seconds is None:
            return ()
        elapsed, origin = job.elapsed_seconds, job.event
    else:
        elapsed, origin = 0., start
    scan = job.event - 1
    at_scan = elapsed + (scan-origin)*SLOT_SECONDS
    k = max(1, floor(at_scan/CHECKPOINT_SECONDS)+1)
    values = []
    while True:
        physical = scan*SLOT_SECONDS + k*CHECKPOINT_SECONDS-at_scan
        control = ceil(physical/SLOT_SECONDS)
        if control >= end:
            break
        if control >= max(job.event, start):
            values.append((control, physical))
        k += 1
    return tuple(values)


def resources_used(job, option):
    use = defaultdict(float)
    for site, a, b in option.segments:
        for t in range(a, b):
            use['GPU', site, t] += job.gpu
    for link, t, amount in option.wan:
        use['WAN', link, t] += amount
    if option.migrated:
        for t in range(option.transfer_start, option.transfer_end):
            use['ACTIVE', '', t] += 1
    return dict(use)


def resource_limit(key, resources):
    kind, name, t = key
    if kind == 'GPU':
        return resources.capacities.get(name, 0)-resources.fixed_gpu.get((name, t), 0)
    if kind == 'WAN':
        return resources.wan_capacities.get((name, t), 0)-resources.fixed_wan.get((name, t), 0)
    return resources.max_active_transfers-resources.fixed_transfers.get(t, 0)


def validate(job, option, boundary, resources):
    boundary.require()
    if not job.admitted:
        raise ValueError('UNADMITTED_REQUIRES_SEPARATE_BACKLOG_LEDGER')
    if option.start not in boundary.allowed_starts or option.start < max(job.submit, job.event):
        raise ValueError('START_WINDOW')
    if option.start != job.reference_start and (job.protected or job.qos in ('high','urgent') or job.unknown_arrival):
        raise ValueError('TEMPORAL_AUTHORITY')
    if job.state == 'RUNNING' and (option.start, option.initial_site) != (job.reference_start, job.reference_site):
        raise ValueError('RUNNING_HISTORY_CHANGED')
    if option.initial_site not in job.initial_sites and option.initial_site != job.reference_site:
        raise ValueError('RESIDENCY_OR_PINNING')
    parts = option.segments
    if len(parts) != (2 if option.migrated else 1):
        raise ValueError('ONE_MIGRATION_MAXIMUM_OR_SEGMENT_COUNT')
    if not parts or parts[0][:2] != (option.initial_site, option.start):
        raise ValueError('SEGMENT_ORIGIN')
    if sum(b-a for _, a, b in parts) != job.service_slots or any(b <= a for _, a, b in parts):
        # Exact current-boundary carry-in checkpoint may have an empty source segment.
        if not (option.migrated and parts[0][1] == parts[0][2] and job.state == 'RUNNING'
                and sum(b-a for _, a, b in parts) == job.service_slots and parts[1][2] > parts[1][1]):
            raise ValueError('FULL_SERVICE')
    if any(parts[i][2] > parts[i+1][1] for i in range(len(parts)-1)):
        raise ValueError('OVERLAPPING_COMPUTE')
    if parts[-1][2] > boundary.latest_completion:
        raise ValueError('SERVICE_CARRYOVER_BOUNDARY')
    if option.migrated:
        if (not job.checkpoint_authorized or job.unknown_arrival or job.migrations_used or len(parts) != 2
                or option.destination == option.initial_site or option.destination not in job.initial_sites):
            raise ValueError('MIGRATION_AUTHORITY')
        if (option.checkpoint, option.physical_checkpoint_seconds) not in checkpoint_records(job, option.start, option.start+job.service_slots):
            raise ValueError('CHECKPOINT_PHASE')
        if not (option.checkpoint <= option.transfer_start < option.transfer_end
                and option.restart_end == option.transfer_end+resources.restart_slots
                and option.restart_end < resources.control_end):
            raise ValueError('WAN_RESTART')
        if (parts[0][2] != option.checkpoint or parts[1][:2] != (option.destination, option.restart_end)
                or parts[1][2]-parts[1][1] != job.service_slots-(option.checkpoint-option.start)):
            raise ValueError('REMAINING_WORK')
        path = resources.paths.get((option.initial_site, option.destination), ())
        expected = {(link, t) for link in path for t in range(option.transfer_start, option.transfer_end)}
        if not path or len(path) != len(set(path)) or len({(l,t) for l,t,_ in option.wan}) != len(option.wan):
            raise ValueError('WAN_PATH')
        if any((l,t) not in expected or n <= 0 for l,t,n in option.wan):
            raise ValueError('WAN_OCCUPANCY')
        for link in path:
            if sum(n for l, _, n in option.wan if l == link) != resources.bytes_per_gpu*job.gpu:
                raise ValueError('WAN_PAYLOAD')
    elif len(parts) != 1 or option.wan:
        raise ValueError('STAY_SEGMENTS')
    for site, _, _ in parts:
        if job.gpu > resources.capacities.get(site, 0):
            raise ValueError('SITE_GPU')
        if job.gpu > max(resources.rack_limits.get(site, (0,))):
            raise ValueError('RACK_COMPATIBILITY')
    if any(n > resource_limit(key, resources)+1e-9 for key, n in resources_used(job, option).items()):
        raise ValueError('IMMUTABLE_RESOURCE_CAPACITY')
    return True


def build_domain(job, boundary, resources, rule='T0_CURRENT', cohort=None):
    boundary.require()
    if resources.restart_slots < 1 or resources.bytes_per_gpu <= 0:
        raise ValueError('MIGRATION_COST_AUTHORITY_REQUIRED')
    candidate, budget, why = temporal_candidate(job, rule, cohort)
    starts = {job.reference_start}
    if candidate:
        starts.update(t for t in boundary.allowed_starts if t >= job.reference_start
                      and (budget is None or t-job.reference_start <= budget))
    sites = set(job.initial_sites) | {job.reference_site} if job.state == 'PENDING' else {job.reference_site}
    kept, rejected, attempted = [], Counter(), Counter()

    def add(option):
        attempted[option.action(job)] += 1
        try:
            validate(job, option, boundary, resources)
        except ValueError as error:
            rejected[str(error)] += 1
            return
        if option in kept:
            rejected['EXACT_DUPLICATE'] += 1
        else:
            kept.append(option)

    for start in sorted(starts):
        for site in sorted(sites):
            add(Option(start, site, ((site, start, start+job.service_slots),)))
            if not job.checkpoint_authorized or job.unknown_arrival or job.migrations_used:
                continue
            checkpoints = checkpoint_records(job, start, min(start+job.service_slots, resources.control_end))
            if not checkpoints:
                rejected['NO_CAUSAL_CHECKPOINT_OR_USEFUL_SERVICE'] += 1
            for cp, physical in checkpoints:
                for dest in sorted(set(job.initial_sites)-{site}):
                    path = resources.paths.get((site, dest), ())
                    if not path:
                        rejected['MISSING_WAN_PATH'] += 1
                        continue
                    for ts in range(cp, resources.control_end):
                        left, te, usage = resources.bytes_per_gpu*job.gpu, ts, []
                        # Fixed-path, maximal full-rate transfer is a declared domain law.
                        while left > 0 and te < resources.control_end:
                            amount = min(left, *(max(0, resources.wan_capacities.get((link, te), 0)) for link in path))
                            if amount:
                                usage.extend((link, te, amount) for link in path)
                            left -= amount
                            te += 1
                        if left:
                            rejected['WAN_TRANSFER_IMPOSSIBLE'] += 1
                            continue
                        restart = te+resources.restart_slots
                        parts = ((site, start, cp), (dest, restart, restart+job.service_slots-(cp-start)))
                        add(Option(start, site, parts, cp, physical, dest, ts, te, restart, tuple(usage)))
    return tuple(sorted(kept)), dict(temporal_candidate=candidate, delay_budget_slots=budget,
        candidate_reason=why, attempted_complete_options=sum(attempted.values()),
        before_by_class=dict(attempted), after_by_class=dict(Counter(o.action(job) for o in kept)),
        kept=len(kept), rejected=dict(rejected), pruning='HARD_ONLY_AND_EXACT_DUPLICATE',
        coupled_feasibility='REQUIRES_FORCED_OPTION_WITNESSES')


def capability(job, feasible_options):
    """Call with globally witnessed options, not merely the prescreen domain."""
    options = tuple(feasible_options)
    starts = {o.start for o in options}
    per_start = defaultdict(set)
    for o in options:
        per_start[o.start].add(o.initial_site)
    ts = job.state == 'PENDING' and job.reference_start in starts and len(starts) >= 2
    ps = job.state == 'PENDING' and any(len(s) >= 2 for s in per_start.values())
    mg = any(o.migrated for o in options)
    return dict(can_timeshift=ts, can_prestart_place=ps, can_checkpoint_migrate=mg,
                FLEX=ts or ps or mg, FIX=not (ts or ps or mg),
                timeshift_reason='WITNESSED_ALTERNATIVE' if ts else 'NO_WITNESSED_ALTERNATIVE',
                prestart_reason='WITNESSED_MULTISITE_START' if ps else 'NO_WITNESSED_MULTISITE_START',
                migration_reason='WITNESSED_CHECKPOINT_MOVE' if mg else 'NO_WITNESSED_CHECKPOINT_MOVE')


@dataclass(frozen=True)
class GridRow:
    """Synthetic affine row; line normalized loading or other hard bounds."""
    kind: str
    baseline: float
    gpu_coefficients: dict
    lower: float
    upper: float


def solve_joint(jobs, domains, resources, grid_rows, *, secondary=True,
                force=None, shortfall_cost=None, seconds=10., epsilon=EPSILON_RHO):
    """Bounded synthetic MILP, full-service constants retained for singleton jobs.

    No MESS dispatch/native power model is fabricated. A future reviewed binder
    must map the same lex tuple into both A/M blocks. Optional required shortfall
    precedes intervention, so this prototype cannot silently delete native P2.
    """
    import numpy as np
    from scipy.optimize import milp, Bounds, LinearConstraint
    if set(jobs) != set(domains) or any(not d for d in domains.values()):
        raise ValueError('EMPTY_DOMAIN_OR_POPULATION_CHANGED')
    if not any(r.kind == 'LINE' for r in grid_rows) or epsilon != EPSILON_RHO:
        raise ValueError('PRIMARY_OR_EPSILON_CONTRACT')
    keys = [(uid, k) for uid in sorted(domains) if len(domains[uid]) > 1 for k in range(len(domains[uid]))]
    fixed = {uid: domains[uid][0] for uid in domains if len(domains[uid]) == 1}
    usage = {key: resources_used(jobs[key[0]], domains[key[0]][key[1]]) for key in keys}
    fixed_usage = defaultdict(float)
    for uid, o in fixed.items():
        for key, amount in resources_used(jobs[uid], o).items():
            fixed_usage[key] += amount
    n = len(keys)+1
    rows, lows, highs = [], [], []
    def row(v, lo, hi):
        rows.append(v); lows.append(lo); highs.append(hi)
    for uid in sorted(set(domains)-set(fixed)):
        row([int(key[0] == uid) for key in keys]+[0], 1, 1)
    if force is not None:
        if force in keys:
            row([int(key == force) for key in keys]+[0], 1, 1)
        elif force != (force[0], 0) or force[0] not in fixed:
            raise ValueError('FORCE_OUTSIDE_DOMAIN')
    resource_keys = set(fixed_usage) | set().union(*(set(v) for v in usage.values()))
    resource_keys |= {('GPU', s, t) for s,t in resources.fixed_gpu}
    resource_keys |= {('WAN', s, t) for s,t in resources.fixed_wan}
    resource_keys |= {('ACTIVE', '', t) for t in resources.fixed_transfers}
    for key in sorted(resource_keys):
        row([usage[k].get(key, 0) for k in keys]+[0], -np.inf, resource_limit(key, resources)-fixed_usage[key])
    for grid in grid_rows:
        def effect(u):
            return sum(u.get(('GPU', s, t), 0)*coef for (s,t), coef in grid.gpu_coefficients.items())
        # Fixed background also contributes to grid load; never disappears.
        background = sum(resources.fixed_gpu.get(k, 0)*v for k,v in grid.gpu_coefficients.items())
        base = grid.baseline+effect(fixed_usage)+background
        coeff = [effect(usage[k]) for k in keys]
        row(coeff+[0], grid.lower-base, grid.upper-base)
        if grid.kind == 'LINE':
            row(coeff+[-1], -np.inf, -base)
    objectives = [np.array([0.]*len(keys)+[1.])]
    labels = ['rho_max']
    if secondary:
        if shortfall_cost is not None:
            objectives.append(np.array([shortfall_cost[k] for k in keys]+[0.])); labels.append('required_shortfall')
        metrics = [lambda j,o: int(o.migrated), lambda j,o: abs(o.start-j.reference_start),
                   lambda j,o: int(o.initial_site != j.reference_site)]
        for label, metric in zip(('migration_count', 'shift_slots', 'prestart_changes'), metrics):
            objectives.append(np.array([metric(jobs[u], domains[u][k]) for u,k in keys]+[0.])); labels.append(label)
        # MESS movement is constant inside this A block. Unique deterministic
        # per-job final locks avoid collisions in weighted rank-sum tie breakers.
        for uid in sorted(domains):
            objectives.append(np.array([k if u == uid else 0 for u,k in keys]+[0.])); labels.append('tie:'+uid)
    deadline, receipts, result = monotonic()+seconds, [], None
    for objective, label in zip(objectives, labels):
        remaining = deadline-monotonic()
        if remaining <= 0:
            raise TimeoutError('BOUNDED_CANARY_DEADLINE')
        result = milp(objective, integrality=[1]*len(keys)+[0], bounds=Bounds([0]*n, [1]*len(keys)+[np.inf]),
            constraints=LinearConstraint(np.asarray(rows), lows, highs),
            options={'time_limit': remaining, 'mip_rel_gap': 0.})
        if result.status == 2:
            return None
        if not result.success:
            raise TimeoutError('UNCERTIFIED_CANARY_OPTIMUM:'+result.message)
        value = float(objective @ result.x)
        receipts.append(dict(objective=label, value=value, gap=float(result.mip_gap or 0)))
        row(objective, -np.inf, value+(epsilon if label == 'rho_max' else 1e-8))
    selected = dict(fixed)
    for (uid,k), x in zip(keys, result.x[:-1]):
        if x > .5:
            selected[uid] = domains[uid][k]
    if set(selected) != set(jobs):
        raise ValueError('SELECTION_MASS')
    return dict(selected=selected, passes=receipts, binary_variables=len(keys), fixed_jobs=len(fixed),
                primary_objective='MAX_LINE_LOADING', transformer_in_primary=False,
                scope='SYNTHETIC_ONLY', elapsed_seconds=seconds-(deadline-monotonic()))


def executable_domains(jobs, domains, resources, grid_rows):
    """Exact bounded feasibility witnesses; no single-job fixed-neighbor pruning."""
    return {uid: tuple(o for k,o in enumerate(options)
                       if solve_joint(jobs, domains, resources, grid_rows, secondary=False, force=(uid,k)) is not None)
            for uid,options in domains.items()}
