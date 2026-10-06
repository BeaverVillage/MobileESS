"""Read-only native presolve, never optimize; no scientific deletion authority."""
from .common import *
from v42_redundancy.model import build
from v42_integrated.matrix import arrays
import gurobipy as gp,time,gc
def run(label='C2'):
    begin=time.perf_counter();A,d=load(label);m=build(A,d)
    m.Params.PreCrush=1;m.Params.LazyConstraints=0;m.Params.OutputFlag=1;m.Params.LogToConsole=0
    m.Params.LogFile=str(OUT/(label+'_PRESOLVE.log'))
    before=census(A,d);before.update(SOS=m.NumSOS,general_constraints=m.NumGenConstrs,native_rows=m.NumConstrs,native_columns=m.NumVars,native_nnz=m.NumNZs)
    p=m.presolve();B,e=arrays(p);after=census(B,e);after.update(SOS=p.NumSOS,general_constraints=p.NumGenConstrs)
    # Name survival identifies candidates, never an uncrush/aggregation proof.
    col={str(n):j for j,n in enumerate(e['names'])};row=set(map(str,e['row_names']));entries=[];tightened=[]
    for j,n in enumerate(d['names']):
        k=col.get(str(n));r=dict(kind='COLUMN',original_id=j,name=str(n),family=family(n),presolved_id=k,classification='REMOVED_OR_AGGREGATED_UNAVAILABLE' if k is None else 'SURVIVES_BY_NAME',old_lower=d['lower'][j],old_upper=d['upper'][j])
        if k is not None:
            r.update(new_lower=e['lower'][k],new_upper=e['upper'][k])
            if e['lower'][k]>d['lower'][j] or e['upper'][k]<d['upper'][j]:r['classification']='BOUND_TIGHTENED_BY_NAME';tightened.append(r.copy())
        entries.append(r)
    for i,n in enumerate(d['row_names']):
        # Parent scientific row names may repeat; name survival cannot map them.
        entries.append(dict(kind='ROW',original_id=i,name=str(n),family=family(n),classification='NAME_SURVIVAL_NOT_ROW_MAPPING' if str(n) in row else 'NAME_ABSENT_NOT_PROOF'))
    if label=='C2':table('C2_PRESOLVE_CANDIDATE_MAP.csv',entries,['kind','original_id','name','family','presolved_id','classification','old_lower','old_upper','new_lower','new_upper'])
    sparse.save_npz(OUT/(label+'_PRESOLVED_A.npz'),B);np.savez_compressed(OUT/(label+'_PRESOLVED_DATA.npz'),**e)
    # MPS writer rounds decimals; roundtrip is forensic only. Losslessly captured
    # native CSR above is the authority for size and numerical observations.
    target=OUT/(label+'_PRESOLVED.mps');export_error=None;readback=None
    try:
        p.write(str(target));q=gp.read(str(target));readback=dict(rows=q.NumConstrs,columns=q.NumVars,binaries=q.NumBinVars,nnz=q.NumNZs);q.dispose()
    except gp.GurobiError as ex:export_error=str(ex)
    import gzip,shutil
    export_sha=sha(target) if target.exists() else None;packed=target.with_suffix('.mps.gz')
    if target.exists():
        with target.open('rb') as source,gzip.open(packed,'wb',compresslevel=6) as dest:shutil.copyfileobj(source,dest)
        target.unlink() # Only the explicit task-owned MPS, after successful capture/read.
    result=dict(PASS=True,label=label,Gurobi_version=list(gp.gurobi.version()),original=before,presolved=after,fixed_original=int(np.sum(d['lower']==d['upper'])),fixed_presolved=int(np.sum(e['lower']==e['upper'])),removed_columns=A.shape[1]-B.shape[1],removed_rows=A.shape[0]-B.shape[0],aggregation_mapping_available=False,aggregation_reason='Model.presolve returns a model, not an original-variable uncrush map; absent names are not asserted fixed.',surviving_name_bound_tightenings=len(tightened),bound_tightenings=tightened,original_unchanged=before['signature']==census(*load(label))['signature'],optimize_calls=0,scientific_proof=False,export_readback=readback,export_error=export_error,export_uncompressed_SHA256=export_sha,export_gzip_SHA256=sha(packed) if packed.exists() else None,wall=time.perf_counter()-begin)
    write('C2_PRESOLVE_FORENSIC.json' if label=='C2' else label+'_PRESOLVED_CENSUS.json',result)
    p.dispose();m.dispose();gc.collect();print('READ_ONLY_PRESOLVE',label,before['rows'],after['rows'],after['columns'],after['nnz'],'wall',result['wall'],flush=True);return result
if __name__=='__main__':
    import sys;run(sys.argv[1] if len(sys.argv)>1 else 'C2')
