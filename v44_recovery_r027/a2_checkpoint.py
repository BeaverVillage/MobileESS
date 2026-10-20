"""Deterministically restore saved Phase-I support and the final raw LP point.

No solver runs during restoration. Original source rows, bounds, variables,
raw vectors, prices and all earlier native accounting remain authoritative.
"""
from pathlib import Path
from fractions import Fraction
from dataclasses import asdict
import gzip,pickle,gc
import numpy as np
from v44.common import read,record,verify,atomic,now


def load(path):
    with gzip.open(path,'rb') as stream:return pickle.load(stream)


def save(path,value):
    with Path(path).open('xb') as stream:
        with gzip.GzipFile(fileobj=stream,mode='wb',compresslevel=1,mtime=0) as compressed:pickle.dump(value,compressed,protocol=5)
    return record(path)


def apply_candidates(data,domains,candidates,selected,*,defer_ledger=False):
    from v42_a_stage_domain_v2.active import option_from_json
    from v42_a_stage_early.candidate import expanded_graph
    from v42_a_stage_domain_v2.active import _ledger
    for value in selected:
        c=dict(value);option=option_from_json(c['option']);uid=data[7]['classes'][c['class_id']][0]
        graph=expanded_graph(data[5][uid],option,data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
        graphs=dict(data[5])
        for member in data[7]['classes'][c['class_id']]:graphs[member]=graph
        data=(*data[:5],graphs,data[6],data[7])
        candidates.append(dict(c,option=asdict(option),price=str(c['price'])))
    ledger=None if defer_ledger else _ledger(data,domains,{key:{} for key in data[7]['classes']})
    return data,ledger


def reconstruct(parent,output):
    from v44.checkpoints import assert_dead,ledger_state,checked
    from v44.stages import require_m1
    from v42_a_stage_phase1.core import elastic_master,phase_objective,primal_replay,verify_sign_convention
    from v42_a_stage_canary.phase import artificial_point
    from v42_a_stage_early.progress import capture,inclusion_witness
    from v42_a_stage_compact_rowgen.assembly import build,compact_inverse
    from v42_a_stage_compact_rowgen.lift import expanded_point
    parent,output=Path(parent),Path(output);output.mkdir(exist_ok=False,parents=True)
    assert_dead(parent);start=read(parent/'START.json');verify(start['sources'])
    failure=read(parent/'A2/RESULT.json')
    if failure.get('error')!="ValueError('PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT')":
        raise PermissionError('ONLY_EXACT_DIAGNOSED_A2_WEIGHT_DRIFT_RECOVERY')
    m1=read(parent/'M1/RESULT.json');require_m1(m1,'2025-05-02')
    checked(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json',read(parent/'M1/request.json'),'COMPLETED')
    account=ledger_state(parent/'A2/NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    old=parent/'A2/OUTPUT';trace=read(old/'PHASE_I_TRACE.json');last=trace['trajectory'][-1]
    if last['solve']!=14 or not last['row_closed'] or trace['activation_rounds']!=9:
        raise PermissionError('EXACT_S14_ROW_CLOSED_CHECKPOINT_REQUIRED')
    initial_path=old/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz'
    cache=output.parent/'r027_verified_s14_state.pkl.gz'
    cached=cache.exists()
    initial=load(cache)['state'] if cached else load(initial_path);authority=initial['_campaign']
    candidates=[c for meta in initial['metas'].values() for c in meta['candidates']]
    data=initial['data'];ledger=initial['ledger'];rounds=[];evidence=[record(initial_path),record(old/'PHASE_I_TRACE.json')]
    for row in trace['trajectory'][:-1]:
        folder=old/'PHASE_I'/('S'+str(row['solve']))
        witness=folder/'PHYSICAL_ACTIVATION.json'
        if not witness.exists():continue
        if not read(witness)['PASS']:raise ValueError('UNVERIFIED_OLD_ACTIVATION')
        price=folder/'PRICE/PRICING_RESULT.json'
        if not read(price)['selected_candidates']:price=folder/'REMAINING_PRICE/PRICING_RESULT.json'
        priced=read(price);assert priced['PASS']
        if not cached:data,ledger=apply_candidates(data,initial['domains'],candidates,priced['selected_candidates'],defer_ledger=True)
        evidence.extend([record(price),record(witness),record(folder/'PRIOR_INCLUSION.json')]);rounds.append(row)
    assert len(rounds)==9
    from v42_a_stage_domain_v2.active import _ledger
    if cached:
        print('RESTORED_MATERIALIZED_S14_RECHECKING_ORIGINAL_NATIVE_FINGERPRINT',flush=True)
        state=initial
    else:
        ledger=_ledger(data,initial['domains'],{key:{} for key in data[7]['classes']})
        print('RECONSTRUCTING_S14_FROM_NINE_VERIFIED_ACTIVATIONS',flush=True)
        state=build(initial['reference'],initial['grows'],initial['n'],initial['axes'],data,initial['domains'],ledger,candidates)
        state.update({key:initial[key] for key in ('scientific_descriptor','global_types','atlas')})
        del initial;gc.collect()
    master=elastic_master(state['compact'],state['grows'])
    identity=read(old/'PHASE_I/S14/MODEL_IDENTITY.json');verify([identity['matrix'],identity['attributes']])
    if master.snapshot.fingerprint()!=identity['original_snapshot_sha256']:
        raise ValueError('RESTORED_S14_MATRIX_OBJECTIVE_OR_AXES_MISMATCH')
    if not cached:
        state['_campaign']=authority
        saved=save(cache,dict(state=state))
        atomic(cache.with_suffix('.receipt.json'),dict(PASS=True,checkpoint=saved,original_identity=record(old/'PHASE_I/S14/MODEL_IDENTITY.json')))
    raw_path=Path(read(old/'PHASE_I/S14/NATIVE_RESULT.json')['raw_attributes']['path'])
    with np.load(raw_path,allow_pickle=False) as saved:raw={key:saved[key].copy() for key in ('X','Pi','RC')}
    replay=primal_replay(master.snapshot,raw['X']);sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC'])
    assert replay['PASS'] and sign['PASS'] and phase_objective(master,raw['X'])==Fraction(last['exact_Phi'])
    expanded=expanded_point(state,raw['X'][:state['compact'].matrix.shape[1]])
    original_master=elastic_master(state['reference'],state['grows'])
    if master.weights!=original_master.weights or master.artificial_signs!=original_master.artificial_signs:
        raise ValueError('RESTORED_COMPACT_AND_REFERENCE_NORMALIZATION_DIFFER')
    previous=capture(state['reference'],state['reference_descriptor'],original_master,
        dict(X=artificial_point(original_master,expanded)))
    frozen=dict(zip(original_master.artificial_rows,original_master.weights))
    price=old/'PHASE_I/S14/PRICE/PRICING_RESULT.json';priced=read(price)
    if not priced['selected_candidates']:
        price=old/'PHASE_I/S14/REMAINING_PRICE/PRICING_RESULT.json';priced=read(price)
    assert priced['PASS'] and priced['selected_candidates']
    all_candidates=[c for meta in state['metas'].values() for c in meta['candidates']]
    data,ledger=apply_candidates(state['data'],state['domains'],all_candidates,priced['selected_candidates'])
    print('RECONSTRUCTING_FAILED_S14_ACTIVATION_WITH_PRESERVED_WEIGHTS',flush=True)
    new=build(state['reference'],state['grows'],state['n'],state['axes'],data,state['domains'],ledger,all_candidates)
    moving=elastic_master(new['reference'],new['grows'])
    changed=[dict(row=int(row),old=str(weight),recomputed=str(other))
        for row,weight,other in zip(original_master.artificial_rows,original_master.weights,moving.weights) if weight!=other]
    assert changed and original_master.artificial_signs==moving.artificial_signs
    fixed=elastic_master(new['reference'],new['grows'],weights_by_row=frozen)
    witness,mapped=inclusion_witness(previous,new['reference'],new['reference_descriptor'],fixed,new['n'])
    assert witness['PASS']
    inverse=compact_inverse(new,mapped[:new['reference'].matrix.shape[1]])
    compact=elastic_master(new['compact'],new['grows'],weights_by_row=frozen)
    included=np.r_[inverse,mapped[new['reference'].matrix.shape[1]:]]
    restored=primal_replay(compact.snapshot,included)
    assert restored['PASS'] and phase_objective(compact,included)==previous['Phi']
    best=None;stagnation=0
    for row in [*rounds,last]:
        phi=Fraction(row['exact_Phi'])
        if best is not None:stagnation=stagnation+1 if (best-phi)/best<Fraction(1,100) else 0
        best=phi if best is None else min(best,phi)
    assert stagnation<3
    new.update({key:state[key] for key in ('scientific_descriptor','global_types','atlas')});new['_campaign']=authority
    packet=dict(state=new,frozen_weights=frozen,phase_traces=trace['trajectory'],
        activation_round=10,bestPhi=best,stagnation=stagnation,next_solve=15)
    checkpoint=save(output/'A2_PHASE_I_CONTINUATION.pkl.gz',packet)
    evidence.extend([record(price),record(raw_path),record(old/'PHASE_I/S14/MODEL_IDENTITY.json'),account['ledger']])
    proof=dict(UTC=now(),PASS=True,day='2025-05-02',arm='B3',stage='A2',parent=str(parent),checkpoint=checkpoint,
        original_failure=record(parent/'A2/RESULT.json'),parent_request=record(parent/'A2/request.json'),
        fixed_M1_plan_sha=m1['MESS_plan']['plan_sha'],same_saved_S14_matrix_fingerprint=True,
        saved_S14_primal_replay=replay,saved_S14_dual_sign_replay=sign,
        exact_saved_Phi=last['exact_Phi'],weights_drift=changed,
        original_inclusion_witness=witness,new_compact_elastic_replay=restored,
        exact_Phi_preserved=str(previous['Phi']),next_solve=15,activation_round=10,
        inherited_stagnation=stagnation,Native_account=account,new_Native_calls=0,
        original_rows_bounds_types_objectives_unchanged=True,original_failure_and_raw_preserved=True,
        frozen_normalization_policy='PRESERVE_EXACT_S14_WEIGHTS_ACROSS_NEW_COLUMNS_NO_SIGN_GUARD_BYPASS',
        sources=evidence,implementation=record(__file__))
    atomic(output/'ADMISSION.json',proof)
    print(dict(PASS=True,next_solve=15,changed_weights=len(changed),Native_used=account['measured'],remaining=account['remaining']),flush=True)
    return proof
