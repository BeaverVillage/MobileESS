"""Independent PR220 warm canary; predecessor source bodies are read-only."""
from pathlib import Path
import hashlib,json,numpy as np
from fractions import Fraction as F
from tools.route_centered_lb1800 import adapter as old
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_global_local_multistart_dual1800'
BASE='b9684fa0999b88092d0cd38229f3453ef3f901b4'
INITIAL_UB=.5398310226338695
GLOBAL_LB=.46498486997548166
HISTORICAL=.5461621302242249
DELTA=1e-5
RAW_REL='docs/v42_b2_route_centered_local_branching1800/calls/008_R2_LATE_SMALL/native/FINAL_RAW.npz'
REPLAY_REL='docs/v42_b2_route_centered_local_branching1800/calls/008_R2_LATE_SMALL/REPLAY_001.json'
RAW_SHA='3f3314b0ca9235ffeff02e3d4bdaab97477f4390992fddbd486a047ebd62d686'
VECTOR_SHA='f717de66ee0ad06aadd6c09baa1a3667d775b045bceb4305510ce0db184f8776'
v,r,n,g=old.v,old.r,old.n,old.g
write,read,record=old.write,old.read,old.record
old.old.DOCS=DOCS;old.old.prior.DOCS=DOCS;old.old.prior.base.DOCS=DOCS;old.old.prior.base.configure()
r.ORIGINALS['PR220']=(Path('D:/v42_b2_route_centered_local_branching1800_20261012'),BASE)
paths_of=old.paths_of;route_values=old.route_values;restriction=old.restriction;signature=old.signature
stationary_paths=old.old.stationary_paths
def guard():
    for path,digest in read(DOCS/'EXECUTED_SOURCE_HASHES.json').items():
        assert v.file_sha(ROOT/path)==digest,'SOURCE_POLICY_DRIFT:'+path
def route_spec(case,candidate):
    spec=old.old.route_spec(case,candidate)
    spec.update(stage=candidate['stage'],family=candidate['family'],warm_start_compatible=False,
        center_included=False,start_reason='Different complete original DAG: no incompatible PR220 Start')
    return spec
def audit(case,center,spec,low,high,output=None):
    if spec['method']=='ROUTE_FIXED':result=old.old.audit(case,None,spec,low,high)
    else:
        from tools.global_local_multistart1800.proof import neighborhood
        result=neighborhood(case,center,spec,low,high)
    if output:write(output,result)
    return result
