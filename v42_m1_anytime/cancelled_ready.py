"""Clean/pushed delivery of verified partial evidence after user cancellation."""
from unittest.mock import patch
from .core import ROOT,CASE,REPORTS,read,write
from .publish import timeline
from v42_unified.storage import sha
from v42_m1_hybrid import delivery_ready as previous

def ready():
    with patch.object(previous,'write',lambda *a,**k:None):result=previous.ready()
    final=read(REPORTS/'INDEPENDENT_FINAL_VERIFICATION.json');manifest=read(REPORTS/'SHA256_MANIFEST.json')
    tests=read(REPORTS/'ZERO_NATIVE_REGRESSION.json');old=read(ROOT/'docs/v42_m1_fast_hybrid_20261008/ZERO_NATIVE_REGRESSION.json')
    if not final['PASS'] or not final['user_cancelled'] or final['full_75_minute_frontier_completed'] or final['M1_ACCEPTED'] or final['P2_certificate'] is not None:raise ValueError('CANCELLED_SCOPE_OR_CERTIFICATE_DRIFT')
    required=set()
    for folder in (REPORTS,ROOT/'v42_m1_anytime'):
        for p in folder.rglob('*'):
            if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in p.parts:required.add(p.relative_to(ROOT).as_posix())
    required.update(('tests/test_v42_m1_anytime.py','Start-V42-M1-Anytime.ps1'))
    if set(manifest['files'])!=required:raise ValueError('FULL_DELIVERY_MANIFEST_COVERAGE_REQUIRED')
    for name,digest in manifest['files'].items():
        if sha(ROOT/name)!=digest:raise ValueError('CANCELLED_MANIFEST_DRIFT:'+name)
    if tests['failed'] or set(old['passed'])-set(tests['passed']):raise ValueError('649_PASS_PRESERVATION_FAILED')
    ledger=read(REPORTS/'NATIVE_RUNTIME_LEDGER.json')
    if ledger['termination']!='USER_REQUESTED_STOP' or ledger['budget_reset'] or ledger['consumed_or_reserved_Native_budget']>5400 or ledger['exact_aggregate_Runtime_and_Work_available']:raise ValueError('INTERRUPTED_COST_QUARANTINE_REQUIRED')
    proof=timeline()
    result.update(schema='V42_INTEGRATION_AND_CANCELLED_ANYTIME_DELIVERY_V4',test_counts=final['tests'],
        anytime_frontier=dict(final),anytime_research_goal_completed=False,user_requested_stop=True,
        final_partial_evidence_independently_verified=True,final_75_minute_frontier_claimed=False,
        anytime_manifest_sha256=sha(REPORTS/'SHA256_MANIFEST.json'),anytime_timeline_audit=proof,
        anytime_native_started_calls=27,anytime_native_completed_calls=26,
        anytime_native_interrupted_calls=1,anytime_native_budget_charged=ledger['consumed_or_reserved_Native_budget'],
        anytime_exact_total_Runtime_and_Work_available=False,coding_and_Git_delivery_are_not_Native_Runtime=True)
    result['scientific_state']['new_May01_anytime_partial_frontier']=dict(case_sha=CASE,
        exact_LB=final['exact_Global_LB'],exact_UB=final['exact_Global_UB'],gap_percent=final['certified_gap_percent'],
        user_cancelled=True,full_75_minute_frontier_completed=False,M1_ACCEPTED=False,P2_certificate=None,
        production_promoted=False,May12_A2_M2_transfer=False)
    result['M_handoff']['additional_anytime_contract']=str(REPORTS/'ANYTIME_HANDOFF_KO.md')
    write(ROOT/'V42_INTEGRATION_READY.json',result)
    return result

if __name__=='__main__':
    value=ready();print('CANCELLED_ANYTIME_CLEAN_PUSHED_READY',value['integration_HEAD'],value['test_counts'])
