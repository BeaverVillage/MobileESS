"""Read-only production-size row/lift/attribution measurement; Native0."""
from pathlib import Path
import sys,os,time,gzip,pickle,gc
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022
import numpy as np
from v44.common import atomic,read,record,now
from v44_recovery_r022.row_generation import ActiveRows,exact_phi
from v44_recovery_r022.phase_speed import compile_attribution
from v44_recovery_r022.a2_continue import FrozenWeights
from v44_recovery_r022.snapshot_checks import install
from v42_a_stage_phase1.core import phase_objective,primal_replay
from v42_a_stage_phase1.backend import artificial_point
from v42_a_stage_compact_rowgen.assembly import partition
from v42_a_stage_practical.attribution import analyze
from v42_may_campaign_native90.preflight import native_zero

out=Path('D:/MobileESS_V44/development/r022/real_validation_02');out.mkdir(parents=True,exist_ok=False)
root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt004/A2/OUTPUT')
with native_zero() as denied,install():
    start=time.perf_counter()
    with gzip.open(root/'STATIC/INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
    print('loaded',state['compact'].matrix.shape,flush=True)
    s=state['compact'];G=state['grows'];weights=FrozenWeights(state['reference'],G,None);full=weights.elastic_master(s,G)
    with np.load(root/'STATIC/NATIVE/PHASE_I/S3/NATIVE_RAW.npz') as raw:x=raw['X'][:s.matrix.shape[1]]
    fullpoint=artificial_point(full,x)[0];p=state['prior_compact'];activity=s.matrix@p-s.rhs
    included=set(range(len(G),s.matrix.shape[0]))|set(state['axes'].values())
    included.update(np.flatnonzero((np.diff(s.matrix.indptr[:len(G)+1])>0)&(abs(activity[:len(G)])<=1e-6)))
    t=time.perf_counter();manager=ActiveRows(state,included,full);identity_seconds=time.perf_counter()-t
    assert set(range(len(G),s.matrix.shape[0]))<=manager.included
    t=time.perf_counter();old=phase_objective(full,fullpoint);old_seconds=time.perf_counter()-t
    t=time.perf_counter();new=exact_phi(full,fullpoint);new_seconds=time.perf_counter()-t
    assert old==new
    print('phi_speed',old_seconds,new_seconds,flush=True)
    local,owned=partition(s,state['metas'],G)
    t=time.perf_counter();original=analyze(full,dict(X=fullpoint),state['data'],state['axes'],owned,state['atlas'],out/'ORIGINAL');original_seconds=time.perf_counter()-t
    print('original_attribution',original_seconds,flush=True)
    t=time.perf_counter();optimized=compile_attribution(analyze)(full,dict(X=fullpoint),state['data'],state['axes'],owned,state['atlas'],out/'OPTIMIZED');optimized_seconds=time.perf_counter()-t
    assert original[0]==optimized[0] and np.array_equal(original[1],optimized[1]) and original[2]==optimized[2]
    assert (out/'ORIGINAL/RESIDUAL_ROWS.csv').read_bytes()==(out/'OPTIMIZED/RESIDUAL_ROWS.csv').read_bytes()
    assert not denied
    atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_calls=0,production_size_initial_state_only=True,
        source=record(root/'STATIC/INITIAL_STATE.pkl.gz'),full_rows=s.matrix.shape[0],original_columns=s.matrix.shape[1],
        selected_rows=len(manager.included),selected_global_rows=sum(i<len(G) for i in manager.included),
        full_artificials=len(full.artificial_rows),selected_artificials=sum(2 if s.senses[i]=='=' else 1 for i in manager.included if i<len(G)),
        semantic_identity_seconds=identity_seconds,full_Phi=str(new),exact_Phi_original_seconds=old_seconds,
        exact_Phi_optimized_seconds=new_seconds,attribution_original_seconds=original_seconds,attribution_optimized_seconds=optimized_seconds,
        exact_Phi_and_attribution_and_ranking_and_CSV_identical=True,wall_seconds=time.perf_counter()-start,
        end_to_end_campaign_speedup_not_claimed=True))
    print(read(out/'RESULT.json'),flush=True)
