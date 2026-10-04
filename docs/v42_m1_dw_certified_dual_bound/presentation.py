"""Presentation-only terminal log clarification; no scientific optimization."""
import sys
sys.path.insert(0,sys.argv[1])
from v42_dw_bound.common import *
from v42_dw_bound.finalize import manifest
assert (OUT/'DW_FINAL_RESULT.json').exists()
s=read(OUT/'DW_BOUND_SPEED_AUDIT.json');w=read(OUT/'DW_RMP_WARMSTART_AUDIT.json')
hints=[h for h in w['hints'] if h['basis_supplied']]
counts={key:sum(h['native_basis_acceptance']==key for h in hints) for key in sorted({h['native_basis_acceptance'] for h in hints})}
s['RMP_warm_distribution_scope']='Previous optimal basis hint SUPPLIED; native acceptance is separately evidenced in DW_RMP_WARMSTART_AUDIT.json.'
s['native_basis_acceptance_counts']=counts
s['CG_iteration_time_scope']='Sum of native RMP/pricing optimize wall calls at each RMP dual; separate build, audits, certificates and checkpoint I/O excluded.'
write('DW_BOUND_SPEED_AUDIT.json',s)
v=read(OUT/'VERIFICATION.json');audit=read(OUT/'FULL_ORIGINAL_LOCAL_PRICING_POSTAUDIT.json');assert audit['PASS']
v['supplemental_full_original_local_pricing_postaudit']=dict(PASS=True,candidates=len(audit['checks']),optimization_calls=0,repair_calls=0,artifact_SHA=sha(OUT/'FULL_ORIGINAL_LOCAL_PRICING_POSTAUDIT.json'))
write('VERIFICATION.json',v)
def stats(x):
    return ' / '.join('NULL' if x[k] is None else f"{x[k]:.6f}s" for k in ('median','p95','maximum'))
p=OUT/'FINAL_REVIEW_KO.md';lines=p.read_text(encoding='utf8').splitlines()
for i,line in enumerate(lines):
    if line.startswith('13. '):lines[i]=f"13. Optimal pricing median/p95/max: {stats(s['optimal_pricing_seconds'])}."
    if line.startswith('14. '):lines[i]=f"14. RMP basis hint supplied median/p95/max: {stats(s['RMP_warm_seconds'])}; cold {stats(s['RMP_cold_seconds'])}. Native acceptance {counts}; supplied를 accepted warm start로 해석하지 않음."
    if line.startswith('28. '):lines[i]+=' CG iteration timing은 optimize wall 합계이며 build/audit/checkpoint는 별도. 고정 Method2 정책의 native basis discard 로그 보존.'
    if line.startswith('1. '):lines[i]+=' 사용자 정책 재설계 중단: POLICY_EXPERIMENT_PARTIAL, scientific INCONCLUSIVE. 정상 native terminate receipt 미확인; active call21 제외.'
    if line.startswith('27. '):lines[i]+=' optimize wall은 완료된 call만 합산; 중단된 call21의 정확한 terminal wall은 NULL. 마지막 telemetry elapsed 관측값을 별도 보존.'
p.write_text('\n'.join(lines)+'\n',encoding='utf8')
p=OUT/'PR_DESCRIPTION.md';body=p.read_text(encoding='utf8').split('\n\nWarm-start log clarification:')[0]
p.write_text(body+f'\n\nWarm-start log clarification: basis hints were supplied on {len(hints)} later RMP calls, with native log acceptance {counts}. Timing distributions refer to hint supply, not confirmed basis use. The fixed Method2 policy is unchanged. Every saved valid pricing candidate also passes a read-only audit of all original unreduced local rows. Atomic checkpoints retain reconstruction data; this experiment has no automated restart CLI.\n\nUser-requested policy redesign stop: POLICY_EXPERIMENT_PARTIAL, scientific INCONCLUSIVE. The session interrupt exited without a normal native terminal receipt for active call21; its partial bound/incumbent is excluded. Reported optimize wall sums completed calls only; interrupted-call exact wall is NULL. No scientific failure or nonmaterial decision is inferred.\n',encoding='utf8')
manifest()
print('PRESENTATION_CLARIFICATION_PASS',counts)
