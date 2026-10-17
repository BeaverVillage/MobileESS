"""Full production-size 138-class matrix/proof equality, Native optimize forbidden."""
from pathlib import Path
import sys,os,pickle,gzip,time,gc,psutil
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r023
from v44.common import atomic,record,read,now
from v44_recovery_r022u.phase_rebuild import Rebuild as Baseline,content_key
from v44_recovery_r023.phase_rebuild import Rebuild
from v44_recovery_r023.snapshot_checks import install
from v42_may_campaign_native90.preflight import native_zero
from v42_a_stage_early.candidate import expanded_graph
from v42_a_stage_domain_v2.active import option_from_json
import numpy as np

out=Path('D:/MobileESS_V44/development/r023/full_138_classes');out.mkdir(parents=True,exist_ok=False)
source=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt005/A2/OUTPUT/STATIC/INITIAL_STATE.pkl.gz')
with gzip.open(source,'rb') as f:state=pickle.load(f)
print('loaded',len(state['data'][7]['classes']),state['compact'].matrix.shape,flush=True)
results=[]
def measure(label,memo,data,candidates):
    atomic(out/'STATUS.json',dict(UTC=now(),label=label))
    start=time.perf_counter()
    got=memo.build(state['reference'],state['grows'],state['n'],state['axes'],data,state['domains'],state['ledger'],candidates)
    seconds=time.perf_counter()-start
    item=dict(label=label,wall_seconds=seconds,
        fingerprints={k:got[k].fingerprint() for k in ('compact','reference')},
        descriptor_sha=content_key(got['reference_descriptor']).hex(),proofs_sha=content_key(got['projection_proofs']).hex(),
        metas_sha=content_key(got['metas']).hex(),shapes={k:got[k].matrix.shape for k in ('compact','reference')},
        RSS_bytes=psutil.Process().memory_info().rss,profile=memo.report())
    results.append(item);atomic(out/(label+'.json'),item);print(label,seconds,item['RSS_bytes'],flush=True)
    del got;gc.collect()

with native_zero() as denied,install():
    baseline=Baseline();new=Rebuild()
    candidates=[c for meta in state['metas'].values() for c in meta['candidates']]
    measure('initial_r022u',baseline,state['data'],candidates)
    measure('initial_r023',new,state['data'],candidates)
    price=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt005/A2/OUTPUT/PHASE_I/S11/PRICE/PRICING_RESULT.json')
    selected=read(price)['selected_candidates']
    data=state['data']
    for candidate in selected:
        uid=data[7]['classes'][candidate['class_id']][0]
        option=option_from_json(candidate['option'])
        graph=expanded_graph(data[5][uid],option,data[1][uid],state['domains'][uid],uid in data[7]['preserve_singleton_mixed_flow'])
        data,_=new.update_graph(data,state['domains'],candidate['class_id'],graph)
        candidates.append(candidate)
    measure('activated_r022u',baseline,data,candidates)
    measure('activated_r023',new,data,candidates)
    assert len(denied)==0
for old,new in [(results[0],results[1]),(results[2],results[3])]:
    for key in ('fingerprints','descriptor_sha','proofs_sha','metas_sha','shapes'):assert old[key]==new[key],(key,old['label'])
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_calls=0,class_count=len(state['data'][7]['classes']),
    source=record(source),candidate_source=record(price),candidates_added=len(selected),results=results,
    whole_original_and_compact_matrix_objective_descriptor_proofs_metas_identical=True,
    current_worker_interrupted=False,production_end_to_end_speedup_not_claimed=True))
print('FULL_138_CLASSES_PASS',flush=True)
