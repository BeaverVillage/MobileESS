from copy import deepcopy
from dataclasses import asdict
from time import perf_counter
import math
import json
from pathlib import Path
import hashlib
import numpy as np
from .actual import _require_public_metadata
from .policy import digest, _receipt, migration_guard, ReservationLedger
from .reservation_state import union_job_segments
from .trajectory_tracking import TrackingReference, service_integral, require_tracking_public
from .frozen_unknown import _migration_capability
from .unified_contract import require_bindings
from v42_final.workload import ForecastBook


CONTRACT = 'V42_SIGNED_SENSITIVITY_RUNTIME60_V1'


MODE = 'CAUSAL_SIGNED_GRID_ALLOCATION'


DELAY_SECONDS = (0, 900, 1800, 2700, 3600)


def grid_numeric_fingerprint(packet):
    """Every numeric array read by original scalar electrical rows."""
    fingerprint = hashlib.sha256()
    def add(name, value):
        array = np.asarray(value)
        fingerprint.update(name.encode()); fingerprint.update(str((array.shape,array.dtype.str)).encode())
        fingerprint.update(array.tobytes())
    for name in ('controls','p_slope','cos','sin','line_indices','transformer_indices'):
        add(name,getattr(packet,name))
    for name in ('ap','correction','bias'):
        for t,value in enumerate(getattr(packet,name)):
            add(name+str(t),value)
    for t,coefficient in enumerate(packet.coefficients):
        for name in ('voltage_constant','voltage_matrix','flow_p_constant','flow_p_matrix',
                'flow_q_constant','flow_q_matrix','current_constant','current_matrix','anchor','branch_limits'):
            add(str(t)+name,getattr(coefficient,name))
        fingerprint.update(digest(dict(ratings=list(coefficient.transformer_ratings),
            control_names=list(coefficient.control_names),branch_names=list(coefficient.branch_names))).encode())
    fingerprint.update(digest(dict(voltage_lower=packet.voltage_lower,voltage_upper=packet.voltage_upper,
        sites=list(packet.sites),branch_names=list(packet.branch_names),control_names=list(packet.control_names),
        pf=packet.pf)).encode())
    return fingerprint.hexdigest()


def conditional_remaining_runtime(metadata):
    """Public quantiles are forecasts, never exact completion guarantees."""
    elapsed = float(metadata.get('accumulated_compute_seconds', 0))
    q50 = float(metadata['t50_seconds'])
    q90 = metadata.get('experimental_prediction_Q90_seconds')
    return dict(total_Q50_seconds=q50, total_Q90_seconds=q90, elapsed_seconds=elapsed,
        conditional_remaining_Q90_seconds=None, conditional_provider_status='NOT_CERTIFIED',
        public_remaining_Q50_seconds=max(0., q50-elapsed),
        physical_remaining_runtime_seconds=None,
        physical_remaining_runtime_status='UNOBSERVED_RUNNING_RIGHT_CENSORED' if metadata.get('state')=='RUNNING' else 'NOT_A_COMPLETION_FORECAST',
        zero_Q50_remaining_is_physical_completion=False,
        running_hold_required=metadata.get('state') == 'RUNNING',
        quantile_is_completion_guarantee=False)


def anonymous_cohort_residual(reference, metadata, now):
    """Exact original cohort marginals; residual work remains a soft forecast.

    The original model has separate hour/time and site/time marginals. Their
    canonical transportation product preserves both without inventing UIDs.
    Source x/CDF/carry are replayed before any residual can inform a guard.
    """
    from .q90_recourse import load_nominal_service
    z = np.zeros_like(reference.arrays['G_Unknown_Q50_Plan'])
    identity = reference.identity
    if not np.any(reference.arrays['G_Unknown_Q50_Plan']) and not np.any(identity.get('CC4_Q50', [])):
        return z, dict(status='ZERO_ANONYMOUS_FORECAST', hard_occupancy=False)
    required = ('CC4_Q50', 'CC4_Q90', 'CC4_service', 'CC4_carryout',
        'Timing_CDF_Q10', 'Timing_CDF_Q90', 'CC4_source_authority')
    if any(k not in identity for k in required):
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason='SOURCE_COHORT_CDF_AUTHORITY_MISSING',
            safe_promotion_allowed=False, hard_occupancy=False)
    sites = reference.sites
    a = dict(resource_sites=list(sites), aidc_anchor=identity['CC4_source_authority']['aidc_anchor'],
        nominal_site_GPU={s:reference.arrays['G_Unknown_Q50_Plan'][:,j].tolist() for j,s in enumerate(sites)},
        known_site_GPU={s:reference.arrays['G_Known_Plan'][:,j].tolist() for j,s in enumerate(sites)},
        CC4_service=identity['CC4_service'], CC4_carryout=identity['CC4_carryout'])
    try:
        nominal = load_nominal_service(a, identity['CC4_Q50'], identity['Timing_CDF_Q10'],
            identity['Timing_CDF_Q90'], source_authority=identity['CC4_source_authority'])
    except ValueError as exc:
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason=str(exc),
            safe_promotion_allowed=False, hard_occupancy=False)
    book = ForecastBook(tuple(identity['CC4_Q50']), tuple(identity['CC4_Q90']), reference.begin)
    prefix = []
    for uid, m in sorted(metadata.items()):
        if m.get('origin_unknown') is not True:
            continue
        submit = m['submit_seconds']
        if submit < reference.begin:
            prefix.append(uid)
        elif submit <= now and submit < reference.begin+86400 and m.get('cc4_eligible', True):
            book.submit(uid, submit, now, m['gpu'], m['t50_seconds'])
    rows = [book.row(h, now) for h in range(24)]
    q50 = np.asarray(identity['CC4_Q50'], float)
    remaining = np.asarray([r['remaining_CC4_Q50_GPUh'] for r in rows])
    ratio = np.divide(remaining, q50, out=np.zeros(24), where=q50 > 0)
    x = np.asarray(nominal['x_GPUh'], float)
    carry = np.asarray(nominal['carryout_GPUh_by_hour'], float)
    site = reference.arrays['G_Unknown_Q50_Plan']
    site_total = site.sum(axis=1)
    weights = np.divide(site, site_total[:,None], out=np.zeros_like(site), where=site_total[:,None] > 0)
    # z[h,t,s] has both exact native marginals before residual depletion.
    cohort_site = 4*x[:,:,None]*weights[None,:,:]
    if not np.allclose(cohort_site.sum(axis=0), site, atol=1e-7, rtol=0):
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason='COHORT_SITE_MARGINAL_DRIFT',
            safe_promotion_allowed=False, hard_occupancy=False)
    residual = (cohort_site*ratio[:,None,None]).sum(axis=0)
    residual_carry = carry*ratio
    mass = residual.sum()/4+residual_carry.sum()
    if abs(mass-remaining.sum()) > 1e-7:
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason='RESIDUAL_COHORT_MASS_DRIFT',
            safe_promotion_allowed=False, hard_occupancy=False)
    return residual, dict(status='SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS', hard_occupancy=False,
        original_nominal_service_sha=nominal['nominal_service_sha'], original_forecast_mutated=False,
        residual_nominal_GPUh=float(remaining.sum()), residual_in_day_GPUh=float(residual.sum()/4),
        residual_carryout_GPUh=float(residual_carry.sum()), cohort_rows=rows,
        unique_Dday_observed_UIDs=sorted(book.submissions), prefix_Unknown_UIDs_separate=prefix,
        mathematical_site_cohort_coupling='CANONICAL_TRANSPORTATION_PRODUCT_PRESERVES_BOTH_NATIVE_MARGINALS',
        actual_physical_completion_or_future_UID_read=False, Q90_as_physical_occupancy=False)


class SignedSensitivityPolicy:
    frozen_schema = CONTRACT
    lookup_only = False
    controller_contract = CONTRACT
    execution_mode = MODE

    def __init__(self, reference, packet, *, bindings, expected_bindings, migration_authority=None,
                 runtime_repair=True, basic=False, evidence_scope='REAL_DIAGNOSTIC'):
        require_bindings(bindings, expected_bindings)
        reference.require_immutable()
        if packet.bindings != bindings or tuple(packet.sites) != reference.sites or packet.begin_seconds != reference.begin:
            raise ValueError('SIGNED_ALLOCATION_COMMON_AXIS_BINDING_DRIFT')
        self.reference, self.packet = reference, packet
        self.bindings = dict(bindings)
        self.migration_authority = deepcopy(migration_authority)
        self.runtime_repair, self.basic, self.evidence_scope = runtime_repair, basic, evidence_scope
        self.spec = dict(contract=CONTRACT, bindings=self.bindings, evidence_scope=evidence_scope,
            reference_target_sha=reference.sha, migration_authority_sha=digest(self.migration_authority),
            response_numeric_sha=grid_numeric_fingerprint(packet),
            C1_source_sha=reference.identity.get('C1_Power_Model_SHA'),
            current_power_model='EXACT_OBSERVED_ORIGINAL_C1_PCC_PQ',
            future_power_model='ORIGINAL_DMINUS1_C1_ENDPOINT_SECANT_PREDICTION',
            allocation_source_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            anonymous_residual_rule='EXACT_SOURCE_COHORT_TRANSPORT_FORECASTBOOK_DEPLETION_V1',
            ranking=['HARD_FEASIBILITY', 'ALL_LINE_PHASE_TIME_MAX_LOADING', 'CRITICAL_LOADING_HOURS',
                'Q90_RUNTIME_QUEUE_REBOUND_RISK', 'INTENTIONAL_DELAY', 'MIGRATION_COUNT', 'DETERMINISTIC_SITE_TIME'],
            candidates_seconds=list(DELAY_SECONDS), online_global_optimizer_calls=0, runtime_repair=runtime_repair,
            basic=basic, anonymous_CC4_hard_occupancy=False, conditional_remaining_provider='NOT_CERTIFIED')
        self.sha = digest(self.spec)
        self.audit, self.funnel, self.times = [], [], []
        self.assignments, self.last_selection = {}, {}
        self.current, self.metadata = None, {}
        self.boundary_completed_UIDs = set()
        self.diagnostics = []
        self._baseline_grid_cache = {}
        self.baseline_cache_hits, self.baseline_cache_misses = 0, 0
        self._c1_model, self._current_weather_provider = None, None
        self._selection_response_sha = None
        if evidence_scope.startswith('REAL') and not self.spec['C1_source_sha']:
            raise ValueError('REAL_FROZEN_C1_SOURCE_SHA_REQUIRED')

    @property
    def document(self):
        self.reference.require_immutable()
        return dict(schema=self.frozen_schema, spec=deepcopy(self.spec), policy_sha=self.sha,
            bindings=deepcopy(self.bindings), reference=dict(
                arrays={k:v.tolist() for k,v in self.reference.arrays.items()},
                sites=list(self.reference.sites), begin=self.reference.begin,
                commands=self.reference.commands, identity=deepcopy(self.reference.identity),
                target_sha=self.reference.sha), migration_authority=deepcopy(self.migration_authority))

    def save(self, path):
        Path(path).write_text(json.dumps(self.document, sort_keys=True, allow_nan=False), encoding='utf-8')

    @classmethod
    def load(cls, path, *, bindings):
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        require_bindings(d['bindings'], bindings)
        if d['schema'] != cls.frozen_schema or digest(d['spec']) != d['policy_sha']:
            raise ValueError('SIGNED_SERIALIZED_POLICY_SHA_DRIFT')
        if d['spec']['allocation_source_sha'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
            raise ValueError('SIGNED_ALLOCATION_CODE_SOURCE_DRIFT')
        r, a = d['reference'], d['reference']['arrays']
        reference = TrackingReference(a['G_Known_Plan'], a['G_Unknown_Q50_Plan'], a['IT_Plan'],
            a['PCC_P_Plan'], a['PCC_Q_Plan'], sites=r['sites'], begin=r['begin'],
            commands=r['commands'], identity=r['identity'])
        if reference.sha != r['target_sha']:
            raise ValueError('SIGNED_SERIALIZED_REFERENCE_SHA_DRIFT')
        if (reference.sha != d['spec']['reference_target_sha'] or
                digest(d['migration_authority']) != d['spec']['migration_authority_sha']):
            raise ValueError('SIGNED_SERIALIZED_REFERENCE_OR_MIGRATION_AUTHORITY_DRIFT')
        self = cls.__new__(cls)
        self.reference, self.packet, self.bindings = reference, None, dict(bindings)
        self.spec, self.sha = d['spec'], d['policy_sha']
        self.migration_authority = d['migration_authority']
        self.runtime_repair, self.basic = self.spec['runtime_repair'], self.spec['basic']
        self.evidence_scope = self.spec['evidence_scope']
        self.audit, self.funnel, self.times, self.diagnostics = [], [], [], []
        self.assignments, self.last_selection = {}, {}
        self.current, self.metadata = None, {}
        self.boundary_completed_UIDs = set()
        self._baseline_grid_cache = {}
        self.baseline_cache_hits, self.baseline_cache_misses = 0, 0
        self._c1_model, self._current_weather_provider = None, None
        self._selection_response_sha = None
        return self

    def bind_runtime_packet(self, packet):
        if packet.bindings != self.bindings or tuple(packet.sites) != self.reference.sites or packet.begin_seconds != self.reference.begin:
            raise ValueError('SIGNED_RUNTIME_PACKET_ANCHOR_DRIFT')
        if grid_numeric_fingerprint(packet) != self.spec['response_numeric_sha']:
            raise ValueError('SIGNED_RUNTIME_RESPONSE_NUMERIC_DRIFT')
        self.packet = packet
        return self

    def bind_observed_c1(self, model, *, current_weather_provider):
        """Late bind a source-pinned C1 callback and current-tick-only weather.

        The policy never receives or enumerates future Actual weather. The
        driver supplies a guarded callback after observing its current tick.
        """
        if (not model.authority_sha or not callable(current_weather_provider)
                or self.packet is None or model.capacities != self.packet.capacities
                or abs(model.power_factor-self.packet.pf) > 1e-12):
            raise ValueError('OBSERVED_ORIGINAL_C1_AUTHORITY_REQUIRED')
        expected = self.spec['C1_source_sha']
        if self.evidence_scope.startswith('REAL') and (not expected or model.authority_sha != expected):
            raise ValueError('REAL_ORIGINAL_C1_SOURCE_SHA_DRIFT')
        if expected is not None and model.authority_sha != expected:
            raise ValueError('FROZEN_C1_SOURCE_SHA_DRIFT')
        self._c1_model, self._current_weather_provider = model, current_weather_provider
        self._baseline_grid_cache.clear()
        return self

    def _current_weather(self, now):
        if self.current is None or self.current[0] != float(now):
            raise ValueError('ONLY_CURRENT_OBSERVED_WEATHER_ALLOWED')
        if self._current_weather_provider is None:
            if self.evidence_scope.startswith('REAL'):
                raise ValueError('REAL_EXACT_CURRENT_C1_CONTEXT_REQUIRED')
            return None
        weather = deepcopy(self._current_weather_provider(float(now)))
        _require_public_metadata(weather)
        return weather

    def _grid_delta(self, t, gpu, now):
        if t == int((now-self.reference.begin)//900) and self._c1_model is not None:
            weather = self._current_weather(now)
            exact = self._c1_model.recompute(np.asarray([gpu], float), self.packet.sites, [weather])
            cols = [self.packet.control_names.index('aidc_load_kw['+s+']') for s in self.packet.sites]
            return (exact['PCC_P_kw'][0]-self.packet.controls[t, cols])/self.packet.p_slope[t]
        if t == int((now-self.reference.begin)//900) and self.evidence_scope.startswith('REAL'):
            raise ValueError('REAL_EXACT_CURRENT_C1_CONTEXT_REQUIRED')
        return gpu-self.reference.arrays['G_Total_Plan'][t]

    def require_bindings(self, expected):
        require_bindings(self.bindings, expected)
        if digest(self.spec) != self.sha:
            raise ValueError('SIGNED_POLICY_SHA_DRIFT')
        self.reference.require_immutable()
        if (self.reference.sha != self.spec['reference_target_sha'] or
                digest(self.migration_authority) != self.spec['migration_authority_sha']):
            raise ValueError('SIGNED_REFERENCE_OR_MIGRATION_AUTHORITY_DRIFT')
        if self.packet is not None and self.packet.bindings != self.bindings:
            raise ValueError('SIGNED_RUNTIME_PACKET_ANCHOR_DRIFT')
        if (self.packet is not None and self.evidence_scope.startswith('REAL')
                and grid_numeric_fingerprint(self.packet) != self.spec['response_numeric_sha']):
            raise ValueError('SIGNED_RUNTIME_RESPONSE_NUMERIC_DRIFT')

    def observe(self, now, use, metadata):
        if self.current is None or self.current[0] != float(now) or self.current[1] != dict(use):
            self._baseline_grid_cache.clear()
        self.current = (float(now), dict(use))
        self.metadata = metadata

    def _public_future(self, reservations, exclude):
        """Per-UID union; Running forecasts are separate from hard holds."""
        hard = np.zeros_like(self.reference.arrays['G_Total_Plan'])
        expected = hard.copy()
        known = hard.copy()
        bookings = reservations.reservations
        plans = getattr(reservations, 'known_plans', {})
        uids = set(bookings) | set(plans) | set(self.metadata)
        for uid in uids:
            if uid == exclude or uid in self.boundary_completed_UIDs:
                continue
            booking = bookings.get(uid, {})
            rows = [] if booking.get('status') == 'RELEASED' else booking.get('segments', [])
            rows = rows + plans.get(uid, [])
            m = self.metadata.get(uid, {})
            if m.get('state') == 'COMPLETED':
                rows = []
            hard_profile = service_integral(self.packet.sites, rows, self.reference.begin)
            hard += hard_profile
            future_rows = rows
            if m.get('state') == 'RUNNING':
                remaining = max(0., m['t50_seconds']-m.get('accumulated_compute_seconds', 0))
                hold = max(remaining, 900-self.current[0]%900)
                future_rows = rows + [dict(resource='gpu:'+m['current_site'], begin=self.current[0],
                    end=self.current[0]+hold, quantity=m['gpu'])]
            elif m.get('state') == 'PENDING' and m.get('origin_unknown') is True and not rows:
                # Submitted work removed from its anonymous SUBMIT cohort can
                # still be waiting. Its public FCFS prediction is soft; it is
                # never inserted into a committed/hard reservation ledger.
                site = m.get('reference_site', m.get('source_site'))
                if site in self.packet.sites:
                    start = max(self.current[0], m['reference_start_seconds'])
                    future_rows = [dict(resource='gpu:'+site, begin=start,
                        end=start+max(m['t50_seconds'], 1e-9), quantity=m['gpu'])]
            expected_profile = service_integral(self.packet.sites, future_rows, self.reference.begin)
            expected += expected_profile
            if uid in plans or m.get('origin_unknown') is False:
                known += hard_profile
        slot = int((self.current[0]-self.reference.begin)//900)
        if 0 <= slot < 96:
            instant = np.array([self.current[1][s] for s in self.packet.sites], float)
            own = self.metadata.get(exclude, {})
            if own.get('state') == 'RUNNING':
                instant[self.packet.sites.index(own['current_site'])] -= own['gpu']
            hard[slot] = np.maximum(hard[slot], instant)
            expected[slot] = np.maximum(expected[slot], instant)
        self.last_hard_profile = hard
        anonymous, audit = anonymous_cohort_residual(self.reference, self.metadata, self.current[0])
        self.anonymous_residual_audit = audit
        # Current is exact observed physical C1; future anonymous demand is a
        # separate residual expectation and never enters reservations.feasible.
        if audit['status'] == 'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS':
            anonymous[:max(0, slot+1)] = 0
            expected += anonymous
        return expected, known

    def current_guard(self, metadata, segments, now, observed):
        # Execution-phase guards receive a fresh physical observation even
        # between control ticks; it is not a future candidate observation.
        if self.current is None or self.current[0] != float(now):
            self.observe(now, observed, self.metadata)
        slot = int((now-self.reference.begin)//900)
        if not 0 <= slot < 96:
            return 'CURRENT_GRID_SLOT_UNSUPPORTED'
        instant = np.array([observed[s] for s in self.packet.sites], float)
        if metadata.get('state') == 'RUNNING':
            instant[self.packet.sites.index(metadata['current_site'])] -= metadata['gpu']
        for seg in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
            site = seg['resource'][4:]
            if metadata['gpu'] > max(self.packet.rack_compatibility[site]):
                return 'RACK_GANG_INCOMPATIBLE'
            if seg['begin'] <= now < seg['end']:
                instant[self.packet.sites.index(site)] += seg['quantity']
        if np.any(instant > [self.packet.capacities[s]+1e-9 for s in self.packet.sites]):
            return 'GPU_CAPACITY'
        _, bad = self.packet._at_slot(slot, self._grid_delta(slot, instant, now))
        return None if not bad else 'CURRENT_OBSERVED_'+bad[0]['reason']

    def _score(self, metadata, segments, now, baseline):
        if getattr(self, 'anonymous_residual_audit', {}).get('status') == 'CONSERVATION_NOT_CERTIFIED':
            return None, 'ANONYMOUS_FORECAST_CONSERVATION_NOT_CERTIFIED'
        profile = service_integral(self.packet.sites, segments, self.reference.begin)
        slot = int((now-self.reference.begin)//900)
        instant_base = np.asarray([self.current[1][s] for s in self.packet.sites], float)
        if metadata.get('state') == 'RUNNING':
            instant_base[self.packet.sites.index(metadata['current_site'])] -= metadata['gpu']
        instant_candidate = instant_base.copy()
        for row in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
            if row['begin'] <= now < row['end']:
                instant_candidate[self.packet.sites.index(row['resource'][4:])] += row['quantity']
        # Exact original rows are cached only for the complete same baseline,
        # clock and response authority. A candidate changes only its own GPU
        # profile; untouched slots retain their original scores/violations.
        authority = (digest(self.packet.bindings), digest(self.packet.authority),
            self._selection_response_sha or grid_numeric_fingerprint(self.packet),
            tuple(c.coefficient_sha256 for c in self.packet.coefficients),
            self.packet.controls.tobytes(), self.packet.p_slope.tobytes(),
            self.packet.voltage_lower, self.packet.voltage_upper,
            tuple(self.packet.line_indices), tuple(self.packet.transformer_indices),
            None if self._c1_model is None else self._c1_model.authority_sha,
            digest(self._current_weather(now)), instant_base.tobytes())
        key = (float(now), slot, baseline.tobytes(), authority)
        cached = self._baseline_grid_cache.get(key)
        if cached is None:
            cached = {t:self.packet._at_slot(t, self._grid_delta(t, instant_base if t == slot else baseline[t], now))
                for t in range(max(0, slot), 96)}
            self._baseline_grid_cache[key] = cached
            self.baseline_cache_misses += 1
            if len(self._baseline_grid_cache) > 4:
                self._baseline_grid_cache.pop(next(iter(self._baseline_grid_cache)))
        else:
            self.baseline_cache_hits += 1
        peaks, violations, nonworsening = [], [], True
        for t in range(max(0, slot), 96):
            if t == slot or np.any(profile[t]):
                gpu = instant_candidate if t == slot else baseline[t]+profile[t]
                delta = self._grid_delta(t, gpu, now)
                peak, bad = self.packet._at_slot(t, delta)
            else:
                peak, bad = cached[t]
            peaks.append(peak)
            if bad:
                _, base_bad = cached[t]
                nonworsening = nonworsening and {r['reason'] for r in bad}.issubset({r['reason'] for r in base_bad})
                violations.extend(bad)
        if violations:
            self.diagnostics.append(dict(uid=metadata['uid'], time_seconds=now,
                status='BASELINE_SAME_VIOLATION_TYPE_NOT_SAFE_PASS' if nonworsening else 'HARD_GRID_REJECT',
                violations=violations, hard_feasible=False))
            return None, 'PREDICTED_'+violations[0]['reason']
        q90 = metadata.get('experimental_prediction_Q90_seconds')
        risk = max(0., float(metadata['t50_seconds'] if q90 is None else q90)-metadata['t50_seconds'])*metadata['gpu']/3600
        soft_over = float(np.maximum(baseline+profile-[self.packet.capacities[s] for s in self.packet.sites], 0).sum()/4)
        return dict(grid_peak=max(peaks, default=0.), loading_hours=sum(peaks)*.25,
            risk_GPUh=risk+soft_over, soft_prediction_capacity_risk_GPUh=soft_over,
            checked_grid_slots=len(peaks), Job_Q90_seconds=q90, profile=profile,
            affine_approximation_only=True, Fresh_AC_PASS_claimed=False), None

    def _record(self, m, now, decision, began, count, rejected):
        self._selection_response_sha = None
        elapsed = perf_counter()-began
        self.times.append(elapsed)
        decision.update(uid=m['uid'], policy_sha=self.sha, online_global_optimizer_calls=0,
            execution_mode=MODE, controller_contract=CONTRACT, candidate_count=count,
            decision_seconds=elapsed, rejected_candidates=rejected)
        self.last_selection[m['uid']] = deepcopy(decision)
        self.audit.append(dict(uid=m['uid'], time_seconds=now, state=m['state'], decision=deepcopy(decision)))
        return decision

    def select(self, metadata, receipt, now, reservations, *, reserve=True):
        began = perf_counter()
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        if not metadata.get('is_observed', True) or metadata['submit_seconds'] > now:
            return self._record(metadata, now, dict(action='QUEUE', status='OBSERVATION_REQUIRED'), began, 0, [])
        if self.current is None or self.current[0] != now:
            raise ValueError('CURRENT_OBSERVATION_REQUIRED')
        if int(metadata['gpu']) != metadata['gpu'] or metadata['gpu'] <= 0:
            raise ValueError('WHOLE_GPU_GANG_REQUIRED')
        r = _receipt(receipt)
        self._selection_response_sha = grid_numeric_fingerprint(self.packet)
        baseline, _ = self._public_future(reservations, metadata['uid'])
        source = metadata.get('reference_site', metadata.get('source_site'))
        origin = math.ceil(max(now, r['reference_start_seconds'], metadata.get('release_seconds') or -math.inf,
            metadata.get('hard_earliest_start_seconds') or -math.inf)/900)*900
        allowed = set(r['allowed_starts_seconds'])
        starts = sorted({origin} | {r['reference_start_seconds']+d for d in DELAY_SECONDS
            if r['reference_start_seconds']+d >= now and r['reference_start_seconds']+d in allowed})
        rows, rejected, count = [], [], 0
        for site in sorted(set(metadata['compatible_sites'])):
            if site != source and (self.basic or metadata.get('can_prestart_place') is not True):
                rejected.append(dict(site=site, reason='PREPLACE_SOURCE_AUTHORITY'))
                continue
            for start in starts:
                count += 1
                if self.basic and (site != source or start != origin):
                    continue
                end = start+max(metadata['t50_seconds'], 1e-9)
                spend = max(metadata.get('additional_start_delay_seconds', 0), start-r['reference_start_seconds'], 0)
                reason = None
                queue_only = site == source and start == origin and origin > r['latest_start_seconds']
                if not queue_only and start not in allowed:
                    reason = 'SOURCE_START_WINDOW'
                if not queue_only and spend+metadata.get('cumulative_migration_interruption_seconds', 0) > r['budget_seconds']+1e-9:
                    reason = 'SHARED_QOS_BUDGET'
                if start > origin and metadata.get('Can_TimeShift') is not True:
                    reason = 'NO_TIME_SHIFT_AUTHORITY'
                if metadata['gpu'] > max(self.packet.rack_compatibility[site]):
                    reason = 'RACK_GANG_INCOMPATIBLE'
                if any(metadata.get(k) is not None and value > metadata[k] for k, value in (
                        ('hard_latest_start_seconds', start), ('completion_deadline_seconds', end))):
                    reason = 'HARD_WINDOW'
                segments = [dict(resource='gpu:'+site, begin=start, end=end, quantity=metadata['gpu'])]
                if reason is None and metadata.get('runtime_backfill_evaluation_seconds') == now and start == now:
                    ok, why = safe_backfill(metadata, now=now, site=site,
                        reservations=reservations, uid=metadata['uid'], evidence_scope=self.evidence_scope)
                    if not ok:
                        reason = 'BACKFILL_'+why
                if reason is None:
                    reason = reservations.feasible(segments, exclude=metadata['uid'])
                if reason is None:
                    reason = self.current_guard(metadata, segments, now, self.current[1])
                score = None
                if reason is None:
                    score, reason = self._score(metadata, segments, now, baseline)
                if reason:
                    rejected.append(dict(site=site, start_seconds=start, reason=reason))
                    continue
                burden = metadata.get('additional_start_delay_seconds', 0) if queue_only else spend
                key = (round(score['grid_peak'], 12), score['loading_hours'], score['risk_GPUh'], burden, 0, site, start)
                rows.append((key, dict(site=site, start_seconds=start, nominal_end_seconds=end,
                    segments=segments, additional_start_delay_seconds=burden,
                    action='PREPLACE' if site != source else 'DELAY' if start > origin else 'START',
                    status='SIGNED_MAX_LOADING_SELECTED',
                    tracking={k:v for k,v in score.items() if k != 'profile'}), score['profile']/4))
        for _, row, profile in sorted(rows, key=lambda x:x[0]):
            if reserve:
                ok, reason = reservations.reserve(metadata['uid'], row['segments'], replace=True)
                if not ok:
                    rejected.append(dict(site=row['site'], reason=reason))
                    continue
                metadata['additional_start_delay_seconds'] = max(metadata.get('additional_start_delay_seconds', 0), row['additional_start_delay_seconds'])
                self.assignments[metadata['uid']] = profile
            return self._record(metadata, now, row, began, count, rejected)
        return self._record(metadata, now, dict(action='QUEUE', status='NO_HARD_FEASIBLE_SIGNED_ACTION',
            reason=rejected[-1]['reason'] if rejected else 'NO_AUTHORIZED_ACTION'), began, count, rejected)

    def select_migration(self, metadata, receipt, now, reservations, *, checkpoint_at=None, reserve=True):
        began = perf_counter()
        self._selection_response_sha = grid_numeric_fingerprint(self.packet)
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        stages = dict(RUNNING=metadata.get('state') == 'RUNNING', CHECKPOINT=False,
            AUTHORITY=False, DESTINATION=False, REMAINING=False, WAN=False, GPU_RACK=False,
            BUDGET=False, SELECTED=False, COMPLETED=False)
        rejected, rows = [], []
        def stay(reason):
            self.funnel.append(dict(uid=metadata['uid'], time_seconds=now, reason=reason, **stages))
            return self._record(metadata, now, dict(action='STAY', status=reason, reason=reason), began, len(rows), rejected)
        elapsed = metadata.get('accumulated_compute_seconds', 0)
        if not stages['RUNNING']:
            return stay('NO_OBSERVED_RUNNING')
        if elapsed < 1800 or abs(elapsed%1800) > 1e-7 or checkpoint_at is None or checkpoint_at > now:
            return stay('NO_OBSERVED_CHECKPOINT')
        stages['CHECKPOINT'] = True
        if metadata.get('migration_count', 0):
            return stay('MAXIMUM_ONE_MIGRATION')
        if self.basic or metadata.get('Can_Checkpoint_Migrate') is not True:
            return stay('NO_CHECKPOINT_SOURCE_AUTHORITY')
        stages['AUTHORITY'] = True
        remaining = max(0., metadata['t50_seconds']-elapsed)
        if remaining <= 0:
            return stay('CONDITIONAL_REMAINING_NOT_CERTIFIED_RUNNING_HOLD')
        stages['REMAINING'] = True
        baseline, _ = self._public_future(reservations, metadata['uid'])
        stay_segments = [dict(resource='gpu:'+metadata['current_site'], begin=now, end=now+remaining, quantity=metadata['gpu'])]
        stay_score, _ = self._score(metadata, stay_segments, now, baseline)
        for destination in sorted(set(metadata['compatible_sites'])-{metadata['current_site']}):
            stages['DESTINATION'] = True
            cap = deepcopy(metadata.get('migration_capability') or _migration_capability(
                self.migration_authority, metadata['current_site'], destination, metadata['gpu']))
            if not cap:
                rejected.append(dict(site=destination, reason='NO_SOURCE_WAN_TRANSFER_RESTART_AUTHORITY'))
                continue
            stages['WAN'] = True
            m = dict(metadata, migration_capability=cap)
            migration, reason = migration_guard(m, receipt, now=now, accumulated_compute_seconds=elapsed,
                destination=destination, remaining_nominal_seconds=remaining, reservations=reservations, checkpoint_at=checkpoint_at)
            if migration is None:
                rejected.append(dict(site=destination, reason=reason))
                continue
            stages['BUDGET'] = True
            a, b = migration['times']['transfer_start'], migration['times']['transfer_end']
            migration['segments'].extend(dict(resource='wan:LINK::'+link, begin=a, end=b,
                quantity=cap['bandwidth_bytes_per_second']) for link in cap.get('route_links', []))
            reason = reservations.feasible(migration['segments'], exclude=metadata['uid'])
            if reason is None:
                reason = self.current_guard(metadata, migration['segments'], now, self.current[1])
            if reason:
                rejected.append(dict(site=destination, reason=reason))
                continue
            stages['GPU_RACK'] = True
            score, reason = self._score(metadata, migration['segments'], now, baseline)
            if reason:
                rejected.append(dict(site=destination, reason=reason))
                continue
            key = lambda s, burden: (round(s['grid_peak'], 12), s['loading_hours'], s['risk_GPUh'], burden)
            if stay_score is not None and key(score, migration['interruption_seconds']) >= key(stay_score, 0):
                rejected.append(dict(site=destination, reason='FEASIBLE_STAY_RANK_PREFERRED'))
                continue
            rows.append((key(score, migration['interruption_seconds']), destination, cap, migration, score))
        for _, destination, cap, migration, score in sorted(rows, key=lambda x:(x[0], x[1])):
            if reserve:
                ok, reason = reservations.reserve(metadata['uid'], migration['segments'], replace=True)
                if not ok:
                    rejected.append(dict(site=destination, reason=reason))
                    continue
                metadata['migration_capability'] = cap
            stages['SELECTED'] = True
            self.funnel.append(dict(uid=metadata['uid'], time_seconds=now,
                reason='FEASIBLE_MIGRATION_REPLACES_INFEASIBLE_STAY' if stay_score is None else 'SELECTED', **stages))
            return self._record(metadata, now, dict(action='CHECKPOINT_MIGRATE', status='SIGNED_MIGRATION_SELECTED',
                migration=migration, tracking={k:v for k,v in score.items() if k != 'profile'}), began, len(rows), rejected)
        return stay(rejected[-1]['reason'] if rejected else 'NO_DESTINATION')


def safe_backfill(metadata, *, now, site, reservations, uid, evidence_scope='REAL_DIAGNOSTIC'):
    """Q50/Q90 cannot prove completion before the next committed reservation."""
    peers = []
    for other, row in reservations.reservations.items():
        if other != uid and row.get('status') != 'RELEASED':
            peers.extend(row.get('segments', []))
    for other, rows in getattr(reservations, 'known_plans', {}).items():
        if other != uid:
            peers.extend(rows)
    starts = [s['begin'] for s in peers if s['resource'] == 'gpu:'+site and s['begin'] > now]
    next_booking = min(starts, default=None)
    if next_booking is None:
        return True, 'NO_FUTURE_COMMITTED_BOOKING'
    # The current real Runtime Provider has no validated finite deterministic
    # completion-bound registry. Arbitrary request metadata is not a provider
    # certificate; positive finite-bound witnesses remain named fixtures.
    if not evidence_scope.startswith('NAMED_'):
        return False, 'VALIDATED_NONPREEMPTIVE_RUNTIME_BOUND_PROVIDER_NOT_AVAILABLE'
    upper = metadata.get('source_runtime_upper_bound_seconds')
    authority = metadata.get('runtime_upper_bound_authority', {})
    if upper is None or not authority.get('source_sha') or authority.get('observed_at_seconds', math.inf) > now:
        return False, 'NO_SOURCE_CERTIFIED_RUNTIME_UPPER_BOUND'
    if not math.isfinite(float(upper)) or upper <= 0 or now+upper > next_booking:
        return False, 'UPPER_BOUND_CROSSES_COMMITTED_RESERVATION'
    segments = [dict(resource='gpu:'+site, begin=now, end=now+upper, quantity=metadata['gpu'])]
    reason = reservations.feasible(segments, exclude=uid)
    return reason is None, reason or 'SOURCE_UPPER_BOUND_FITS_COMMITTED_RESERVATION'
