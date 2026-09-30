"""New supervised entrypoint; PR97 worker and receipts remain unchanged."""
from v42_boundary.common import *

def worker(context,payload):
    for r in payload.get('sources',[]):require(sha(r['path'])==r['sha256'],'BUILD_SOURCE_DRIFT')
    require(read(OUT/'A1_LEGACY_ACCELERATED_EQUIVALENCE.json')['PASS'],'EXACT_EQUIVALENCE_REQUIRED')
    from v42_boundary.run import generate
    generate(context)

def validator(candidate,payload):
    return dict(PASS=False,reason='DOMAIN_GENERATION_IS_NOT_A_PLAN')
