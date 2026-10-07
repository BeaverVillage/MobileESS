"""One conditional C3S root-only test: native PR162 settings, NodeLimit=1."""
import json,re
from collections import defaultdict
import numpy as np
from scipy import sparse
from pure_lp import OUT,PARENT,write,load,replay,sha
from analyze_point import context,SOURCE

def main():
    summary=json.loads((OUT/'LP_STRENGTHENING_SUMMARY.json').read_text())
    assert summary['materially_strengthened'],'NO_AUTHORIZATION_WITHOUT_MATERIAL_STRENGTHENING'
    assert not (OUT/'C3S_ROOT_ONCE.json').exists(),'ROOT_RETRY_FORBIDDEN'
    c=context();A,d,start=c['A'],c['d'],c['start'];cuts=json.loads((OUT/'SELECTED_CUTS.json').read_text());assert cuts
    proof=json.loads((OUT/'INEQUALITY_INDEPENDENT_VERIFICATION.json').read_text());assert proof['PASS']
    rr=[];cc=[];vv=[]
    for i,q in enumerate(cuts):
        for j,w in q['terms'].items():rr.append(i);cc.append(int(j));vv.append(w)
    C=sparse.csr_matrix((vv,(rr,cc)),shape=(len(cuts),A.shape[1]));S=sparse.vstack([A,C],format='csr')
    e=dict(d,rhs=np.r_[d['rhs'],[q['rhs'] for q in cuts]],sense=np.r_[d['sense'],np.full(len(cuts),'<')],row_names=np.r_[d['row_names'],['exact_hull_'+q['id'] for q in cuts]])
    assert (S[:A.shape[0]]!=A).nnz==0
    sparse.save_npz(OUT/'C3S_ADDED_ROWS.npz',C)
    startcheck=replay(S,e,start)
    n=len(c['full']['names']);original=c['offset'].copy();nz=c['target']>=0;original[nz]+=start[c['target'][nz]];original=original[:n]
    assert np.array_equal(original[c['full']['types']!='C'],np.rint(original[c['full']['types']!='C']))
    from v42_one_tree_bc.audit import Validator
    physical=Validator(sparse.load_npz(SOURCE/'FULL_A.npz'),c['full'])(original)
    assert startcheck['PASS'] and physical['PASS'],'ORIGINAL_VALIDATED_START_MUST_PASS'
    write('C3S_START_REPLAY.json',dict(PASS=True,C3S_matrix=startcheck,original_physical_validation=physical,start_SHA256=sha(PARENT/'C3A_VALID_START.npz'),point_changed=False,physical_P1_P2_changed=False))
    write('C3S_MODEL_CENSUS.json',dict(C3A=dict(rows=A.shape[0],columns=A.shape[1],binaries=9322,continuous=296718,nnz=A.nnz),added=dict(rows=len(cuts),columns=0,nnz=C.nnz),C3S=dict(rows=S.shape[0],columns=S.shape[1],binaries=9322,continuous=296718,nnz=S.nnz),baseline_rows_deleted=0))
    write('C3S_AUTHORITY.json',dict(PASS=True,C3A_matrix_SHA256=sha(PARENT/'C3A_A.npz'),C3A_data_SHA256=sha(PARENT/'C3A_DATA.npz'),selected_cuts_SHA256=sha(OUT/'SELECTED_CUTS.json'),added_matrix_SHA256=sha(OUT/'C3S_ADDED_ROWS.npz'),integer_feasible_set_unchanged=True,P1_P2_unchanged=True,proof='INEQUALITY_INDEPENDENT_VERIFICATION.json',material_selection=summary))
    import gurobipy as gp
    from v42_redundancy.model import build
    model=build(S,e);settings=json.loads((OUT/'aborted_1h_provenance/SOLVER_PARAMETERS.json').read_text())['settings']
    settings.update(TimeLimit=900,NodeLimit=1)
    for k,v in settings.items():model.setParam(k,v)
    model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(OUT/'C3S_ROOT_NATIVE.log')
    model.setAttr('Start',model.getVars(),start.tolist());model.update()
    observations=[]
    def cb(m,where):
        if where==gp.GRB.Callback.MIP:
            row=dict(Runtime=m.cbGet(gp.GRB.Callback.RUNTIME),Work=m.cbGet(gp.GRB.Callback.WORK),NodeCount=m.cbGet(gp.GRB.Callback.MIP_NODCNT),SolCount=m.cbGet(gp.GRB.Callback.MIP_SOLCNT),UB=m.cbGet(gp.GRB.Callback.MIP_OBJBST),LB=m.cbGet(gp.GRB.Callback.MIP_OBJBND))
            if not observations or any(row[k]!=observations[-1][k] for k in ['NodeCount','SolCount','UB','LB']):observations.append(row)
    write('C3S_ROOT_ONCE.json',dict(optimize_calls=1,NodeLimit=1,TimeLimit=900,settings=settings,full_BB_authorized=False))
    model.optimize(cb)
    x=None;candidate=None
    if model.SolCount:
        x=np.asarray(model.getAttr('X'));np.savez_compressed(OUT/'C3S_ROOT_POINT.npz',x=x);candidate=replay(S,e,x)
    log=(OUT/'C3S_ROOT_NATIVE.log').read_text();m=re.search(r'Root relaxation: objective ([^,]+), (\d+) iterations, ([\d.]+) seconds \(([\d.]+) work units\)',log)
    write('C3S_ROOT_RESULT.json',dict(native_Status=model.Status,native_Runtime=model.Runtime,native_Work=model.Work,native_NodeCount=model.NodeCount,native_SolCount=model.SolCount,native_UB=float(model.ObjVal) if model.SolCount else None,native_global_bound=float(model.ObjBound),native_gap=float(model.MIPGap) if model.SolCount else None,root_log_metrics=dict(objective=float(m[1]),iterations=int(m[2]),seconds=float(m[3]),Work=float(m[4])) if m else None,settings=settings,optimize_calls=1,observations=observations,candidate_matrix_replay=candidate,validated_start_supplied=True,root_diagnostic_only=True,production_acceptance=False,full_BB_executed=False,NodeLimit=1,TimeLimit=900))
    model.dispose();print('C3S_ROOT_DONE',flush=True)

if __name__=='__main__':main()
