"""Original production hierarchy and fixed replay after a selected shell PASS."""
import sys,shutil,pickle,gzip
import numpy as np,scipy.sparse as sp
from .common import *
from v42_a_stage_domain_v2.execution import require_action_authorized

def main(shell):
    require_action_authorized(DAY,'A1')
    from v42_pr134_b1 import native,replay as fixed
    from v42_pr134_b1.worker import physical_validation
    from v42_pr134_b1.common import identity
    source=CASE/shell;result=read(source/'RESULT.json')
    if result['integer_witness_PASS'] is not True or result['original_full_replay_PASS'] is not True:raise PermissionError('INTEGER_FULL_REPLAY_GATE_REQUIRED')
    if not read(source/'INDEPENDENT_PHYSICAL_FEASIBILITY.json')['PASS']:raise PermissionError('PHYSICAL_GATE_REQUIRED')
    other_heavy();target=CASE/'PRODUCTION'
    if target.exists():raise PermissionError('FRESH_PRODUCTION_IDENTITY_REQUIRED')
    target.mkdir();output=target/'A1';output.mkdir()
    bundle=read(PRODUCTION/'inputs'/DAY/'NATIVE_INPUT.json')
    def progress(v):atomic(CASE/'PROGRESS.json',dict(v,shell=shell,stage='NORMAL_A1',report_UTC=now()))
    def selected_static(_bundle,input_folder,out,progress):
        if digest(_bundle)!=digest(bundle):raise PermissionError('INPUT_IDENTITY_DRIFT')
        proof=read(source/'COMPACT/COMPRESSION_VERIFICATION.json')
        if not proof['PASS']:raise PermissionError('EXACT_PROJECTION_REQUIRED')
        for k in ('original_matrix','original_attributes','reduced_matrix','proof','objective'):
            if sha(proof[k]['path'])!=proof[k]['sha256']:raise PermissionError('FROZEN_CAPTURE_DRIFT')
        # Copy immutable scientific static data only. No diagnostic point,
        # incumbent/basis, bound, lock or prior native runtime enters production.
        for p in (source/'COMPACT').glob('A2SC*'):
            if p.suffix in ('.json','.npz'):shutil.copyfile(p,out/p.name)
        shutil.copyfile(source/'EXPANDED_MATRIX.npz',out/'A0_MATRIX.npz')
        shutil.copyfile(source/'COMPACT/A0_ATTRIBUTES_CODED.npz',out/'A0_ATTRIBUTES_CODED.npz')
        shutil.copyfile(source/'SCIENTIFIC_INTERFACES.pkl.gz',out/'SCIENTIFIC_INTERFACES.pkl.gz')
        with (source/'DATA.pkl').open('rb') as f:data=pickle.load(f)
        with gzip.open(source/'SCIENTIFIC_INTERFACES.pkl.gz','rb') as f:descriptor=pickle.load(f)
        _,_,coeff,power,idle,swing=native.bind(bundle,input_folder,out)
        sc,_,_,materialize=native.sc_namespace(out);mapping=sc.proof_data('A2SC')['mapping']
        originals=read(source/'OBJECTIVES.json');projected=read(source/'COMPACT/PROJECTED_OBJECTIVES.json')
        assert [x['name'] for x in originals]==[x['name'] for x in projected]
        atomic(out/'ACTIVE_ORIGINAL_OBJECTIVES.json',originals);atomic(out/'ACTIVE_OBJECTIVES.json',projected)
        atomic(out/'BUILD_RECEIPT.json',dict(PASS=True,static_source=record(source/'STATIC_ONLY.json'),compression=proof,
               diagnostic_point_loaded=False,old_native_runtime_loaded=False,optimizer_calls=0,first_feasible_tested_shell=shell,global_minimum_claimed=False))
        a=sp.load_npz(out/'A0_MATRIX.npz');z=sc.attributes()
        return data,descriptor,a,z,mapping,projected,coeff,power,idle,swing,materialize
    old=native.build_static;native.build_static=selected_static
    try:
        native.run_a1(bundle,PRODUCTION/'inputs'/DAY,output,progress)
    except Exception as e:
        r=read(output/'A1_SOLVE_RESULT.json') if (output/'A1_SOLVE_RESULT.json').exists() else {}
        classification='MAY19_DOMAIN_FEASIBLE_BUT_PRODUCTION_TIMEOUT' if 'DATE_TIMEOUT' in str(e) else 'MAY19_PRESCREENING_UNRESOLVED'
        atomic(target/'RESULT.json',dict(classification=classification,integer_feasibility_PASS=True,normal_A1_accepted=False,error=str(e),normal_result=r))
        return
    finally:native.build_static=old
    # New local identity; original monthly production/CURRENT remains untouched.
    freeze=dict(read(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json'))
    import subprocess
    freeze.update(run_id='MAY19_PRACTICAL_RESCUE_'+shell,Git_SHA=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    atomic(target/'PIPELINE_IDENTITY.json',dict(freeze_identity=identity(freeze,DAY,'A1'),domain=record(source/'SELECTED_DOMAIN_INPUT.json'),source=BASE))
    import gurobipy as gp
    model_class=gp.Model
    class NoOptimize(model_class):
        def optimize(self,*a,**kw):
            from v42_a_stage_domain_v2.execution import guard_model_optimize
            guard_model_optimize(self)
            raise PermissionError('ACTUAL_FRESH_NATIVE_REOPTIMIZATION_FORBIDDEN')
    gp.Model=NoOptimize
    try:
        plan=target/'PLANNING_FREEZE';plan.mkdir();fixed.freeze_planning(PRODUCTION,DAY,output,plan,freeze)
        actual=target/'ACTUAL';actual.mkdir();fixed.actual(plan,identity(freeze,DAY,'PLANNING_FREEZE'),actual)
        fresh=target/'FRESH_AC';fresh.mkdir();fixed.fresh(PRODUCTION,DAY,plan,actual,fresh,freeze,progress)
        fresh_result=read(fresh/'FRESH_RESULT.json');passed=physical_validation(fresh_result)
        atomic(target/'PHYSICAL_VALIDATION.json',dict(PASS=passed,fresh=fresh_result,Actual_reoptimization=0,PQ_repair=0))
        atomic(target/'RESULT.json',dict(classification='MAY19_PRESCREENING_RESCUED' if passed else 'MAY19_PRESCREENING_UNRESOLVED',
               integer_feasibility_PASS=True,normal_A1_accepted=True,Planning_freeze_PASS=True,Actual_fixed_PASS=True,Fresh_physical_PASS=passed,
               current_monthly_production_modified=False))
    finally:gp.Model=model_class
if __name__=='__main__':main(sys.argv[1])
