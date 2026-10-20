"""Original vs cached assembly of real A2 classes, including a new path column."""
from pathlib import Path
import os,sys,time,pickle,gzip,gc
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
import scipy.sparse as sp
from dataclasses import replace
from fractions import Fraction
from v44.common import atomic,read,record,now
from v42_a_stage_compact_rowgen.assembly import build
from v44_recovery_r020.phase_rebuild import Rebuild,content_key
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_sparse.runtime import coefficient_vector
from v42_may_campaign_native90.preflight import native_zero

out=Path('D:/MobileESS_V44/development/r020_class_validation_04');out.mkdir(exist_ok=False)
root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt001/A2/OUTPUT')
with (root/'STATIC/DATA/DATA.pkl').open('rb') as stream:data=pickle.load(stream)
roster=read(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
priced=read(root/'PHASE_I/S14/REMAINING_PRICE/PRICING_RESULT.json');candidate=priced['selected_candidates'][0];del priced
chosen=[candidate['class_id']]
for count,migration in [(1,False),(2,True)]:
    hit=next(r['class_id'] for r in roster if r['cardinality']==count and bool(r['full_physical_migration'])==migration and r['class_id'] not in chosen)
    chosen.append(hit)
prep=dict(data[7],classes={k:data[7]['classes'][k] for k in chosen})
data=(*data[:7],prep)
full={}
for k in chosen:
    row=next(r for r in roster if r['class_id']==k)
    with gzip.open(row['external_full_block_cache']['path'],'rb') as stream:cache=pickle.load(stream)
    full[k]=cache['graph']
graphs={u:data[5][u] for k in chosen for u in prep['classes'][k]}
data=(*data[:5],graphs,data[6],prep)
axes=set()
for k in chosen:
    uid=prep['classes'][k][0];job=data[1][uid]
    for graph in (graphs[uid],full[k]):
        for family in ('r0','r1'):
            axes.update(('GPU',site,t) for site,t in graph.states[family])
        for family in ('f0','f1'):
            for site,end in graph.events[family]:axes.update(('RUNTIME',s,t) for (s,t),v in coefficient_vector(job,data[4][uid],site,end,data[0]))
        for key,tr in graph.transfers.items():
            axes.update(('WAN',link,t) for link,t,v in tr.wan)
            axes.update(('ACTIVE','',t) for t in range(key[2],tr.end))
axes={key:i for i,key in enumerate(sorted(axes))};m=len(axes);grows=tuple(range(m))
base=LinearSnapshot(sp.csr_matrix((m,1)),np.zeros(1),np.ones(1),np.full(m,'='),np.zeros(m),np.array(['C']),
    tuple(Objective(name,((0,Fraction(1)),) if name=='rho' else (),0) for name in ('rho','migration_count','shift_magnitude','prestart_relocation'))).require()
memo=Rebuild();results=[]
def measure(label,function,current,candidates):
    atomic(out/'STATUS.json',dict(UTC=now(),phase=label))
    start=time.perf_counter();state=function(base,grows,1,axes,current,{}, {},candidates);seconds=time.perf_counter()-start
    result=dict(label=label,wall_seconds=seconds,fingerprints={k:state[k].fingerprint() for k in ('compact','reference')},
        projection_proofs=state['projection_proofs'],descriptor_sha=content_key(state['reference_descriptor']).hex(),
        shapes={k:state[k].matrix.shape for k in ('compact','reference')})
    results.append(result);atomic(out/(label+'.json'),result);print(label,seconds,flush=True)
    return result
with native_zero() as denied:
    original=measure('original',build,data,[])
    cold=measure('cold',memo.build,data,[])
    warm=measure('warm',memo.build,data,[])
    for r in (cold,warm):
        for k in ('fingerprints','projection_proofs','descriptor_sha'):assert r[k]==original[k],(r['label'],k)
    graph_map=dict(graphs)
    for uid in prep['classes'][candidate['class_id']]:graph_map[uid]=full[candidate['class_id']]
    changed=(*data[:5],graph_map,data[6],prep)
    from v42_a_stage_phase1.producer import native_block
    from v42_a_stage_early.candidate import point_for_option,exact_coupling
    from v42_a_stage_domain_v2.active import option_from_json
    ck=candidate['class_id'];uid=prep['classes'][ck][0]
    local,B,_,units=native_block(changed,ck,full[ck],tuple(axes),averaged=True)
    point=point_for_option(dict(snapshot=local,B=B,units=units,graph=full[ck]),data[1][uid],data[3],option_from_json(candidate['option']),len(prep['classes'][ck]))
    candidate=dict(candidate,coupling=[(i,str(v)) for i,v in exact_coupling(B,point).items()])
    expected=measure('changed_original',build,changed,[candidate])
    got=measure('changed_cached',memo.build,changed,[candidate])
    for k in ('fingerprints','projection_proofs','descriptor_sha'):assert got[k]==expected[k],k
    assert len(denied)==0
assert memo.blocks.hits>0 and memo.proofs.hits>0
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_optimizer_calls=0,
    source=record(root/'STATIC/DATA/DATA.pkl'),classes=chosen,real_A2_classes=True,full_campaign_fixture=False,
    results=results,warm_speedup=original['wall_seconds']/warm['wall_seconds'],
    changed_class_speedup=expected['wall_seconds']/got['wall_seconds'],profile=memo.report(),
    original_and_changed_matrix_objective_descriptor_proofs_identical=True,constraints_or_tolerances_changed=False))
print('PASS',memo.report(),flush=True)
