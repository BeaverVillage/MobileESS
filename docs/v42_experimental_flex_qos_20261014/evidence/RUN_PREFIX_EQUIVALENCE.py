"""Two-slot same-case performance proof, never a Full96/AC certificate."""
from pathlib import Path
import sys,json,gzip,time,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.a_engine import digest
from v42_integration.experimental_replay import load_conditional_source
from v42_integration.experimental_actual import run_conditional_case
from RUN_FLEX_COMPARISON import serial,source_ok
IDENTITY_ONLY={'policy_sha','policy_id_sha','rule_id','candidate_id','selected_candidate',
    'source_freeze_sha','source_epoch_sha','online_grid_horizon_evaluations','signed_packet_evaluation_calls'}
def canonical(v):
    if isinstance(v,dict):return {k:canonical(x) for k,x in v.items() if k not in IDENTITY_ONLY}
    if isinstance(v,list):return [canonical(x) for x in v]
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    return v
def main(label):
    freeze=json.loads((ROOT/'audit/SOURCE_FREEZE_C.json').read_text(encoding='utf8'));assert source_ok(freeze)
    case=digest(dict(case='DECLARED_SAME_INPUT_TWO_SLOT_ENGINEERING_EQUIVALENCE',scenario='E1',FLEX='FLEX30',
        original_planning_case_sha='623efbcbd6344b9c18540ff2a496a112b43c93b1d277c50d9c9b682fc11bcce0'))
    source=load_conditional_source()
    original_factory=source['fresh_actual_inputs']
    def prefix_inputs():
        prepared,planning=original_factory()
        prepared['arguments']['weather']=prepared['arguments']['weather'][:2]
        return prepared,planning
    source['fresh_actual_inputs']=prefix_inputs
    began=time.perf_counter()
    result=run_conditional_case(source,scenario='E1',participation='FLEX30',algorithm='GRID_SENSITIVITY_AWARE',
        case_sha=case,source_freeze_sha=freeze['source_sha'],end_slots=2)
    wall=time.perf_counter()-began;folder=ROOT/'audit/performance'/label;folder.mkdir(parents=True,exist_ok=True)
    with gzip.open(folder/'PREFIX_RESULT.json.gz','wt',encoding='utf8') as stream:json.dump(result,stream,default=serial,sort_keys=True)
    semantics={k:canonical(result[k]) for k in ('receipt','job_event_ledger','qos_ledger','queue_ledger',
        'experimental_candidate_audit','experimental_reference_audit','migration_receipts','cc4_depletion_ledger')}
    with gzip.open(folder/'PREFIX_BEHAVIOR_CANONICAL.json.gz','wt',encoding='utf8') as stream:json.dump(semantics,stream,sort_keys=True)
    arrays={k:result[k] for k in ('occupancy_GPU','compute_occupancy_GPU')}
    arrays.update({'physical_'+k:v for k,v in result['physical'].items() if isinstance(v,np.ndarray)})
    np.savez_compressed(folder/'PREFIX_ARRAYS.npz',**arrays)
    receipt=dict(source_sha=freeze['source_sha'],case_sha=case,slots=2,Full96=False,wall_seconds=wall,
        canonical_behavior_sha=digest(semantics),array_sha={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in arrays.items()},
        source_after_PASS=source_ok(freeze),scope='ENGINEERING_TWO_SLOT_EQUIVALENCE_NOT_FULL96_OR_AC',
        Native_calls=0,AC_calls=0,receipt=result['receipt'])
    (folder/'PREFIX_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    assert receipt['source_after_PASS'];print(json.dumps(receipt),flush=True)
if __name__=='__main__':main(sys.argv[1])
