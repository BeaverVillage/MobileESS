"""Assemble the accepted PR134 authority. Native optimize is forbidden here."""
import os
os.environ.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
import json, pickle, shutil, sys, time, subprocess
from array import array
from collections import Counter
import numpy as np
import scipy.sparse as sp
from .common import *

ACCEPTED = ROOT/'docs/v42_single_worker_single_thread_a1_m1'
CACHE = Path(r'C:\Users\kjw39\Documents\Codex\2026-10-03\single-worker-single-thread-a1-m1\SINGLE_THREAD_LOCAL')
DATA_SHA = '79263899f1040d8b13b5af29dc881c52e83ac543c96f90f8e63e9061b637aa74'

def census(m):
    a=m.getA(); rd=np.diff(a.indptr); cd=np.bincount(a.indices,minlength=m.NumVars)
    return dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,
        integers=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,nnz=int(a.nnz),
        coefficient_min_abs=float(abs(a.data[a.data!=0]).min()) if a.nnz else 0,
        coefficient_max_abs=float(abs(a.data).max()) if a.nnz else 0,
        max_row_density=int(rd.max(initial=0)),max_column_density=int(cd.max(initial=0)))

def replay(a,z,x):
    activity=a@x
    violation=np.maximum(0,np.where(z['sense']=='<',activity-z['rhs'],
                          np.where(z['sense']=='>',z['rhs']-activity,abs(activity-z['rhs']))))
    bound=np.maximum(0,np.maximum(z['lb']-x,x-z['ub']))
    integer=np.abs(x[z['vtype']!='C']-np.rint(x[z['vtype']!='C']))
    worst=int(np.argmax(violation)); tolerance=1e-5
    return dict(PASS=max(violation.max(initial=0),bound.max(initial=0),integer.max(initial=0))<=tolerance,
        original_authority_tolerance=tolerance,all_rows_replayed=a.shape[0],all_columns_replayed=a.shape[1],
        max_row_violation=float(violation.max(initial=0)),max_bound_violation=float(bound.max(initial=0)),
        max_integrality_residual=float(integer.max(initial=0)),violations_over_authority=int((violation>tolerance).sum()),
        worst_row_index=worst,worst_row_family=str(z['rf_names'][z['rf'][worst]]),
        raw_point_rounded_or_clipped=False)

def run():
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=BASE:
        raise ValueError('PR134_EXACT_HEAD_REQUIRED')
    LOCAL.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    freeze=json.loads((ACCEPTED/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json').read_text(encoding='utf8'))
    source=json.loads((ACCEPTED/'A1_EXECUTED_SOURCE_RECEIPT.json').read_text(encoding='utf8'))
    assert freeze['PASS'] and freeze['accepted'] and freeze['physical']['PASS']
    for f in source['files']:
        assert sha(ROOT/f['path'])==f['sha256'],f['path']
    assert sha(CACHE/'DATA.pkl')==DATA_SHA==freeze['source_data_sha256']
    shutil.copyfile(CACHE/'DATA.pkl',LOCAL/'DATA.pkl')
    identity=dict(base=BASE,accepted_freeze=record(ACCEPTED/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json'),
        original_data=record(CACHE/'DATA.pkl'),original_raw_point=record(CACHE/'A1_FINAL_POINT.npz'),
        executed_source_files=source['files'],scientific_sources_unchanged=True,
        PR150_PR151_inputs_used=False,acceptance=freeze['result']['status'])
    write('PR134_BASE_IDENTITY.json',identity)
    os.environ['V42_ROOT_OUTPUT']=str(OUT.relative_to(ROOT))
    os.environ['V42_ROOT_LOCAL']=str(LOCAL)
    import gurobipy as gp
    original_model=gp.Model; row_labels=[]; row_codes=array('H'); label_codes={}
    class StaticModel(original_model):
        def optimize(self,*a,**kw):
            from v42_a_stage_domain_v2.execution import guard_model_optimize
            guard_model_optimize(self)
            raise PermissionError('STATIC_OPTIMIZE_FORBIDDEN')
        def addConstr(self,*a,**kw):
            n=kw.get('name',a[1] if len(a)>1 else '')
            frame=sys._getframe(1)
            family=n.split('[')[0] if n else 'row_'+Path(frame.f_code.co_filename).parent.name+'_'+str(frame.f_lineno)
            if family not in label_codes:
                label_codes[family]=len(row_labels);row_labels.append(family)
            row_codes.append(label_codes[family])
            return super().addConstr(*a,**kw)
    gp.Model=StaticModel
    from v42_root.data import prepare
    from v42_root.native import build
    from v42_integrated.contract import physical_authority,all_transformer_rows,evaluate,grid_audit
    from v42_two.contract import aidc_groups,passes
    from v42_root.certify import certificate
    import v42_boundary.model as boundary
    t=time.perf_counter()
    with physical_authority() as thermal:
        write('CURRENT_STATIC_THERMAL_AUTHORITY.json',thermal)
        data=prepare(); bundle=data[0]
        assert len(data[1])==1499 and bundle['day']=='2025-05-01' and bundle['RUNTIME_PROVIDER_READY']
        from v42_capacity.common import resolve
        sources=[]
        def walk(v):
            if isinstance(v,dict):
                if 'path' in v and 'sha256' in v:
                    p=resolve(v); assert sha(p)==v['sha256'];sources.append(record(p))
                for x in v.values():walk(x)
            elif isinstance(v,list):
                for x in v:walk(x)
        walk(bundle)
        bundle_path=ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'
        assert json.loads(bundle_path.read_text(encoding='utf8'))==bundle,'ACCEPTED_BUNDLE_DRIFT'
        identity.update(bundle=record(bundle_path),input_sources=sources,jobs=1499,horizon=96,
            cached_classes_independently_reverified=data[-1]['cached_classes_independently_reverified'])
        write('PR134_BASE_IDENTITY.json',identity)
        original=boundary.add_grid;boundary.add_grid=all_transformer_rows(original)
        class Context:
            folder=LOCAL
            def check(self):pass
            def progress(self,p):
                (LOCAL/'PROGRESS.json').write_text(json.dumps(clean(p)),encoding='utf8')
                if p.get('classes_complete',0)%25==0: print(p,flush=True)
        try:m,units,levels,controls,bindings=build(Context(),data,'F2-CRA')
        finally:boundary.add_grid=original
        m.setObjective(levels[0][1]);m.update()
        m.Params.Threads=1;m.Params.Method=1;m.Params.Seed=20260929;m.Params.MIPGap=.005
        c=census(m);c.update(jobs=1499,horizon=96,build_wall_seconds=time.perf_counter()-t,optimization_calls=0)
        write('A0_CENSUS.json',c);write('CURRENT_A0_MODEL_CENSUS.json',c)
        assert all(c[k]==v for k,v in dict(rows=9133426,columns=7449002,binaries=2223230,nnz=53767578).items()),'ACCEPTED_CENSUS_DRIFT'
        print('ACCEPTED_CENSUS_MATCH',c,flush=True)
        a=m.getA();vn=m.getAttr('VarName');rn=m.getAttr('ConstrName')
        old=np.load(CACHE/'A1_FINAL_POINT.npz');x=old['values'];names=old['names']
        axis=np.array_equal(np.asarray(vn),names)
        write('PR134_ACCEPTED_AXIS_AUDIT.json',dict(PASS=axis,columns=len(vn),
             mismatch_count=int(np.sum(np.asarray(vn)!=names)) if len(vn)==len(names) else None))
        assert axis,'ACCEPTED_POINT_AXIS_DRIFT'
        vf_labels=['unnamed_auxiliary'];vf_codes=np.zeros(m.NumVars,dtype=np.uint16);vfc={'unnamed_auxiliary':0}
        def mark(i,f):
            if f not in vfc:vfc[f]=len(vf_labels);vf_labels.append(f)
            vf_codes[i]=vfc[f]
        for u in units:
            for family,items in u['v'].items():
                for v in items.values():
                    if isinstance(v,gp.Var) and vf_codes[v.index]==0:mark(v.index,family)
        for group,items in bindings.items():
            if isinstance(items,dict):
                for v in items.values():
                    if isinstance(v,gp.Var) and vf_codes[v.index]==0:mark(v.index,group)
        for i,n in enumerate(vn):
            if vf_codes[i]==0:mark(i,n.split('[')[0] if not n.startswith('C') else 'unnamed_auxiliary')
        rf=np.array(row_codes,dtype=np.uint16); assert len(rf)==m.NumConstrs
        for i,n in enumerate(rn):
            if n.startswith('NormalAmps['):
                if 'NormalAmps' not in label_codes:label_codes['NormalAmps']=len(row_labels);row_labels.append('NormalAmps')
                rf[i]=label_codes['NormalAmps']
        z=dict(lb=np.array(m.getAttr('LB')),ub=np.array(m.getAttr('UB')),vtype=np.array(m.getAttr('VType')),
            sense=np.array(m.getAttr('Sense')),rhs=np.array(m.getAttr('RHS')),obj=np.array(m.getAttr('Obj')),
            vf=vf_codes,vf_names=np.array(vf_labels),rf=rf,rf_names=np.array(row_labels))
        np.savez_compressed(LOCAL/'A0_ATTRIBUTES_CODED.npz',**z);sp.save_npz(LOCAL/'A0_MATRIX.npz',a)
        np.savez_compressed(LOCAL/'ACCEPTED_POINT.npz',values=x)
        objective=[]
        def expr_row(n,ex):
            ex=gp.LinExpr(ex)
            return dict(name=n,constant=ex.getConstant(),indices=[ex.getVar(i).index for i in range(ex.size())],
                coefficients=[ex.getCoeff(i) for i in range(ex.size())])
        active=passes(aidc_groups(levels,units,data))
        objective=[expr_row(n,e) for n,e in levels]
        write('CURRENT_OBJECTIVE_HIERARCHY.json',objective)
        write('ACTIVE_OBJECTIVE_HIERARCHY.json',[dict(group=g,**expr_row(n,e)) for g,n,e in active])
        row_replay=replay(a,z,x)
        physical,selected,values,_=certificate(m,units,data,controls,bindings,levels,x,row_replay['max_row_violation'])
        from v42_bootstrap.grid import coefficients
        _,coeff=coefficients(bundle)
        physical['all_phase_grid']=grid_audit(coeff,values,evaluate(levels[0][1],x))
        physical['PASS']=physical['PASS'] and physical['all_phase_grid']['PASS']
        locks=[]
        for (g,n,e),r in zip(active,freeze['result']['passes']):
            val=evaluate(e,x);rhs=r['objective']+(1e-7 if n=='rho' else 1e-8)
            locks.append(dict(component=n,point_value=val,original_lock_rhs=rhs,PASS=val<=rhs+1e-5))
        control_diff=float(np.max(abs(np.array(values)-np.array(freeze['anchor']['controls']))))
        witness=dict(BASELINE_FEASIBLE_WITNESS_PASS=bool(row_replay['PASS'] and physical['PASS'] and all(r['PASS'] for r in locks) and control_diff<=1e-5),
            raw_point_axis_exact_match=axis,full_row_replay=row_replay,physical=physical,original_final_locks=locks,
            accepted_control_max_difference=control_diff,accepted_selected_jobs_equal=clean(selected)==freeze['selected_jobs'],
            original_raw_point=record(CACHE/'A1_FINAL_POINT.npz'),optimization_calls=0)
        write('PR134_ACCEPTED_WITNESS_REPLAY.json',witness)
        assert witness['BASELINE_FEASIBLE_WITNESS_PASS'],'ACCEPTED_FULL_MODEL_WITNESS_FAILED'
        table('A_STAGE_VARIABLE_FAMILY_CENSUS.csv',[dict(family=f,count=int(np.sum(vf_codes==i))) for i,f in enumerate(vf_labels)])
        table('A_STAGE_ROW_FAMILY_CENSUS.csv',[dict(family=f,count=int(np.sum(rf==i))) for i,f in enumerate(row_labels)])
        identity.update(model_fingerprint=m.Fingerprint,matrix=record(LOCAL/'A0_MATRIX.npz'),attributes=record(LOCAL/'A0_ATTRIBUTES_CODED.npz'),
             active_objectives=record(OUT/'ACTIVE_OBJECTIVE_HIERARCHY.json'),raw_census=c)
        write('PR134_BASE_IDENTITY.json',identity)
        write('A0_MODEL_FREEZE.json',identity)
        print('BASELINE_FEASIBLE_WITNESS_PASS',flush=True)
        del a,rn,vn,old,names
        m.Params.LogFile=str(LOCAL/'A0_PRESOLVE.log');m.Params.OutputFlag=1
        t=time.perf_counter();p=m.presolve();pc=census(p)
        pc.update(wall_seconds=time.perf_counter()-t,original=c,optimization_calls=0,
            fixed_variables=int(np.sum(z['lb']==z['ub'])),eliminated_rows=m.NumConstrs-p.NumConstrs,
            eliminated_columns=m.NumVars-p.NumVars,discovery_only=True,variable_mapping_available=False,
            implied_bounds='Supported presolve API does not expose mapping; exact propagation certified separately',
            aggregation_candidates='Discovery only; unsupported permanent deletion forbidden')
        write('A0_PRESOLVE_FORENSIC.json',pc);write('CURRENT_A0_PRESOLVE_FORENSIC.json',pc)
        p.dispose();m.dispose()
    gp.Model=original_model

if __name__=='__main__':run()
