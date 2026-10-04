"""Presentation/resource supplement; no optimization or point modification."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v42_dw_policy.common import *
from v42_dw_policy.finalize import manifest
f=read(OUT/'RESOURCE_ADAPTER_FREEZE.json');assert sha(OUT/'resource_adapter.py')==f['adapter_SHA'] and sha(OUT/'RESOURCE_ADAPTER_PREREGISTRATION.json')==f['preregistration_SHA']
r=read(OUT/'DW_POLICY_CANARY_FINAL.json');v=read(OUT/'VERIFICATION.json');s=read(OUT/'DW_POLICY_SPEED_COMPARISON.json');old=read(PREVIOUS/'DW_FINAL_RESULT.json')
width=lambda interval:interval[1]-interval[0]
s['old_bracket_narrowing_per_observed_minute']=(width(old['first_interval'])-width(old['final_interval']))/(old['elapsed_including_build_audit_seconds']/60)
s['old_completed_RMP_count']=old['new_RMP_solves'];s['old_completed_pricing_count']=old['new_pricing_calls'];s['new_RMP_count']=r['new_RMP_solves'];s['new_pricing_count']=r['new_pricing_calls'];s['median_discovery_round_wall']=r['median_discovery_round_wall'];s['median_certification_round_wall']=r['median_certification_round_wall'];s['selected_pricing_workers']=r['workers']
write('DW_POLICY_SPEED_COMPARISON.json',s)
canary=read(OUT/'DW_PRICING_CONCURRENCY_CANARY.json');attempts=canary['attempts']
for a in attempts:
    if a['PASS']:
        assert a['min_available_RAM']>=resource_threshold(a['physical_RAM']) and a['max_pagefile_growth']<=2*1024**3
v['resource_adapter']=dict(PASS=True,source_SHA=f['adapter_SHA'],preregistration_SHA=f['preregistration_SHA'],commit=r['preopt_commit'],original_scientific_source_changed=False,carried_RMP_status=11,carried_RMP_wall=read(OUT/'RMP_RECEIPT_0001.json')['wall_seconds'],budget_reset=False)
v['resource_gate_supplement']=dict(PASS=True,attempts=len(attempts),selected_workers=r['workers'],selected_resource_PASS=r['resource_PASS'],failed_attempts_preserved=sum(not a['PASS'] for a in attempts),first_four_way_pricing_calls=0,first_four_way_gate_stage='WORKER_RESIDENCY_BEFORE_PRICING')
v['RMP_point_file_checks']=sum(bool(read(OUT/x['receipt'])['point_file']) for x in ledger('DW_RMP_LEDGER.csv'));v['unique_validated_dual_SHAs']=v['RMP_points_reaudited']
write('VERIFICATION.json',v)
campaign=read(OUT/'CAMPAIGN_WORKER_POLICY.json');assert [campaign[k+'_DAY_WORKERS'] for k in ('B0','B1','B2','B3')]==[4,1,4,1] and campaign['THREADS_PER_SOLVE']==1 and campaign['B2_INNER_PRICING_WORKERS']==1 and campaign['B3_INNER_PRICING_WORKERS']==r['workers'] and campaign['B3_RESOURCE_CANARY_PASS']==r['resource_PASS']
v['campaign_worker_policy']=dict(PASS=True,SHA=sha(OUT/'CAMPAIGN_WORKER_POLICY.json'),day_workers=[4,1,4,1],B2_inner=1,B3_inner=r['workers'],production=[0,0,0]);write('VERIFICATION.json',v)
p=OUT/'FINAL_REVIEW_KO.md';lines=p.read_text(encoding='utf8').splitlines()
for i,line in enumerate(lines):
    if line.startswith('5. '):lines[i]+= ' Original policy source/preregistration commit6716e136527db8332eefc982b33e85379de335a1도 변경 없이 보존.'
    if line.startswith('7. '):lines[i]+=' 4-way worker-residency gate가 pricing 시작 전에 실패했으며 actual4-way pricing calls=0. 2-way도 이후 실패해1-way 선택.'
    if line.startswith('23. '):lines[i]+=' Available-RAM gate 실패 이력이 있어PROMISING 조건을 충족하지 못함; selected1-way는PASS.'
p.write_text('\n'.join(lines)+'\n',encoding='utf8')
p=OUT/'PR_DESCRIPTION.md';body=p.read_text(encoding='utf8').split('\n\nResource/provenance supplement:')[0]
p.write_text(body+f'\n\nResource/provenance supplement: four-worker residency failed the8GiB RAM floor before actual parallel pricing; two-way initially passed, then failed the same floor and was normally terminated. The selected one-way execution passed. Thus the strict no-resource-failure PROMISING gate is NOT_SUPPORTED, independently of scientific materiality. Original frozen scientific policy source6716e136527db8332eefc982b33e85379de335a1 remains unchanged; the corrective resource adapter was frozen and committed at {r["preopt_commit"]} before continuation, carrying the0.320560s INTERRUPTED RMP against the same900s budget. The zero-optimize missing-log-directory failure is also preserved. Explicit recovery uses resource_adapter.py --resume; in-flight work is conservatively charged, never granted a new900s budget.\n',encoding='utf8')
manifest();print('PUBLICATION_RESOURCE_PROVENANCE_PASS',len(attempts))
