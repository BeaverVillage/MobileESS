"""Explicit experimental gates. Missing candidate bytes cannot authorize a solve."""
import math
import numpy as np
from v42_benders.canonical import digest_arrays

def restore_first_x(receipt,path,n):
    if not receipt.get('restored') or not receipt.get('source_x_sha256'):raise ValueError('PR115_FIRST_X_UNAVAILABLE')
    from .common import sha
    if sha(path)!=receipt.get('file_sha256'):raise ValueError('FIRST_X_FILE_HASH')
    with np.load(path,allow_pickle=False) as z:
        if not np.array_equal(z['names'],n.names[n.xi]):raise ValueError('FIRST_X_AXIS')
        x=z['values']
    if x.shape!=n.xlower.shape or not np.isfinite(x).all() or np.any(x!=np.rint(x)) or np.any(x<n.xlower) or np.any(x>n.xupper):raise ValueError('FIRST_X_DOMAIN')
    if digest_arrays(x)!=receipt['source_x_sha256']:raise ValueError('FIRST_X_VECTOR_HASH')
    return x

def isolated_gate(first_x,fixture,result):
    return bool(first_x.get('restored') and fixture.get('PASS') and fixture.get('agreement')==1536 and
        result.get('same_x_verified') and ((result.get('status')==3 and result.get('independent_valid_cut')) or
        (result.get('status')==2 and result.get('independent_physics_witness'))))

def progress_gate(isolated,b3):
    return bool(isolated and not b3.get('numerical_contradiction',True) and b3.get('uncertified_cuts_used',1)==0 and
        (b3.get('independent_valid_cuts',0)>=1 or b3.get('validated_witness') or b3.get('global_master_infeasible')))

def production_gate(canary):
    vals=[canary.get('upper'),canary.get('lower')]
    if any(v is None or not math.isfinite(v) for v in vals):return False
    ub,lb=vals
    return bool(canary.get('cut_validity') and canary.get('independent_original_UB') and canary.get('global_LB_valid') and
        canary.get('numerical_stability') and canary.get('uncertified_cuts_used',1)==0 and lb<=ub+1e-7 and
        (lb>=.5722125039436496+1e-4 or (ub-lb)/abs(ub)<=.005))

def downstream_allowed(p1_accepted,user_approval=False):return bool(p1_accepted and user_approval)

def classify_b3(validated_witness=False,global_master_infeasible=False,uncertified_cuts_used=0):
    if uncertified_cuts_used:return 'B3_INCONCLUSIVE'
    if validated_witness and global_master_infeasible:raise ValueError('NUMERICAL_CONTRADICTION')
    if validated_witness:return 'B3_NEGATIVE_CERTIFIED'
    if global_master_infeasible:return 'B3_POSITIVE_CERTIFIED'
    return 'B3_INCONCLUSIVE'
