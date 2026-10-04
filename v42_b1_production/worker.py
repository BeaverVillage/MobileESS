"""One isolated stage of the explicit B1 historical implementation port."""
import os
import sys
import traceback
from .common import *


def valid_receipt(receipt, expected, root):
    if receipt.get('identity') != expected or receipt.get('PASS') is not True or receipt.get('mode') != 'B1_PRODUCTION' or receipt.get('SYNTHETIC_ONLY'):
        return False
    try:
        files = receipt['files']
        return bool(files) and all(Path(r['path']).resolve().is_relative_to(root.resolve())
            and sha(r['path']) == r['sha256'] for r in files)
    except (KeyError, OSError):
        return False


def guard_gurobi(stage):
    import gurobipy as gp
    original = gp.Model
    calls = []
    class GuardedModel(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setParam('Threads', 1)
        def setParam(self, name, value):
            if str(name).lower() == 'threads' and value != 1:
                raise PermissionError('B1_THREADS_DRIFT')
            return super().setParam(name, value)
        def optimize(self, *args, **kwargs):
            if stage != 'A1' or int(self.Params.Threads) != 1:
                raise PermissionError('ACTUAL_REOPTIMIZATION_OR_THREADS_DRIFT')
            if self.Params.TimeLimit > 1800:
                raise PermissionError('A1_TIMELIMIT_DRIFT')
            calls.append(dict(Threads=1, TimeLimit=float(self.Params.TimeLimit)))
            return super().optimize(*args, **kwargs)
    gp.Model = GuardedModel
    return calls


def physical_validation(fresh):
    s = fresh['summary']
    keys = ('voltage_violation_count', 'line_current_violation_count',
            'transformer_current_violation_count', 'transformer_kva_violation_count')
    return bool(fresh['converged'] and s['convergence_count'] == 96 and
        all(s[k] == 0 for k in keys) and fresh['checker_SHA'] == CHECKER and
        fresh['all_MESS_PQ_zero'] and fresh['NormalAmps_current'] and
        not fresh['Planning_tap_replay'] and all(fresh[k] == 0 for k in
        ('Actual_reoptimization', 'local_PQ_repair', 'global_PQ_repair')))


def execute(request):
    root = Path(request['root']).resolve()
    freeze = read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json')
    Config(**read(root/'B1_CAMPAIGN_CONFIG.json'))
    verify_freeze(freeze,read(root/'B1_CAMPAIGN_CONFIG.json'))
    day, stage = request['day'], request['stage']
    expected = identity(freeze, day, stage)
    if request['identity'] != expected or request.get('mode') != 'B1_PRODUCTION':
        raise PermissionError('WORKER_IDENTITY')
    deps = request['dependencies']
    if set(deps) != set(STAGES[:STAGES.index(stage)]):
        raise PermissionError('CAUSAL_STAGE_ORDER')
    for prior, row in deps.items():
        if sha(row['receipt']) != row['sha256'] or not valid_receipt(
                read(row['receipt']), identity(freeze,day,prior), root):
            raise PermissionError('DEPENDENCY_OUTPUT_SHA')
    output = Path(request['output']).resolve()
    if not output.is_relative_to(root) or output.exists():
        raise PermissionError('FRESH_ISOLATED_ATTEMPT_REQUIRED')
    output.mkdir(parents=True)
    calls = guard_gurobi(stage)
    def folder(prior): return Path(read(deps[prior]['receipt'])['folder'])
    from . import replay
    if stage == 'A1':
        if sha(root/'inputs'/day/'NATIVE_INPUT.json') != freeze['day_input_SHA'][day]:
            raise PermissionError('CURRENT_DAY_INPUT_SHA')
        from .native import run_a1
        result = run_a1(read(root/'inputs'/day/'NATIVE_INPUT.json'),output,Path(request['progress']))
    elif stage == 'PLANNING_FREEZE':
        result = replay.freeze_planning(root,day,folder('A1'),output,freeze)
    elif stage == 'ACTUAL':
        result = replay.actual(folder('PLANNING_FREEZE'),identity(freeze,day,'PLANNING_FREEZE'),output)
    elif stage == 'FRESH_AC':
        def progress(value): atomic(Path(request['progress']),value)
        result = replay.fresh(root,day,folder('PLANNING_FREEZE'),folder('ACTUAL'),output,freeze,progress)
    else:
        fresh = read(folder('FRESH_AC')/'FRESH_RESULT.json')
        actual = read(folder('ACTUAL')/'ACTUAL_FIXED_REPLAY_RECEIPT.json')
        plan = read(folder('A1')/'A1_FREEZE.json')
        passed = physical_validation(fresh) and plan['PASS'] and plan['accepted'] and all(
            actual[k] == 0 for k in ('Actual_reoptimization','local_PQ_repair','global_PQ_repair','M1','M2','MESS_PQ'))
        result = dict(PASS=bool(passed),folder=str(output),physical=fresh,
                      B2=0,B3=0,M1=0,M2=0,Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0)
        atomic(output/'VALIDATION_FREEZE.json',dict(result,identity=expected))
        if not passed: raise ValueError('B1_PHYSICAL_VALIDATION_FAIL')
    if stage != 'A1' and calls: raise PermissionError('POST_FREEZE_OPTIMIZER_CALL')
    if stage == 'A1' and len(calls)!=4: raise PermissionError('COMPLETE_CURRENT_A1_REQUIRED')
    files = [record(p) for p in sorted(output.rglob('*')) if p.is_file()]
    receipt = dict(result,identity=expected,mode='B1_PRODUCTION',files=files,
                   native_optimize_calls=len(calls),solver_calls=calls,
                   Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0,
                   B2=0,B3=0,M1=0,M2=0,worker_PID=os.getpid(),finished_UTC=now())
    atomic(request['result'],receipt)
    return receipt


def main(request_path):
    request = read(request_path)
    try: execute(request)
    except BaseException as error:
        atomic(request['error'],dict(type=type(error).__name__,error=str(error),traceback=traceback.format_exc(),UTC=now()))
        traceback.print_exc()
        return 1
    return 0


if __name__ == '__main__': sys.exit(main(sys.argv[1]))
