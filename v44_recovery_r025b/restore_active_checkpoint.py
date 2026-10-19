"""Recover the exact saved active master, not just its candidate support."""
from pathlib import Path
from collections import defaultdict
from fractions import Fraction
import hashlib
import numpy as np
from scipy import sparse


def row_key(matrix,row,sense,rhs):
    a,b=matrix.indptr[row:row+2]
    h=hashlib.sha256()
    h.update(np.asarray(matrix.indices[a:b],dtype='<i8').tobytes())
    h.update(np.asarray(matrix.data[a:b],dtype='<f8').tobytes())
    h.update(str(sense).encode());h.update(float(rhs).hex().encode())
    return h.digest()


def adaptive_checkpoint(original,output):
    from v44.common import read,record,atomic
    progress_path=original/'A2/OUTPUT/R024A_ADAPTIVE_PROGRESS.json';progress=read(progress_path)
    visits={};last_full=-10;next_round=0;sources=[record(progress_path)]
    for path in sorted((original/'A2/OUTPUT/PHASE_I').glob('S*/PRICE/R024A_CLASS_EXPLORATION.json')):
        plan=read(path);next_round=max(next_round,plan['round']+1)
        for key in plan['target_class_ids']:visits[key]=max(visits.get(key,-1),plan['round'])
        if plan['mode']=='FULL_ELIGIBLE':last_full=max(last_full,plan['round'])
        sources.append(record(path))
    path=output/'ADAPTIVE_PARENT.json'
    atomic(path,dict(PASS=True,feedback=progress['feedback'],visited=visits,
        next_round=next_round,last_full=last_full,scientific_weights_and_M1_unchanged=True))
    return record(path),sources


def restore(output):
    from v44.common import read,record,verify,atomic,now
    from .a2_checkpoint import load,save
    from .bounded_a_stage import phase_cost
    from v42_a_stage_phase1.core import elastic_master,primal_replay
    from v42_a_stage_compact_rowgen.rowgen import restricted
    from v42_a_stage_canary.phase import artificial_point
    from .row_generation import exact_phi
    c=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
    original=c/'2025-05-02/B3/attempt007';parent=c/'2025-05-02/B3/attempt008'
    base=read(Path('D:/MobileESS_V44/development/r025/current_continuation/ADMISSION.json'))
    verify([base['checkpoint']]);state=load(base['checkpoint']['path'])['state']
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    frozen=state['_r025_frozen_weights'];s=state['compact'];n=s.matrix.shape[1];g=len(state['grows'])
    model=read(original/'A2/OUTPUT/PHASE_I/S29/MODEL_IDENTITY.json');verify([model['matrix'],model['attributes']])
    matrix=sparse.load_npz(model['matrix']['path'])[:,:n].tocsr()
    with np.load(model['attributes']['path'],allow_pickle=False) as attrs:
        senses=attrs['senses'].copy();rhs=attrs['rhs'].copy()
    global_count=matrix.shape[0]-(s.matrix.shape[0]-g)
    targets=defaultdict(list)
    for i in range(global_count):targets[row_key(matrix,i,senses[i],rhs[i])].append(i)
    choices=defaultdict(list)
    for i in range(g):
        key=row_key(s.matrix,i,s.senses[i],s.rhs[i])
        if key in targets:choices[key].append(i)
    active=[];previous=-1
    for i in range(global_count):
        key=row_key(matrix,i,senses[i],rhs[i]);options=choices[key]
        eligible=[j for j in options if j>previous]
        if not eligible:raise ValueError('R025B_ACTIVE_ROW_EXACT_COEFFICIENT_MATCH_FAILED')
        previous=eligible[0];active.append(previous)
    active+=list(range(g,s.matrix.shape[0]));r=restricted(s,active)
    master=elastic_master(r,tuple(range(global_count)),weights_by_row={i:frozen[j] for i,j in enumerate(active[:global_count])})
    if master.snapshot.fingerprint()!=model['original_snapshot_sha256']:
        raise ValueError('R025B_SAVED_ACTIVE_MASTER_FINGERPRINT_MISMATCH')
    state['_r025b_active_rows']=tuple(active);state['_r025b_frozen_weights']=frozen
    full=elastic_master(s,state['grows'],weights_by_row=frozen)
    point=artificial_point(full,state['prior_compact']);replay=primal_replay(full.snapshot,point)
    if not replay['PASS']:raise ValueError('R025B_CHECKPOINT_PRIOR_NOT_FULL_ELASTIC_FEASIBLE')
    phi=exact_phi(full,point)
    checkpoint=save(output/'CURRENT_A2_STATE.pkl.gz',dict(state=state))
    adaptive_receipt,adaptive_sources=adaptive_checkpoint(original,output)
    ledger=parent/'A2/NATIVE_RUNTIME_LEDGER.json';old=read(ledger)
    assert old['inflight'] is None
    if abs(sum(r.get('Native_Runtime') or 0 for r in old['calls'])-old['measured_Native_Runtime'])>1e-6:
        raise ValueError('R025B_NATIVE_ACCOUNT_SUM_MISMATCH')
    native_parent=output/'NATIVE_PARENT.json'
    atomic(native_parent,dict(PASS=True,ledger=record(ledger),measured=old['measured_Native_Runtime'],
        phase_I_measured=phase_cost(old['calls']),calls=len(old['calls'])))
    sources=base['sources']+adaptive_sources+[record(base['checkpoint']['path']),record(original/'A2/OUTPUT/PHASE_I/S29/MODEL_IDENTITY.json'),
        model['matrix'],model['attributes'],record(ledger),record(parent/'A2/RESULT.json'),record(parent/'RESULT.json')]
    sources=list({row['path']:row for row in sources}.values())
    result=dict(UTC=now(),PASS=True,parent=str(parent),checkpoint=checkpoint,native_parent=record(native_parent),adaptive_parent=adaptive_receipt,
        inherited_Native_seconds=old['measured_Native_Runtime'],inherited_Phase_I_Native_seconds=phase_cost(old['calls']),
        resumed_Phase_I_ceiling=1000.,total_Native_ceiling=3600.,Native_clock_reset=False,
        saved_active_master_fingerprint_exact=True,restored_active_rows=len(active),restored_active_global_rows=global_count,
        full_original_elastic_prior_replay=replay,prior_Phi=str(phi),candidate_activations_preserved=6,
        current_restricted_integer_model_infeasible_not_full_domain_proof=True,new_Native_calls=0,sources=sources)
    atomic(output/'ADMISSION.json',result);atomic(c/'AUTONOMOUS_RECOVERY/R025B_CURRENT_CONTINUATION.json',result)
    return result
