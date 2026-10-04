from v42_dw_policy.common import *
from v42_dw_policy.resume import budget_to_carry
import ast
def prices():return [read(p) for p in sorted((OUT/'pricing_receipts').glob('PRICE_*.json'))]
def test_union_overlapping_parallel_calls():assert union_seconds([(0,20),(0,20),(1,21),(1,21)])==21
def test_union_disjoint_RMP_and_pricing():assert union_seconds([(0,10),(12,32),(12,32),(34,44)])==40
def test_union_nested_and_empty():assert union_seconds([(0,20),(2,5),(20,25)])==25 and union_seconds([])==0
def test_resource_floor_small_host():assert resource_threshold(32*1024**3)==8*1024**3
def test_resource_floor_large_host():assert resource_threshold(128*1024**3)==.15*128*1024**3
def test_resume_budget_without_open_call():assert budget_to_carry(dict(elapsed_budget=100),None)==100
def test_resume_budget_charges_worst_open_batch():assert budget_to_carry(dict(elapsed_budget=100),dict(spent_before=125,reserved_optimize_seconds=64))==189
def test_resume_budget_never_extends():assert budget_to_carry(dict(elapsed_budget=890),dict(spent_before=895,reserved_optimize_seconds=124))==900
def test_discovery_classification_does_not_require_optimum():assert candidate_class(9,True,-1e-7)=='VALID_NEGATIVE_DISCOVERY_COLUMN'
def test_discovery_classification_rejects_invalid_or_small_negative():assert candidate_class(9,False,-1.)=='NO_VALID_NEGATIVE_DISCOVERY_COLUMN' and candidate_class(9,True,-1e-8)=='NO_VALID_NEGATIVE_DISCOVERY_COLUMN'
def test_scientific_base_exact():assert read(OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json')['scientific_base']==BASE
def test_partial_history_and_source_preserved():assert preserve_old()>10000 and read(PREVIOUS/'EXACT_PRICING_POLICY_STOP_RECEIPT.json')['materiality_at_stop']=='INCONCLUSIVE'
def test_accepted_checkpoint_exact_and_exclusions():
    a=read(OUT/'DW_POLICY_RESUME_CHECKPOINT_AUDIT.json');assert a['PASS'] and a['total_retained_columns']==1066 and a['old_policy_added_optimal_columns']==18 and a['excluded_calls']==[17,18] and a['interrupted_unreceipted_call_excluded']==21
    for c in a['checks']:assert sha(ROOT/c['file'])==c['file_SHA']
def test_discovery_original_local_and_physical_points():
    for p in prices():
        if p['type']=='DISCOVERY' and p['valid_point']:assert p['physical']['PASS'] and p['full_original_local']['PASS'] and p['physical']['integer_pattern_exact']
def test_added_discovery_columns_manual_rc_not_optimum_claim():
    pp=prices()
    for c in ledger('DW_DISCOVERY_COLUMN_LEDGER.csv'):
        p=next(p for p in pp if p['call']==int(c['pricing_call']));assert p['type']=='DISCOVERY' and p['valid_point'] and p['rc_inc']<=-1e-7 and c['label']=='VALID_NEGATIVE_DISCOVERY_COLUMN' and c['pricing_optimum_claimed']=='False'
def test_discovery_never_claims_optimality_or_no_column():
    for p in prices():
        if p['type']=='DISCOVERY':assert not p['pricing_optimality_claimed'] and p['discovery_column_label'] in ('VALID_NEGATIVE_DISCOVERY_COLUMN','NO_VALID_NEGATIVE_DISCOVERY_COLUMN')
def test_certification_beta_global_ObjBound_same_dual():
    for path in (OUT/'bound_certificates').glob('*.json'):
        c=read(path);assert c['type'] in ('CERTIFICATION','FINAL_CERTIFICATION')
        if c['certified']:
            for file,beta in zip(c['pricing_receipts'],c['beta_raw']):p=read(OUT/file);assert p['dual_SHA']==c['dual_SHA'] and p['valid_bound'] and p['ObjBound']==beta and p['native_status'] in (2,9)
def test_corrected_theorem_unchanged():assert read(OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json')['certificate_source_SHA']==sha(ROOT/'v42_dw_bound/certificate.py') and read(PREVIOUS/'DW_CORRECTED_DUAL_THEOREM.json')['PASS']
def test_same_dual_across_four_independent_pricers():
    pp=prices()
    for r in ledger('DW_RMP_LEDGER.csv'):assert all(p['dual_SHA']==r['dual_SHA'] for p in pp if p['round']==int(r['round']))
def test_full_domain_no_fixing_and_caps():
    for p in prices():assert p['full_original_domain'] and p['horizon']==96 and p['no_fixing'] and not p['callback_first_negative_stop'] and p['settings']['TimeLimit']<={'DISCOVERY':20,'CERTIFICATION':60,'FINAL_CERTIFICATION':120}[p['type']]
def test_solver1e8_postsolve1e6_contract():
    p=read(OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json');assert p['postsolve_affine_tolerance']==1e-6
    for r in prices():assert r['settings']['Threads']==1 and r['settings']['FeasibilityTol']==r['settings']['IntFeasTol']==r['settings']['OptimalityTol']==1e-8
def test_budget_900_no_extension_and_checkpoint_no_deletion():
    r=read(OUT/'DW_POLICY_CANARY_FINAL.json');c=read(OUT/'DW_POLICY_CHECKPOINT_LATEST.json');assert r['total_optimize_wall_union']<=900 and len(c['pool'])==1066+r['new_discovery_columns'] and c['total_retained_columns']==len(c['pool']) and 'restart_state' in c
def test_campaign_worker_policy_and_no_nested_explosion():
    p=read(OUT/'CAMPAIGN_WORKER_POLICY.json');assert [p[x+'_DAY_WORKERS'] for x in ('B0','B1','B2','B3')]==[4,1,4,1] and p['THREADS_PER_SOLVE']==1 and p['B2_INNER_PRICING_WORKERS']==1 and p['maximum_simultaneous_pricing_processes']==4
    r=read(OUT/'DW_POLICY_CANARY_FINAL.json');assert r['workers'] in (1,2,4) and (r['resource_PASS'] or r['workers']==1 or r['policy_canary']!='PROMISING')
def test_May_and_downstream_no_execution():
    r=read(OUT/'DW_POLICY_CANARY_FINAL.json');assert r['May_production']==[0,0,0] and r['no_branch_and_price'] and not r['old_TIME_LIMIT_retroactively_added']
    from v42_campaign.plan import build_plan
    from v42_dw_bound.common import REF
    assert build_plan()==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')
