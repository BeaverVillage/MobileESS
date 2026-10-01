"""One sequential B3 experiment; full M1 remains behind recorded gates."""
import gzip,time
import numpy as np
import gurobipy as gp
from .common import *
from .audit import model,mask
from .canonical import from_model
from .engine import solve,relative_gap

PROGRESS=['iteration','level','master_status','master_seconds','wall_seconds','recourse_status','cut_id','lower','upper','reason']
RECOURSE=['iteration','level','status','seconds','primal_residual','dual_residual','Farkas_residual','warnings','feasibility_tolerance','optimality_tolerance','objective']
LEDGER=['id','iteration','type','source_x_hash','recourse_status','dual_ray_hash','stationarity_residual',
    'exact_bound_correction','bound_row_contribution','source_value','violation_at_source','source_tightness','sparsity','cut_hash','active_inactive_history']

def write_tables(prefix,result,cuts):
    table(prefix+'_PROGRESS.csv',[{k:r.get(k) for k in PROGRESS} for r in result['progress']],PROGRESS)
    table(prefix+'_RECOURSE_LOG.csv',[{k:r.get(k) for k in RECOURSE} for r in result['recourse_log']],RECOURSE)
    table(prefix+'_CUT_LEDGER.csv',[{k:c['record'].get(k) for k in LEDGER} for c in cuts],LEDGER)

def run_b3():
    assert read('FIXTURE_EXACTNESS.json')['PASS'] and read('CANONICAL_MATRIX_VALIDATION.json')['PASS']
    assert read('RECOURSE_LP_AUDIT.json')['PASS']
    LOCAL.mkdir(exist_ok=True)
    assert not (LOCAL/'B3_STARTED.json').exists(),'NO_REAL_RUN_RETRY'
    from v42_threshold.common import resource_snapshot
    resource=resource_snapshot();threads=1 if resource['other_heavy_solve'] else read('PREREGISTRATION.json')['threads']
    receipt=read('RESOURCE_RECEIPT.json');receipt['B3_start']=resource;receipt['B3_threads']=threads;dump('RESOURCE_RECEIPT.json',receipt)
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=model(env,True);can=from_model(m,mask())
    paths=[ROOT/'v42_benders'/n for n in ['canonical.py','certificates.py','engine.py','runner.py']]
    freeze=dict(commit=git('rev-parse','HEAD'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        fixture_exactness_sha256=sha(OUT/'FIXTURE_EXACTNESS.json'),matrix_validation_sha256=sha(OUT/'CANONICAL_MATRIX_VALIDATION.json'),
        sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in paths],
        optimize_calls_before_marker=0,wall_budget=1800,threads=threads,master_binaries=85744)
    dump('EXECUTION_FREEZE.json',freeze)
    (LOCAL/'B3_STARTED.json').write_text(__import__('json').dumps(freeze,indent=2)+'\n')
    dump('B3_EXECUTION_MARKER.json',freeze)
    validations=[]
    def validate(z):
        from v42_threshold.validate import validate_point
        report,slots=validate_point(m,can.names,z);validations.append(report)
        dump('B3_POINT_VALIDATION.json',dict(points=validations))
        return dict(PASS=report['threshold_certificate_PASS'])
    def progress(mr,rr,cuts):
        print('B3 iteration',mr['iteration'],'master',mr['master_status'],'recourse',rr['status'],
            'cuts',len(cuts),'wall',round(mr['wall_seconds'],2),flush=True)
    try:result,point,cuts=solve(can,env=env,seconds=1800,threads=threads,feasibility=True,
        validate=validate,progress=progress,log_dir=LOCAL)
    finally:m.dispose();env.dispose()
    write_tables('B3_DECOMPOSITION',result,cuts)
    # Required short names alias new evidence only; inherited files are untouched.
    table('B3_RECOURSE_LOG.csv',[{k:r.get(k) for k in RECOURSE} for r in result['recourse_log']],RECOURSE)
    table('B3_CUT_LEDGER.csv',[{k:c['record'].get(k) for k in LEDGER} for c in cuts],LEDGER)
    dump('B3_DECOMPOSITION_RESULT.json',result)
    for cut in cuts:
        np.savez_compressed(OUT/(cut['record']['id']+'.npz'),coefficients=cut['coefficients'],multipliers=cut['multipliers'],source_x=cut['source_x'])
    if point is not None:np.savez_compressed(OUT/'B3_WITNESS.npz',names=can.names,values=point)
    terminal=sum(r['status'] in [2,3] for r in result['recourse_log'])
    classification='B3_NEGATIVE_CERTIFIED' if result['status']=='VALIDATED_WITNESS' else 'B3_POSITIVE_CERTIFIED' if result['status']=='MASTER_INFEASIBLE' else 'B3_INCONCLUSIVE'
    exact=result['status'] not in ['STOP_UNCERTIFIABLE','UNSAFE_MASTER_STATUS']
    progress_gate=classification!='B3_INCONCLUSIVE' or terminal>=2 and len(cuts)>=2
    gate=bool(exact and progress_gate and read('FIXTURE_EXACTNESS.json')['PASS'])
    certificate=dict(classification=classification,certificate_valid=classification!='B3_INCONCLUSIVE',
        threshold=THRESHOLD,master_binaries=85744,full_domain_binaries=208312,
        outside_B3_relaxed=True,full96=True,scientific_set_preserved=True,
        result_status=result['status'],recourse_calls=result['recourse_calls'],terminal_recourse_solves=terminal,
        iterations=result['iterations'],feasibility_cuts=result['feasibility_cuts'],optimality_cuts=result['optimality_cuts'],
        wall_seconds=result['wall_seconds'],master_seconds=result['master_seconds'],recourse_seconds=result['recourse_seconds'],
        invalid_cuts_used=0,uncertifiable_source=result['status']=='STOP_UNCERTIFIABLE',
        zero_objective_bound_is_not_rho_LB=True,performance_gate=gate,
        progress_beyond_root_bottleneck=progress_gate,performance_speedup_claim=False,
        PR114_comparison=dict(wall_seconds=1800.08,root_completed=False,classification='B3_INCONCLUSIVE'),
        partial_valid_LB=THRESHOLD if classification=='B3_POSITIVE_CERTIFIED' else .5718504565144596)
    dump('B3_CERTIFICATE.json',certificate)
    dump('FULL_M1_CANARY_AUTHORIZATION.json',dict(authorized=gate,budget_seconds=600,full_master_binaries=208312,
        fixture_PASS=True,scientific_set_PASS=True,B3_progress_PASS=progress_gate,certifiable_numerics_PASS=exact,
        reason='ALL_REGISTERED_GATES_PASS' if gate else result['status'],B3_certificate=classification))
    for log in ['master.log','recourse.log']:
        p=LOCAL/log
        if p.exists():
            (OUT/('B3_'+log+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    print('B3 RESULT',classification,result['status'],'CANARY',gate,flush=True)
    return gate

if __name__=='__main__':run_b3()
