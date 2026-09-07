"""Deterministic family sweeps; raw-candidate coverage is audit-only.

This module controls compute, never model rows, candidate domains or locks.
Each sweep visits five families in order. A family's wall-time slice can
contain several complete-job neighborhoods. Improving the CURRENT objective
restarts a normal sweep. A stagnant normal sweep gets one overlapping sweep.
"""
import math

VERSION = 'V41R1_FAMILY_SWEEP_EARLY_STOP_V2'
FAMILIES = ('ELECTRICAL_CRITICAL_WINDOW', 'IDC_BLOCK',
            'RUNNING_MIGRATION_BLOCK', 'PENDING_RELOCATION_BLOCK', 'COVERAGE')
GUARDS = (900., 480., 180., 120., 120.)
NORMAL_SECONDS = (420., 180., 45., 45., 30.)
DIVERSIFICATION_SECONDS = (150., 90., 30., 30., 0.)
TOLERANCES = (1e-10, 1e-9, 0., 0., 0.)
STAGES = {
    'PRIMARY_MIN_RHO': 0, 'rho_max': 0,
    'V41_SECONDARY_MIN_MEAN_H4_SHORTFALL': 1, 'V41_mean_H4_shortfall_GPUh': 1,
    'SECONDARY_MIN_MIGRATIONS': 2,
    'TERTIARY_COMPLETE_REFERENCE_DEVIATION': 3,
    'complete_segment_site_symmetric_GPU_slots': 3,
    'QUATERNARY_STABLE_TIE': 4, 'deterministic_tie': 4,
    **{f'P{i+1}': i for i in range(5)},
}


def material_improvement(before, after, priority, accepted):
    # isclose prevents subtraction rounding at exactly the established
    # tolerance from spuriously resetting stagnation. No feasibility change.
    delta = float(before[priority]) - float(after[priority])
    tol = TOLERANCES[priority]
    return bool(accepted and delta > tol and not math.isclose(delta, tol, rel_tol=1e-6, abs_tol=0.))


class FamilySweep:
    def __init__(self, priority, used, scale=1.):
        self.priority=priority; self.scale=scale; self.sweep_id=0
        self.material_improvements=0; self.normal_completed=0; self.diversification_completed=0
        self.normal_started=0; self.diversification_started=0; self.records=[]
        self.stage_families=set(); self.reason=None
        self._begin('NORMAL', used)

    def _begin(self, mode, used):
        self.mode=mode; self.sweep_id+=1; self.family_index=0
        self.sweep_started=used; self.family_started=used; self.families=set(); self.neighborhoods=0
        if mode=='NORMAL': self.normal_started+=1
        else: self.diversification_started+=1

    @property
    def family(self): return FAMILIES[self.family_index]

    @property
    def family_seconds(self):
        durations=NORMAL_SECONDS if self.mode=='NORMAL' else DIVERSIFICATION_SECONDS
        return durations[self.priority]*self.scale/len(FAMILIES)

    def _record(self, used, reason):
        self.records.append(dict(sweep_id=self.sweep_id, mode=self.mode,
            families_completed=sorted(self.families), family_coverage_fraction=len(self.families)/len(FAMILIES),
            runtime_seconds=used-self.sweep_started, neighborhoods=self.neighborhoods, reason=reason))

    def observe(self, used, material):
        self.stage_families.add(self.family); self.neighborhoods+=1
        if material:
            self.material_improvements+=1; self._record(used, 'MATERIAL_CURRENT_OBJECTIVE_IMPROVEMENT')
            self._begin('NORMAL', used); return True
        if used-self.family_started < self.family_seconds: return False
        self.families.add(self.family)
        if self.family_index < len(FAMILIES)-1:
            self.family_index+=1; self.family_started=used; return False
        self._record(used, 'COMPLETED_NO_MATERIAL_IMPROVEMENT')
        if self.mode=='NORMAL':
            self.normal_completed+=1
            if self.priority==4:
                self.reason='NORMAL_FAMILY_SWEEP_NO_IMPROVEMENT'; return False
            self._begin('DIVERSIFICATION', used); return True
        self.diversification_completed+=1
        self.reason='FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT'
        return False

    def finish(self, used, reason):
        if not self.reason: self._record(used, reason)
        self.reason=self.reason or reason

    def metrics(self):
        return dict(compute_control_version=VERSION, stage_priority=f'P{self.priority+1}',
            STAGE_SWEEP_ID=self.sweep_id, sweep_mode=self.mode, current_family=self.family,
            stage_family_coverage_fraction=len(self.stage_families)/len(FAMILIES),
            stage_families_opened=sorted(self.stage_families),
            sweep_family_coverage_fraction=len(self.families)/len(FAMILIES),
            material_improvements=self.material_improvements,
            normal_sweeps_started=self.normal_started, normal_sweeps_completed=self.normal_completed,
            diversification_sweeps_started=self.diversification_started,
            diversification_sweeps_completed=self.diversification_completed,
            termination_reason=self.reason, sweeps=self.records,
            raw_candidate_coverage_required_for_stopping=False)


def objective_floor(priority, vector, *, production_verified):
    """Analytical floors of the original, independently audited objectives.

    P2 is mean nonnegative H4 xi; P3 is a count of migrations; P4 is
    GPU-weighted full occupancy symmetric difference. Factorization may have
    negative coefficients but cannot change this nonnegative original metric.
    These certificates concern this stage under accepted higher-priority locks,
    and do NOT certify earlier F&O stages or the joint lexicographic solution.
    """
    if not production_verified or priority not in (1,2,3): return None
    if vector[priority] != 0.: return None
    return dict(bound=0., incumbent=0., gap=0.,
        scope='CURRENT_OBJECTIVE_UNDER_ACCEPTED_HIGHER_PRIORITY_LOCKS',
        proof={1:'MEAN_OF_NONNEGATIVE_H4_SHORTFALL', 2:'NONNEGATIVE_MIGRATION_COUNT',
               3:'NONNEGATIVE_GPU_WEIGHTED_OCCUPANCY_SYMMETRIC_DIFFERENCE'}[priority],
        joint_lexicographic_global_certificate=False)


def current_structure(engine, priority):
    """Recompute priorities from the accepted physical state, without pruning."""
    import numpy as np
    if engine.context is None: return dict(critical_issue_slot=24, near_binding_electrical_set=[], reserve_stress=[])
    ctx=engine.context; names={n:i for i,n in enumerate(engine.names)}
    sites=tuple(ctx.capacity.aidc_ids)
    pcc=np.asarray([[engine.values[names[f'PCC[{t},{s}]']] for s in sites] for t in range(96)])
    from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
    controls=controls_from_trajectory(ctx.coefficients, pcc, engine.fixed_mess)
    grid=evaluate_grid(ctx.coefficients, controls, ctx.nodes)
    result=dict(critical_issue_slot=24+grid['critical_slot'], critical_branch=grid['critical_line'],
        critical_phase=grid['critical_phase'], rho_max=grid['rho_max'], near_binding_electrical_set=[], reserve_stress=[])
    if priority==0:
        from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading, is_dominated_mess_current_row
        threshold=grid['rho_max']-.01*max(abs(grid['rho_max']),1e-12)
        for t,(coeff,x) in enumerate(zip(ctx.coefficients,controls)):
            loads=anchored_polygon_loading(coeff,x)
            for k,n in enumerate(coeff.branch_names):
                if not n.startswith('transformer.') and not is_dominated_mess_current_row(n) and loads[k]>=threshold:
                    result['near_binding_electrical_set'].append(dict(branch=n, phase=n.rsplit('::',1)[-1], issue_slot=t+24, loading=float(loads[k])))
        result['near_binding_threshold']=threshold
        result['near_binding_scope']='PRIORITIZATION_ONLY; ALL_CANDIDATES_RETAINED'
    if priority==1:
        from dayahead.v41.reserve import diagnostics
        gpu=np.asarray([[engine.values[names[f'GPU[{t},{s}]']] for s in sites] for t in range(96)])
        reserve=diagnostics(ctx.v41_ml_snapshot,ctx.capacity,gpu)
        eligible=ctx.v41_ml_snapshot['future_service_eligible_sites']
        for k,xi in enumerate(reserve['xi_GPUh']):
            if xi<=0: continue
            for s in eligible:
                result['reserve_stress'].append(dict(site=s,start=k+24,end=k+40,shortfall_GPUh=xi,
                    occupancy_GPUh=float(.25*gpu[k:k+16,sites.index(s)].sum())))
        result['reserve_stress'].sort(key=lambda r:(-r['shortfall_GPUh'],-r['occupancy_GPUh'],r['start'],r['site']))
    return result
