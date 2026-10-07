"""One original-model diagnostic and an independently evaluated IIS LP ray."""
import argparse,time,gc
from collections import defaultdict,Counter
from fractions import Fraction as Q
import gurobipy as gp
import numpy as np,scipy.sparse as sp
from .common import *
from .static_gate import arrays

def exact_ray(a,z,ray):
    combined=defaultdict(Q);rhs=Q(0);sign=[];used=[]
    for i in np.flatnonzero(ray):
        weight=Q(float(ray[i]));sense=str(z['sense'][i])
        if sense=='<' and weight<0 or sense=='>' and weight>0:sign.append(int(i))
        rhs+=weight*Q(float(z['rhs'][i]));p,q=a.indptr[i:i+2]
        for j,c in zip(a.indices[p:q],a.data[p:q]):combined[int(j)]+=weight*Q(float(c))
        used.append(dict(row=int(i),multiplier=str(weight),sense=sense,RHS=str(Q(float(z['rhs'][i])))))
    minimum=Q(0);bad=[];terms=[]
    for j,c in sorted(combined.items()):
        if not c:continue
        value=z['lb'][j] if c>0 else z['ub'][j]
        if not np.isfinite(value):bad.append(dict(variable=j,coefficient=str(c),selected_bound=str(value)));continue
        minimum+=c*Q(float(value));terms.append(dict(variable=j,coefficient=str(c),bound=str(Q(float(value)))))
    return dict(PASS=not sign and not bad and minimum>rhs,exact_minimum=str(minimum),exact_rhs=str(rhs),
        contradiction_margin=str(minimum-rhs),margin_float=float(minimum-rhs),invalid_sign_rows=sign,
        unbounded_residual_terms=bad,rows=used,bound_terms=terms,
        arithmetic='Exact fractions of binary64 snapshot coefficients, bounds, RHS and raw native ray; no residual dropping')

def run(day):
    for d in DAYS:
        if not read(OUT/(label(d)+'_MODEL_IDENTITY.json'))['PASS']:raise PermissionError('THREE_MODEL_STATIC_GATE')
    if not read(OUT/('B0_TO_B1_NESTING_AUDIT_'+label(day)+'.json'))['direct_witness_status'].startswith('UNAVAILABLE'):raise PermissionError('WITNESS_BRANCH_MUST_BE_EXPLICIT')
    target=CASE/day;receipt=OUT/(label(day)+'_ORIGINAL_NATIVE_DIAGNOSIS.json')
    if receipt.exists():raise PermissionError('ONE_ORIGINAL_DIAGNOSTIC_ALREADY_RECORDED')
    a,z=arrays(target,'A0');names=dict(np.load(target/'ORIGINAL_NATIVE_NAMES.npz'))
    m=gp.Model('PR134_ORIGINAL_FULL_'+day);m.Params.OutputFlag=0
    x=m.addMVar(a.shape[1],lb=z['lb'],ub=z['ub'],vtype=z['vtype'],obj=z['obj']);m.addMConstr(a,x,z['sense'],z['rhs']);m.update()
    m.setAttr('VarName',names['vars'].tolist());m.setAttr('ConstrName',names['rows'].tolist());m.update()
    for key,v in SETTINGS.items():m.setParam(key,v)
    m.Params.LogFile=str(target/'ORIGINAL_FULL_DIAGNOSIS.log');m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.TimeLimit=BUDGET
    m.optimize();spent=float(m.Runtime)
    result=dict(day=day,status=m.Status,native_runtime=spent,original_model=True,scientific_settings=SETTINGS,
        raw_native_names=record(target/'ORIGINAL_NATIVE_NAMES.npz'),model_matrix=record(target/'A0_MATRIX.npz'),
        original_model_native_fingerprint=m.Fingerprint,optimization_calls=1,SolCount=m.SolCount,
        root_iterations=float(m.IterCount),nodes=float(m.NodeCount),Work=float(m.Work),
        scientific_infeasibility_independently_proven=False)
    atomic(receipt,result)
    print(day,'original status',m.Status,'runtime',spent,flush=True)
    if m.Status!=gp.GRB.INFEASIBLE:
        if m.SolCount:np.savez_compressed(target/'ORIGINAL_RAW_WITNESS.npz',values=np.array(m.getAttr('X')))
        m.dispose();return
    m.Params.TimeLimit=max(0,BUDGET-spent);begin=time.perf_counter();m.computeIIS();spent+=time.perf_counter()-begin
    rows=np.flatnonzero(np.array(m.getAttr('IISConstr')));lbs=np.flatnonzero(np.array(m.getAttr('IISLB')));ubs=np.flatnonzero(np.array(m.getAttr('IISUB')))
    m.write(str(OUT/(label(day)+'_ORIGINAL_IIS.ilp')))
    result.update(IIS_rows=rows.tolist(),IIS_LB_variables=lbs.tolist(),IIS_UB_variables=ubs.tolist(),IIS_minimal=bool(m.IISMinimal),
        diagnostic_native_and_IIS_wall_accounted=spent,IIS_file=record(OUT/(label(day)+'_ORIGINAL_IIS.ilp')))
    conflicts=[]
    for i in rows:
        p,q=a.indptr[i:i+2]
        conflicts.append(dict(row_index=int(i),row_name=str(names['rows'][i]),family=str(z['rf_names'][z['rf'][i]]),
            sense=str(z['sense'][i]),RHS=float(z['rhs'][i]),variables=';'.join(str(names['vars'][j])+':'+repr(float(c)) for j,c in zip(a.indices[p:q],a.data[p:q]))))
    table(OUT/(label(day)+'_ORIGINAL_IIS_ROWS.csv'),conflicts,['row_index','row_name','family','sense','RHS','variables'])
    m.dispose();del m,x;gc.collect()
    # A continuous IIS relaxation is a certificate problem, not a modified
    # production model. LP infeasibility proves integer-model infeasibility.
    columns=np.unique(a[rows].indices);small=a[rows][:,columns]
    # IISLB/IISUB omit implicit binary domains. Retaining every original
    # bound makes this an exact relaxation of a subset of original rows,
    # sufficient (not necessarily minimal) for an original infeasibility proof.
    iz=dict(lb=z['lb'][columns],ub=z['ub'][columns],rhs=z['rhs'][rows],sense=z['sense'][rows])
    lp=gp.Model('ORIGINAL_IIS_CERTIFICATE_ONLY');lp.Params.OutputFlag=0
    lx=lp.addMVar(len(columns),lb=iz['lb'],ub=iz['ub']);lp.addMConstr(small,lx,iz['sense'],iz['rhs']);lp.update()
    lp.Params.Threads=1;lp.Params.Method=1;lp.Params.InfUnbdInfo=1;lp.Params.DualReductions=0
    lp.Params.TimeLimit=max(0,BUDGET-spent);lp.Params.LogFile=str(target/'ORIGINAL_IIS_LP_CERTIFICATE.log');lp.optimize();spent+=lp.Runtime
    result.update(IIS_LP_status=lp.Status,IIS_LP_native_runtime=lp.Runtime,diagnostic_budget_used=spent,
        IIS_LP_certificate_only=True,IIS_LP_all_original_bounds_retained=True,production_settings_changed=False)
    if lp.Status==gp.GRB.INFEASIBLE:
        ray=np.array(lp.getAttr('FarkasDual'));np.savez_compressed(target/'ORIGINAL_IIS_RAW_FARKAS.npz',ray=ray,rows=rows,columns=columns)
        cert=exact_ray(small,iz,ray);atomic(target/'EXACT_RAW_FARKAS_CHECK.json',cert)
        result.update(raw_FarkasProof=float(lp.FarkasProof),exact_ray_PASS=cert['PASS'],
            exact_ray_summary={k:v for k,v in cert.items() if k not in ('rows','bound_terms')},
            exact_ray=record(target/'EXACT_RAW_FARKAS_CHECK.json'),raw_ray=record(target/'ORIGINAL_IIS_RAW_FARKAS.npz'),
            scientific_infeasibility_independently_proven=cert['PASS'])
    lp.dispose();atomic(receipt,result)
    print(day,'IIS',len(rows),'rows',len(columns),'cols','certificate',result.get('exact_ray_PASS'),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('day',choices=DAYS);run(parser.parse_args().day)
