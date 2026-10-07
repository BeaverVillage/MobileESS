"""Date-routed immutable inputs; same May19 source builders and policies."""
from dataclasses import asdict
from time import perf_counter
from pathlib import Path
import sys
import gzip,pickle
import numpy as np
from v42_pr134_b1.common import read,record,atomic
from v42_pr134_b1.native import bind
from v42_pr134_sc.snapshot import capture
from v42_two.contract import aidc_groups,passes
from v42_integrated.contract import physical_authority,all_transformer_rows
from v42_a_stage_domain_v2.census import load_frozen,PRODUCTION,digest
from v42_a_stage_domain_v2.fast_census import load_physical_cache,required_supports
from v42_a_stage_domain_v2.fast_prepare import STATIC as CACHE_STATIC
from v42_a_stage_domain_v2.fast_backend import Backend,frozen_grid_priority
from v42_a_stage_domain_v2.active import ActivePolicy,prepare_fast_active
from v42_a_stage_domain_v2.stress_backend import snapshot_of
from v42_a_stage_phase1.producer import row_partition,native_block,complete_graph
from v42_a_stage_phase1.backend import assemble_original,constructed_point
from v42_a_stage_compact_rowgen.assembly import build,compact_inverse
from .policy import ROOT,OUT,STATIC,DAYS

def prepare(day):
    if day not in DAYS:raise PermissionError('REQUESTED_CANARY_ORDER_ONLY')
    folder=OUT/day;folder.mkdir(parents=True,exist_ok=True);static=STATIC/day;static.mkdir(parents=True,exist_ok=True)
    if (folder/'INITIAL_VERIFICATION.json').exists():raise PermissionError('CANARY_ALREADY_PREPARED')
    t=perf_counter();frozen_data,frozen=load_frozen(day);expected=read(ROOT/'docs/v42_a_stage_v2_stress4_20261007/STATIC_SOURCE_DATA_IDENTITY.json')['dates'][day]
    inputs=PRODUCTION/'inputs'/day;bundle=read(inputs/'NATIVE_INPUT.json')
    if record(frozen/'DATA.pkl')['sha256']!=expected['DATA_file']['sha256'] or record(inputs/'NATIVE_INPUT.json')['sha256']!=expected['frozen_native_input']['sha256'] or digest(asdict(frozen_data[3]))!=expected['resources_sha256'] or digest(bundle)!=digest(frozen_data[0]):raise ValueError('FROZEN_SCIENTIFIC_CANARY_IDENTITY_DRIFT')
    _,native,coeff,*_=bind(bundle,inputs,static/'BASE')
    scores,ranking=frozen_grid_priority(coeff,frozen_data[3])
    domains=load_physical_cache(day,frozen_data,frozen/'DATA.pkl',CACHE_STATIC)
    data,domains,ledger=prepare_fast_active(frozen_data,policy=ActivePolicy(2,8,0),required_support=required_supports(day,frozen_data),
        grid_scores=scores,expected_grid_priority_hash=ranking['score_sha256'],physical_domains=domains)
    for members in data[7]['classes'].values():
        uid=members[0]
        if data[5][uid].fixed and (len(domains[uid].stays)!=1 or domains[uid].blocks):raise ValueError('NONFIXED_SCIENTIFIC_CLASS_FOLDED_TO_CONSTANT')
    class Context:
        folder=static/'BASE'
        def check(self):pass
        def progress(self,value):atomic(folder/'BUILD_PROGRESS.json',dict(day=day,**value))
    import v42_boundary.model as boundary
    old=boundary.add_grid;boundary.add_grid=all_transformer_rows(old);boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
    import gurobipy as gp
    model_class=gp.Model;row_labels=[];row_codes=[];label_codes={}
    class StaticModel(model_class):
        def addConstr(self,*a,**kw):
            name=kw.get('name',a[1] if len(a)>1 else '')
            frame=sys._getframe(1)
            family=name.split('[')[0] if name else 'row_'+Path(frame.f_code.co_filename).parent.name+'_'+str(frame.f_lineno)
            if family not in label_codes:label_codes[family]=len(row_labels);row_labels.append(family)
            row_codes.append(label_codes[family]);return super().addConstr(*a,**kw)
    gp.Model=StaticModel
    try:
        with physical_authority():model,units,levels,controls,bindings=native.build(Context(),data,'F2-CRA')
    finally:
        gp.Model=model_class;boundary.add_grid=old;boundary.planning_grid.__globals__['add_grid']=old
    objectives=[(name,expr) for _,name,expr in passes(aidc_groups(levels,units,data))]
    base=snapshot_of(model,objectives);desc=capture(model,units,levels,controls,bindings,static/'SCIENTIFIC_INTERFACES.pkl.gz')
    localcols=[]
    for u in desc['units']:
        for items in u['v'].values():
            for e in items.values():localcols.extend((int(e[1]),) if e[0]=='v' else map(int,e[2]) if e[0]=='e' else ())
    n=min(localcols);global_types=base.vtypes[:n].copy();backend=Backend();backend.data=data
    rawaxes=backend._coupling_rows(model,bindings);axes={}
    for (family,key),row in rawaxes.items():
        axes[(family.upper(),*key) if isinstance(key,tuple) else (family.upper(),'',key)]=row
    grows,_,_=row_partition(base,desc,n,axes.values())
    if len(row_codes)!=model.NumConstrs:raise ValueError('ORIGINAL_ROW_FAMILY_CAPTURE_REQUIRED')
    # The original builder may interleave global and local rows.  The
    # assembled reference orders only the selected original global rows first.
    rf=np.asarray(row_codes)[np.asarray(grows,dtype=np.int64)];rf_names=np.asarray(row_labels);families=rf_names[rf]
    voltage=read(data[0]['electrical_certificate']['path'])['outputs']['voltage']
    if record(voltage['path'])['sha256']!=voltage['sha256']:raise ValueError('GRID_ARCHIVE_DRIFT')
    with np.load(voltage['path']) as z:node_names=z['node_names'].copy()
    resource_variables=[]
    for kind,site,t in axes:
        e=desc['known'].get((site,t)) if kind=='GPU' else desc['risk'].get((site,t)) if kind=='RUNTIME' else None
        if e is not None and e[0]!='v':raise ValueError('ORIGINAL_RESOURCE_AXIS_REQUIRED')
        resource_variables.append(int(e[1]) if e is not None else -1)
    atlas=dict(rf=rf,rf_names=rf_names,node_names=node_names,voltage_lower_rows=np.flatnonzero(families=='voltage_lower'),
        voltage_upper_rows=np.flatnonzero(families=='voltage_upper'),resource_variables=np.asarray(resource_variables),domains=domains)
    if len(atlas['voltage_upper_rows'])!=96*len(node_names):raise ValueError('ORIGINAL_VOLTAGE_TIME_NODE_AXIS_REQUIRED')
    model.dispose()
    ref,rdesc,G,local,owned,newaxes=assemble_original(base,grows,n,axes,data)
    state=build(ref,G,n,newaxes,data,domains,ledger,[]);state['scientific_descriptor']=desc;state['global_types']=global_types;state['atlas']=atlas
    prior,_=constructed_point(state['reference'],state['reference_descriptor'],data,n,range(len(G),state['reference'].matrix.shape[0]))
    state['prior_original']=prior;state['prior_compact']=compact_inverse(state,prior)
    roster=[]
    for i,(key,members) in enumerate(sorted(data[7]['classes'].items())):
        uid=members[0];graph=complete_graph(data[1][uid],domains[uid],uid in data[7].get('preserve_singleton_mixed_flow',()))
        snap,B,c,u=native_block(data,key,graph,tuple(newaxes),averaged=True)
        path=static/'FULL_BLOCKS'/(key[:12]+'.pkl.gz');path.parent.mkdir(exist_ok=True)
        with gzip.open(path,'xb',compresslevel=1) as f:pickle.dump(dict(snapshot=snap,B=B,constant=c,units=u,graph=graph),f,protocol=5)
        roster.append(dict(PASS=True,class_id=key,cardinality=len(members),external_full_block_cache=record(path),
            full_physical_STAY=len(domains[uid].stays),full_physical_migration=sum(len(b[-1]) for b in domains[uid].blocks),
            full_compact_blocks=len(domains[uid].blocks),complete_graph_sha256=graph.sha,complete_local_snapshot_sha256=snap.fingerprint(),
            complete_native_local_rows=snap.matrix.shape[0],complete_native_primitive_columns=snap.matrix.shape[1],complete_nnz=snap.matrix.nnz))
        print('CANARY_FULL_BLOCK',day,i+1,len(data[7]['classes']),flush=True)
    atomic(folder/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(PASS=True,records=roster,producer='UNCHANGED_MAY19_FULL_NATIVE_BUILDER',frozen_input=record(frozen/'DATA.pkl')))
    path=static/'INITIAL_STATE.pkl.gz'
    with gzip.open(path,'xb',compresslevel=1) as f:pickle.dump(state,f,protocol=5)
    receipt=dict(PASS=True,day=day,state=record(path),input=record(inputs/'NATIVE_INPUT.json'),frozen_data=record(frozen/'DATA.pkl'),
        rows=state['compact'].matrix.shape[0],cols=state['compact'].matrix.shape[1],nnz=state['compact'].matrix.nnz,
        original_integer_snapshot=base.fingerprint(),all_classes=len(roster),source_builders_same_as_May19=True,
        projection_proofs=state['projection_proofs'],build_seconds=perf_counter()-t,solver_retuning=False)
    atomic(folder/'INITIAL_VERIFICATION.json',receipt);print('CANARY_PREPARED',day,receipt['rows'],receipt['cols'],flush=True)
    return state
