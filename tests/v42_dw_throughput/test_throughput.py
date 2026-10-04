from v42_dw_throughput.common import *
import numpy as np
from v42_dw_throughput.resume import budget_to_carry
def prices():return [read(p) for p in sorted((OUT/'pricing_receipts').glob('PRICE_*.json'))]
def test_new_floor_does_not_fail_one_to_eight_GiB():
    for gib in (1,2,4,7.9):assert not resource_failures(dict(available_RAM=gib*1024**3,commit_percent=90),[])
def test_commit_and_RAM_hard_boundaries():
    assert resource_failures(dict(available_RAM=1024**3-1,commit_percent=94),[])==['AVAILABLE_RAM_BELOW_1_GIB']
    assert resource_failures(dict(available_RAM=7*1024**3,commit_percent=95),[])==['SYSTEM_COMMIT_AT_LEAST_95_PERCENT']
def test_thrashing_requires_sustained_both_conditions():
    rows=[dict(perf=i,pagefile_used=i*30*1024**2,hard_page_input_pages_per_sec=1500) for i in range(11)]
    assert severe_paging(rows)
    assert not severe_paging([dict(r,hard_page_input_pages_per_sec=0) for r in rows])
    assert not severe_paging([dict(r,pagefile_used=2*1024**3) for r in rows])
    assert not severe_paging(rows[:10])
    assert not severe_paging([dict(r,hard_page_input_pages_per_sec=None) for r in rows])
def test_adaptive_rule_boundary_and_clamps():
    assert next_smoothing_weight(.3,.51)==.15 and next_smoothing_weight(.3,.5)==.3
    assert next_smoothing_weight(.3,.1)==.375 and next_smoothing_weight(.1,10)==.1
    assert next_smoothing_weight(.8,0)==.8
def test_parallel_overlap_and_budget_union_are_distinct():
    spans=[(0,20),(1,21),(2,22),(3,23)];assert union_seconds(spans)==23 and overlap_seconds(spans,4)==17
    assert overlap_seconds([(0,20),(21,41),(42,62),(63,83)],4)==0
def test_crash_resume_same_900_budget():
    assert budget_to_carry(dict(elapsed_budget=200),dict(spent_before=210,reserved_optimize_seconds=64))==274
    assert budget_to_carry(dict(elapsed_budget=899),dict(spent_before=899,reserved_optimize_seconds=64))==900
def test_PR141_exact_checkpoint_no_retroactive_points():
    b=read(OUT/'DW_THROUGHPUT_BASE_AUDIT.json');assert b['PR141_head']==BASE_HEAD and b['total_retained_columns']==1078 and len(b['checks'])==1078 and not b['old_TIME_LIMIT_retroactively_promoted'] and not b['interrupted_uncertified_points_promoted']
    assert preserve_old()>10000
def test_preregistered_smoothing_and_science_before_optimize():
    p=read(OUT/'DW_THROUGHPUT_PREREGISTRATION.json');assert p['adaptive_smoothing']['enabled'] and p['adaptive_smoothing']['initial']==.30 and not p['adaptive_smoothing']['box_proximal_trust_region'] and p['schedule']==['DISCOVERY']*5+['CERTIFICATION']
    assert p['certificate_source_SHA']==sha(ROOT/'v42_dw_bound/certificate.py')
def test_every_snapshot_smoothing_recurrence_and_convexity():
    previous_pi=previous_conv=previous_true=None;weight=.30
    for h in ledger('DW_DUAL_SMOOTHING_LEDGER.csv'):
        with np.load(OUT/f"RMP_POINT_{int(h['round']):04d}.npz") as z:pi=z['pi'];conv=z['alpha']
        with np.load(OUT/h['smooth_file']) as z:smooth=z['pi'];sc=z['alpha']
        assert float(h['alpha_used'])==weight and hashlib.sha256(smooth.tobytes()+sc.tobytes()).hexdigest()==h['smoothed_dual_SHA']
        if previous_pi is None:assert np.array_equal(pi,smooth) and np.array_equal(conv,sc)
        else:
            assert np.array_equal(smooth,weight*pi+(1-weight)*previous_pi) and np.array_equal(sc,weight*conv+(1-weight)*previous_conv)
            d=float(np.linalg.norm(pi-previous_true,np.inf)/max(1e-12,np.linalg.norm(previous_true,np.inf)))
            weight=max(.1,.5*weight) if d>.5 else weight if d>.1 else min(.8,1.25*weight)
        assert weight==float(h['alpha_next']);previous_pi=smooth.copy();previous_conv=sc.copy();previous_true=pi.copy()
def test_discovery_uses_smooth_certification_uses_true():
    smooth={int(h['round']):h for h in ledger('DW_DUAL_SMOOTHING_LEDGER.csv')}
    for p in prices():
        if p['type']=='DISCOVERY':assert p['dual_SHA']==smooth[p['round']]['smoothed_dual_SHA']
        else:assert p['dual_SHA']==p['true_dual_SHA'] and not p['stabilized_discovery']
def test_multicolumn_independent_validation_both_RC_authorities():
    for p in prices():
        assert sum(c['selected'] for c in p['candidates'])<=4
        for c in p['candidates']:
            if c['selected']:assert c['physical']['PASS'] and c['full_original_local']['PASS'] and c['rc_inc']<=-1e-7 and c['manual_search_rc']<=-1e-7 and c['physical']['integer_pattern_exact'] and not c['pricing_optimum_claimed']
def test_bit_exact_pool_monotonic_and_no_rank_claim():
    b=read(OUT/'DW_THROUGHPUT_BASE_AUDIT.json');c=read(OUT/'DW_THROUGHPUT_CHECKPOINT_LATEST.json');r=read(OUT/'DW_THROUGHPUT_FINAL.json');assert c['pool'][:1078]==b['checks'] and len(c['pool'])==1078+r['new_discovery_columns']
    for col in ledger('DW_DISCOVERY_COLUMN_LEDGER.csv'):assert col['label']=='VALID_NEGATIVE_DISCOVERY_COLUMNS' and col['pricing_optimum_claimed']=='False'
def test_actual_four_overlap_not_worker_residency():
    s=read(OUT/'DW_TRUE_4WAY_RESOURCE_SUMMARY.json');pp=prices();assert abs(overlap_seconds([p['interval'] for p in pp],4)-s['all_native_pricing_overlap_four_seconds'])<1e-6
    if s['PASS']:assert s['all_native_pricing_overlap_four_seconds']>0 and s['actual_4way_pricing_calls']>=4
def test_native_full_domain_numeric_and_time_contract():
    for p in prices():
        s=p['settings'];assert s['Threads']==1 and s['FeasibilityTol']==s['IntFeasTol']==s['OptimalityTol']==1e-8 and s['TimeLimit']<=(20 if p['type']=='DISCOVERY' else 60)
        assert p['full_original_domain'] and p['horizon']==96 and p['no_fixing'] and not p['basis_or_pool_restriction'] and not p['callback_first_negative_stop']
def test_warm_selection_has_same_optimal_objective_basis_acceptance_speed():
    w=read(OUT/'DW_RMP_WARM_COLD_COMPARISON.json')
    if w['selected']:
        assert w['objective_agreement_PASS'] and w['median_wall_reduction']>=.3 and all(r['full_postsolve']['PASS'] for r in w['records'])
        assert all(r['basis_accepted'] for r in w['records'] if r['path']=='warm')
        obj=[r['objective'] for r in w['records']];assert max(obj)-min(obj)<=1e-8
def test_copy_canary_budget_charged_and_no_native_overlap():
    b=read(OUT/'DW_OPTIMIZE_INTERVALS.json');r=read(OUT/'DW_THROUGHPUT_FINAL.json');assert r['total_optimize_wall_union']<=900 and abs(union_seconds(b['intervals'])+b['carried_budget_seconds']-r['total_optimize_wall_union'])<1e-9
    for c in read(OUT/'DW_RMP_WARM_COLD_COMPARISON.json')['records']:
        assert c['interval'] in b['intervals']
        for p in prices():assert c['interval'][1]<=p['interval'][0] or c['interval'][0]>=p['interval'][1]
def test_fixture_smoothing_matches_full_optimum_and_true_recovery():
    p=read(OUT/'DW_STABILIZATION_FIXTURE_PROOF.json');assert p['PASS'] and p['same_optimum'] and p['native_intervals_charged']
    for r in p['runs']:assert r['no_stabilized_certificate'] and abs(r['objective']-p['full_enumeration_optimum'])<=1e-8
def test_certificates_never_use_smoothed_authority_or_discovery_bounds():
    for file in (OUT/'bound_certificates').glob('*.json'):
        c=read(file);assert c['type']!='DISCOVERY'
        if c['certified']:
            for p,beta in zip(c['pricing_receipts'],c['beta_raw']):r=read(OUT/p);assert r['dual_SHA']==r['true_dual_SHA']==c['dual_SHA'] and r['valid_bound'] and r['ObjBound']==beta
def test_no_production_and_original_plan():
    r=read(OUT/'DW_THROUGHPUT_FINAL.json');assert r['May_production']==[0,0,0] and r['no_branch_and_price'] and not r['box_proximal_trust_region_run']
    from v42_campaign.plan import build_plan
    from v42_dw_bound.common import REF
    assert build_plan()==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')
