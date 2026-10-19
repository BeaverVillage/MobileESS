"""Native0 reconstruction of the user-stopped r024a support and feasible elastic witness."""
from pathlib import Path
from fractions import Fraction
import gc,gzip,pickle
import numpy as np


def restore(parent,output):
    from v44.common import read,record,verify,atomic,now
    from v44.checkpoints import assert_dead,ledger_state
    from v42_a_stage_phase1.core import elastic_master,primal_replay,phase_objective
    from v42_a_stage_canary.phase import artificial_point
    from v42_a_stage_compact_rowgen.lift import expanded_point
    from v42_a_stage_compact_rowgen.assembly import compact_inverse
    from v42_a_stage_early.progress import capture,inclusion_witness
    from .a2_checkpoint import load,save,apply_candidates
    from .phase_rebuild import Rebuild
    from v42_may_campaign_native90.a_routing import native_zero_scope
    import gurobipy as gp
    parent=Path(parent);output=Path(output);assert_dead(parent)
    output.mkdir(parents=True,exist_ok=False)
    interruption=read(parent/'USER_INTERRUPTION.json')
    if interruption.get('reason')!='R025A_USER_REQUESTED_NATIVE60_PHASE400_UB_POLICY_STOP':
        raise PermissionError('R025A_ONLY_EXPLICIT_CURRENT_POLICY_CONTINUATION')
    verify([interruption['prior_ledger'],interruption['trace']])
    account=ledger_state(parent/'A2/NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    old=parent/'A2/OUTPUT';trace=read(old/'PHASE_I_TRACE.json')
    last=next(r for r in reversed(trace['trajectory']) if r['row_closed'])
    assert last==trace['trajectory'][-1]
    initial_path=old/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz';initial=load(initial_path)
    full=elastic_master(initial['reference'],initial['grows'])
    frozen=dict(zip(full.artificial_rows,full.weights));del full
    candidates=[c for meta in initial['metas'].values() for c in meta['candidates']]
    data=initial['data'];evidence=[record(initial_path),interruption['prior_ledger'],interruption['trace']]
    completed=[]
    for row in trace['trajectory']:
        folder=old/'PHASE_I'/('S'+str(row['solve']))
        if not (folder/'PHYSICAL_ACTIVATION.json').exists():continue
        for name in ('PHYSICAL_ACTIVATION.json','PRIOR_INCLUSION.json'):
            assert read(folder/name)['PASS'];evidence.append(record(folder/name))
        price=folder/'PRICE/PRICING_RESULT.json';priced=read(price)
        assert priced['PASS'] and priced['selected_candidates'];evidence.append(record(price))
        completed.append((row['solve'],priced['selected_candidates']))
        if row['solve']<last['solve']:
            data,_=apply_candidates(data,initial['domains'],candidates,priced['selected_candidates'],defer_ledger=True)
    from v42_a_stage_domain_v2.active import _ledger
    rebuild=Rebuild()
    with native_zero_scope(gp,construction_check=lambda:None):
        ledger=_ledger(data,initial['domains'],{k:{} for k in data[7]['classes']})
        state=rebuild.build(initial['reference'],initial['grows'],initial['n'],initial['axes'],data,initial['domains'],ledger,candidates)
        for key in ('scientific_descriptor','global_types','atlas','_campaign'):state[key]=initial[key]
        proof=read(old/'PHASE_I'/('S'+str(last['solve']))/'R024A_FULL_PHI.json')
        if state['compact'].matrix.shape[1]!=proof['original_columns']:
            raise ValueError('R025A_RESTORED_COMPACT_COLUMN_COUNT_DRIFT')
        raw_receipt=read(old/'PHASE_I'/('S'+str(last['solve']))/'NATIVE_RESULT.json')['raw_attributes'];verify([raw_receipt]);evidence.append(raw_receipt)
        with np.load(raw_receipt['path'],allow_pickle=False) as raw:x=raw['X'][:proof['original_columns']].copy()
        expanded=expanded_point(state,x)
        master=elastic_master(state['reference'],state['grows'],weights_by_row=frozen)
        point=artificial_point(master,expanded);replay=primal_replay(master.snapshot,point)
        phi=phase_objective(master,point)
        if not replay['PASS'] or abs(phi-Fraction(last['exact_Phi']))>Fraction(1,100000000):
            raise ValueError('R025A_SAVED_RAW_FULL_REFERENCE_REPLAY_FAIL')
        del initial;gc.collect()
        trailing=[batch for index,batch in completed if index>=last['solve']]
        if trailing:
            previous=capture(state['reference'],state['reference_descriptor'],master,dict(X=point))
            del master;gc.collect()
            for batch in trailing:data,_=apply_candidates(data,state['domains'],candidates,batch,defer_ledger=True)
            ledger=_ledger(data,state['domains'],{k:{} for k in data[7]['classes']})
            new=rebuild.build(state['reference'],state['grows'],state['n'],state['axes'],data,state['domains'],ledger,candidates)
            for key in ('scientific_descriptor','global_types','atlas','_campaign'):new[key]=state[key]
            nm=elastic_master(new['reference'],new['grows'],weights_by_row=frozen)
            witness,mapped=inclusion_witness(previous,new['reference'],new['reference_descriptor'],nm,new['n'])
            if not witness['PASS'] or phase_objective(nm,mapped)!=phi:raise ValueError('R025A_CONTINUATION_INCLUSION_FAIL')
            expanded=mapped[:new['reference'].matrix.shape[1]];state=new
            atomic(output/'PRIOR_INCLUSION.json',witness)
        state['prior_original']=expanded;state['prior_compact']=compact_inverse(state,expanded)
        state['_r025a_frozen_weights']=frozen
        checkpoint=save(output/'CURRENT_A2_STATE.pkl.gz',dict(state=state))
    account_path=output/'NATIVE_PARENT.json'
    atomic(account_path,dict(PASS=True,ledger=account['ledger'],measured=account['measured'],calls=account['calls']))
    result=dict(UTC=now(),PASS=True,parent=str(parent),checkpoint=checkpoint,
        native_parent=record(account_path),Native_clock_reset=False,inherited_Native_seconds=account['measured'],
        last_saved_Phi=last['Phi'],replayed_Phi=str(phi),saved_raw_reference_replay=replay,
        completed_activations_restored=len(completed),new_Native_calls=0,sources=evidence,
        physical_domains_constraints_and_integer_types_unchanged=True)
    atomic(output/'ADMISSION.json',result);return result
