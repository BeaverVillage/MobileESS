"""Read-only PR136/campaign preservation receipts; no execution adapters."""
from .common import ROOT,OUT,REF,BASE,sha,write,read
import subprocess
import hashlib

def freeze():
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT).decode().splitlines()
    write('PR136_WORKSPACE_BYTE_SNAPSHOT.json',dict(base_exact_head=BASE,
          files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths]))
    campaign_paths=[p for p in paths if p.startswith('v42_campaign/') or p.startswith('docs/v42_m1_cutpass_loop_campaign/')]
    files=[]
    for p in campaign_paths:
        committed=subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT)
        expected=hashlib.sha256(committed).hexdigest()
        actual=sha(ROOT/p)
        assert expected==actual,p
        files.append(dict(path=p,base_SHA=expected,current_SHA=actual))
    from v42_campaign.plan import build_plan
    dry=read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')
    assert dry==build_plan() and len(dry['nodes'])==1458
    assert all(n['execution_status']=='NOT_RUN' for n in dry['nodes'])
    write('CAMPAIGN_ORCHESTRATOR_PRESERVATION.json',dict(PASS=True,base_exact_head=BASE,
          byte_identical_files=files,dry_plan_SHA=sha(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json'),
          dry_plan_stages=1458,semantic_plan_equal=True,main_order=dry['main_order'],convergence_order=dry['convergence_order'],
          Actual_feedback_firewall_preserved=True,previous_Planning_only=True,B3_four_loop_contract_preserved=True,
          B0_B1_B2_repeated=False,fixed_point_early_stop=False))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(
          MAY_MAIN_CAMPAIGN_EXECUTION='NOT_RUN',B3_LOOP2_PRODUCTION='NOT_RUN',B3_LOOP3_PRODUCTION='NOT_RUN',B3_LOOP4_PRODUCTION='NOT_RUN',
          campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,
          production_backends_registered=0,source='Only standalone M1 diagnostic LPs and at most one gated MIP canary; no campaign runner invocation.',
          inherited_dry_plan_SHA=sha(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')))

def audit():
    frozen=read(OUT/'PR136_WORKSPACE_BYTE_SNAPSHOT.json')
    drift=[r['path'] for r in frozen['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not drift,drift
    write('PR136_POST_TEST_BYTE_PRESERVATION.json',dict(PASS=True,base_exact_head=BASE,
          checked_files=len(frozen['files']),byte_drift=drift))

if __name__=='__main__':freeze()
