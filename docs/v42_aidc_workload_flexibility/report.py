"""Reporting only; cannot change registration, eligibility, or memberships."""
from pathlib import Path
import json,hashlib
import pandas as pd
from study import HERE,dump,csv,sha

def write(name,text):(HERE/name).write_text(text,encoding='utf-8')

def main():
    comp=pd.read_csv(HERE/'RULE_COMPARISON.csv').query('period == "MAY"').set_index('rule')
    r0=comp.loc['R0']; memberships={r:pd.read_csv(HERE/f'FLEXIBLE_MEMBERSHIP_{r}.csv',dtype={'job_uid':str}) for r in comp.index}
    funnel=[]
    for rule,f in memberships.items():
        for qos,g in f.groupby('qos'):
            a=g.state_at_issue.eq('PENDING') & ~g.protected
            b=a & g.AIDC_site.ne('UNASSIGNED') & g.start_slot.between(24,119)
            c=b & g.individual_slack_slots.ge(1)
            e=c & (g.qos.eq('standby') | g.cohort_latency_tolerant)
            for stage,mask in [('all',g.index==g.index),('pending_unprotected',a),('frozen_in_day_admitted',b),('positive_reference_slack',c),('cohort_or_standby',e),('terminal_domain',g.temporal_domain),('capacity_witness',g.temporal_flexible)]:
                funnel.append(dict(rule=rule,qos=qos,stage=stage,jobs=int(sum(mask)),GPUh=float(g.loc[mask,'day_GPUh'].sum())))
    csv('ELIGIBILITY_FUNNEL.csv',pd.DataFrame(funnel))
    normal=memberships['R1'].query('qos == "normal" and cohort_latency_tolerant and 24 <= start_slot < 120')
    assert len(normal)==456 and ((normal.start_slot+normal.safe_duration_slots)>120).all()
    audit=json.loads((HERE/'INDEPENDENT_VALIDATION.json').read_text(encoding='utf-8'))
    raw=json.loads((HERE/'RAW_REQUEST_BRIDGE.json').read_text(encoding='utf-8'))
    def pct(a,b):return 100*a/b
    table='| Rule | Flexible job-days | Jobs % | Flexible GPUh | GPUh % | Incremental PCC kWh | PCC % | Added job-days / GPUh |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for rule,r in comp.iterrows():
        table+=f'| {rule} | {r.flexible_jobs:,.0f} | {r.flexible_jobs_pct:.6f} | {r.flexible_GPUh:,.2f} | {r.flexible_GPUh_pct:.6f} | {r.flexible_AIDC_PCC_kWh:,.6f} | {r.flexible_AIDC_energy_pct:.6f} | {r.new_jobs:,.0f} / {r.new_GPUh:,.2f} |\n'
    levels='| R0 definition | Job-days | Day GPUh | GPUh % | Incremental PCC % |\n|---|---:|---:|---:|---:|\n'
    for name,j,g,e in [('stored standby eligibility gate',r0.gate_jobs,r0.gate_GPUh,r0.gate_PCC_kWh),('exact restored production temporal domain',r0.domain_jobs,r0.domain_GPUh,r0.domain_PCC_kWh),('registered standalone capacity-witness screen',r0.flexible_jobs,r0.flexible_GPUh,r0.flexible_AIDC_PCC_kWh)]:
        levels+=f'| {name} | {j:,.0f} | {g:,.2f} | {pct(g,r0.total_GPUh):.6f} | {pct(e,r0.total_AIDC_PCC_kWh):.6f} |\n'
    flags=dict(BASELINE_REPRODUCED=True,LATENCY_AWARE_RULE_VALID=True,SERVICE_PRESERVATION_PASS=True,
        FLEXIBLE_GPUH_SHARE_R0=r0.flexible_GPUh/r0.total_GPUh,
        FLEXIBLE_GPUH_SHARE_R1=comp.loc['R1','flexible_GPUh']/r0.total_GPUh,
        FLEXIBLE_GPUH_SHARE_R2=comp.loc['R2','flexible_GPUh']/r0.total_GPUh,
        V42_WORKLOAD_RULE_RECOMMENDED='R0',PRODUCTION_CHANGED=False,OPTIMIZER_CHANGED=False,ML_CHANGED=False,
        FLAG_SCOPE='offline May reference, registered standalone capacity-witness temporal metric; not global optimizer flexibility or operational certification',
        FULL_RAW_PERIOD_ELIGIBILITY_AVAILABLE=False,OPERATIONAL_LATENCY_TOLERANCE_CERTIFIED=False,
        PRODUCTION_DOMAIN_GPUH_SHARE_R0=r0.domain_GPUh/r0.total_GPUh,
        PRODUCTION_DOMAIN_GPUH_SHARE_R1=comp.loc['R1','domain_GPUh']/r0.total_GPUh,
        PRODUCTION_DOMAIN_GPUH_SHARE_R2=comp.loc['R2','domain_GPUh']/r0.total_GPUh,
        PRODUCTION_GATE_GPUH_SHARE_R0=r0.gate_GPUh/r0.total_GPUh)
    dump('FINAL_FLAGS.json',flags)
    write('README.md',f'''# V42 AIDC workload flexibility eligibility study

R1 adds **no temporal-flexible jobs or GPUh** under the registered rule and frozen service boundaries. R2 removes 43 standby job-days / 56.5 GPUh. Retain R0; this study does not support a new production latency rule.

{table}
The primary metric above is the pre-registered standalone capacity-witness screen: one job moves while every other job remains at B0. It is a conservative sufficient feasibility test, **not the production optimizer's jointly coupled temporal domain**. R0 production gate and candidate-domain reproduction are reported separately:

{levels}
Denominators: {r0.total_jobs:,.0f} independent job-day records, {r0.total_GPUh:,.2f} admitted reference Day-D GPUh, {r0.total_AIDC_PCC_kWh:,.6f} frozen unscaled B0 PCC kWh. Full safe-duration service totals {r0.total_full_service_GPUh:,.2f} GPUh, with pre-day/tail/backlog included; it is a separate metric. May snapshots repeatedly contain the same physical job, so these are not monthly unique-job execution totals.

`ALL_AVAILABLE` and `MAY` both cover May 01–31, 2025. Whole-raw-trace eligibility is **NOT_AVAILABLE** because other dates lack this exact V41R4 frozen reference/domain authority. No runtime model, admission schedule, or workload scale was invented to fill that gap. Raw-request bridge covers {raw['raw_total_records']:,} raw accounting rows and {raw['unique_reference_jobs']:,} unique evaluation jobs; TRAIN has 439,534 distinct jobs completed before 2025-01-01.

## Reproduce

Python 3.11, numpy, pandas, pyarrow; versions are in `ENVIRONMENT.json`. Original local input paths and exact SHA-256s are in `SOURCE_MANIFEST.json`. Constants at the top of `study.py` locate external archives; path relocation is permissible only with identical hashes. Large original trace/frozen input archives are external dependencies, not bundled here.

From this directory:
```
python -m unittest test_contract -v
python study.py evaluate
python raw_request_bridge.py
python validate_independently.py
python report.py
```
`evaluate` restores ignored TRAIN CSV from the checked-in deterministic gzip and verifies its registered hash. It regenerates this study's evidence only. To independently rebuild TRAIN, use a fresh copy/output directory without registration artifacts, then `python study.py prepare`; never overwrite this frozen registration. `prepare` refuses an existing registration. The threshold/rule registration was committed at `f937659f` (exact-byte preservation `fcc28fd0`) before evaluation.

The only post-freeze evaluation-code repair resolves a missing legacy source path to an identical SHA-256 copy in the retained repository. `IMPLEMENTATION_AMENDMENT.json` records it. No rule/threshold changes followed evaluation.

## Evidence

- `FLEXIBLE_MEMBERSHIP_R*.csv` deliberately retain **all** reference jobs and flags, including fixed/unadmitted jobs; filter `temporal_flexible` for primary membership. `temporal_domain` is the production-style geometric domain, `eligible_standby` the exact original stored gate, and `spatial_flexible` the unchanged frozen spatial/migration membership.
- `FEASIBLE_OPTIONS.csv` lists every safe standalone alternative as exact site/start sets. Options are alternatives, not independently selectable simultaneous moves; a future scheduler must retain aggregate capacity constraints.
- `COHORT_LATENCY_STATISTICS.csv`, `TRAIN_MEMBERSHIP.csv.gz`, `ELIGIBILITY_FUNNEL.csv`, `INCLUSION_BY_COHORT.csv`, and `SHIFT_WINDOW_DISTRIBUTION.csv` expose cohort support, selection, reason and windows.
- `GPUH_SHARE_BY_DAY.csv` and `RULE_COMPARISON.csv` contain exact numerators/denominators, category totals, and non-targeted 20/30/40 reporting.
- `SERVICE_FEASIBILITY_AUDIT.json`, `LEAKAGE_AUDIT.json`, `RAW_REQUEST_BRIDGE.json`, and `INDEPENDENT_VALIDATION.json` distinguish observed checks from provenance limitations.
- Read `FINAL_REVIEW_KO.md` for the verdict and `PROVENANCE_LIMITATIONS.md` before interpreting these as operational workload flexibility.

No ML/CC4/runtime fitting or prediction, traffic, optimizer, MESS, grid simulation, Actual replay, or V42 A1-M1-A2-M2 execution occurred. Existing evidence was read only. No production integration was made.
''')
    write('CURRENT_RULE_AUDIT.md',f'''# Current rule reproduction

The literal stored gate is `state_at_issue == PENDING and qos == standby and RSP_start_slot + safe_duration_slots <= RW_completion_slot`. It is recomputed for all 47,009 reference records and compared exactly with `eligible_standby`.

The active V41R4 temporal restoration additionally requires the existing migration contract's admitted in-day PENDING reference: `24 <= reference_start < 120`. The original `terminal.start_bounds` uses:

```
lower = max(24, RSP_start_slot)
upper = min(RW_completion_slot - safe_duration_slots,
            119,
            120 - safe_duration_slots + max(0, reference_end - 120))
```

RUNNING, unadmitted, pre-day starts and out-of-day starts remain fixed for temporal decisions. A gate can be true but the start window can have zero width. Each restored start can use any original whole-gang-compatible site/rack. The restoration does not create shifted-start checkpoint migration products. A separate capacity coupling remains necessary across selected options.

{levels}
All 31 daily frozen manifests' per-job added option counts and daily restored counts match exactly. Independent verification extracts only the two pure original terminal functions by AST and compares bounds; it imports or runs no production pipeline. The baseline occupancy matches the frozen 96×12 GPU arrays exactly, and the separate C1 implementation matches frozen PCC arrays within 1e-8 kW.

Primary screen vs production: the standalone witness restriction is **additional analysis**, not a claim that production enforces fixed-other-job occupancy for every domain option. It rejects {int(r0.domain_jobs-r0.flexible_jobs):,} domain job-days lacking a feasible single-job move. Joint coordinated movements might recover some; no optimizer was run, so neither their achievable share nor a system dispatch schedule is claimed.

No 14.x% value was used as an authority. With raw frozen B0 GPU and PCC denominators, gate GPUh is {pct(r0.gate_GPUh,r0.total_GPUh):.9f}%, gate marginal PCC share {pct(r0.gate_PCC_kWh,r0.total_AIDC_PCC_kWh):.9f}%, domain GPUh {pct(r0.domain_GPUh,r0.total_GPUh):.9f}%, and domain marginal PCC share {pct(r0.domain_PCC_kWh,r0.total_AIDC_PCC_kWh):.9f}%. These differ because idle/facility power and nonmovable gate-positive work are not flexible energy.

Energy is reference-occupancy attribution: `sum(P_C1(IT_total)-P_C1(IT_total - 0.5477239090195797*kW*flexible_GPU))*0.25h`; denominator is `sum(frozen B0 PCC)*0.25h`. It retains installed idle power and exact frozen weather/C1 coefficients. It is not measured per-job energy, energy saving, a new power scale, or post-dispatch energy. Dynamic IT energy is separately reported. Existing later paper scaling is outside this raw-authority audit.

Protection is temporal. Original frozen spatial/migration rights include protected/carry-in work; those rights and membership are unchanged. Historical migration has its own checkpoint/service contract and does not imply a universal user deadline. See prior frozen `docs/v41r4_final/evidence/posthoc/DEADLINE_AUDIT_REPORT.md` in the base branch. This study claims reference-completion/terminal preservation for new standalone temporal options only, not a retroactive SLA certificate for every legacy migration.
''')
    write('PROVENANCE_LIMITATIONS.md','''# Provenance and scientific limits

1. Raw Slurm accounting request/QoS fields are final recorded fields. Matching them to a frozen snapshot is not proof that those versions were available at the historical D-1 decision. Submission/event-time filtering and a strictly mature TRAIN split pass, but historical request-version and full scheduler-census provenance remain unverified. Operational no-future-information certification is therefore unavailable. This is an offline proxy study.
2. Observed queue delay reflects congestion, priority, resource scarcity, user behavior and possible throttling. It is not consent to additional delay and does not measure a user latency SLA. Median, support N=100, fixed buckets and a one-slot minimum are registered research choices. Sparse/unknown cohorts fail closed; no evaluated threshold search was conducted. Conditioning on completed history induces selection bias.
3. The literature motivates separating delay-tolerant work and preserving service. [Radovanovic et al.](https://arxiv.org/abs/2106.11750) describe temporal workload shifting with daily capacity preservation. It supplies no numerical Kestrel tolerance. [NLR batch-job documentation](https://natlabrockies.github.io/HPC/Documentation/Slurm/batch_jobs/) identifies standby as idle-node work; it does not certify that normal jobs tolerate additional waiting. Current documentation is not a historical snapshot of the 2025 policy.
4. Workload classes here are deterministic scheduler policy classes (`NORMAL_QUEUE_CONTROLLED`, etc.), not measured application identities such as training/inference. Requested GPU/node/walltime buckets do not establish application semantics.
5. Frozen safe durations are preserved exactly, including their slot rounding. They are model bounds, not guaranteed realized service. Requested-walltime RW completion is a synthetic reference completion coordinate, not a supplied end-user deadline. No new model, realized future duration or actual replay is used.
6. May is previously exposed historical evidence. This task froze rules before this evaluation but cannot turn May into an untouched prospective test. Full raw-trace dates have no complete V41R4 frozen admission/reference/domain coverage; their eligibility is NOT_AVAILABLE. ALL_AVAILABLE equals MAY, not the entire raw dataset. A new full-period scheduling/runtime experiment is outside this authorization.
7. Site capacities total 780 GPUs; logical rack labels are nonadditive whole-gang compatibility envelopes, not a measured physical rack census. Exact frozen limits are preserved. The standalone capacity screen is sufficient for a one-job substitution into B0, but not a joint scheduling feasibility guarantee and not the original production candidate domain. No capacity screen is represented as an optimizer result.
8. Spatial-only/both are workload rights from the unchanged original manifest. They do not establish that all migration options can execute simultaneously or within a nonexistent SLA. Protected jobs gain no new temporal right, while existing protected spatial rights remain intact.
9. GPUh is allocated requested-GPU slot service, not GPU utilization telemetry. May aggregates are independent job-day observations, with repeated physical IDs. PCC energy is a frozen synthetic facility model evaluated at baseline occupancy; marginal attribution is not metered per-job energy or energy savings.
10. All numeric baseline labels are explicit: the literal eligibility gate, geometric production domain, and newly registered standalone screen have different shares. Using the gate or spatial union to advertise 20/30/40% temporal flexibility would misstate this result.
''')
    write('FINAL_REVIEW_KO.md',f'''# V42 workload eligibility 최종 검토

**R1/R2를 새 main workload rule로 승격할 근거가 없다. 기존 R0를 유지한다.** R1은 추가 작업/GPUh가 없고, R2는 더 좁은 지연 예산 때문에 standby 43 job-days, 56.5 GPUh를 제외한다. 이는 registered 규칙에서 얻은 결과이며 20/30/40%에 맞추는 재조정은 하지 않았다.

## 1. 기존 rule은 얼마나 보수적인가?

단순 standby gate와 실제 이동 가능성은 같지 않다. 아래는 동일한 May reference와 raw power authority에서 다시 계산한 값이다.

{levels}
보수성의 원인은 QoS 하나만이 아니다. R1의 latency-tolerant normal은 702 job-days이고 그중 당일 시작 대상은 456건이다. 456건 모두 safe-duration reference가 D24를 넘기므로 terminal 잔여 service 증가 금지에 의해 시작 상한이 reference start와 같아진다. 즉 이 frozen reference에서는 standby hard gate만 제거해도 추가 temporal 후보가 없다. 모든 normal workload가 본질적으로 유연하지 않다는 결론은 아니다.

## 2–3. Baseline 및 R1/R2 flexible GPUh는?

{table}
표의 primary는 사전 등록한 **다른 작업을 B0에 고정한 단일 작업 이동의 용량 witness** 기준이다. 이를 기존 production optimizer의 전체 flexibility라고 부르지 않는다. Production geometric domain의 R0/R1 GPUh 비중은 각각 {pct(r0.domain_GPUh,r0.total_GPUh):.9f}% / {pct(comp.loc['R1','domain_GPUh'],r0.total_GPUh):.9f}%, R2는 {pct(comp.loc['R2','domain_GPUh'],r0.total_GPUh):.9f}%이다. 원래 gate의 비중은 {pct(r0.gate_GPUh,r0.total_GPUh):.9f}%다. 기존 14.x%를 복사하거나 GPUh와 PCC 분모를 혼용하지 않았다.

분모는 47,009 job-days, {r0.total_GPUh:,.2f} 당일 admitted GPUh, {r0.total_AIDC_PCC_kWh:,.6f} PCC kWh다. 고유 작업은 raw bridge에서 {raw['unique_reference_jobs']:,}개다. 전체 safe-duration service 분모 {r0.total_full_service_GPUh:,.2f} GPUh는 당일 GPUh와 구별하며 CSV에 별도 기록한다. fixed/unadmitted/post-day 작업도 membership에서 삭제하지 않았다.

## 4. 20%, 30%, 40% 중 자연스럽게 나타나는 수준은?

새 규칙의 실제 temporal domain과 단일 작업 capacity witness 기준에서는 **셋 모두 도달하지 않는다**. 단순 standby gate는 20%를 넘지만 이동 권한/terminal/용량을 모두 통과했다는 뜻이 아니다. 기존 spatial 권한을 합한 union은 {pct(r0.union_GPUh,r0.total_GPUh):.6f}%로 크지만 그것을 새로운 temporal flexibility로 주장하지 않는다. CSV는 이 정의들을 분리한다.

## 5. 증가분의 QoS/workload cohort는?

증가분은 **0**이다. 모든 temporal witness는 standby / STANDBY_QUEUE_CONTROLLED에서 온다. R2가 제외한 43건도 standby다. QoS, partition, workload class, GPU bucket, reason별 모집단·포함량·추가량은 `INCLUSION_BY_COHORT.csv`, 단계별 탈락은 `ELIGIBILITY_FUNNEL.csv`에 있다. 결과를 보고 cohort나 median/N/slot threshold를 변경하지 않았다.

## 6. Service/QoS/terminal constraints는 보존되는가?

새로 열거한 standalone 옵션에서 safe duration, RW reference completion, 개별 terminal 잔여량, 원래 admission, whole-gang/site/rack 한계를 모두 검사했다. 다른 작업 B0 occupancy를 포함해 용량 위반 옵션을 제거했고, witness가 없는 작업은 이 screen에서 fixed다. protected temporal membership 변화는 0이며 전체 job-day 및 GPUh 질량을 보존했다. 기존 spatial/migration membership은 그대로다. 조합된 여러 이동을 동시에 실행하는 스케줄의 feasibility나 실제 runtime SLA는 검사하지 않았다. 기존 migration의 별도 완료 규칙을 새 universal deadline으로 바꾸지 않았다.

독립 구현은 {audit['membership_rows']:,}행, {audit['all_options_independently_checked']:,}옵션, source hash {audit['source_hashes_rechecked']}개를 검증했고 original R0 terminal 함수와 일치한다. 8개 contract test도 통과했다. TRAIN은 2025-01-01 이전 완료 439,534개이며 evaluation realized start/end/queue는 eligibility에 사용하지 않는다. 과거 request/QoS version provenance 미인증 때문에 운영 수준의 no-future-leakage 증명은 아니다.

## 7. Trace-derived인가, 문헌 가정인가?

TRAIN queue 분포·N·GPUh 및 frozen reference별 수치는 trace-derived다. Queue 중앙값을 추가 지연 허용량으로 해석하는 부분과 N=100은 **문헌으로 수치가 인증되지 않은 연구 가정**이다. 15분은 기존 scheduling resolution이다. [Carbon-Aware Computing for Datacenters](https://arxiv.org/abs/2106.11750)는 지연 허용 작업과 daily service 보존이라는 방향을 뒷받침하며, [NLR QoS 문서](https://natlabrockies.github.io/HPC/Documentation/Slurm/batch_jobs/)는 standby idle-node semantics를 뒷받침한다. 어느 쪽도 Kestrel normal 작업의 개별 SLA를 제공하지 않는다.

## 8. V42 main workload rule 근거는 충분한가?

**Latency-aware R1/R2 승격에는 불충분하다. R0 유지 권고다.** 추가 효과가 없고 실제 지연 허용 계약 및 historical request version 인증이 없다. 운영 승격에는 issue-time request version와 사용자/서비스 지연 예산의 authority가 필요하다. 현재 자료만으로 terminal 완화, workload scaling, 미래 realized 정보, threshold 역산을 추가하지 않았다.

전체 기간 제한: `ALL_AVAILABLE`은 frozen V41R4 authority가 존재하는 May 31일 전체다. 원 raw trace 전체 기간의 동일 eligibility 수치는 **NOT_AVAILABLE**이다. 다른 기간을 새로 admission/runtime 계산해서 메우는 것은 이번 금지 범위와 충돌하므로 하지 않았다. 따라서 요청한 전체 raw 기간 비교는 미충족 항목으로 명시한다.

## 최종 flags

`TRUE`는 offline May/standalone-option 검증 범위다. latency tolerance의 운영 인증 또는 jointly executable optimizer solution을 뜻하지 않는다. share는 0–1 단위다.

```json
{json.dumps(flags,indent=2,ensure_ascii=False)}
```

기존 frozen evidence overwrite, production/optimizer/ML 변경, 금지된 pipeline 실행은 없었다.
''')
    dump('IMPLEMENTATION_AMENDMENT.json',dict(kind='PATH_RESOLUTION_ONLY',initial_study_sha256=json.loads((HERE/'PRE_EVALUATION_FREEZE.json').read_text())['files']['study.py'],final_study_sha256=sha(HERE/'study.py'),reason='Frozen may_domain.py path absent; resolve retained base-repository copy and require original manifest SHA-256 equality.',rule_registration_changed=False,thresholds_changed=False,evaluation_result_used_to_change_rule=False,validator_repairs=['UTF-8 reading on Windows','invoke frozen terminal function only for its original in-day admitted PENDING call boundary']))
    import platform,numpy,pyarrow
    dump('ENVIRONMENT.json',dict(python=platform.python_version(),pandas=pd.__version__,numpy=numpy.__version__,pyarrow=pyarrow.__version__))
    dump('VALIDATION_SUMMARY.json',dict(contract_tests=8,contract_tests_pass=True,independent_validation=audit,raw_request_match_pass=not any(raw['request_mismatches'].values()) and raw['missing_job_days']==0 and raw['submit_after_issue']==0,registration_sha256=sha(HERE/'FLEXIBILITY_RULE_REGISTRATION.json'),coverage_limitation='FULL_RAW_PERIOD_NOT_AVAILABLE'))
    write('PR_DESCRIPTION.md',f'''V41R4 standby eligibility was often conflated with executable temporal flexibility. This offline study reproduces the exact 47,009 job-day gate and all 31 restored candidate manifests, then compares preregistered TRAIN-only latency rules without modifying production.

{table}
The primary table uses a conservative single-job capacity witness with all other jobs fixed. The original production temporal domain is {pct(r0.domain_GPUh,r0.total_GPUh):.6f}% GPUh; the literal gate is {pct(r0.gate_GPUh,r0.total_GPUh):.6f}%. These are reported separately, with exact frozen-C1 incremental PCC attribution. R1 adds nothing because all 456 otherwise eligible in-day normal records cross D24 and have zero terminal-preserving delay; R2 tightens standby budgets. No threshold was changed after evaluation. Retain R0.

Validation: 8 contract tests; independent reproduction of 141,027 membership records and 139,061 options; original terminal formulas; 228 source hashes; exact baseline GPU occupancy and PCC reproduction. All fixed/admitted populations, full service and spatial/migration rights remain present. No optimizer, runtime model, ML, CC4, traffic, grid, MESS, Actual or V42 coordinator was executed or changed.

Limitations: observed queue is not an SLA, historical request versions remain unverified, single-job alternatives are not a joint schedule, and May is previously exposed. Full raw-period eligibility is unavailable: ALL_AVAILABLE means all 31 frozen V41R4 May dates, not the entire raw trace. This draft explicitly records that unmet coverage requirement and does not recommend production latency-rule promotion.

Scope: only `docs/v42_aidc_workload_flexibility/`, based on the frozen V41R4 evidence branch. External raw/frozen archives are SHA-bound dependencies. Registration precedes evaluation in git history.
''')

if __name__=='__main__':main()
