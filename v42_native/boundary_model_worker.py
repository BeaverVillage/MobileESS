"""Supervised full A1 model construction after exact-domain completion."""
from v42_boundary.common import *

def worker(context,payload):
    for r in payload.get('sources',[]):require(sha(r['path'])==r['sha256'],'MODEL_SOURCE_DRIFT')
    from v42_boundary.model import solve
    solve(context)

def validator(candidate,payload):
    return dict(PASS=candidate.get('stage')=='A1' and candidate.get('accepted_native_plan') is True
        and candidate.get('physical_audit',{}).get('PASS') is True and candidate.get('full_linear_max_violation',1)>-1e-10
        and candidate.get('full_linear_max_violation',1)<=1e-5
        and candidate.get('domain_sha')==read(GEN/'DOMAIN_COMPLETE.json')['domain_sha'])
