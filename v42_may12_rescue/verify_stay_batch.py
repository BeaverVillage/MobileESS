"""Actual May12 matrix/price/graph verification, with ZERO optimize calls."""
import gzip,pickle,time
import numpy as np
from .policy import ROOT,OUT,STATIC,OLDOUT,DAY
from .stay_batch import augment
from .prepare import route
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_canary.pricing import full_pricing
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_phase1.runner import load_cache,block_folder
from v42_a_stage_compact_rowgen.assembly import partition

def run():
    start=time.perf_counter();route();folder=OUT/'STAY_BATCH_ACTUAL_VERIFICATION'
    with gzip.open(STATIC/'P1_S0.pkl.gz','rb') as f:saved=pickle.load(f)
    state,raw=saved['state'],saved['raw'];s=state['compact'];local,owned=partition(s,state['metas'],state['grows'])
    class Completed:
        calls=0
        def remaining(self):return 3600-read(OUT/'NEW_NATIVE_BUDGET_LEDGER.json')['actual_Runtime']
        def solve(self,snapshot,target,component):
            original=block_folder(OUT/'P1/S0/PRICE',target.name)
            result=read(original/'NATIVE_RESULT.json');identity=read(result['model_identity']['path'])
            if identity['original_snapshot_sha256']!=snapshot.fingerprint() or record(result['raw_attributes']['path'])!=result['raw_attributes']:
                raise ValueError('READ_ONLY_ORACLE_REUSE_MATRIX_OR_RAW_DRIFT')
            return result,dict(np.load(result['raw_attributes']['path']))
    if (folder/'PRICE/FULL_PRICING_RESULT.json').exists():
        from .completed_pricing import restore
        # The shadow receipts refer to the same exact cached native points.
        # Reverify the complete saved original round; preserve shadow results.
        priced=read(folder/'PRICE/FULL_PRICING_RESULT.json')
        _,negative=restore(state,OUT/'P1/S0/PRICE',raw)
    else:
        priced,negative=full_pricing(Completed(),s,None,raw,None,state['data'],state['domains'],state['ledger'],state['axes'],state['n'],state['grows'],local,owned,folder/'PRICE')
    old=read(OUT/'PRE_IMPLEMENTATION_BOUNDARY1/P1/S0/PRICE/FULL_PRICING_RESULT.json')
    for key in ('full_domain_phase1_lower_bound','global_bound','min_stay_rc','min_migration_rc','negative_blocks'):
        if priced[key]!=old[key]:raise ValueError('EXACT_ZERO_SUM_OPTIMIZATION_CHANGED_BOUND:'+key)
    directions,proof=augment(state,negative,folder/'PRICE',folder);checks=[]
    required={r['class_id']:r for r in read(OLDOUT/DAY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    for direction,r in zip(directions,proof['records']):
        if not r['count']:continue
        key=direction['class_id'];cache=load_cache(required[key])
        fullB=cache['B'].tocsc();snap,B,constant,units=native_block(state['data'],key,direction['graph'],tuple(state['axes']))
        if np.any(constant!=0):raise ValueError('BATCH_STAY_NATIVE_COUPLING_CONSTANT_DRIFT')
        columns={option:int(e[1]) for u in units if u.get('stay_count') for option,e in u['v']['y'].items() if e[0]=='v'}
        newB=B.tocsc();A=snap.matrix.tocsc();count=r['admitted_negative_concrete_STAY_columns'][0]['count']
        base=np.where(snap.senses=='=',snap.rhs!=0,np.where(snap.senses=='<',snap.rhs<0,snap.rhs>0))
        failed=np.flatnonzero(base)
        if len(failed)!=1 or snap.senses[failed[0]]!='=' or snap.rhs[failed[0]]!=count or np.any(snap.lower>0) or np.any(snap.upper<0):
            raise ValueError('BATCH_STAY_REBUILT_NATIVE_BASE_LOCAL_ROWS_FAIL')
        for option in r['admitted_negative_concrete_STAY_columns']:
            j=columns[(option['site'],option['start'])];a,b=A.indptr[j:j+2]
            if b-a!=1 or A.indices[a]!=failed[0] or A.data[a]!=1 or not snap.lower[j]<=count<=snap.upper[j]:
                raise ValueError('BATCH_STAY_REBUILT_NATIVE_LOCAL_COLUMN_FAIL')
            x,y=fullB.getcol(option['column']),newB.getcol(j)
            if not np.array_equal(x.indices,y.indices) or not np.array_equal(x.data,y.data):raise ValueError('BATCH_STAY_REBUILT_NATIVE_COUPLING_COLUMN_DRIFT')
        checks.append(dict(class_id=key,PASS=True,all_additional_columns_checked=r['count'],rows=snap.matrix.shape[0],cols=snap.matrix.shape[1]))
    result=dict(PASS=True,actual_May12_matrix=True,native_optimize_calls=0,batch_certificate=record(folder/'BATCH_NEGATIVE_STAY_CERTIFICATE.json'),
        additional_negative_concrete_STAY_columns=proof['additional_negative_concrete_STAY_columns'],rebuilt_native_block_checks=checks,
        exact_filtered_zero_sums_produced_identical_bound_and_RC=True,old_full_pricing_wall=old['pricing_wall_seconds'],
        cached_oracle_shadow_pricing_wall=priced['pricing_wall_seconds'],timing_scopes_differ_no_uncontrolled_speedup_claim=True,
        all_pricing_candidates_remain_in_full_domain=True,wall_seconds=time.perf_counter()-start)
    result['actual_validation_sources']=[record(ROOT/p) for p in (
        'v42_may12_rescue/verify_stay_batch.py','v42_may12_rescue/stay_batch.py',
        'v42_a_stage_phase1/core.py','v42_a_stage_acceptance/global_box.py')]
    atomic(OUT/'STAY_BATCH_ACTUAL_VERIFICATION.json',result)
    print('MAY12_ACTUAL_EXACT_STAY_BATCH_PASS',result['additional_negative_concrete_STAY_columns'],result['wall_seconds'],flush=True)
if __name__=='__main__':run()
