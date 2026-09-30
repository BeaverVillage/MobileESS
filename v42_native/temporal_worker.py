"""Bounded native temporal-interface canary entrypoint."""
from v42_temporal.common import *
from v42_temporal.native import solve_a1
from v42_final.gates import require_a1
from v42_native.supervision import atomic

def worker(context,payload):
    require_a1(read(OUT/'MAY01_TS_CC4_RESOURCE_FEASIBILITY.json'))
    for r in payload['sources']:require(sha(r['path'])==r['sha256'],'TEMPORAL_SOURCE_DRIFT')
    b=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    ledger=pd.read_csv(OUT/'TS_HIERARCHICAL_BACKOFF_LEDGER.csv',dtype={'job_id':str}).set_index('job_id').to_dict('index')
    result=solve_a1(context,b,ledger)
    if result is not None:
        # Raw results never cross an acceptance boundary without an independent
        # full option/resource/grid validator and the ordered later stages.
        atomic(context.folder/'raw_complete_plan.json',result)

def validator(candidate,payload):
    return dict(PASS=False,reason='RAW_DIAGNOSTICS_REQUIRE_INDEPENDENT_NATIVE_ACCEPTANCE')
