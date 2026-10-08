"""Independent bit-level PR162 objective verifier; no solver/builder import."""
import hashlib,io,subprocess
from pathlib import Path
import numpy as np
COMMIT='1d922c91eb27056a5ccc79c92ef18146707099ab'
DATA='docs/v42_m1_ultracompact_exact_20261006/C3A_DATA.npz'
NPZ_SHA='20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467'
COEFFICIENT_SHA='d6761e4a352d4d6bd2208033e9357a24f126a133c92e544e73d50e003f740b0b'
AXIS_SHA='a9613e108820333920047d0bacc98fa34690db8c83a5d099a870e22e213ddf8a'
def digest(b):return hashlib.sha256(b).hexdigest()
def load_authority(root):
    blob=subprocess.check_output(['git','show',COMMIT+':'+DATA],cwd=root)
    assert digest(blob)==NPZ_SHA,'PR162_SCIENTIFIC_BLOB_HASH_FAILURE'
    assert digest((Path(root)/DATA).read_bytes())==NPZ_SHA,'WORKTREE_SCIENTIFIC_AUTHORITY_FAILURE'
    with np.load(io.BytesIO(blob)) as z:d={k:z[k].copy() for k in ('names','objective','constant')}
    assert digest(d['objective'].tobytes())==COEFFICIENT_SHA
    assert digest(d['names'].tobytes())==AXIS_SHA
    assert np.flatnonzero(d['objective']).tolist()==[239826] and d['objective'][239826]==1. and d['names'][239826]=='rho_max'
    assert d['constant'].tobytes().hex()=='0000000000000000'
    return d

def verify(root,candidate,model_sense=1):
    original=load_authority(root);checks={};details={}
    for k in ('objective','constant','names'):
        a=np.asarray(original[k]);b=np.asarray(candidate[k])
        checks[k+'_dtype_shape_bytes_identical']=a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
        details[k]=dict(source_dtype=str(a.dtype),candidate_dtype=str(b.dtype),source_shape=list(a.shape),candidate_shape=list(b.shape),source_SHA256=digest(a.tobytes()),candidate_SHA256=digest(b.tobytes()))
    checks['minimize']=model_sense==1
    source_hash=digest(original['objective'].tobytes()+original['constant'].tobytes())
    candidate_hash=digest(np.asarray(candidate['objective']).tobytes()+np.asarray(candidate['constant']).tobytes())
    return dict(PASS=all(checks.values()),authority_commit=COMMIT,authority_file=DATA,authority_file_SHA256=NPZ_SHA,independent_git_blob_reader=True,no_builder_import=True,no_zero_normalization=True,no_tolerance=True,checks=checks,details=details,objective_hash_definition='SHA256(raw objective float64 C-order bytes || raw scalar ObjCon float64 bytes); variable-axis hash separately verified',source_objective_SHA256=source_hash,candidate_objective_SHA256=candidate_hash,source_variable_axis_SHA256=AXIS_SHA,ObjCon_bits_hex=original['constant'].tobytes().hex(),rho_column=239826,objective='minimize rho_max')
