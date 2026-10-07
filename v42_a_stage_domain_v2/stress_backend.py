"""Frozen B1 scientific interfaces with fresh exact V2 lex stage matrices.

Only the sequential qualification runner invokes this adapter. Large static
matrices live outside Git; their immutable byte receipts remain in the review.
No historical point, bound, objective lock or elapsed solve clock is imported.
"""
from pathlib import Path
from fractions import Fraction
from dataclasses import asdict
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from . import AUTHORITY
from .census import load_frozen, PRODUCTION, digest as scientific_digest
from .domain import prepare_active
from .execution import tag_model_for_day
from .lexstage import (Objective, LinearSnapshot, LexLock, rebuild_locked_snapshot,
    project_migration_zero, lift_zero_projection, integer_objective_proof,
    integer_optimality_certificate)
from .stress_runner import StageBuild
from v42_pr134_b1.common import atomic, read, record, digest

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/v42_a_stage_domain_authority_v2_20261007'
STATIC=Path('C:/v42_a_stage_v2_stress4_20261007/static')


def snapshot_of(model, objectives):
    model.update()
    result=[]
    for name,expr in objectives:
        expression=gp.LinExpr(expr)
        terms=tuple((int(expression.getVar(i).index),Fraction(expression.getCoeff(i)))
                    for i in range(expression.size()))
        result.append(Objective(name,terms,Fraction(expression.getConstant())))
    return LinearSnapshot(model.getA(),np.asarray(model.getAttr('LB')),
        np.asarray(model.getAttr('UB')),np.asarray(model.getAttr('Sense')),
        np.asarray(model.getAttr('RHS')),np.asarray(model.getAttr('VType')),
        tuple(result)).require()


def expressions(snapshot, variables):
    result=[]
    for objective in snapshot.objectives:
        terms=objective.coefficients()
        coefficients=[float(v) for v in terms.values()]
        if any(Fraction(v)!=exact for v,exact in zip(coefficients,terms.values())):
            raise ValueError('NONEXACT_NATIVE_OBJECTIVE_MATERIALIZATION')
        if Fraction(float(objective.constant))!=objective.constant:
            raise ValueError('NONEXACT_NATIVE_OBJECTIVE_CONSTANT')
        result.append((objective.name,gp.LinExpr(coefficients,[variables[j] for j in terms])+float(objective.constant)))
    return result


def materialize(snapshot,day):
    snapshot.require()
    model=gp.Model('A_STAGE_V2_FRESH_LOCKED_STAGE');model.Params.OutputFlag=0
    tag_model_for_day(model,day)
    x=model.addMVar(snapshot.matrix.shape[1],lb=snapshot.lower,ub=snapshot.upper,vtype=snapshot.vtypes)
    model.addMConstr(snapshot.matrix,x,snapshot.senses,snapshot.rhs);model.update()
    difference=model.getA()-snapshot.matrix;difference.eliminate_zeros()
    if difference.nnz:raise ValueError('FRESH_LOCKED_STAGE_MATRIX_DRIFT')
    for attr,expected in [('LB',snapshot.lower),('UB',snapshot.upper),('Sense',snapshot.senses),
                          ('RHS',snapshot.rhs),('VType',snapshot.vtypes)]:
        if not np.array_equal(np.asarray(model.getAttr(attr)),expected):
            raise ValueError('FRESH_LOCKED_STAGE_'+attr+'_DRIFT')
    return model,expressions(snapshot,model.getVars())


def row_replay(snapshot,point):
    point=np.asarray(point,dtype=float)
    if point.ndim!=1 or len(point)!=snapshot.matrix.shape[1] or not np.all(np.isfinite(point)):
        raise ValueError('FINITE_ORIGINAL_COLUMN_AXIS_POINT_REQUIRED')
    activity=snapshot.matrix@point
    violation=np.maximum(0,np.where(snapshot.senses=='<',activity-snapshot.rhs,
        np.where(snapshot.senses=='>',snapshot.rhs-activity,abs(activity-snapshot.rhs))))
    bounds=np.maximum(0,np.maximum(snapshot.lower-point,point-snapshot.upper))
    integer=abs(point[snapshot.vtypes!='C']-np.rint(point[snapshot.vtypes!='C']))
    worst=int(np.argmax(violation)) if len(violation) else None
    return dict(PASS=max(violation.max(initial=0),bounds.max(initial=0),integer.max(initial=0))<=1e-5,
        original_authority_tolerance=1e-5,all_rows_replayed=snapshot.matrix.shape[0],
        all_columns_replayed=snapshot.matrix.shape[1],max_row_violation=float(violation.max(initial=0)),
        max_bound_violation=float(bounds.max(initial=0)),max_integrality_residual=float(integer.max(initial=0)),
        worst_row_index=worst,raw_point_rounded_or_clipped=False)


class Backend:
    def __init__(self):
        self.base=None;self.current=None;self.mapping=None;self.descriptor=None
        self.data=None;self.coeff=None;self.domains=None;self.last_verification=None
        self.model=None

    def _initial(self,day,folder):
        from v42_pr134_b1.native import bind
        from v42_pr134_sc.snapshot import capture
        from v42_two.contract import aidc_groups,passes
        from v42_integrated.contract import physical_authority,all_transformer_rows
        import v42_boundary.model as boundary
        data,frozen=load_frozen(day)
        census=read(DOCS/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json'))
        inputs=PRODUCTION/'inputs'/day
        bundle=read(inputs/'NATIVE_INPUT.json')
        if scientific_digest(bundle)!=scientific_digest(data[0]):raise ValueError('FROZEN_INPUT_BUNDLE_DRIFT')
        preregistered=read(ROOT/'docs/v42_a_stage_v2_stress4_20261007/STATIC_SOURCE_DATA_IDENTITY.json')['dates'][day]
        for field,path in [('DATA_file',frozen/'DATA.pkl'),('frozen_native_input',inputs/'NATIVE_INPUT.json')]:
            expected=preregistered[field]
            if record(path)['sha256']!=expected['sha256']:
                raise ValueError('PREREGISTERED_'+field+'_HASH_DRIFT')
        if scientific_digest(asdict(data[3]))!=preregistered['resources_sha256']:
            raise ValueError('PREREGISTERED_PHYSICAL_RESOURCE_DRIFT')
        self.data,self.domains=prepare_active(data,complete_stay=True)
        if not self.data[7]['complete_stay_active']:raise ValueError('FULL_ORIGINAL_STAY_ACTIVATION_FAILED')
        static=STATIC/day;static.mkdir(parents=True,exist_ok=True)
        module,native,self.coeff,*_=bind(bundle,inputs,static)
        class Context:
            def __init__(self):self.folder=static
            def check(self):pass
            def progress(self,value):atomic(folder/'BUILD_PROGRESS.json',dict(day=day,**value))
        old=boundary.add_grid;boundary.add_grid=all_transformer_rows(old)
        boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
        try:
            with physical_authority():
                model,units,levels,controls,bindings=native.build(Context(),self.data,'F2-CRA')
        finally:
            boundary.add_grid=old;boundary.planning_grid.__globals__['add_grid']=old
        objectives=[(name,expr) for _,name,expr in passes(aidc_groups(levels,units,self.data))]
        self.base=snapshot_of(model,objectives);self.current=self.base
        self.model=model
        self.mapping=np.arange(self.base.matrix.shape[1],dtype=np.int64)
        self.descriptor=capture(model,units,levels,controls,bindings,static/'SCIENTIFIC_INTERFACES.pkl.gz')
        sp.save_npz(static/'V2_ACTIVE_ORIGINAL_MATRIX.npz',self.base.matrix)
        np.savez_compressed(static/'V2_ACTIVE_ORIGINAL_ATTRIBUTES.npz',lower=self.base.lower,
            upper=self.base.upper,senses=self.base.senses,rhs=self.base.rhs,vtypes=self.base.vtypes)
        proofs={name:integer_objective_proof(self.base,name) for name in ('migration_count','shift_magnitude','prestart_relocation')}
        atomic(folder/'ACTUAL_OBJECTIVE_INTEGRALITY.json',proofs)
        identity=dict(PASS=True,day=day,input=record(inputs/'NATIVE_INPUT.json'),
            frozen_data=record(frozen/'DATA.pkl'),resource_sha256=scientific_digest(asdict(self.data[3])),
            original_frozen_bundle_sha256=scientific_digest(bundle),new_authority=AUTHORITY,
            source_matrix_sha256=self.base.fingerprint(),historical_lock_imported=False,
            historical_point_imported=False,historical_bound_imported=False,
            CC4_Runtime_service_GPU_WAN_grid_physics_changed=False)
        domain=dict(census,qualification_active_STAY_options=census['hard_valid_STAY_starts'],
            qualification_lazy_STAY_options=0,qualification_complete_STAY_active=True,
            qualification_representation=self.data[7]['stay_active_policy'],
            migration_integer_closure_proven=False,physical_domain_hash=self.data[7]['physical_domain_hash'])
        metadata=dict(scientific_identity_PASS=True,STAY_DOMAIN_COMPLETE=True,
            input_identity=identity,domain_census=domain,
            actual_objective_integrality=proofs,static_artifacts=[record(static/name) for name in
                ('V2_ACTIVE_ORIGINAL_MATRIX.npz','V2_ACTIVE_ORIGINAL_ATTRIBUTES.npz','SCIENTIFIC_INTERFACES.pkl.gz')],
            base_matrix_sha256=self.base.fingerprint(),historical_warm_start_used=False,
            migration_pricing_state='UNRESOLVED: no verified native LP path-column projection; do not infer closure')
        return StageBuild(model,units,objectives,controls,bindings,self.data,self.coeff,metadata)

    def build(self,day,folder,component,locks,previous):
        if component=='rho':
            if locks or previous is not None:raise ValueError('FRESH_RHO_HAS_NO_HISTORICAL_LOCKS')
            return self._initial(day,folder)
        if previous is None or previous['stage']['active_domain_objective_proven'] is not True:
            raise ValueError('NEW_RUN_PROVEN_PREVIOUS_OBJECTIVE_REQUIRED')
        warm_original=lift_zero_projection(previous['point'],self.mapping)
        exact=[]
        for lock in locks:
            if lock.get('current_new_run_only') is not True or lock.get('historical_lock_imported') is not False:
                raise ValueError('HISTORICAL_LEX_LOCK_REJECTED')
            value=lock['optimum'] if lock['component']=='rho' else int(round(lock['optimum']))
            exact.append(LexLock(lock['component'],value,True,digest(lock),1e-7 if lock['component']=='rho' else 0))
        current,rebuild=rebuild_locked_snapshot(self.base,exact)
        projection=None;mapping=np.arange(self.base.matrix.shape[1],dtype=np.int64)
        migration=next((lock for lock in exact if lock.component=='migration_count'),None)
        if migration is not None and migration.value==0:
            source=current
            current,mapping,proof=project_migration_zero(source,migration_lock_row=rebuild['lock_rows']['migration_count'])
            projection=proof.verify(source)
            atomic(folder/'ACTUAL_ZERO_PROJECTION_PROOF.json',dict(projection,proof=asdict(proof)))
        strengthening=None
        if component in ('shift_magnitude','prestart_relocation'):
            from .strengthening import strengthen_histogram_capacity,verify_histogram_capacity_strengthening
            before_cuts=current
            current,strengthening=strengthen_histogram_capacity(self.base,current,self.descriptor,self.data,mapping)
            independently_verified=verify_histogram_capacity_strengthening(
                self.base,before_cuts,current,self.descriptor,self.data,mapping,strengthening)
            if independently_verified.get('PASS') is not True:
                raise ValueError('INTEGER_STRENGTHENING_INDEPENDENT_VERIFICATION_FAIL')
            atomic(folder/'ACTUAL_SHIFT_STRENGTHENING.json',dict(strengthening,
                independent_verification=independently_verified))
        atomic(folder/'ACTUAL_LEX_REBUILD_PROOF.json',rebuild)
        previous['native_model'].dispose()
        model,objectives=materialize(current,day)
        keep=np.flatnonzero(mapping>=0)
        warm=warm_original[keep]
        warm_audit=row_replay(current,warm)
        if warm_audit['PASS']:
            model.setAttr('Start',warm.tolist())
        atomic(folder/'CURRENT_RUN_WARM_START_AUDIT.json',dict(warm_audit,
            loaded=warm_audit['PASS'],historical_point_imported=False,source='PREVIOUS_NEWLY_VERIFIED_LEX_STAGE'))
        self.current=current;self.mapping=mapping;self.last_verification=None
        self.model=model
        return StageBuild(model,None,objectives,None,None,self.data,self.coeff,
            dict(previous['metadata'],stage_rebuild=rebuild,migration_zero_projection=projection,
                 integer_strengthening=strengthening,
                 stage_equivalence=dict(PASS=rebuild['PASS'] and (projection is None or projection['PASS']),
                    same_original_integer_schedules_plus_current_locks=True,
                    same_LP_projection_before_valid_strengthening=True,
                    same_LP_projection_after_strengthening_asserted=False,
                    only_independently_verified_integer_valid_strengthening=True),
                 current_run_warm_start_loaded=warm_audit['PASS'],
                 current_locked_matrix_sha256=current.fingerprint()))

    def verify(self,build,point,component):
        from v42_pr134_sc.snapshot import certify
        from v42_integrated.contract import physical_authority
        lifted=lift_zero_projection(point,self.mapping)
        current=row_replay(self.current,point);original=row_replay(self.base,lifted)
        with physical_authority():
            physical,selected,controls,_=certify(self.descriptor,self.data,lifted,original,self.coeff)
        result=dict(PASS=current['PASS'] and physical['PASS'],physical=physical,selected_jobs=selected,
            controls=controls,current_locked_rows=current,base_original_rows=original,
            source_matrix_sha256=self.current.fingerprint(),historical_point_used=False,
            exact_zero_lift_used=bool(np.any(self.mapping<0)))
        self.last_verification=result
        return result

    def integer_certificate(self,component,incumbent,valid_lower_bound):
        proof=integer_objective_proof(self.current,component)
        # The global bound belongs to this newly solved, exact locked matrix.
        # Its scope is explicitly active-only; an omitted-pool bound is not used.
        fingerprint=self.current.fingerprint()
        objective=self.current.objective(component)
        expected_objective=np.zeros(self.current.matrix.shape[1])
        for column,value in objective.coefficients().items():expected_objective[column]=float(value)
        objective_current=bool(self.model is not None
            and np.array_equal(np.asarray(self.model.getAttr('Obj')),expected_objective)
            and float(self.model.ObjCon)==float(objective.constant))
        bound_current=bool(self.model is not None and self.model.Status in (gp.GRB.OPTIMAL,gp.GRB.TIME_LIMIT)
            and self.model.SolCount>0 and float(self.model.ObjVal)==incumbent
            and float(self.model.ObjBound)==valid_lower_bound and objective_current)
        primal_current=bool(self.last_verification and self.last_verification['PASS']
            and self.last_verification['source_matrix_sha256']==fingerprint)
        result=integer_optimality_certificate(component,incumbent,valid_lower_bound,
            bound_independently_validated=bound_current,
            primal_independently_validated=primal_current,
            integrality_proven=proof['PASS'])
        return dict(result,objective_integrality=proof,current_matrix_sha256=fingerprint,
            current_native_objective_coefficients_verified=objective_current,
            bound_source='CURRENT_NATIVE_ACTIVE_MATRIX_GLOBAL_BOUND',historical_bound_used=False)

    def domain_closure(self,build,result):
        status=dict(result['domain_status'])
        status.update(LP_PRICING_CLOSED=False,MIGRATION_PRICING_CLOSED=False,
            INTEGER_DOMAIN_CLOSURE_PROVEN=False,PRODUCTION_DOMAIN_ACCEPTED=False,
            scientific_full_domain_optimal=False,
            closure_limitation='Native mixed flow LP is not yet independently proven equivalent to a physical path-column master. No branch-and-price/full integer closure certificate exists.',
            all_scientific_objectives_certified=False)
        return status
