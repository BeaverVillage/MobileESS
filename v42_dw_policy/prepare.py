"""Read-only accepted checkpoint audit and pre-optimize policy freeze."""
from .common import *
def prepare():
    import numpy as np
    from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
    from v42_dw_root.partition import axes
    from v42_degen.identity import inputs
    from v42_dw_root.models import hash_column
    stop=read(PREVIOUS/'EXACT_PRICING_POLICY_STOP_RECEIPT.json');assert stop['history_preserved'] and not stop['scientific_failure']
    import shutil
    shutil.copyfile(PREVIOUS/'EXACT_PRICING_POLICY_STOP_RECEIPT.json',OUT/'EXACT_PRICING_POLICY_STOP_RECEIPT.json')
    assert not (OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json').exists()
    oldsha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    frozen=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked if p and not p.startswith(('v42_dw_policy/','tests/v42_dw_policy/','docs/v42_m1_dw_discovery_certification_policy/'))]
    write('OLD_POLICY_BYTE_FREEZE.json',dict(old_policy_stop_commit=oldsha,scientific_base=BASE,files=frozen))
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native);checks=[]
    for directory,h in old_columns():
        m=UNITS.index(h['MESS']);b=blocks[m]
        with np.load(directory/h['file']) as z:
            new=h.get('format')=='policy_optimal';x=z['x'] if new else z['local_values'];axis=z['axis'] if new else z['original_columns'];a=z['a'] if new else z['master_coefficients'];c=float(z['c']) if new else float(z['objective'])
            assert np.array_equal(axis,b.columns) and np.array_equal(b.B@x,a) and hash_column(x,a,c)==h['SHA256']
            physical=b.validate(x,True);assert physical['PASS']
        checks.append(dict(MESS=h['MESS'],file=(directory/h['file']).relative_to(ROOT).as_posix(),file_SHA=sha(directory/h['file']),column_SHA=h['SHA256'],PASS=True,old_policy_new_optimal=new))
    assert len(checks)==1066 and sum(c['old_policy_new_optimal'] for c in checks)==18
    initial=read(PREVIOUS/'DW_BOUND_CHECKPOINT_AUDIT.json');assert initial['PASS'] and len(initial['checks'])==1048
    assert all(sha(ROOT/c['file'])==c['file_SHA'] for c in initial['checks'])
    post=read(PREVIOUS/'FULL_ORIGINAL_LOCAL_PRICING_POSTAUDIT.json');assert post['PASS']
    oldprices=ledger('DW_OPTIMAL_PRICING_LEDGER.csv',PREVIOUS);excluded=[p for p in oldprices if p['classification']=='TIME_LIMIT_WITH_VALID_BOUND']
    write('DW_POLICY_RESUME_CHECKPOINT_AUDIT.json',dict(PASS=True,initial_columns=4,PR140_generated_columns=1044,old_policy_added_optimal_columns=18,total_retained_columns=1066,excluded_TIME_LIMIT_incumbents=len(excluded),excluded_calls=[int(p['call']) for p in excluded],interrupted_unreceipted_call_excluded=21,checks=checks,old_unreduced_local_row_audits_SHA=[sha(PREVIOUS/'DW_BOUND_CHECKPOINT_AUDIT.json'),sha(PREVIOUS/'FULL_ORIGINAL_LOCAL_PRICING_POSTAUDIT.json')],old_policy_stop_commit=oldsha,no_retroactive_promotion=True,old_failed_dual_reuse=False,cold_RMP=True))
    write('DW_DISCOVERY_CERT_PREREGISTRATION.json',dict(scientific_base=BASE,old_policy_stop_commit=oldsha,checkpoint_columns=1066,optimize_budget_seconds=BUDGET,budget_authority='Union of actual native optimize wall intervals across worker processes plus sequential RMP solves; build/audit/test and checkpoint I/O separately recorded.',schedule=['DISCOVERY','DISCOVERY','DISCOVERY','CERTIFICATION'],discovery_cap_seconds=20,certification_cap_seconds=60,final_certification_max_seconds=120,final_reserve_rule='After each ordinary round, if remaining optimize budget >=120 and cannot fit another complete D1 D2 D3 C1 block estimated as 3*(last_RMP_wall+20*ceil(4/workers))+(last_RMP_wall+60*ceil(4/workers)) plus 8s reserve, perform final certification. Cap=min(120,(remaining-RMP_reserve-4)/ceil(4/workers)), with conservative RMP reserve=max(30,last_RMP_wall). Never extend900s.',
      candidate_workers=[4,2,1],Threads=1,environment=ENV,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,postsolve_affine_tolerance=POST,discovery_negative_threshold=DISCOVERY_RC,no_negative_BestBd_authority=-EPS,MIPGap=0,MIPGapAbs=0,full_original_domain=True,heuristic_domain_restriction=False,column_deletion=False,column_aging=False,previous_feasible_MIP_start_only=True,
      corrected_theorem_SHA=sha(PREVIOUS/'DW_CORRECTED_DUAL_THEOREM.json'),certificate_source_SHA=sha(ROOT/'v42_dw_bound/certificate.py'),bound_authority='Terminal native global ObjBound, including ObjCon; fixed1e-8 safety and outward Fraction rounding; exact global residual box correction unchanged.',certificate_policy='Only CERTIFICATION and FINAL_CERTIFICATION publish corrected lower bounds/material decisions. Discovery finite bounds preserved diagnostically, without lower-bound/no-negative/convergence claims.',certification_column_policy='No columns added in certification rounds; next discovery generates columns under its own fresh dual.',
      material_threshold=T_MATERIAL,material_stop='L>=threshold or OPTIMAL audited RMP U<=threshold, immediately stop; otherwise INCONCLUSIVE',convergence='All four terminal OPTIMAL same-dual rc>=-1e-8 and safe bracket gap<=1e-6; BestBd no-negative is also separately recorded. No incomplete-pricing convergence.',
      resource_gate=dict(min_available_RAM='max(8GiB,0.15*physical_RAM)',severe_pagefile_growth_bytes=2*1024**3,sampling_seconds=1,allow_external_heavy_processes=False,no_OOM=True,no_license_error=True,no_numerical_or_model_mismatch=True,downgrade=[4,2,1]),performance_gate=dict(discovery_round_wall='median<=60s with4 workers, <=120s with1/2; includes RMP, pricing, validation, column addition, checkpoint.',throughput='Validated added discovery columns per total canary elapsed minute strictly greater than preserved old policy columns per observed elapsed minute.',no_scientific_violation=True,no_resource_safety_failure=True),stop_file='STOP_REQUEST.json: monitor calls Model.terminate(), terminal receipts preserved, no abrupt kill',no_production=True))
    policy=dict(B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,THREADS_PER_SOLVE=1,B2_INNER_PRICING_WORKERS=1,B3_INNER_PRICING_WORKERS='Selected1/2/4 only after resource gate PASS',maximum_simultaneous_pricing_processes=4,main_order=['B0','B1','B2','B3(L1)','B3(L2)','B3(L3)','B3(L4)'],B3_loop=['A1','M1','A2','M2'],Actual_feedback_to_Planning=False,next_Planning='previous Planning only',production_calls=[0,0,0])
    write('CAMPAIGN_WORKER_POLICY.json',policy)
    p=read(OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json');p['final_reserve_rule']='Reserve120s for a final certification before starting another ordinary cycle/round; cycle estimate is3*(last_RMP_wall+20*ceil(4/workers))+(last_RMP_wall+60*ceil(4/workers))+8s. At cycle boundary use final certification when remaining<cycle_estimate+120, or before an ordinary round if remaining<max(30,last_RMP_wall)+ordinary_cap*ceil(4/workers)+124. Final cap=min(120,(remaining_after_RMP-4)/ceil(4/workers)); no automatic extension.';write('DW_DISCOVERY_CERT_PREREGISTRATION.json',p)
    print('POLICY_PREREG_CHECKPOINT_PASS',len(checks),oldsha)
def freeze():
    sources=[p for p in (ROOT/'v42_dw_policy').glob('*.py')]
    write('EXECUTION_FREEZE.json',dict(sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(sources)],preregistration_SHA=sha(OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json')))
if __name__=='__main__':
    import sys
    freeze() if '--freeze-only' in sys.argv else prepare()
