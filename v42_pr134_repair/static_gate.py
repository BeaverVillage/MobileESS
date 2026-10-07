"""Read-only scientific reconstruction and nesting audit; no optimize calls."""
import gc,gzip,pickle,shutil,json
import numpy as np, scipy.sparse as sp
import gurobipy as gp
from .common import *

def arrays(folder,prefix):
    z=dict(np.load(folder/(prefix+'_ATTRIBUTES_CODED.npz')))
    z['lb']=np.where(z['lb']<=-1e100,-np.inf,z['lb'])
    z['ub']=np.where(z['ub']>=1e100,np.inf,z['ub'])
    return sp.load_npz(folder/(prefix+'_MATRIX.npz')),z

def nesting(day):
    base=ROOT/'docs/v42_may_b0_zero_margin_holdout';d='DAY_'+day.replace('-','')
    p=read(base/'INPUT/BUNDLE'/d/'PLANNING_INPUT_BUNDLE.json')
    refs=read(base/'BUNDLE'/d/'REFERENCE.json');b=read(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json')
    r0={r['job_uid']:r for r in refs['rows']};r1={r['job_uid']:r for r in b['known_population']}
    with (failed(day)/'DATA.pkl').open('rb') as f:data=pickle.load(f)
    _,jobs,bounds,res,raw,graphs,_,_=data
    differences=[];domain=[];fatal=[]
    for uid in sorted(r0):
        x,y=r0[uid],r1[uid]
        for k,l in [('state','state'),('GPU_gang','GPU_gang'),('runtime_authority','runtime_authority'),('Q50_total_seconds','V10_Q50_total_seconds'),('service_slots','service_slots'),('nominal_remaining_seconds','nominal_remaining_seconds')]:
            if x.get(k)!=y.get(l):fatal.append(dict(job_uid=uid,field=k,B0=x.get(k),B1=y.get(l)))
        # PENDING elapsed None and 0 both mean no elapsed service; placement
        # compatibility is reconstructed from the frozen physical envelope.
        if (x.get('elapsed_seconds') or 0)!=(y.get('elapsed_seconds') or 0):fatal.append(dict(job_uid=uid,field='elapsed_seconds'))
        if uid not in jobs:continue
        j=jobs[uid];g=graphs[uid];s,t=x['planning_site'],x['reference_start']
        reason=[]
        if s!=j.reference_site:reason.append('NONZERO_PRESTART_RELOCATION_RELATIVE_TO_PR134_R0')
        if t!=j.reference_start:reason.append('NONZERO_TIMESHIFT_RELATIVE_TO_PR134_R0')
        if g.fixed:
            allowed=(s,t)==(g.fixed.initial_site,g.fixed.start)
        else:allowed=(s,t) in g.events['y']
        if not allowed:reason.append('B0_START_SITE_ABSENT_COMPLETE_PR134_DOMAIN')
        rr=dict(job_uid=uid,B0_site=s,B1_site=j.reference_site,B0_start=t,B1_start=j.reference_start,
            GPU=j.gpu,service_slots=j.service_slots,allowed_starts=list(bounds[uid].allowed_starts),
            fixed_domain=g.fixed is not None,B0_point_in_domain=allowed,reason=';'.join(reason))
        domain.append(rr)
        if reason:differences.append(rr)
    cols=list(domain[0]);table(OUT/(label(day)+'_ZERO_ACTION_DOMAIN_AUDIT.csv'),domain,cols)
    facts=dict(day=day,physical_population_equal=set(r0)==set(r1),Runtime_GPU_service_mismatches=fatal,
        same_current_C0_Q50=p['forecast_inputs']['current_CC4']['Q50_GPUh']==b['C0_Q50'],
        same_current_C0_Q90=p['forecast_inputs']['current_CC4']['Q90_GPUh']==b['C0_Q90'],
        same_capacity=p['capacities']==b['capacities'],same_issue=p['issue_time']==b['issue_time'],
        B0_reference=record(base/'BUNDLE'/d/'REFERENCE.json'),B1_reference=b['reference'],
        B0_rule=refs['audit']['queue_rule'],B1_rule='PR134_ORIGINAL_R0_REQUESTED_DURATION_REFERENCE_WITH_CURRENT_Q50_SERVICE',
        zero_action_embedding=False if differences else None,differing_positive_jobs=len(differences),
        absent_start_site_jobs=sum(not x['B0_point_in_domain'] for x in domain),first_counterexample=differences[:5],
        timing_axis='Both issue-relative slots; day controls use issue slots24..119',
        B0_CC4_rule='capacity queue retains carryout/backlog',B1_CC4_rule='cohort temporal Q10/Q90 cumulative envelope and work-conservation',
        B0_to_B1_CC4_embedding_proven=False,C1_grid_embedding_proven=False,
        direct_witness_status='UNAVAILABLE_ZERO_ACTION_DOMAIN_COUNTEREXAMPLE',
        scientific_change_to_force_embedding_permitted=False,optimization_calls=0,
        explanation='B0 current FCFS Q50 reference is not the PR134 R0 reference. Identical service does not imply identical admitted no-action trajectory. No witness is fabricated or rounded.')
    if fatal:raise ValueError('CURRENT_RUNTIME_POPULATION_MISMATCH')
    write('B0_TO_B1_NESTING_AUDIT_'+label(day)+'.json',facts)
    for name in ('ORIGINAL','COMPRESSED'):
        table(OUT/(label(day)+'_'+name+'_WITNESS_VIOLATIONS.csv'),[],
            ['row_name','row_family','LHS','RHS','sense','residual','involved_variables','counterpart','reduction'])
    write(label(day)+'_WITNESS_REPLAY_STATUS.json',dict(status=facts['direct_witness_status'],
        empty_violation_tables_mean_NO_WITNESS_NOT_PASS=True,fully_valid_integer_witness=False,
        numerical_rescue_authorized=False))
    print(day,'nesting absent:',len(differences),'outside domain:',facts['absent_start_site_jobs'],flush=True)

def reconstruction(day):
    from v42_pr134_b1.native import bind,objective_list
    from v42_integrated.contract import physical_authority,all_transformer_rows
    from v42_two.contract import aidc_groups,passes
    target=CASE/day;target.mkdir(exist_ok=True)
    for p in failed(day).iterdir():
        if p.is_file() and p.name not in ('A1_SOLVE.log',):
            q=target/p.name
            if not q.exists():shutil.copyfile(p,q)
    bundle=read(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json')
    data_mod,native,_,_,_,_=bind(bundle,PRODUCTION/'inputs'/day,target)
    class Context:
        folder=target
        def check(self):pass
        def progress(self,value):
            atomic(target/'STATIC_BUILD_PROGRESS.json',value)
    data=data_mod.prepare()
    import v42_boundary.model as boundary
    old=boundary.add_grid;boundary.add_grid=all_transformer_rows(old)
    boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
    try:
        with physical_authority():m,units,levels,controls,bindings=native.build(Context(),data,'F2-CRA')
    finally:
        boundary.add_grid=old;boundary.planning_grid.__globals__['add_grid']=old
    m.setObjective(levels[0][1]);m.update()
    a,z=arrays(target,'A0');actual=m.getA();delta=actual-a;delta.eliminate_zeros()
    if delta.nnz:raise ValueError('ORIGINAL_MATRIX_RECONSTRUCTION_DRIFT')
    for key,zkey in [('LB','lb'),('UB','ub'),('RHS','rhs'),('Sense','sense'),('Obj','obj'),('VType','vtype')]:
        got=np.array(m.getAttr(key))
        if key in ('LB','UB'):got=np.where(got<=-1e100,-np.inf,np.where(got>=1e100,np.inf,got))
        if not np.array_equal(got,z[zkey]):raise ValueError('ORIGINAL_'+key+'_DRIFT')
    active=[dict(group=group,**e) for (group,_,_),e in zip(passes(aidc_groups(levels,units,data)),objective_list([(name,expr) for _,name,expr in passes(aidc_groups(levels,units,data))]))]
    if active!=read(target/'ACTIVE_ORIGINAL_OBJECTIVES.json'):raise ValueError('ORIGINAL_FOUR_OBJECTIVE_DRIFT')
    np.savez_compressed(target/'ORIGINAL_NATIVE_NAMES.npz',vars=np.array(m.getAttr('VarName')),rows=np.array(m.getAttr('ConstrName')))
    result=dict(day=day,original_native_names=record(target/'ORIGINAL_NATIVE_NAMES.npz'),
        original_matrix=record(target/'A0_MATRIX.npz'),original_attributes=record(target/'A0_ATTRIBUTES_CODED.npz'),
        raw_original_fingerprint=m.Fingerprint,original_rebuilt_from_PR134=True,coefficient_differences=0,
        original_bounds_RHS_senses_objective_types_equal=True,all_four_objectives_equal=True,models=[])
    for key,v in SETTINGS.items():m.setParam(key,v)
    result['models'].append(dict(name='ORIGINAL_FULL',rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,
        binary=m.NumBinVars,integer=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,native_fingerprint=m.Fingerprint))
    m.dispose();del m,actual,a,z,units,levels,controls,bindings,data;gc.collect()
    a,z=arrays(target,'A2SC')
    for relaxed in (False,True):
        m=gp.Model('CURRENT_COMPRESSED_RELAXED' if relaxed else 'CURRENT_COMPRESSED');m.Params.OutputFlag=0
        x=m.addMVar(a.shape[1],lb=z['lb'],ub=z['ub'],vtype='C' if relaxed else z['vtype'],obj=z['obj'])
        m.addMConstr(a,x,z['sense'],z['rhs']);m.update()
        actual=m.getA();delta=actual-a;delta.eliminate_zeros()
        if delta.nnz:raise ValueError('COMPRESSED_MATRIX_DRIFT')
        for key,k in [('RHS','rhs'),('Sense','sense'),('Obj','obj')]:
            if not np.array_equal(np.array(m.getAttr(key)),z[k]):raise ValueError('COMPRESSED_'+key+'_DRIFT')
        for key in ('LB','UB'):
            got=np.array(m.getAttr(key));got=np.where(got<=-1e100,-np.inf,np.where(got>=1e100,np.inf,got))
            if not np.array_equal(got,z[key.lower()]):raise ValueError('COMPRESSED_BOUND_DRIFT')
        if not np.array_equal(np.array(m.getAttr('VType')),np.full(a.shape[1],'C') if relaxed else z['vtype']):raise ValueError('COMPRESSED_TYPE_DRIFT')
        for key,v in SETTINGS.items():m.setParam(key,v)
        result['models'].append(dict(name=m.ModelName,rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,
            binary=m.NumBinVars,integer=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,native_fingerprint=m.Fingerprint))
        m.dispose();del m,x,actual,delta;gc.collect()
    result.update(PASS=True,optimization_calls=0,solver_settings=SETTINGS,integrality_only_relaxed_in_third=True)
    write(label(day)+'_MODEL_IDENTITY.json',result)
    print(day,'three native models built and exact axes verified without optimize',flush=True)

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['nesting','models']);parser.add_argument('--day',choices=DAYS)
    args=parser.parse_args()
    for day in (args.day,) if args.day else DAYS:
        (nesting if args.operation=='nesting' else reconstruction)(day)
if __name__=='__main__':main()
