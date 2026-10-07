from common import *
import itertools
from collections import defaultdict,Counter

def enumerate_paths(a,unit,start,end):
    allowed=a.reachable[unit]
    outgoing=defaultdict(list)
    for k in sorted(allowed):outgoing[a.arcs[k][:2]].append(k)
    result=[]
    def extend(path):
        arc=a.arcs[path[-1]]
        if arc[3]>=end:result.append(tuple(path));return
        for k in outgoing[arc[2],arc[3]]:extend(path+(k,))
    for k in sorted(allowed):
        if a.arcs[k][1]<=start<a.arcs[k][3]:extend((k,))
    assert len(result)==len(set(result))
    return result

def main():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    A,d,x=load();a=Authority();p=physical_reader();check=p.check(x,A,d,is_start=True)
    assert check['PASS']
    freeze=ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json'
    identity=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_MODEL_IDENTITY.json')
    assert sha(freeze)==identity['A1_freeze_sha256']
    check.update(UB_ref=UB,objective_matches_reference=abs(check['objective']-UB)<1e-15,A1_frozen_interface_SHA256=sha(freeze),A1_decision_variables=0,original_matrix_rows_checked=A.shape[0],original_integer_variables=9322)
    write('UB_VALIDATION.json',check)
    historical=read(HISTORY/'ROOT_GAP_CONCLUSION.json');native=read(PARENT/'C3_MILP_RESULT.json')
    assert historical['baseline_valid_global_LB']==LB
    write('LB_VALIDATION.json',dict(PASS=True,LB_ref=LB,authority='PR162 native global MILP bound, conservative tolerance-adjusted; PR167 independently preserved',native_reference=native,PR167_reference=historical,source_SHA256={str(p.relative_to(ROOT)):sha(p) for p in (HISTORY/'ROOT_GAP_CONCLUSION.json',PARENT/'C3_MILP_RESULT.json')},LP_proxy_not_promoted=True))
    write('NUMERICAL_BOUND_AUTHORITY.json',dict(LB_ref=LB,UB_ref=UB,approximate_LP_proxy=.568711942993466,PR167_numerical_audit=read(HISTORY/'NUMERICAL_LP_BOUND_AUDIT.json'),every_new_LB_requires_separate_certificate=True,tolerance=1e-8))
    previous_hashes={str(p.relative_to(ROOT)):sha(p) for directory in (HISTORY,PARENT) for p in directory.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.suffix!='.pyc'}
    write('BASE_IDENTITY.json',dict(PASS=True,base=BASE,scientific_base='1d922c91eb27056a5ccc79c92ef18146707099ab',rows=A.shape[0],cols=A.shape[1],nnz=A.nnz,previous_namespace_hashes=previous_hashes,no_physics_change=True))
    snapshot('CONCURRENCY_BEFORE.json')
    paths=enumerate_paths(a,'MESS04',69,73)
    dist=Counter(sum(a.arcs[k][-1] is None for k in path) for path in paths)
    disjuncts=sum(2**n*count for n,count in dist.items())
    write('MESS04_69_72_PATH_CENSUS.json',dict(mobility_paths=len(paths),by_connected_slots=dict(dist),disjunctions_connected_mode_only=disjuncts,all_integer_mode_trajectories=len(paths)*16,free_transit_modes_factored_exact_binary_cube=True,maximum_path_length=max(map(len,paths)),arcs=len(a.arcs),battery=vars(a.battery),entry_in_transit=sum(a.arcs[p[0]][1]<69 for p in paths),exit_in_transit=sum(a.arcs[p[-1]][3]>73 for p in paths)))
    np.savez_compressed(OUT/'MESS04_69_72_PATHS.npz',paths=np.array([list(p)+[-1]*(4-len(p)) for p in paths],dtype=np.int32))
    print('PREPARED',check['objective'],'paths',len(paths),'disjuncts',disjuncts,'distribution',dict(dist),flush=True)

if __name__=='__main__':main()
