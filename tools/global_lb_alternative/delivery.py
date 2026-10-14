"""Read-only mathematical replay and Korean evidence reports; no solver calls."""
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
import argparse
import csv
import json
import shutil
import subprocess

import numpy as np
from scipy import sparse

from tools.global_lb_alternative.research import OUT,ROOT,CURRENT,PHYS,BASE,read,write,file_sha,csv_write
from tools.global_lb_alternative.math import require,signature
from tools.verify_physical_global_lb import OriginalGeometry


def bind_source_metadata():
    """Correct an evidence field label, without changing any mathematics or solve.

    Original trial metadata remains in TRIAL_ORIGINAL_BINDING.json. The initial
    field held the source/input identity packet SHA, not execution-source SHA.
    FINAL_FREEZE supplies the actual original execution-source authority.
    """
    audit=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')
    original=audit['binding']
    freeze_path=Path('D:/v42_may_joint_repair_campaign_20261013/FINAL_FREEZE.json')
    freeze=read(freeze_path)
    require(freeze['PASS'] and freeze['physics_unchanged'],'ORIGINAL_EXECUTION_SOURCE_NOT_FROZEN')
    if original['source_sha']==freeze['source_SHA']:
        return
    new=dict(original,source_sha=freeze['source_SHA'],source_input_packet_sha=original['source_sha'],
             physical_source_git=audit['physical_source_git'])
    write(OUT/'TRIAL_ORIGINAL_BINDING.json',dict(original_binding=original,certified_binding=new,
        original_source_freeze_path=str(freeze_path),original_source_freeze_sha=file_sha(freeze_path),
        correction='Trial source_sha held the source/input packet digest. Relabel to actual original execution-source SHA; retain the old digest separately. No model, coefficient, bound, result, solver call or runtime changed.',
        Native_calls=0))
    def replace(value):
        if isinstance(value,dict):
            if value==original:return new.copy()
            return {k:replace(v) for k,v in value.items()}
        if isinstance(value,list):return [replace(v) for v in value]
        return value
    for path in OUT.rglob('*.json'):
        if path.name=='TRIAL_ORIGINAL_BINDING.json':continue
        value=read(path);changed=replace(value)
        if changed!=value:write(path,changed)
    audit=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')
    for path in (freeze_path,Path('D:/v42_may_joint_repair_campaign_20261013/dates/B2/2025-05-02/attempts/attempt_01/NATIVE_RUNTIME_LEDGER.json')):
        audit['protected_files'].append(dict(path=str(path),sha256=file_sha(path)))
    write(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT_AUDIT_SUPPLEMENT.json',dict(PASS=True,binding=new,
        actual_original_execution_source_sha=freeze['source_SHA'],original_input_packet_sha=original['source_sha'],
        original_source_freeze_sha=file_sha(freeze_path),metadata_only_correction=True))
    write(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json',audit)
    # Numerical solver optima do not make an exact mathematical subgradient.
    path=OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json';q=read(path)
    for p in q['evaluations']:p['update_oracle']='NUMERICAL_PRIMAL_HEURISTIC_CANDIDATE_GENERATION_ONLY_NEVER_EXACT_SUBGRADIENT'
    write(path,q)


def helper_repair():
    bound=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')['binding']
    hist=read(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json')['evaluations']
    chosen=max(hist,key=lambda p:F(p['exact_LB']))
    catalog=read(OUT/'ORIGINAL_AFFINE_ROW_CATALOG.json')['rows']
    A=sparse.load_npz(CURRENT/'FULL_A.npz').tocsr()
    with np.load(CURRENT/'FULL_DATA.npz') as z:d={k:z[k].copy() for k in z.files}
    geom=OriginalGeometry(A,d)
    rho=list(d['names']).index('rho_max');residual={rho:F(1)};row_term=F(0);pi={}
    def add(row,multiplier):
        nonlocal row_term
        pi[row]=pi.get(row,F(0))+multiplier
        row_term+=multiplier*F(float(d['rhs'][row]))
        begin,end=A.indptr[row:row+2]
        for j,a in zip(A.indices[begin:end],A.data[begin:end]):
            j=int(j);residual[j]=residual.get(j,F(0))-multiplier*F(float(a))
    for k,w in chosen['weights'].items():add(int(k),-F(w))
    for k,w in chosen['mu'].items():add(int(k),-F(w)*(1 if d['sense'][int(k)]=='<' else -1))
    before={j:v for j,v in residual.items() if j in geom.definitions and v}
    count=0
    while True:
        active=next((j for j,v in residual.items() if v and j in geom.definitions),None)
        if active is None:break
        value=residual[active];add(geom.definitions[active],value);count+=1
        require(count<10000,'HELPER_MULTIPLIER_CYCLE')
    require(residual[rho]==0,'RHO_STATIONARITY_NOT_EXACT_ZERO')
    expected=defaultdict(F);constant=F(0)
    for key,value in list(chosen['weights'].items())+list(chosen['mu'].items()):
        p=catalog[key];v=F(value);constant+=v*F(p['constant'])
        for j,a in p['terms'].items():expected[int(j)]+=v*F(a)
    expected={j:v for j,v in expected.items() if v};actual={j:v for j,v in residual.items() if v}
    require(actual==expected and row_term==constant,'EXACT_HELPER_MULTIPLIER_REPAIR_MISMATCH')
    require(all(d['sense'][i]=='=' or d['sense'][i]=='<' and v<=0 or d['sense'][i]=='>' and v>=0 for i,v in pi.items()),
            'CORRECTED_ORIGINAL_ROW_SIGN_CONE')
    packet=dict(PASS=True,binding=bound,evaluation=chosen['evaluation'],before_nonzero_helper_residuals=len(before),
        correction_operations=count,after_helper_residual_exact_zero=True,rho_residual_exact_zero=True,
        exact_original_row_multipliers={str(i):str(v) for i,v in pi.items() if v},
        row_constant=str(row_term),physical_objective_exactly_equal_to_decomposed_objective=True,
        indefinite_equalities_use_free_signed_multipliers=True,infinite_original_bounds_changed=False,
        scope='Exact stationarity of all original injection/response helper axes. Physical minimum uses numerical global subproblem bounds; no exact B&B trace.',Native_calls=0)
    write(OUT/'EXACT_HELPER_MULTIPLIER_REPAIR.json',packet)
    audit=read(OUT/'NUMERICAL_DUAL_REPAIR_AUDIT.json');audit['exact_original_helper_multiplier_repair']=packet
    write(OUT/'NUMERICAL_DUAL_REPAIR_AUDIT.json',audit)
    print('EXACT_HELPER_REPAIR_PASS',len(before),count)


def reports():
    bound=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')['binding']
    current=read(OUT/'B2_CURRENT_UB_LB_REGISTRY.json');final=read(OUT/'FINAL_GLOBAL_LB_REGISTRY.json')
    a=read(OUT/'LAGRANGIAN_GLOBAL_LB_CERTIFICATE.json');b=read(OUT/'CUT_BASED_GLOBAL_LB_CERTIFICATE.json')
    histories=read(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json')['evaluations']
    supports=read(OUT/'MULTIPERIOD_HULL_CUT_CERTIFICATES.json')['certificates']
    resources=[]
    for p in (OUT/'A').rglob('RESULT.json'):resources.append(dict(algorithm='A',path=str(p),**read(p)))
    for p in (OUT/'B').rglob('RESULT.json'):resources.append(dict(algorithm='B',path=str(p),**read(p)))
    memory=read(OUT/'RESOURCE_MEMORY_AUDIT.json')
    memory['binding']=bound
    memory.update(native_results=resources,
        maximum_native_peak_RSS_bytes=max(p['peak_RSS_bytes'] for p in resources),
        maximum_native_peak_private_commit_bytes=max(p['peak_private_commit_bytes'] for p in resources),
        external_prelaunch_block=dict(receipt=str(OUT/'A/E02_A2_SPARSE_SIGNED_MULTIPERIOD/MESS02/RESOURCE_BEFORE.json'),
            reason='Unknown externally loaded Gurobi in Known/Unknown pytest, PID26168; exited without our intervention.',
            real_parallel_optimize_proven=False,no_owned_worker_was_terminated=True),
        workers_launched_by_research=1,concurrent_owned_native_calls=0,global_other_worker_absence_continuously_proven=False)
    write(OUT/'RESOURCE_MEMORY_AUDIT.json',memory)
    native_a=sum(p['Native_Runtime'] for p in resources if p['algorithm']=='A')
    native_b=sum(p['Native_Runtime'] for p in resources if p['algorithm']=='B')
    rows=[]
    k48=read(ROOT/'docs/v42_critical_grid_cg/iteration02/RESULT.json')
    k48_stages=[read(ROOT/f'docs/v42_critical_grid_cg/{i}/RESULT.json') for i in ('iteration01','iteration02')]
    for algorithm,lb,seconds,peak,verdict in (
        ('K48 Baseline',current['LB_K48'],sum(p['Runtime'] for p in k48_stages),max(p['peak_process_RSS_bytes'] for p in k48_stages),'BASELINE'),
        ('Stabilized Lagrangian',a['LB'],native_a,max(p['peak_RSS_bytes'] for p in resources if p['algorithm']=='A'),a['verdict']),
        ('Multi-period Route-SOC',b['LB'],native_b,max(p['peak_RSS_bytes'] for p in resources if p['algorithm']=='B'),b['verdict']),
        ('Best Certified Global LB',final['LB'],native_a+native_b,None,'FINAL_BASELINE_PRESERVED')):
        rows.append(dict(Algorithm=algorithm,Valid_Global_LB=lb,Delta_vs_K48=None if lb is None else lb-current['LB_K48'],
            Global_Gap_percent=None if lb is None else 100*(current['FULL_UB']-lb)/current['FULL_UB'],
            Native_Seconds=seconds,Peak_RAM_GiB=None if peak is None else peak/1024**3,Verdict=verdict))
    csv_write(OUT/'ALGORITHM_COMPARISON.csv',rows)
    # Method reuse is scoped to actual original coefficients, not historical values.
    prs=read(OUT/'PR_LATEST_HEADS.json')
    lines=['# PR 원본 방법 재사용 감사','',
        '| PR | 확인 HEAD | 사용 범위 |','|---|---|---|']
    scopes={187:'Injection P/Q stationarity support 손실과 raw sign 실패의 역사적 원인. 값 전용 없음.',
      202:'원래 등식 유도 finite envelope와 sign-cone/box 인증 원칙. 기존 코드/보고서 원본 Git object 읽음; 숫자 이전 없음.',
      203:'완전96-slot integer trajectory support와 탐색 가격/인증 가격 분리. 원본 adapter/pricing/보고서 읽음; 기존 가격·LB 이전 없음.',
      209:'모든 단일 차량 FULL 물리 행/Bounds/types, exact helper 소거, A0 네 인증값 재사용 및 현재 행렬 재대조.',
      210:'4-MESS Joint16 및 exact Compact proof. 원본 그대로 보존.',211:'K48 포함관계·외향행 및 수치 Global Bound 재사용; current FULL 수치 영역 동일성 확인.',
      214:'기존 BASE Point/CSR/Pi/RC 검증 후 Original 좌표 복원. 기존 단일 SOC cut을 반복하지 않음.',
      215:'Snapshot/Window 약한 하한의 부정적 결과. 시간 분해로 실험을 대체하지 않음.',
      220:'보호할 FULL Moving UB와 원본 Raw/DAG. 새 UB 탐색 없음.',221:'별도 승인 연구1790.197s 원장 보존, 새 PR222 원장과 실행 범위 구분.',
      222:'수치적 FULL/Dense 동일 문제와 incumbent registry, 현재1003.501s prefix, HOLD 연구 기준.'}
    for p in prs:lines.append(f"| [{p['number']}]({p['url']}) | `{p['headRefOid']}` | {scopes[p['number']]} |")
    lines+=['','HEAD 정정 필요 없음. PR222 위 별도 Research worktree만 변경했다. 다른 PR을 cherry-pick하지 않았다.',
       'PR202/203/187은 Git fetch된 원본 보고서 및 코드를 읽었다. Source18r helper 포함관계는 현재 전체 FULL CSR/domain과 저장 slice를 독립 재대조했다.']
    (OUT/'PR209_PR211_PR214_METHOD_REUSE_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    math_text='''# Stabilized Lagrangian Dual 수학 계약

원본 P1은 min rho_max, ObjCon0, rho∈[0,1]이다. 저장 binary64 CSR/RHS를 정확한 유리수로 해석한다. 선택된 선로행은 원본 injection/response binding 등식으로 소거하여 rho ≥ b_k + Σ_m a_kmᵀx_m를 얻는다. 부호와 상수는 독립된 세 구현으로 재도출했다. Pdis 양/ Pch 음 injection과 correction 및 고정 AIDC는 모두 원본 행에 들어 있다.

각 X_m은 FULL의 해당 차량 arc/charge_mode/SOC/Pch/Pdis/Q 열과 비영 support가 그 차량에만 속하는 모든 행, 원래 Bounds/정수 타입을 그대로 유지한다. 임의 FULL 정수해의 차량 사영은 X_m에 포함된다. Initial/terminal SOC,96 energy rows,97SOC, PCS16, charge/discharge 배타성, 원래 flow/terminal 의미와 이동 ETA/energy를 제거하지 않는다. FULL의 mixed injection 정의 및 다른 Grid 행을 차량별로 복제하지 않는다.

추가 결합행은 원래 sense가 <이면 그대로, >이면 부호를 뒤집어 g_j≤0으로 정규화한다. Equality는 비음수 부등식 승수에 넣지 않는다. w≥0,Σw=1 및 μ≥0에 대해 L=b_w+Σμg_const+Σ_m inf_Xm (a_wm+Σμg_jm)ᵀx_m 이고, L≤FULL optimum이다. mu g≤0이므로 결합 제약을 완화한 목적값은 원래 rho를 넘지 않는다. Σw=1을 정확히 유지해 남는 rho 최소화항은0이다. 합이 달라지는 일반화라면 min_{rho∈[0,1]}(1−Σw)rho를 포함해야 하며 본 구현은 그러한 입력을 거부한다.

Native 목적계수 ĉ와 exact c의 차이 δ=c−ĉ에 대해 E_min=Σmin(δ_j l_j,δ_j u_j)를 exact 계산한다. 원래 유한 차량 Bounds만 사용하며 L_m=Native global minimization bound+E_min이다. Incumbent Objective는 LB로 쓰지 않는다. GLOBAL bound의 유효성은 원래 Gurobi numerical contract에 의존하며 exact B&B proof trace가 아니다. 정수 영역 포함 및 transport 증명과 이 Numerical trust 단계를 분리한다.

A0는 PR209의 동일 객관계수와 현재 FULL slice를 재대조한 뒤 네 기존 인증값을 재사용했다. A1은 raw Pi를 거부하고 별도 sign-cone vector의 finite-box weak duality 값을 재검산한 초기가격이다. A2는 실제 signed critical response의 다시간 sparse objective, A3는 전압·변압기 승수를 포함한다. weight simplex의 projected ascent와 L2 trust radius.15, μ∈[0,100] clipping, 고정 선택/seed0, exact normalization, 중복 SHA,6 evaluations 및360s cap을 사용한다.

업데이트 점은 numerical local incumbent를 사용한 휴리스틱 후보 생성이다. OPTIMAL이어도 exact mathematical subgradient라고 주장하지 않는다. 미완료 incumbent는 global bound 또는 exact oracle로 쓰지 않는다. 두 stabilized 후보는 서로 다른 물리 단위를 가진 μ의 비정규화 gradient 때문에 너무 큰 가격을 만들었고 인증값이 크게 약화됐다. 이 negative result를 보존하며 같은 예산의 자동 추가 탐색은 없다. Scale-aware coupling stabilization의 효과는 이번에 측정하지 않았다.

원래 helper에 대한 정확한 equality 승수 repair도 Native0으로 수행했다. helper h의 +1 pivot equality 승수에 현재 d_h를 더하고 residual에서 d_h A_h를 빼면 해당 helper residual이0이 된다. 원래 acyclic definition graph를 따라 반복해 모든 injection/response helper residual과 rho residual이 exact0, 물리 목적계수 및 상수가 decomposition과 정확히 같음을 검증했다. 원래 무한 Bound는 바꾸지 않았다. `EXACT_HELPER_MULTIPLIER_REPAIR.json`에 실제 승수와 검산을 저장했다.
'''
    (OUT/'LAGRANGIAN_DECOMPOSITION_MATH_KO.md').write_text(math_text,encoding='utf-8')
    proof='''# Multi-period Route–SOC Support 포함관계 증명

차량별 FULL 사영을 포함하는 전체96-slot 정수 물리 X_m을 사용한다. 중요한 창 W의 원본 signed thermal response로 S_W(x_m)=Σ_{t∈W} c_tᵀy_t를 만들고, X_m 전체에서 max S_W를 푼다. 시간창 밖 물리, 이동 ETA/energy, 모든 SOC 및 terminal, PCS, mode, 접속, charging rebound 경로도 그대로 남는다. 차를 부분 ESS로 분할하거나 경로를 제한하지 않는다.

최대화의 Numerical global upper bound β와 E_max=Σmax((c−ĉ)_j l_j,(c−ĉ)_j u_j)를 exact 계산하면 U=β+E_max≥max_Xm S_W이다. 따라서 임의 FULL integer projection은 S_W≤U를 만족한다. Incumbent maximizing Objective는 상한으로 쓰지 않는다. Solver B&B numerical contract는 exact 정수 trace와 구분한다.

원본→Compact alias x=offset+Tz를 정확한 Fraction으로 대입한다. ĉ_cut−c_cut의 원래 proved Compact box support upper error를 RHS에 더하고 binary64 RHS를 +∞ 방향으로 반올림한다. 따라서 native cut은 원래 유효 부등식의 바깥 relaxation이다. 모든 K48 행/목적/Bounds를 unchanged prefix로 두고 이 cut만 추가하면 FULL integer projection⊆strengthened relaxation⊆K48 relaxation이다. Integer support가 source의 어떤 FULL 해라도 제거하면 기각한다.

현재 Root는 PR214 BASE 원시 점을 변조 없이 Original 물리 좌표로 복원했다. 응답 helper 값 전부를 저장한 FULL 전력 가능해라고 주장하지 않는다. ORIGINAL_ROOT_POINT는 mapped_columns의 물리/rho 값만 권위이며 다른 helper 좌표는 미복원0이다. Window29–32와27–34를 critical dual31/line.l10 phaseA 및 signed contribution/mode/route/SOC 패턴으로 선정했다. 실제 important support solve 두 개만 실행했고, 일반 단일-slot SOC 행을 복제하지 않았다.

두 인증 상한은 실제 Root support보다 컸다. 따라서 실제 위반 cut0, 채택 cut0, strengthened model/LP NOT_RUN이다. 잠재 포함관계 정리와 실제 강화 효과를 구분하며 신규 cut 또는 Global LB를 발명하지 않는다. 다른 방향/시간창의 hull 효과는 미측정이다.

PR222의 등록된 검증 Moving incumbent 전부(1개)를 실제 current FULL validator로 재검증하고 각 support inequality에 exact 대입했다. 이 witness 검사는 보편적 정수 유효성 증명의 대체가 아니다. 작은4-slot fixture는 두 ETA2 route와16mode pattern, 합32개의 정수 분기를 전수 열거하고 각 연속 power/SOC polytope를 SciPy LP로 검사했다. 각 route는 원래 형태의 flow/connection/mode/energy/terminal physics를 갖는다. Universal gross-power upper4는 한 차량 경로와 mode의 포함관계로 증명되며 LP mixture39/8가 위반함을 exact 확인했다. Fixture는 actual May01 cut 효과나 scientific constants 변경이 아니다.
'''
    (OUT/'MULTIPERIOD_HULL_VALIDITY_PROOF_KO.md').write_text(proof,encoding='utf-8')
    # Common code is reusable; stage-specific SHA/anchor and full inclusion must be newly supplied.
    write(OUT/'M1_M2_INTERFACE_FIXTURES.json',dict(binding=bound,B2_accepted=False,M1_heavy_calls=0,M2_heavy_calls=0,
        status='INTERFACE_FIXTURE_ONLY_NO_INTEGRATION_CANDIDATE',required_stage_fields=['source','case','matrix','domain','objective','fixed_AIDC_anchor'],
        stage_bindings_rejected_when_foreign=True,numeric_B2_bound_transfer_allowed=False,
        fixed_A1_A2_actual_matrices_NOT_RUN=True,reason='No certified material B2 gain; do not integrate or execute M1/M2 heavy optimization.'))
    def display(v):return '—' if v is None else f'{v:.12g}' if isinstance(v,(int,float)) else str(v)
    table=['| Algorithm | Valid Global LB | Delta vs K48 | Global Gap (%) | Native seconds | Peak RAM GiB | Verdict |',
           '|---|---:|---:|---:|---:|---:|---|']
    for p in rows:table.append('| '+' | '.join(display(p[k]) for k in p)+' |')
    support_table=['| Unit / window | Root support | Certified upper | Violation | Adopted |','|---|---:|---:|---:|---|']
    for p in supports:support_table.append(f"| {p['unit']} / {p['start']}–{p['start']+p['size']-1} | {p['root_support']:.12f} | {float(F(p['Global_Upper_Bound'])):.12f} | {p['root_violation']:.12f} | false |")
    regression=read(OUT/'FULL_REGRESSION_RESULT.json') if (OUT/'FULL_REGRESSION_RESULT.json').exists() else None
    text=f'''# V42 B2 May01 대안 Global LB 연구 최종 검토

두 방법의 **인증된 Global LB 개선은0**이다. 기존 K48 `{final['LB']}`와 현재 Original FULL 재검증 Moving UB `{current['FULL_UB']}`를 보존한다. Global Gap `{final['gap_percent']:.9f}%`,3% 목표 미달이며 M1/M2 통합 후보를 채택하지 않는다. A는 유효하지만 비실질, B는 실제 Root 위반이 없어 신규 Global LB를 계산하지 않았다. NOT_RUN을0이나 K48로 채우지 않았다.

{chr(10).join(table)}

K48 Native360.083s는 기존 PR211 K32/K48 연구 비용이며 새 비용에 합산하지 않는다. 새 A {native_a:.9f}s + B {native_b:.9f}s = {native_a+native_b:.9f}s,22 Native calls, Worker1/Threads1이다. A6 weight evaluations 중 A0 네 Bound는 동일성 검증 후 cached reuse, 실제20 calls; B support2 calls와 strengthened LP0 calls다. 현재 May01 prefix1003.5010001659393s에 새254.02099990844727s를 연결한 유효 누적1257.521...s로1800s 안이다. 상세 정확한 binary64 합은 원장에 있다. May02943.4019999504089s, PR221 별도 명시 승인 fresh 연구1790.1970002651215s는 보존한다. PR221 session을 다시 열거나 사용시간을 초기화하지 않았다. 이번 지시는 PR222 current campaign Case/원장에 대한 추가 연구이므로 해당1003.501s prefix에 이번 사용량을 차감한다. 다른 과거 연구가 같은1800s session이라고 가정해 합산하지 않으며 그 별도 승인 근거는 원본 PR221 ledger의 historical_before_fresh/same_fresh_used다.

## 실제 Source·Case·숫자 권위

PR222 Git HEAD12594e281bb89611331950f11f775a2612d3cb48 위 독립 research worktree다. 실제 original execution Source SHA `{bound['source_sha']}`, physical Source18r Git497609b46faa14ea7e32a9483a333ab32fd264ef, current Case `{bound['case_sha']}`, FULL Matrix `{bound['matrix_sha']}`, named Domain `{bound['domain_sha']}`, Objective `{bound['objective_sha']}`와 연결했다.

과거 Case34c0efff...와 현재 metadata Caseb6577cef...는 같지 않다. 전체 FULL CSR/domain, Dense CSR/domain, 원래 route/battery/고정 AIDC 수치 효과와 current FULL replay의 수치 모델 동일성으로 K48를 연결했다. 다른 Case의 숫자를 임의 이전하지 않았다. 원본 Input/Source packet SHA를 execution Source SHA로 잘못 이름 붙였던 초기 metadata는 후속 Native0에서 정정했고 old packet digest 및 원래 binding은 `TRIAL_ORIGINAL_BINDING.json`에 보존했다. 모델/계수/Bounds/승수/Runtime 변경은0이다.

현재 FULL moving replay는 등록된 incumbent1개 모두 PASS, 정확한 Binary pattern 및 원본 Validator tolerance를 유지했다. MESS03 STA08→IDC06(4/6/7), IDC06→IDC05(64/66/66), IDC05→IDC01(77/79/79), 이동 에너지66.66442632042374kWh; MESS01/02/04는 원래 STA01/STA12/STA06 STAY다. 이 UB/경로는 수정하지 않았다. restricted incumbent를 FULL UB로 승격하지 않았다.

## 논문 질문15개에 대한 답

1. K48 정체의 직접 관측은 PR214 BASE LP objective0.4649848699754816가 PR211 MIP Global Bound와 사실상 같고, 이번 A3도 같은 수치를 재현했다는 것이다. 이번 관측에서 더 많은 B&B 시간의 효과를 보이지 않았다. exact full formulation ceiling이나 전체 hull ceiling은 미증명이다.
2. LP의 네 차량은 원본 DAG의 fractional arc/node 흐름과 fractional charge modes로 여러 site/path를 동시에 표현한다. Mode에 따라 같은 시점 charge/discharge 혼합도 가능하다. 실제 root census는 CSV에 저장했다. 중요한 MESS03은29/30에 약297.455kW 방전,31에300kW 방전하며 SOC675.565→597.225→518.947→440kWh로 내려가고32 이후 분수 recharge/travel 조합을 보인다. 이 패턴 자체를 유일한 gap 원인이라고 단정하지 않는다.
3. Lagrangian은 각 차의 전체96-slot 원래 integer arc/mode 및 SOC/P/Q/PCS/ETA/energy를 하나의 X_m으로 보존한다. 차량을 조각 ESS로 나누거나 route를 고정하지 않는다.
4. 공유 injection 정의는 exact 소거했고 grid voltage/thermal/transformer/shared electrical coupling은 해당 승수로 dualize하거나 생략했다. 원래 electrical row signs/constants를 반영했다.
5. FULL 사영⊆X_1×...×X_4이고 w simplex 및 μg≤0으로 원래 objective 아래의 Lagrangian값을 얻는다. 네 minima의 유효 global lower bound와 exact constant/rounding 보정만 합친다.
6. A0의16개1/16 uniform rows, A1의 두 critical thermal rows, A2의4-slot sparse responses, A3의 추가 voltage/transformer 가격을 비교했다. 마지막 stabilized 후보들은 크게 약했고 best candidate는 A3로 유지됐다. best와 last를 혼동하지 않는다.
7. 핵심은 slot31 line.l10 phaseA facet1 w≈0.8859562083, line.l52 phaseA facet1 w≈0.1140437917이다. 추가 전압 하한 row[31,383] μ≈0.00022899886 및 transformer_kVA[31,212,6] μ≈1.07407414e-7가 A3에서 중요했다. 실제 원본 row/phase/time과 exact prices는 catalog/history에 있다.
8. B는 여러 시간의 signed grid service를 전체96-slot 정수 운전영역에서 support 최대화하므로 ETA/energy/terminal/rebound와 단일 route를 함께 고려한다. 원래 SOC balance 합산이나 기존 single-slot 가용성 행 복제가 아니다.
9. 이번 두 방향에서는 실제 위반을 확인하지 못했다. 아래 certified upper보다 root support가 작아 두 후보 모두 기각했다.
10. 임의 FULL integer projection이 X_m에 있고 U≥max_Xm S이므로 cut을 만족한다. Exact alias/outward rounding과 작은32분기 fixture 및 current incumbent replay는 각각 별도 검사다. incumbent 만족만으로 보편적 유효성을 주장하지 않는다.
11. 새 LB 개선은 없었다. A3의 현재 두 선로와 grid 가격을 individual integer supports가 재현했고, 선택된 B signed service는 integer feasible support 안이었다. 이 limited experiment로 모든 가능한 Lagrangian/hull 방향을 기각하지 않는다.
12. 실제 Native/memory는 비교표 및 resource JSON에 있다. A2 MESS02 직전에 외부 Known/Unknown pytest가 Gurobi를 로드해 prelaunch gate가 차단했다. 종료를 관측한 후 이미 완료된 calls를 exact/objective/ledger 재검산하여 재호출 없이 미실행 차만 이어갔다. 다른 worker를 중지하지 않았다. 외부 test가 이전 호출 중 실제 Optimize했는지는 증명하지 못하므로 continuous worldwide zero-overlap 주장도 하지 않는다.
13. 최종 Global Gap은13.864737209%로 개선0, target LB는 {current['FULL_UB']*.97:.12f} 이상이다. 원래 FULL UB replay가 성공한 같은 수치 Case에 대해서만 계산했다.
14. 여기 X_m은 FULL 사영을 포함하는 무제한 original route domain이다. Restricted pool/local branching의 ObjBound를 사용하지 않는다. exact inclusion/transport는 PASS, numerical Solver bound 계약은 별도이며 exact B&B proof trace는 아니다.
15. M1/M2는 각각 고정 A1/A2 AIDC anchor, RHS/Response/MESS context 및 Source/Case/Matrix/Objective SHA가 새로 필요하다. Stage mismatch와 bound transfer를 fixture로 거부한다. 실제 M1/M2 Matrix/Heavy0; B2 material gain이 없어 후속 통합도 기각한다.

{chr(10).join(support_table)}

## 검증·실행 한계

Native0 identity, original slice/full coefficient mapping, current FULL UB replay, exact weak-duality recalculation, exact original equality-multiplier repair, outward support transport, small exhaustive fixture 및 독립 최종 인증을 저장했다. 원시 solver logs/Point/Bound/CSR/data/parameters/resource gate를 모두 보존했다. Actual/Full96/OpenDSS fresh validation, 전체May31 restart, B1/B3 최적화는 실행하지 않았다. 기존 HOLD와 Supervisor disabled는 유지했다.

신규 집중 tests는 실행 전10개 PASS, 이후 추가 quarantine/부호 gate 포함12개 PASS다. 전체 회귀 최초 collection은 기존 missing tmp/v29_projection_cache_draft/original_loader.py와 동명test_certificate 충돌로 중단됐다. importlib 모드로 계속한 전체 회귀 결과는 `FULL_REGRESSION_RESULT.json` / `FULL_REGRESSION_CONTINUED.log`에 실제 pass/fail/skip/collection error를 기록한다. Gurobi optimize/presolve가 필요한 test는 budget 보존용 guard로 SKIP하며 PASS로 세지 않는다. 전체 suite PASS를 주장하지 않는다.

검증 수준: A Level1(유효 Numerical Global LB), Level2/3/4 FAIL. B Native0/support validity만 PASS, 위반 cut 및 신규 LB 없음. 알고리즘 둘 다 M1/M2 통합용 material acceptance REJECT다. 계산시간 확대나 K64/K96 전환은 이번 negative result의 정당한 후속이라고 가정하지 않는다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    (OUT/'README.md').write_text('# B2 Global LB 대안 연구\n\n[한국어 최종 검토](FINAL_REVIEW_KO.md) · [Lagrangian 증명](LAGRANGIAN_DECOMPOSITION_MATH_KO.md) · [다기간 support 증명](MULTIPERIOD_HULL_VALIDITY_PROOF_KO.md)\n',encoding='utf-8')
    print('REPORTS_WRITTEN',native_a,native_b)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['bind','repair','reports'])
    args=p.parse_args();dict(bind=bind_source_metadata,repair=helper_repair,reports=reports)[args.phase]()
