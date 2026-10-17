"""Measured May02 pilot report; publish only the explicitly authorized PR doc."""
from pathlib import Path
import subprocess,json
from v44.common import read,record,verify,atomic,now


def optional(path):return read(path) if Path(path).exists() else {}


def summarize(root):
    root=Path(root);a=root/'A2';output=a/'OUTPUT'
    trace=optional(output/'PHASE_I_TRACE.json').get('trajectory',[])
    model=[];kappa=[];runtime=0.;peak=[];barrier=0.
    for p in (output/'PHASE_I').glob('S*/NATIVE_RESULT.json'):
        value=read(p);runtime+=value.get('native_seconds',0.) or 0.;peak.append(value.get('peak_RSS_bytes') or 0)
        barrier+=value.get('BarIterCount',0.) or 0
        identity=optional(p.parent/'MODEL_IDENTITY.json')
        if identity:model.append({k:identity.get(k) for k in ('rows','cols','nnz')})
        quality=optional(p.parent/'R024_NUMERICAL_ACCEPTANCE.json') or optional(p.parent/'R021_NUMERICAL_ACCEPTANCE.json')
        for attempt in quality.get('attempts',[]):
            value=(attempt.get('quality') or {}).get('Kappa')
            if isinstance(value,(float,int)):kappa.append(value)
    profile=optional(output/'R024_PHASE_COMPONENT_PROFILE.json')
    if profile.get('peak_RSS_bytes'):peak.append(profile['peak_RSS_bytes'])
    return dict(root=str(root),status=optional(root/'RESULT.json').get('status','RUNNING'),A2=optional(a/'RESULT.json'),
        ledger={k:optional(a/'NATIVE_RUNTIME_LEDGER.json').get(k) for k in ('measured_Native_Runtime','wall_seconds','inflight')},
        maximum_rows=max((r['rows'] for r in model),default=None),maximum_columns=max((r['cols'] for r in model),default=None),
        maximum_nnz=max((r['nnz'] for r in model),default=None),LP_Native_seconds=runtime,peak_RSS_bytes=max(peak,default=None),
        maximum_Kappa=max(kappa,default=None),Barrier_iterations=barrier,phase_trace=trace,
        Full_PhaseI_zero=optional(output/'PHASE_I_ZERO_CERTIFICATE.json'),P1=optional(output/'P1_RESULT.json'),
        component_profile=profile,M2=optional(root/'M2/RESULT.json'),final=optional(root/'RESULT.json'))


def write_report(case):
    from .operations import OPS,PERMIT
    case=Path(case);worktree=Path(__file__).resolve().parents[1]
    old=summarize(case.parent/'attempt005');new=summarize(case)
    baseline=read(OPS/'R024_PASS_AND_M1_PRESERVATION_BASELINE.json');verify(baseline['files'])
    output=case/'A2/OUTPUT';progress=optional(output/'R024_ADAPTIVE_PROGRESS.json')
    pricing=[read(p) for p in (output/'PHASE_I').glob('S*/PRICE/PRICING_RESULT.json')]
    explored=set(k for p in pricing for k in p['class_ids'])
    admission=optional(case/'FRESH_A2_RESTART_ADMISSION.json')
    value=dict(UTC=now(),revision='v44_recovery_r024',attempt=case.name,baseline=old,current=new,
        adaptive_progress=progress,unique_priced_classes=len(explored),pricing_rounds=len(pricing),
        new_A1_M1_Native_calls=0,all_existing_PASS_and_M1_bytes_unchanged=True,
        Native_zero_restart_admission=admission,permit=record(PERMIT))
    atomic(OPS/'R024_MEASURED_COMPARISON.json',value)
    text='# May02 B3 A2 Adaptive Multi-Column Pricing r024\n\n'
    text+=f"기록 UTC: {value['UTC']}; Case: {case}; PR: https://github.com/BeaverVillage/MobileESS/pull/233\n\n"
    text+='사용자 지시로 r022 attempt005를 Native 비실행 경계에서 중단했다. 667호출/567.3849945068359초와 Raw/Trace/로그/원장은 보존했고 중단 분류는 USER_REQUESTED_ALGORITHM_REVISION_STOP이다. 마지막 행 검사 완료 Phi는0.0011475893025559441이었다. 기존13 PASS와 완료된 May02 B1 A1 및 B3 M1은 SHA 검증하고 재최적화하지 않는다.\n\n'
    text+='r023의 정확한 sparse 재조립/행 생성/활성행 대응/Full Phi/prior inclusion/물리옵션 및 원래 raw primal/dual 인증을 상속한다. 과학 원본은 그대로이며 별도 봉인 r024 어댑터에서 Phase I 탐색과 선택만 바꿨다. P1 본문은 원본과 동일하다. 허용치 Full Phi1e-8, 원본 잔차1e-6, 독립 Gap0.5%, M2 및 Actual/Fresh 정책은 유지한다.\n\n'
    text+='기존 상위 전체16+이동가능16 클래스 휴리스틱에 최소8개 미탐색/오래 미탐색 클래스를 순환 추가한다. 행 검사 완료 Full Phi의 실제 감소율이 연속2회15% 미만이면 탐색을 확대하고3회이면 전체 Eligible 탐색을 수행한다. 전체 탐색 뒤 한 라운드 쉬고 필요 시 다시 넓히며, 감소가 좋아도5회 주기의 전체 탐색으로 굶는 클래스를 방지한다. 모든 LP마다 전체 탐색하지 않는다. 실제 eligible 클래스 ID, 현재/누적 coverage와 각 클래스 oracle/physical recovery 영수증을 남긴다. 전체 Class 탐색은 모든 물리 옵션/혼합 LP의 Pricing Closure와 다르다.\n\n'
    text+='모든 생성 후보는 원래 Native Query, 원본 물리 membership/local primal/exact coupling/현재 원시 dual의 정확한 음의 RC 검증을 통과한다. 추정 영향도와 음의 가격 강도를 함께 쓰고 클래스/사이트/시간대/종류 다양성을 보상하며 GPU시간 중복을 감점하는 다중열 배치를 선택한다. STAY/Migration이 모두 있으면 양쪽 후보를 포함하되 어느 동작도 실제 해에 강제하지 않는다. 배치는 휴리스틱이며 feasible/optimal 인증이 아니다. 원본 전체 모델에서 재최적화하고 신규 전압 위반 및 동일 원본 행/동결 가중치의 Full Phi 변화를 확인한다.\n\n'
    text+='각 행 검사 완료 후 R024_ACTUAL_FULL_PHI_FEEDBACK.json에 이전/현재 Full Phi, 실제 감소율, 이전 배치/RC, 전압 행·slot/node/phase·원본 선형 단위 부족량·현재 AIDC resource 값·고정 M1 P/Q·LP Native 시간을 남긴다. A-stage slot24는 M-stage slot0에 대응한다. 전압 민감도와 GPU/Deadline/STAY/Migration 여유는 R024_VIOLATION_GUIDANCE.json에 탐색 순위용으로만 저장한다. 선형 행 부족량을 AC pu로 바꾸어 보고하지 않는다. Dual 변화는 진단만 하며 안정화 dual은 추가하지 않았다.\n\n'
    text+='기존의3회 미소 감소 뒤 새 batch를 재최적화하기도 전에 종료하던 분기는 확대 배치를 실제로 평가하는 진단으로 바꿨다. 모든 호출은 동일5400초 예산 안에 남는다. 후보가 없다고 불가능을 주장하지 않고 NOT_CERTIFIED로 분류한다. 고정 M1의 LP 불가능성은 전체 원본 LP/정확한 완전 Pricing/엄밀한 양의 Phase I 하한 없이는 인증하지 않는다.\n\n'
    text+='| 측정 | 중단 r022 attempt005 | 새 r024 |\n|---|---:|---:|\n'
    for label,before,after in [
        ('전체 A2 Native 초',old['ledger']['measured_Native_Runtime'],new['ledger']['measured_Native_Runtime']),
        ('전체 A2 Wall 초',old['ledger']['wall_seconds'],new['ledger']['wall_seconds']),
        ('최대 Master 행',old['maximum_rows'],new['maximum_rows']),('최대 변수',old['maximum_columns'],new['maximum_columns']),
        ('최대 측정 RSS bytes',old['peak_RSS_bytes'],new['peak_RSS_bytes']),
        ('누적 Pricing Class','기존 초기37LP 시점35/138; 종료 시점은 원본기록',len(explored))]:
        text+=f'| {label} | {before} | {after} |\n'
    text+=f"\n새 Native0 시작 admission: {bool(admission.get('PASS'))}; A1/M1 새 Native0회; M1 plan SHA: {admission.get('M1_plan_sha','준비중')}. Full Phase I: {bool(new['Full_PhaseI_zero'].get('PASS'))}; P1: {bool(new['P1'].get('PASS'))}; A2: {new['A2'].get('classification','RUNNING')}; Gap: {new['A2'].get('certified_gap','미인증')}; M2: {new['M2'].get('status','미실행')}; Actual/Fresh: {new['final'].get('PASS','미완료')}.\n\n"
    text+='B1 A1/A2와 B3 A1/A2 공통 scope이며 실제 캠페인은 B1 A1 및 B3 A2에서 사용한다. 이후 미실행 Case에도 현재 A2 PASS 조건 없이 적용한다. A2 인증 후 기존 K48_M2→M2→Actual→독립 Fresh96으로 이어진다. 시간별 Codex 점검과 케이스 오류 격리·다음 날짜 진행 정책을 유지한다.\n\n'
    text+='검증·배정 영수증: OPS/R024_CHANGE_AND_VALIDATION.json, R024_SEALED.json, RECOVERY_R024_EXECUTION_PERMIT.json, R024_CURRENT_A2_STOPPED.json, R024_FRESH_A2_RESTARTED.json, 새 Attempt/PARENT_VERIFICATION/R024_PARENT_COMPATIBILITY.json. 미완료 인증과 미측정 전체 A2 개선은 주장하지 않는다.\n'
    target=worktree/'docs/v44/MAY02_B3_A2_ADAPTIVE_MULTI_COLUMN_PRICING_KO.md';target.write_text(text,encoding='utf-8')
    return target,value


def publish(case):
    """User explicitly requested commit/push to Draft PR233 in pasted text."""
    from .operations import OPS
    path,value=write_report(case);worktree=Path(__file__).resolve().parents[1]
    relative=str(path.relative_to(worktree));branch='codex/v44-may01-07-prestart'
    def git(*args):return subprocess.check_output(['git',*args],cwd=worktree,stderr=subprocess.STDOUT,text=True,encoding='utf-8').strip()
    if git('status','--porcelain','--',relative):
        git('add','--',relative);git('commit','--only','-m','Record measured May02 B3 r024 A2 outcome','--',relative)
    # Ordinary fast-forward push; an external remote change is never forced.
    pushed=git('push','origin','HEAD:refs/heads/'+branch)
    receipt=dict(UTC=now(),PASS=True,commit=git('rev-parse','HEAD'),PR='https://github.com/BeaverVillage/MobileESS/pull/233',report=record(path),push=pushed,
        completed_case_PASS=value['current']['final'].get('PASS'),existing_PASS_bytes_preserved=True)
    atomic(OPS/'R024_REPORT_PUBLISHED.json',receipt)
    return receipt
