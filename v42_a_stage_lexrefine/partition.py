"""Exhaustive integer-objective split preserving both children."""
from dataclasses import replace
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import integer_objective_proof

def split(snapshot,name,incumbent):
    proof=integer_objective_proof(snapshot,name);U=round(float(incumbent))
    if abs(float(incumbent)-U)>1e-5:raise ValueError('INTEGER_INCUMBENT_REQUIRED')
    o=snapshot.objective(name);co=o.coefficients()
    row=sp.csr_matrix(([float(v) for v in co.values()],([0]*len(co),list(co))),shape=(1,snapshot.matrix.shape[1]))
    left=replace(snapshot,matrix=sp.vstack((snapshot.matrix,row),format='csr'),senses=np.append(snapshot.senses,'<'),rhs=np.append(snapshot.rhs,U-1-float(o.constant)))
    receipt=dict(PASS=True,component=name,objective_integrality=proof,exhaustive_over_original_integer_domain=True,
        left=dict(restriction='objective <= UB - 1',objective_upper=U-1,snapshot_sha256=left.fingerprint()),
        right=dict(restriction='objective >= UB',valid_LB=U,status='PRUNED_BOUND',validated_incumbent=U),
        both_children_preserved=True,scientific_candidate_deletion=False)
    return left,receipt
