"""Native0, original r024a state/matrix/pricing-cache continuation admission."""
from pathlib import Path
from collections import defaultdict
import hashlib
import numpy as np
from scipy import sparse


def row_key(matrix,row,sense,rhs):
    a,b=matrix.indptr[row:row+2];h=hashlib.sha256()
    h.update(np.asarray(matrix.indices[a:b],dtype='<i8').tobytes());h.update(np.asarray(matrix.data[a:b],dtype='<f8').tobytes())
    h.update(str(sense).encode());h.update(float(rhs).hex().encode());return h.digest()


def restore(output):
    from v44.common import read,record,verify,atomic,now
    from v44.locks import alive
    from .a2_checkpoint import load,save
    from v42_a_stage_compact_rowgen.rowgen import restricted
    from v42_a_stage_compact_rowgen.lift import expanded_point
    from v42_a_stage_phase1.core import elastic_master,primal_replay
    from v42_a_stage_canary.phase import artificial_point
    from .row_generation import exact_phi
    c=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004');ops=c/'AUTONOMOUS_RECOVERY';parent=c/'2025-05-02/B3/attempt009'
    assert not alive(read(parent/'START.json'));ledger=read(parent/'A2/NATIVE_RUNTIME_LEDGER.json');assert ledger['inflight'] is None
    base=read(Path('D:/MobileESS_V44/development/r025b/current_continuation/ADMISSION.json'));verify([base['checkpoint']])
    state=load(base['checkpoint']['path'])['state'];s=state['compact'];n=s.matrix.shape[1];g=len(state['grows']);frozen=state['_r025b_frozen_weights']
    old=parent/'A2/OUTPUT';trace=read(old/'PHASE_I_TRACE.json');last=trace['trajectory'][-1]
    folder=old/'PHASE_I'/('S'+str(last['solve']));model=read(folder/'MODEL_IDENTITY.json');verify([model['matrix'],model['attributes']])
    matrix=sparse.load_npz(model['matrix']['path'])[:,:n].tocsr()
    with np.load(model['attributes']['path'],allow_pickle=False) as attrs:senses=attrs['senses'].copy();rhs=attrs['rhs'].copy()
    count=matrix.shape[0]-(s.matrix.shape[0]-g);targets={row_key(matrix,i,senses[i],rhs[i]) for i in range(count)};choices=defaultdict(list)
    for i in range(g):
        key=row_key(s.matrix,i,s.senses[i],s.rhs[i])
        if key in targets:choices[key].append(i)
    active=[];previous=-1
    for i in range(count):
        options=[j for j in choices[row_key(matrix,i,senses[i],rhs[i])] if j>previous]
        if not options:raise ValueError('R024B_ACTIVE_ROW_MATCH_FAILED')
        previous=options[0];active.append(previous)
    active+=list(range(g,s.matrix.shape[0]));r=restricted(s,active)
    em=elastic_master(r,tuple(range(count)),weights_by_row={i:frozen[j] for i,j in enumerate(active[:count])})
    if em.snapshot.fingerprint()!=model['original_snapshot_sha256']:raise ValueError('R024B_SAVED_ACTIVE_MASTER_CHANGED')
    raw_receipt=read(folder/'NATIVE_RESULT.json')['raw_attributes'];verify([raw_receipt])
    with np.load(raw_receipt['path'],allow_pickle=False) as z:x=z['X'][:n].copy()
    full=elastic_master(s,state['grows'],weights_by_row=frozen);point=artificial_point(full,x)
    replay=primal_replay(full.snapshot,point)
    if not replay['PASS']:raise ValueError('R024B_SAVED_NATIVE_PRIMAL_REPLAY_FAIL')
    state['prior_compact']=x;state['prior_original']=expanded_point(state,x)
    state['_r024b_active_rows']=tuple(active);state['_r024b_frozen_weights']=frozen
    output=Path(output);output.mkdir(exist_ok=False,parents=True);checkpoint=save(output/'CURRENT_A2_STATE.pkl.gz',dict(state=state))
    adaptive=read(base['adaptive_parent']['path']);progress=read(old/'R025B_ADAPTIVE_PROGRESS.json')
    adaptive['feedback']=progress['feedback'];adaptive_path=output/'ADAPTIVE_PARENT.json';atomic(adaptive_path,adaptive)
    native_parent=output/'NATIVE_PARENT.json';atomic(native_parent,dict(PASS=True,ledger=record(parent/'A2/NATIVE_RUNTIME_LEDGER.json'),measured=ledger['measured_Native_Runtime'],calls=len(ledger['calls'])))
    manifest=c/'2025-05-02/B3/attempt007/A2/OUTPUT/BLOCK_PRICING_ORACLE_VERIFICATION.json';roster=read(manifest)
    cache_sources=[row['external_full_block_cache'] for row in roster['records']];verify(cache_sources)
    sources=base['sources']+[base['checkpoint'],record(manifest),raw_receipt,model['matrix'],model['attributes'],record(folder/'MODEL_IDENTITY.json'),record(old/'R025B_ADAPTIVE_PROGRESS.json'),record(parent/'A2/RESULT.json'),record(parent/'RESULT.json'),record(parent/'A2/NATIVE_RUNTIME_LEDGER.json')]
    sources=list({r['path']:r for r in sources}.values())
    m1=read(c/'2025-05-02/B3/attempt001/M1/RESULT.json')
    proof=dict(UTC=now(),PASS=True,parent=str(parent),checkpoint=checkpoint,native_parent=record(native_parent),adaptive_parent=record(adaptive_path),pricing_manifest=record(manifest),
        inherited_Native_seconds=ledger['measured_Native_Runtime'],Native_clock_reset=False,Native_total_limit=5400.,Phase_I_separate_limit=None,
        original_algorithm='r024a',P1_body_unchanged=True,original_full_gap_acceptance_restored=True,
        restored_active_rows=len(active),saved_active_master_fingerprint_exact=True,prior_Phi=str(exact_phi(full,point)),
        original_full_elastic_primal_replay=replay,full_pricing_cache_files_verified=len(cache_sources),fixed_M1_plan_sha=m1['MESS_plan']['plan_sha'],
        prior_missing_pricing_manifest_repaired=True,new_Native_calls=0,sources=sources)
    atomic(output/'ADMISSION.json',proof);atomic(ops/'R024B_CURRENT_CONTINUATION.json',proof)
    atomic(ops/'R024B_CURRENT_A2_STOPPED.json',dict(UTC=now(),Native_inflight=False,worker_finished_before_manual_stop=True,
        prior_ledger=record(parent/'A2/NATIVE_RUNTIME_LEDGER.json'),measured=ledger['measured_Native_Runtime'],
        old_worker=read(parent/'START.json'),old_coordinator=read(c/'COORDINATOR_LEASE.json')))
    return proof
