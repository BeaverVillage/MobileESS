"""Fixed finite PRESTART experiment; never optimize earlier objectives or days."""
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import gzip,pickle,time,hashlib,subprocess,shutil
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import atomic,read,record
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_acceptance.schedule_audit import original_schedule_metrics
from .isolation import ROOT,OUT,STATIC,assert_write_path,require_large_resource_isolation
from .inspect_saved import BASELINE
from .proofs import cutoff_global_bound
from .cuts import original_histograms
from .native import solve


def cutoff(snapshot):
    coefficients=snapshot.objective('prestart_relocation').coefficients()
    row=sp.csr_matrix(([float(v) for v in coefficients.values()],
        ([0]*len(coefficients),list(coefficients))),shape=(1,snapshot.matrix.shape[1]))
    return replace(snapshot,matrix=sp.vstack((snapshot.matrix,row),format='csr'),
        senses=np.r_[snapshot.senses,['<']],rhs=np.r_[snapshot.rhs,59.]).require()


def load_context():
    require_large_resource_isolation()
    with gzip.open(STATIC/'REBUILT_CONTEXT.pkl.gz','rb') as stream:ctx=pickle.load(stream)
    with gzip.open(STATIC/'STRENGTHENED_SNAPSHOT.pkl.gz','rb') as stream:strengthened=pickle.load(stream)
    return ctx,strengthened


def prepare():
    ctx,strong=load_context();sub=cutoff(strong)
    checks=read(OUT/'COMPRESSION_VALIDATION.json');cuts=read(OUT/'VALID_INEQUALITY_VERIFICATION.json')
    if not checks['PASS'] or not cuts['PASS']:raise ValueError('EXACT_CORRECTNESS_GATES_REQUIRED')
    if (OUT/'NEW_NATIVE_CALLS.json').exists() or (OUT/'BENCHMARK_PLAN.json').exists():
        raise PermissionError('NO_NEW_NATIVE_PLAN_RESET')
    cases=[]
    for name,snapshot,seconds,relax,presolve in (
        ('B0_SOURCE_LP',ctx['query'],90,True,-1),
        ('B1_COMPACT_LP',ctx['reduction'].compact,90,True,-1),
        ('B2_CUTS_LP',strong,90,True,-1),
        ('B1_COMPACT_MIP',ctx['reduction'].compact,480,False,-1),
        ('B2_CUTS_MIP',strong,2100,False,1),
        ('B3_CUTOFF_MIP',sub,660,False,1)):
        cases.append(dict(name=name,snapshot_sha256=snapshot.fingerprint(),seconds=seconds,relax=relax,presolve=presolve))
    plan=dict(day='2025-05-10',component='prestart_relocation',cases=cases,
        planned_native_seconds=3510,reserve_seconds=90,Threads=1,simultaneous_native_calls=1,
        parameter_sweep=False,success_gap=.005,stop_if_full_domain_gap_accepted=True,
        B0_MIP_is_saved_original_baseline_no_rerun=True,
        LP_candidates_are_diagnostics_not_integer_feasibility_claims=True,
        B1_auto_presolve_B2_conservative_is_separate_algorithmic_candidate=True,
        B3_full_original_integer_partition_PRE_le_59_complement_PRE_ge_60=True,
        incumbent_UB60_preserved=True,no_memory_limit_or_memory_stop=True,
        original_physics_objectives_tolerances_unchanged=True,
        source_exact_base='1b891dbe5b1dd454d89b657efec7cba469c0cf94',
        gurobi_parameter_reference='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html')
    atomic(OUT/'BENCHMARK_PLAN.json',plan)
    atomic(OUT/'NEW_NATIVE_CONTINUATION_BUDGET.json',dict(day='2025-05-10',native_limit_seconds=3600,
        continuation='MAY10_PRESTART_EXACT_RESCUE_20261008',historical_native_seconds=3623.4080016613007,
        old_budget_and_receipts_immutable=True,planned_native_seconds=3510,
        accounting='sum actual native Runtime; includes presolve, root, search, callbacks',
        memory_limit=None,automatic_memory_termination=False))
    print('FIXED_BENCHMARK_PLAN_READY',len(cases),3510,flush=True)


def freeze():
    if (OUT/'NATIVE_SOURCE_FREEZE.json').exists():raise PermissionError('NO_SOURCE_FREEZE_RESET')
    githead=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    if status:raise PermissionError('COMMIT_REVIEWABLE_NEW_CODE_BEFORE_NATIVE')
    sources={};archive=assert_write_path(STATIC/'EXECUTED_SOURCES')
    for path in sorted(ROOT.rglob('*.py')):
        if any(part in ('.git','__pycache__','.venv') for part in path.parts):continue
        sources[str(path)]=record(path)['sha256']
        target=assert_write_path(archive/path.relative_to(ROOT));target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
    atomic(OUT/'NATIVE_SOURCE_FREEZE.json',dict(git_head=githead,sources=sources,
        archived_sources_directory=str(archive),source_count=len(sources),
        plan_sha256=record(OUT/'BENCHMARK_PLAN.json')['sha256'],
        budget_sha256=record(OUT/'NEW_NATIVE_CONTINUATION_BUDGET.json')['sha256'],
        may12_mutated=False,source_epoch=1))
    print('NEW_NATIVE_SOURCE_FROZEN',githead,len(sources),flush=True)


def linear_value(snapshot,name,x):
    o=snapshot.objective(name);co=o.coefficients()
    return float(o.constant)+float(np.dot(np.fromiter(co.values(),float),x[np.fromiter(co,int)]))


def lp_diagnostics(ctx,snapshot,x,attrs,name):
    raw=x if name=='B0_SOURCE_LP' else ctx['reduction'].inverse(x)
    original=ctx['query'];integer=original.vtypes!='C'
    fractional=integer & (abs(raw-np.rint(raw))>1e-5)
    activity=original.matrix@raw;distance=np.abs(activity-original.rhs)
    axes={}
    for (kind,site,t),row in ctx['physical_state']['axes'].items():
        item=axes.setdefault(kind,dict(rows=0,active_within_1e6=0))
        item['rows']+=1;item['active_within_1e6']+=int(distance[row]<=1e-6)
    groups=[]
    for g in original_histograms(ctx['physical_state'],original):
        entries=g['entries'];cols=np.fromiter(entries.values(),int)
        count=int(fractional[cols].sum())
        if not count:continue
        mass={};remote=0.;shift=0.
        for (site,t),j in entries.items():
            if abs(raw[j])<=1e-8:continue
            mass[site]=mass.get(site,0.)+float(raw[j])
            remote+=float(raw[j])*(site!=g['reference_site']);shift+=float(raw[j])*abs(t-g['reference_start'])
        groups.append(dict(class_id=g['class_id'],jobs=g['cardinality'],fractional_starts=count,
            start_site_mass=mass,prestart_mass=remote,shift_mass=shift))
    diagnostics=dict(raw_primal_available=True,source_original_linear_replay=primal_replay(original,raw),
        relaxed_native_linear_replay=primal_replay(snapshot,x),
        original_integer_coordinates=int(integer.sum()),fractional_integer_coordinates=int(fractional.sum()),
        fractional_binary_coordinates=int((fractional&(original.vtypes=='B')).sum()),
        fractional_original_histogram_classes=len(groups),top_fractional_histograms=sorted(groups,key=lambda g:-g['fractional_starts'])[:25],
        all_four_original_affine_objectives={o.name:linear_value(original,o.name,raw) for o in original.objectives},
        coupling_axes=axes,minimum_activity_distance=float(distance.min(initial=float('inf'))),
        no_rounding_no_clipping=True,integer_or_physical_schedule_authority=False,
        original_global_and_local_rows=len(distance))
    if 'Pi' in attrs and 'RC' in attrs:
        diagnostics['native_raw_dual_RC_sign_replay']=verify_sign_convention(snapshot,attrs['Pi'],attrs['RC'])
    atomic(OUT/'NATIVE'/name/'LP_DIAGNOSTICS.json',diagnostics)


def run():
    started=time.perf_counter();ctx,strong=load_context();reduction=ctx['reduction'];query=ctx['query']
    plan=read(OUT/'BENCHMARK_PLAN.json')
    from v42_a_stage_acceptance import physical
    physical.STATIC=STATIC/'BENCH_ORIGINAL_PHYSICAL'
    replay=physical.Physical(ctx['physical_state'],ctx['original'])
    best=dict(UB=60,LB=2.,point=ctx['warm'].copy(),source='INHERITED_VALIDATED_UB60',physical_PASS=True)
    callback_validation=[]
    def validate(compact,name):
        raw=reduction.inverse(compact)
        if not primal_replay(query,raw)['PASS']:raise ValueError('RESTORED_ORIGINAL_FULL_QUERY_REPLAY_FAILED')
        iv=query.vtypes!='C'
        if np.max(abs(raw[iv]-np.rint(raw[iv])),initial=0)>1e-5:raise ValueError('ORIGINAL_INTEGER_TOLERANCE_FAILED')
        objective=linear_value(query,'prestart_relocation',raw)
        if objective>=best['UB']-1e-5:return
        verification=replay.verify(raw)
        if not verification['PASS']:raise ValueError('INDEPENDENT_ORIGINAL_PHYSICAL_FAILED')
        values={o.name:linear_value(query,o.name,raw) for o in query.objectives}
        metrics,residuals=original_schedule_metrics(ctx['physical_state']['data'][1],verification['selected_jobs'],values)
        if metrics['migration_count']!=0 or metrics['shift_magnitude']!=74:
            raise ValueError('FROZEN_MIGRATION_SHIFT_LOCK_DRIFT')
        if abs(objective-metrics['prestart_relocation'])>1e-5:
            raise ValueError('ORIGINAL_INTEGER_PRESTART_COUNT_DRIFT')
        best.update(UB=metrics['prestart_relocation'],point=raw.copy(),source=name,physical_PASS=True)
        receipt=dict(case=name,original_full_query=primal_replay(query,raw),physical=verification,
            schedule_objectives=metrics,affine_objectives=values,objective_residuals=residuals,
            original_point_rounded_or_clipped=False,artificial_variables=0)
        path=OUT/'NATIVE'/name/f"VALIDATED_UB_{best['UB']}.json";atomic(path,receipt)
        point=assert_write_path(STATIC/'NATIVE'/name/f"VALIDATED_UB_{best['UB']}.npz")
        point.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(point,X=raw)
        callback_validation.append(dict(UB=best['UB'],case=name,physical=record(path),point=record(point)))
        atomic(OUT/'VALIDATED_NEW_UB_TRAJECTORY.json',dict(trajectory=callback_validation))
        print('INDEPENDENT_ORIGINAL_UB_VERIFIED',name,best['UB'],flush=True)
    cases={c['name']:c for c in plan['cases']}
    snapshots=dict(B0_SOURCE_LP=query,B1_COMPACT_LP=reduction.compact,B2_CUTS_LP=strong,
        B1_COMPACT_MIP=reduction.compact,B2_CUTS_MIP=strong,B3_CUTOFF_MIP=cutoff(strong))
    for name,case in cases.items():
        s=snapshots[name];warm=None
        if not case['relax'] and (name!='B3_CUTOFF_MIP' or best['UB']<=59):warm=reduction.forward(best['point'])
        result,attrs=solve(s,name,case['seconds'],relax=case['relax'],presolve=case['presolve'],warm=warm,
            validate=None if case['relax'] else validate)
        if case['relax']:
            if 'X' in attrs:
                relaxed=replace(s,vtypes=np.full(s.matrix.shape[1],'C'))
                lp_diagnostics(ctx,relaxed,attrs['X'],attrs,name)
        else:
            if 'X' in attrs:
                try:validate(attrs['X'],name)
                except Exception as error:atomic(OUT/'NATIVE'/name/'FINAL_CANDIDATE_REJECTION.json',dict(error=repr(error),old_UB60_preserved=True))
            valid_bound=result['native_error'] is None and result['status'] in (2,3,9)
            bound=None
            if valid_bound:
                if name=='B3_CUTOFF_MIP':
                    bound=cutoff_global_bound(60,59,result['ObjBound'],complete_domain=True,
                        objective_integral=True,subquery_infeasible=result['status']==3)
                    bound=None if bound is None else float(bound)
                elif result['status'] in (2,9):bound=result['ObjBound']
            if bound is not None:
                if bound>best['UB']+1e-5:raise ValueError('GLOBAL_BOUND_CONFLICTS_WITH_ORIGINAL_VALIDATED_UB')
                best['LB']=max(best['LB'],bound)
            gap=(best['UB']-best['LB'])/max(abs(best['UB']),1e-12)
            proof=dict(whole_original_575_class_integer_domain=True,compiled_model=record(OUT/'NATIVE'/name/'ACTUAL_MODEL_VERIFICATION.json'),
                compression_proof=record(OUT/'COMPRESSION_VALIDATION.json'),cuts_proof=record(OUT/'VALID_INEQUALITY_VERIFICATION.json'),
                native_result=record(OUT/'NATIVE'/name/'RESULT.json'),original_UB=best['UB'],global_LB=best['LB'],global_gap=gap,
                cutoff_complement_bound=60 if name=='B3_CUTOFF_MIP' else None,
                old_UB60_preserved=True,original_physical_PASS=best['physical_PASS'],
                full_native_query_includes_all_native_open_branches=True,native_bound_authority=valid_bound,
                accepted=gap<=.005,exact_integer_optimality=abs(best['UB']-best['LB'])<=1e-5)
            atomic(OUT/'NATIVE'/name/'FULL_DOMAIN_BOUND_AUDIT.json',proof)
            atomic(OUT/'FINAL_BENCHMARK_STATUS.json',dict(**proof,classification=(
                'PRESTART_EXACT_OPTIMALITY_PROVED' if proof['exact_integer_optimality'] else
                'PRESTART_GLOBAL_GAP_ACCEPTED' if proof['accepted'] else
                'PRESTART_BOUND_IMPROVED_NOT_ACCEPTED' if best['LB']>2 else 'PRESTART_TRACTABILITY_FAIL'),
                best_UB_source=best['source'],wall_seconds=time.perf_counter()-started))
            if proof['accepted']:break
        del attrs
    print('MAY10_PRESTART_FIXED_BENCHMARK_FINISHED',best['UB'],best['LB'],flush=True)


if __name__=='__main__':
    import sys
    {'prepare':prepare,'freeze':freeze,'run':run}[sys.argv[1]]()
