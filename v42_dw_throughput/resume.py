"""Explicit checkpoint recovery, with conservative charge for an open call."""
from .common import *
def budget_to_carry(checkpoint,inflight):
    charged=float(checkpoint['elapsed_budget'])
    if inflight:charged=max(charged,float(inflight['spent_before'])+float(inflight['reserved_optimize_seconds']))
    return min(BUDGET,charged)
def recover():
    assert not (OUT/'DW_THROUGHPUT_FINAL.json').exists(),'TERMINAL_CANARY_CANNOT_AUTOMATICALLY_EXTEND'
    value=read(OUT/'DW_THROUGHPUT_CHECKPOINT_LATEST.json');verify_freeze();preserve_old()
    for column in value['pool']:assert sha(ROOT/column['file'])==column['file_SHA']
    state=value['restart_state'];inflight=read(OUT/'DW_INFLIGHT.json') if (OUT/'DW_INFLIGHT.json').exists() else None
    state['carried_heavy_seconds']=budget_to_carry(value,inflight);state['carried_elapsed_seconds']=value['elapsed_total'];state['best_L'],state['best_U']=value['best_interval']
    state['next_round_id']=max([int(p.stem.split('_')[-1]) for p in OUT.glob('RMP_RECEIPT_*.json')]+[value['round']])
    state['next_call_id']=max([int(p.stem.split('_')[-1]) for p in (OUT/'pricing_receipts').glob('PRICE_*.json')]+[0])
    state['next_column_id']=max([int(p.name.split('_')[1]) for p in (OUT/'columns').glob('COLUMN_*.npz')]+[-1])+1
    write('DW_CRASH_RESUME_RECEIPT.json',dict(PASS=True,checkpoint_SHA=sha(OUT/'DW_THROUGHPUT_CHECKPOINT_LATEST.json'),pool_columns=len(value['pool']),carried_heavy_seconds=state['carried_heavy_seconds'],inflight_charged_conservatively=inflight,new_budget_granted=False,orphan_columns_not_promoted=True,cold_RMP=True,source_commit=value['source_commit']))
    return state
