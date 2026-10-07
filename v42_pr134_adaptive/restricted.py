"""Restricted domain build through unchanged scientific native equations."""
import sys,gzip,pickle,time,copy
from dataclasses import replace,asdict
from collections import defaultdict,Counter
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_compact.graph import Graph
from v42_job_capability import Option,validate
from v42_pr134_b1.native import bind,objective_list,sc_namespace
from .common import *

def expand(data,selected):
    bundle,jobs,bounds,r,raw,graphs,old,prep=data
    bounds=dict(bounds);graphs=dict(graphs)
    selected_by=defaultdict(list)
    for item in selected:selected_by[item['class_id']].append(item)
    for key,items in selected_by.items():
        us=prep['classes'][key];uid=us[0];j=jobs[uid];original=graphs[uid]
        events={k:set(v) for k,v in original.events.items()};states={k:set(v) for k,v in original.states.items()}
        for row in items:
            if row['classification']!='CERTIFICATE_BREAKING' or int(row['checkpoint'])!=-1:raise PermissionError('ONLY_CERTIFIED_STAY_FIRST')
            site=str(row['site']);start=int(row['start']);end=start+j.service_slots
            events['y'].add((site,start));events['f0'].add((site,end));states['r0'].update((site,t) for t in range(start,end))
        allowed=tuple(sorted(set(bounds[uid].allowed_starts)|{int(x['start']) for x in items}))
        for u in us:
            b=replace(bounds[u],allowed_starts=allowed)
            for row in items:validate(jobs[u],Option(int(row['start']),str(row['site']),((str(row['site']),int(row['start']),int(row['start'])+jobs[u].service_slots),)),b,r)
            g=Graph({k:tuple(sorted(v)) for k,v in events.items()},{k:tuple(sorted(v)) for k,v in states.items()},original.compatible,original.physical,original.transfers,None)
            g.sha=digest(dict(events=g.events,states=g.states,old_sha=original.sha))
            graphs[u]=g;bounds[u]=b
    return (bundle,jobs,bounds,r,raw,graphs,old,prep)

def build(day,selected,folder):
    from v42_integrated.contract import all_transformer_rows,physical_authority
    import v42_boundary.model as boundary
    from v42_pr134_sc.snapshot import capture
    from v42_two.contract import aidc_groups,passes
    folder.mkdir(parents=True,exist_ok=True);data0=load(day);data=expand(data0,selected)
    bundle=data[0];dm,native,coeff,power,idle,swing=bind(bundle,PRODUCTION/'inputs'/day,folder)
    original_add=boundary.add_grid;boundary.add_grid=all_transformer_rows(original_add)
    boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
    class Context:
        def __init__(self):self.folder=folder
        def check(self):pass
        def progress(self,value):
            if value.get('classes_complete',value.get('units_complete',0))%20==0:print('build',day,value,flush=True)
    started=time.perf_counter()
    try:
        with physical_authority():m,units,levels,controls,bindings=native.build(Context(),data,'F2-CRA')
    finally:boundary.add_grid=original_add;boundary.planning_grid.__globals__['add_grid']=original_add
    m.update()
    # Capture the entire matrix and semantic interfaces BEFORE any optimization.
    a=m.getA();sp.save_npz(folder/'EXPANDED_MATRIX.npz',a)
    z={k:np.array(m.getAttr(attr)) for k,attr in [('lb','LB'),('ub','UB'),('sense','Sense'),('rhs','RHS'),('vtype','VType')]}
    np.savez_compressed(folder/'EXPANDED_ATTRIBUTES.npz',**z)
    np.savez_compressed(folder/'NATIVE_NAMES.npz',vars=np.array(m.getAttr('VarName')),rows=np.array(m.getAttr('ConstrName')))
    capture(m,units,levels,controls,bindings,folder/'SCIENTIFIC_INTERFACES.pkl.gz')
    active=objective_list([(name,expr) for _,name,expr in passes(aidc_groups(levels,units,data))])
    atomic(folder/'OBJECTIVES.json',active)
    with (folder/'DATA.pkl').open('wb') as f:pickle.dump(data,f,pickle.HIGHEST_PROTOCOL)
    from .global_identity import verify as verify_globals
    global_audit=verify_globals(day,folder);start=global_audit['global_rows'];global_identity=global_audit['PASS']
    if not global_identity:raise ValueError('GLOBAL_PHYSICAL_CC4_GRID_NUMERIC_IDENTITY')
    audit=dict(PASS=True,classes_before=data0[7]['classes'],classes_after=data[7]['classes'],class_counts_unchanged=data0[7]['classes']==data[7]['classes'],
        bundle_SHA=digest(data[0]),original_bundle_SHA=digest(data0[0]),
        resources_unchanged=data[3]==data0[3],jobs_unchanged=data[1]==data0[1],raw_Runtime_unchanged=data[4]==data0[4],
        latest_completion_unchanged=all(data[2][u].latest_completion==data0[2][u].latest_completion for u in data[1]),
        global_grid_CC4_WAN_prefix_rows=start,global_physical_coefficients_RHS_senses_exact_equal=global_identity,
        class_exact_cardinality_rows=m.getAttr('ConstrName').count('class_exact_cardinality'),
        zero_objective_until_domain_freeze=True,four_objectives=[x['name'] for x in active],original_equation_source=record(ROOT/'v42_root/native.py'),
        selected=selected,full_pool_in_native_model=False,CC4_changed=False,voltage_limits_changed=False,capacity_changed=False,service_changed=False,future_information_used=False)
    if not all(audit[x] for x in ('class_counts_unchanged','resources_unchanged','jobs_unchanged','raw_Runtime_unchanged','latest_completion_unchanged')):raise ValueError('PHYSICAL_AUTHORITY_DRIFT')
    atomic(folder/'DOMAIN_AUTHORITY_AUDIT.json',audit)
    census=dict(rows=m.NumConstrs,cols=m.NumVars,binary=m.NumBinVars,integer=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,nnz=m.NumNZs,
        build_seconds=time.perf_counter()-started,added_classes=len(set(x['class_id'] for x in selected)),added_options=len(selected),
        added_starts=len(set((x['class_id'],x['start']) for x in selected)),added_sites=len(set((x['class_id'],x['site']) for x in selected if str(x['site'])!=data[1][data[7]['classes'][x['class_id']][0]].reference_site)),added_migration_lanes=0)
    atomic(folder/'CENSUS.json',census)
    return m,data,units,levels,controls,bindings,census

def execute(day,selected,tag):
    raise PermissionError('DIRECT_MUTABLE_PROTOTYPE_DISABLED; use build_only then solve_snapshot with immutable input and fresh identity')
    folder=CASE/day/tag
    if (folder/'RESULT.json').exists():raise PermissionError('NO_DUPLICATE_RESTRICTED_SOLVE')
    import psutil
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==psutil.Process().pid:continue
        cmd=' '.join(p.info['cmdline'] or [])
        if str(p.info['name']).lower().startswith('python') and any(x in cmd for x in ('v42_pr134_b1.worker','v42_pr134_adaptive.restricted','v42_pr134_adaptive.capacity_master','v42_pr134_adaptive.minimum_probe','v42_pr134_adaptive.solve_snapshot')):raise PermissionError('OTHER_HEAVY_OPTIMIZER:'+str(p.pid))
    atomic(folder/'START.json',dict(day=day,tag=tag,selected=selected,solver=SETTINGS,limit_per_test=600,started=now()))
    m,data,units,levels,controls,bindings,census=build(day,selected,folder)
    m.setObjective(0.)
    for key,value in SETTINGS.items():m.setParam(key,value)
    m.Params.TimeLimit=600.;m.Params.OutputFlag=1;m.Params.LogFile=str(folder/'MIP_NATIVE.log')
    m.update();lp=m.relax();lp.Params.InfUnbdInfo=1;lp.Params.DualReductions=0;lp.Params.LogFile=str(folder/'LP_NATIVE.log')
    lp.optimize()
    result=dict(day=day,tag=tag,selected=selected,census=census,LP_status=lp.Status,LP_runtime=lp.Runtime,LP_Work=lp.Work,LP_iterations=lp.IterCount,
        LP_primal_residual=lp.ConstrVio if lp.SolCount else None,MIP_status=None,MIP_runtime=0.,classification='UNRESOLVED')
    if lp.Status==gp.GRB.INFEASIBLE:
        np.savez_compressed(folder/'RAW_FARKAS.npz',ray=np.array(lp.getAttr('FarkasDual')),rows=np.arange(lp.NumConstrs),columns=np.arange(lp.NumVars))
        result['classification']='RESTRICTED_LP_INFEASIBLE'
    elif lp.Status==gp.GRB.OPTIMAL and lp.SolCount:
        np.savez_compressed(folder/'LP_RAW_POINT.npz',values=np.array(lp.getAttr('X')))
        lp.dispose();lp=None
        m.optimize()
        result.update(MIP_status=m.Status,MIP_runtime=m.Runtime,MIP_Work=m.Work,nodes=m.NodeCount,solutions=m.SolCount,
            primal_residual=m.ConstrVio if m.SolCount else None,integer_residual=m.IntVio if m.SolCount else None)
        if m.SolCount:
            x=np.array(m.getAttr('X'));np.savez_compressed(folder/'MIP_RAW_POINT.npz',values=x)
            from v42_pr134_sc.build import replay
            audit=replay(m.getA(),dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz')),x)
            atomic(folder/'RAW_POINT_ALL_ROWS_REPLAY.json',audit)
            if audit['PASS']:
                result['classification']='INTEGER_FEASIBLE_RAW_POINT_AWAITING_PHYSICAL_VERIFIER'
                selected_jobs=__import__('v42_root.native',fromlist=['reconstruct']).reconstruct(units,data)
                atomic(folder/'SELECTED_PHYSICAL_OPTIONS.json',selected_jobs)
        elif m.Status==gp.GRB.INFEASIBLE:result['classification']='RESTRICTED_MIP_INFEASIBLE'
    atomic(folder/'RESULT.json',result)
    if lp is not None:lp.dispose()
    m.dispose();print('RESTRICTED_RESULT',result,flush=True)
    return result

if __name__=='__main__':
    day,selection,tag=sys.argv[1:];execute(day,read(selection),tag)
