"""Solver-free source freeze and full incumbent replay before preregistered calls."""
from .common import *
def main():
    forbid_optimize();began=time.perf_counter()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    A,d,T,AA,dd=load()
    verifier=module('global_independent_objective',ROOT/'docs/v42_m1_exact_solver_redesign_20261008/objective_identity.py')
    objective=verifier.verify(ROOT,d,1);assert objective['PASS']
    with np.load(ROOT/'docs/v42_m1_route_mode_benders_20261008/artifacts/BEST_VALID_POINT.npz') as z:x=z['x'].copy()
    raw=row_replay(A,d,x);b2=row_replay(AA,dd,x)
    reader=physical_reader();physical=reader.check(x,A,d)
    assert raw['PASS'] and b2['PASS'] and physical['PASS'] and float(d['objective']@x)==UB
    write(OUT/'BASELINE_UB_INDEPENDENT_REPLAY.json',dict(PASS=True,original_C3A=raw,B2=b2,
        original_full_physical=physical,UB=UB,repairs=0,new_native_calls=0))
    sources={}
    for path in [*(PARENT/n for n in EXPECTED),B2/'artifacts/TEMPORAL_VALID_ROWS.npz',
        B2/'artifacts/TEMPORAL_VALID_ROW_DATA.npz',ROUTE,
        ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json',
        ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_MODEL_IDENTITY.json',
        *(ROOT/'docs/v42_m1_gap_rootcause_20261007/source_authority'/n for n in ('FULL_A.npz','FULL_DATA.npz','DATA.pkl')),
        ROOT/'docs/v42_m1_route_mode_benders_20261008/artifacts/BEST_VALID_POINT.npz']:
        rel=path.relative_to(ROOT).as_posix();h=sha(path)
        blob=subprocess.check_output(['git','show',BASE+':'+rel],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest()==h,rel
        sources[rel]=dict(sha256=h,bytes=path.stat().st_size,exact_HEAD_blob_verified=True)
    manifests={}
    for folder in ('v42_m1_joint_formulation_20261008','v42_m1_route_mode_benders_20261008',
            'v42_m1_physics_strengthened_20261008','v42_m1_b2_root_validation_20261008','v42_m1_group_branching_20261008'):
        path=ROOT/'docs'/folder/'SHA256_MANIFEST.json'
        if path.exists():manifests[path.relative_to(ROOT).as_posix()]=sha(path)
    arrays={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in d.items()}
    write(OUT/'SOURCE_IDENTITY.json',dict(PASS=True,source_HEAD=BASE,N=4,sites=24,H=96,slot_minutes=15,
        original_rows=A.shape[0],original_columns=A.shape[1],original_nnz=A.nnz,
        B2_rows=T.shape[0],B2_augmented_rows=AA.shape[0],binary_count=9322,
        objective_identity=objective,sources=sources,original_arrays_SHA256=arrays,inherited_manifests=manifests,
        original_min_rho_objective_preserved=True,physical_feasible_domain_unchanged=True,
        baseline_full_replay_PASS=True,existing_UB_preserved=UB,all_new_outputs_under=str(OUT),
        other_tasks_or_processes_modified=False,production_calls=0,P2_calls=0,downstream_calls=0,
        optimize_calls=0,controller_wall_seconds=time.perf_counter()-began))
    print('SOURCE_AND_FULL_UB_REPLAY_PASS',time.perf_counter()-began,flush=True)
if __name__=='__main__':main()
