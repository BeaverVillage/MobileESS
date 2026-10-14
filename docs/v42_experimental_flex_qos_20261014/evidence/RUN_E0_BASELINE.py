"""Execute the unchanged strict route once; FLEX/algorithm E0 cells are aliases."""
from pathlib import Path
import hashlib,json,gzip,time,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.experimental_replay import load_conditional_source
from v42_integration.actual import run_actual

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'audit/control/FINAL_E0_STRICT_BASELINE_FULL96'
def serial(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    raise TypeError(type(v).__name__)

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [ROOT/'v42_integration'/n for n in ('actual.py','qos.py','policy.py','sensitivity_policy.py','experimental_replay.py')]}
    source=load_conditional_source();prepared,planning=source['fresh_actual_inputs']()
    arguments=prepared['arguments']
    arguments.update(arm='B3',known_schedule=source['known_commands'],
        frozen_policy=source['original_policy'],expected_bindings=source['original_policy'].bindings)
    started=time.perf_counter();result=run_actual(**arguments);wall=time.perf_counter()-started
    with gzip.open(OUT/'CONDITIONAL_ACTUAL_RESULT.json.gz','wt',encoding='utf8') as stream:
        json.dump(result,stream,default=serial,sort_keys=True)
    arrays={k:result[k] for k in ('occupancy_GPU','compute_occupancy_GPU')}
    arrays.update({'physical_'+k:v for k,v in result.get('physical',{}).items() if isinstance(v,np.ndarray)})
    np.savez_compressed(OUT/'ACTUAL_PHYSICAL_ARRAYS.npz',**arrays)
    receipt=dict(scenario='E0',policy='EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1',effective_algorithm='STRICT_SOURCE_BASELINE_ALIAS',
        execution_kind='CAUSAL_EVENT_COUNTERFACTUAL',Full96=True,slots=96,wall_seconds=wall,
        aliases=['E0_'+flex+'_'+algo for flex in ('FLEX20','FLEX30','FLEX40') for algo in ('FIXED','GREEDY','GRID_SENSITIVITY_AWARE')],
        independent_physical_executions=1,source_case_sha=source['planning_freeze']['case_sha'],source_files=sources,
        source_files_unchanged_after=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in sources.items()),
        actual_receipt=result['receipt'],Native_Optimize_calls=0,Fresh_AC='NOT_RUN',Actual_Maximum_Line_Loading=None,
        result_file_sha256=hashlib.sha256((OUT/'CONDITIONAL_ACTUAL_RESULT.json.gz').read_bytes()).hexdigest(),
        raw_or_GPU_or_service_population_modified=False,new_A_M_optimum=False)
    from RUN_FLEX_COMPARISON import retrospective_service_audit
    service_audit=retrospective_service_audit(source,result)
    assert service_audit['PASS'],'E0_SERVICE_MASS_FAILURE'
    (OUT/'RETROSPECTIVE_SERVICE_MASS.json').write_text(json.dumps(service_audit,indent=2)+'\n',encoding='utf8')
    (OUT/'E0_EXECUTION_RECEIPT.json').write_text(json.dumps(receipt,indent=2,default=serial)+'\n',encoding='utf8')
    print(json.dumps(receipt,default=serial))
if __name__=='__main__':run()
