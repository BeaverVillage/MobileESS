"""Native0 S0->S1 coordinate and feasible elastic primal-start audit.

Historical solver output is inspected only in this audit. No production
warm start is installed, no basis is invented and no bound is certified.
"""
import argparse
from collections import defaultdict,deque
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np


def main(snapshots,raw,output):
    import gurobipy as gp
    def forbidden(*a,**k):raise AssertionError('WARM_MAPPING_AUDIT_NATIVE_FORBIDDEN')
    for name in ('optimize','presolve','computeIIS'):setattr(gp.Model,name,forbidden)
    from v42_a_stage_phase1.core import primal_replay,phase_objective
    masters=[]
    for index in (0,1):
        with gzip.open(snapshots/('S'+str(index)+'.pkl.gz'),'rb') as stream:masters.append(pickle.load(stream))
    old,new=masters;A=old.original;B=new.original;n=A.matrix.shape[1]
    if n!=B.matrix.shape[1] or any(not np.array_equal(getattr(A,k),getattr(B,k)) for k in ('lower','upper','vtypes')):
        raise AssertionError('BASE_COLUMN_OR_DOMAIN_CHANGED_REQUIRES_SEPARATE_MAPPING')
    def signature(snapshot,i):
        a,b=snapshot.matrix.indptr[i:i+2]
        return (snapshot.matrix.indices[a:b].tobytes(),snapshot.matrix.data[a:b].tobytes(),
                str(snapshot.senses[i]),np.asarray(snapshot.rhs[i]).tobytes())
    rows=defaultdict(deque)
    for i in range(B.matrix.shape[0]):rows[signature(B,i)].append(i)
    mapping=[]
    for i in range(A.matrix.shape[0]):
        key=signature(A,i)
        if not rows[key]:raise AssertionError('OLD_ORIGINAL_ROW_NOT_INCLUDED_EXACTLY')
        mapping.append(rows[key].popleft())
    with np.load(raw,allow_pickle=False) as z:
        x=z['X'].copy();has_basis=all(k in z for k in ('VBasis','CBasis'))
        pi=z['Pi'].copy();raw_fields=z.files
    if not primal_replay(old.snapshot,x)['PASS']:raise AssertionError('SAVED_S0_RAW_NOT_VALID')
    point=np.zeros(new.snapshot.matrix.shape[1]);point[:n]=x[:n]
    residual=B.matrix@point[:n]-B.rhs
    for j,(row,sign) in enumerate(zip(new.artificial_rows,new.artificial_signs)):
        point[n+j]=max(0.,float(-residual[row]/sign))
    replay=primal_replay(new.snapshot,point)
    dual=np.zeros(B.matrix.shape[0]);dual[mapping]=pi
    report=dict(PASS=True,row_mapping_PASS=True,warm_start_admissible=replay['PASS'],
                status='MAPPED_PRIMAL_REPLAY_PASS' if replay['PASS'] else 'REJECTED_PRIMAL_START_NOT_REPLAYABLE',
                rejection_reason=None if replay['PASS'] else 'NEW_ELASTIC_EQUALITY_BINARY64_CANCELLATION_EXCEEDS_ORIGINAL_TOLERANCE',
                max_abs_base_primal=float(abs(point[:n]).max(initial=0)),
                max_abs_artificial_primal=float(abs(point[n:]).max(initial=0)),Native_optimize_calls=0,
                old_rows=A.matrix.shape[0],new_rows=B.matrix.shape[0],base_columns=n,
                original_rows_mapped_exactly=len(mapping),new_rows_added=B.matrix.shape[0]-A.matrix.shape[0],
                original_bounds_and_types_identical=True,old_native_raw_fields=raw_fields,
                old_native_basis_available=has_basis,VBasis_CBasis_start_installed=False,
                S1_elastic_primal_replay=replay,S1_exact_Phi=str(phase_objective(new,point)),
                exact_Phi_zero_or_global_LB_claimed=False,
                DStart_old_rows_mapped=True,DStart_new_rows_zero=True,DStart_dual_feasibility_claimed=False,
                LPWarmStart_2_preserved_presolve_experiment='NOT_RUN_REQUIRES_NATIVE_APPROVAL',
                production_point_or_bound_reuse=False)
    output.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(output/'DIAGNOSTIC_COORDINATES.npz',old_to_new_rows=np.asarray(mapping),PStart=point,DStart=dual)
    (output/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))
    # A rejected start is a completed negative audit, never a reason to relax
    # replay tolerance or silently install a different production point.


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshots',type=Path,required=True);p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.snapshots,a.raw,a.output)
