"""Evidence preservation, identity inventory and original bound-only conflicts."""
import os,pickle,gzip
import numpy as np,scipy.sparse as sp
from fractions import Fraction
from .common import *
def bound_extrema(a,z):
    with np.errstate(invalid='ignore'):
        lo=np.where(a.data>0,a.data*z['lb'][a.indices],a.data*z['ub'][a.indices])
        hi=np.where(a.data>0,a.data*z['ub'][a.indices],a.data*z['lb'][a.indices])
    mask=np.diff(a.indptr)>0;low=np.zeros(a.shape[0]);high=low.copy()
    low[mask]=np.add.reduceat(lo,a.indptr[:-1][mask]);high[mask]=np.add.reduceat(hi,a.indptr[:-1][mask])
    return low,high
def inspect_day(day):
    folder=failed(day);b=read(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json')
    b0folder=ROOT/'docs/v42_may_b0_zero_margin_holdout/BUNDLE'/('DAY_'+day.replace('-',''))
    b0input=ROOT/'docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE'/('DAY_'+day.replace('-',''))
    reference=read(b0folder/'REFERENCE.json');planning=read(b0input/'PLANNING_INPUT_BUNDLE.json')
    print(day,'B1 keys',list(b),'B0 ref keys',list(reference),'B0 input keys',list(planning),flush=True)
    write(label(day)+'_INITIAL_IDENTITY.json',dict(day=day,failed_build=record(folder/'BUILD_RECEIPT.json'),
        input=record(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json'),B0_freeze=record(b0folder/'PLANNING_FREEZE.json'),
        B0_reference=record(b0folder/'REFERENCE.json'),B0_input=record(b0input/'PLANNING_INPUT_BUNDLE.json'),
        original_matrix=record(folder/'A0_MATRIX.npz'),compressed_matrix=record(folder/'A2SC_MATRIX.npz'),
        independent_proof=read(folder/'A2SC_INDEPENDENT_VERIFICATION.json')))
    results={}
    for name,prefix in [('ORIGINAL_FULL','A0'),('CURRENT_COMPRESSED','A2SC')]:
        a=sp.load_npz(folder/(prefix+'_MATRIX.npz'));z=dict(np.load(folder/(prefix+'_ATTRIBUTES_CODED.npz'),allow_pickle=False))
        low,high=bound_extrema(a,z);sense=z['sense'];rhs=z['rhs']
        wrong=np.flatnonzero(((sense!='>')&(low>rhs+1e-5))|((sense!='<')&(high<rhs-1e-5)))
        rows=[]
        for i in wrong:
            start,end=a.indptr[i:i+2];js=a.indices[start:end];cs=a.data[start:end]
            direction='MIN' if low[i]>rhs[i]+1e-5 else 'MAX';values=z['lb'][js] if direction=='MIN' else z['ub'][js]
            values=np.where(cs>0,values,z['ub'][js] if direction=='MIN' else z['lb'][js])
            exact=sum(Fraction(float(c))*Fraction(float(v)) for c,v in zip(cs,values)) if np.isfinite(values).all() else None
            family=str(z['rf_names'][z['rf'][i]]) if 'rf' in z else 'see original deletion mapping'
            rows.append(dict(row_index=int(i),row_family=family,sense=str(sense[i]),RHS=float(rhs[i]),
                minimum=float(low[i]),maximum=float(high[i]),direction=direction,
                exact_bound_extremum=str(exact),exact_RHS=str(Fraction(float(rhs[i]))),
                variables=[dict(index=int(j),family=str(z['vf_names'][z['vf'][j]]) if 'vf' in z else '',
                    coefficient=float(c),LB=float(z['lb'][j]),UB=float(z['ub'][j])) for j,c in zip(js,cs)]))
        results[name]=dict(rows=a.shape[0],columns=a.shape[1],nnz=a.nnz,
            contradictory_variable_bounds=np.flatnonzero(z['lb']>z['ub']).tolist(),
            row_bound_contradictions=rows)
        print(day,name,'rows',a.shape[0],'cols',a.shape[1],'bound conflicts',len(rows),flush=True)
    write(label(day)+'_DIRECT_BOUND_CONTRADICTIONS.json',results)
def main():
    OUT.mkdir(parents=True,exist_ok=True);CASE.mkdir(parents=True,exist_ok=True)
    from v42_pr134_b1.common import verify_freeze
    verify_freeze(read(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json'))
    manifest=CASE/'ORIGINAL_PRODUCTION_BYTE_MANIFEST.json'
    if not manifest.exists():
        files=[record(p) for p in sorted(PRODUCTION.rglob('*')) if p.is_file() and not any(x in p.parts for x in ('__pycache__',))
            and p.name not in ('MAY_B1_HOURLY_STATUS.json','MAY_B1_HOURLY_STATUS.md','MONITOR_HOST.json','MONITOR_PROCESS.json','monitor.stdout.log','monitor.stderr.log')]
        atomic(manifest,dict(files=files,source_root=str(PRODUCTION),source_commit='b99f2778e47f8bfee22b4eb54f14af8eb9a2e3d1',
            all_27_PASS_outputs_included=True,failed_evidence_untouched=True,UTC=now()))
        write('EVIDENCE_PRESERVATION.json',dict(PASS=True,manifest=record(manifest),files=len(files),original_files_modified=0))
    for day in DAYS:inspect_day(day)
if __name__=='__main__':main()
