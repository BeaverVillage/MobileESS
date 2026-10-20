"""Original vs cached assembly of real A2 classes, including a new path column."""
from pathlib import Path
import os,sys,time,pickle,gzip,gc
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
import scipy.sparse as sp
from dataclasses import replace
from fractions import Fraction
import v44_recovery_r022
from v44.common import atomic,read,record,now
from v42_a_stage_compact_rowgen.assembly import build
from v44_recovery_r022.phase_rebuild import Rebuild,content_key
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_sparse.runtime import coefficient_vector
from v42_may_campaign_native90.preflight import native_zero

out=Path('D:/MobileESS_V44/development/r022/assembly_axis_diagnosis');out.mkdir(exist_ok=False)
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

import inspect,textwrap
from v42_a_stage_compact_rowgen import assembly
from v42_a_stage_phase1 import backend

def optimized_memo():
    memo=Rebuild()
    # Preserve all values/order/dtypes. Materialize the immutable axis lookup once,
    # rather than rebuilding a Python list for every coupling nonzero.
    ns=dict(memo.assemble.__globals__)
    source=textwrap.dedent(inspect.getsource(backend.assemble_original))
    old="    global_parts=[base.matrix[grows,:global_variables].tocsr()]"
    assert source.count(old)==1
    source=source.replace(old,old+"\n    axis_positions=np.asarray([global_position[value] for value in axes.values()],dtype=np.int64)")
    old="[global_position[list(axes.values())[i]] for i in coo.row]"
    assert source.count(old)==1
    source=source.replace(old,"axis_positions[coo.row]")
    exec(compile(source,__file__+'.reference','exec'),ns)
    memo.assemble=ns['assemble_original']
    ns=dict(memo.compiled.__globals__,assemble_original=memo.assemble)
    source=textwrap.dedent(inspect.getsource(assembly.build))
    old="    ids={k:sorted(j for j,v in rowned.items() if v==k) for k in data[7]['classes']}"
    new="    ids={k:[] for k in data[7]['classes']}\n    for j,k in rowned.items():ids[k].append(j)\n    for cols in ids.values():cols.sort()\n    indexed_units=defaultdict(list)\n    member_class={u:k for k,us in data[7]['classes'].items() for u in us}\n    for unit in rdesc['units']:indexed_units[member_class[unit['uid']]].append(unit)\n    axis_positions=np.asarray(tuple(axes.values()),dtype=np.int64)"
    assert source.count(old)==1
    source=source.replace(old,new)
    old="        runits=[shift(u,-first) for u in rdesc['units'] if u['uid'] in members]"
    assert source.count(old)==1
    source=source.replace(old,"        runits=[shift(u,-first) for u in indexed_units[key]]")
    old="[list(axes.values())[i] for i in coo.row]"
    assert source.count(old)==1
    source=source.replace(old,"axis_positions[coo.row]")
    exec(compile(source,__file__+'.compact','exec'),ns)
    memo.compiled=ns['build']
    return memo

baseline=Rebuild();optimized=optimized_memo();results=[]
def measure(label,memo,current,candidates):
    atomic(out/'STATUS.json',dict(UTC=now(),phase=label))
    t=time.perf_counter();state=memo.build(base,grows,1,axes,current,{}, {},candidates);seconds=time.perf_counter()-t
    result=dict(label=label,wall_seconds=seconds,fingerprints={k:state[k].fingerprint() for k in ('compact','reference')},
        proofs_sha=content_key(state['projection_proofs']).hex(),descriptor_sha=content_key(state['reference_descriptor']).hex(),
        shapes={k:state[k].matrix.shape for k in ('compact','reference')})
    results.append(result);atomic(out/(label+'.json'),result);print(label,seconds,flush=True)
    del state;gc.collect();return result
with native_zero() as denied:
    for label,memo in [('baseline_cold',baseline),('optimized_cold',optimized),('optimized_warm',optimized),('baseline_warm',baseline)]:
        measure(label,memo,data,[])
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
    measure('changed_baseline',baseline,changed,[candidate]);measure('changed_optimized',optimized,changed,[candidate])
    assert len(denied)==0
for names in [('baseline_cold','optimized_cold','baseline_warm','optimized_warm'),('changed_baseline','changed_optimized')]:
    expected=next(r for r in results if r['label']==names[0])
    for name in names[1:]:
        actual=next(r for r in results if r['label']==name)
        for k in ('fingerprints','proofs_sha','descriptor_sha','shapes'):assert actual[k]==expected[k],(name,k)
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_calls=0,axis_count=len(axes),real_A2_classes=chosen,full_campaign_fixture=False,results=results,
    original_matrix_objective_descriptor_proofs_identical=True,production_sources_modified=False,production_deployment=False))
print('PASS',flush=True)
