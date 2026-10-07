"""Isolated date/stage process, causal immutable receipt or explicit failure."""
import sys,traceback
from .common import *
from v42_a_stage_domain_v2.execution import require_action_authorized

def physical_validation(fresh):
    s=fresh['summary']
    return bool(fresh['converged'] and s['convergence_count']==96 and all(s[k]==0 for k in
        ('voltage_violation_count','line_current_violation_count','transformer_current_violation_count','transformer_kva_violation_count'))
        and fresh['checker_SHA']==CHECKER and fresh['all_MESS_PQ_zero'] and fresh['NormalAmps_current']
        and not fresh['Planning_tap_replay'] and all(fresh[k]==0 for k in ('Actual_reoptimization','local_PQ_repair','global_PQ_repair')))

def execute(request):
    require_action_authorized(request,request.get('stage','A1'))
    root=Path(request['root']).resolve();freeze=read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json');verify_freeze(freeze)
    day,stage=request['day'],request['stage'];expected=identity(freeze,day,stage)
    if request['identity']!=expected or set(request['dependencies'])!=set(STAGES[:STAGES.index(stage)]):raise PermissionError('CAUSAL_STAGE_IDENTITY')
    for prior,r in request['dependencies'].items():
        if sha(r['receipt'])!=r['sha256'] or not valid_receipt(read(r['receipt']),identity(freeze,day,prior),root):raise PermissionError('CAUSAL_DEPENDENCY_SHA')
    output=Path(request['output']).resolve()
    if not output.is_relative_to(root) or output.exists():raise PermissionError('FRESH_ISOLATED_ATTEMPT_REQUIRED')
    output.mkdir(parents=True)
    if sha(root/'inputs'/day/'NATIVE_INPUT.json')!=freeze['day_input_SHA'][day]:raise PermissionError('CURRENT_INPUT_SHA_DRIFT')
    for r in freeze['day_auxiliary'][day]:
        if sha(r['path'])!=r['sha256']:raise PermissionError('INPUT_WINDOW_OR_OPERATIONS_DRIFT')
    from . import replay
    def folder(prior):return Path(read(request['dependencies'][prior]['receipt'])['folder'])
    def progress(v):atomic(request['progress'],dict(v,worker=process(),timestamp_UTC=now()))
    # A post-freeze stage cannot invoke any native optimization entry point.
    if stage!='A1':
        import gurobipy as gp
        original=gp.Model
        class NoOptimization(original):
            def optimize(self,*a,**kw):
                from v42_a_stage_domain_v2.execution import guard_model_optimize
                guard_model_optimize(self)
                raise PermissionError('ACTUAL_OR_FRESH_REOPTIMIZATION_FORBIDDEN')
        gp.Model=NoOptimization
    if stage=='A1':
        from .native import run_a1
        result=run_a1(read(root/'inputs'/day/'NATIVE_INPUT.json'),root/'inputs'/day,output,progress)
    elif stage=='PLANNING_FREEZE':result=replay.freeze_planning(root,day,folder('A1'),output,freeze)
    elif stage=='ACTUAL':result=replay.actual(folder('PLANNING_FREEZE'),identity(freeze,day,'PLANNING_FREEZE'),output)
    elif stage=='FRESH_AC':result=replay.fresh(root,day,folder('PLANNING_FREEZE'),folder('ACTUAL'),output,freeze,progress)
    else:
        fresh=read(folder('FRESH_AC')/'FRESH_RESULT.json');actual=read(folder('ACTUAL')/'ACTUAL_FIXED_REPLAY_RECEIPT.json');plan=read(folder('A1')/'A1_FREEZE.json')
        passed=physical_validation(fresh) and plan['PASS'] and plan['accepted'] and all(actual[k]==0 for k in ('Actual_reoptimization','local_PQ_repair','global_PQ_repair','M1','M2','MESS_PQ'))
        result=dict(PASS=bool(passed),folder=str(output),physical=fresh,Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0,MESS_PQ=0)
        atomic(output/'VALIDATION_FREEZE.json',dict(result,identity=expected))
        if not passed:raise ValueError('B1_PHYSICAL_VALIDATION_FAIL')
    files=[record(p) for p in sorted(output.rglob('*')) if p.is_file()]
    receipt=dict(result,identity=expected,files=files,mode='B1_PRODUCTION',finished_UTC=now(),worker=process(),
        Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0,B2=0,B3=0,M1=0,M2=0,memory_guards=False)
    atomic(request['result'],receipt)
    return receipt

def main(path):
    request=read(path)
    try:execute(request)
    except BaseException as error:
        atomic(request['error'],dict(type=type(error).__name__,error=str(error),traceback=traceback.format_exc(),UTC=now(),classification=classify(error),
            worker=process(),scientific_infeasibility_proven=False))
        traceback.print_exc();return 1
    return 0

if __name__=='__main__':sys.exit(main(sys.argv[1]))
