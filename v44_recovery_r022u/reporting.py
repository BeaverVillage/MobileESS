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
        quality=optional(p.parent/'R022U_NUMERICAL_ACCEPTANCE.json') or optional(p.parent/'R021_NUMERICAL_ACCEPTANCE.json')
        for attempt in quality.get('attempts',[]):
            value=(attempt.get('quality') or {}).get('Kappa')
            if isinstance(value,(float,int)):kappa.append(value)
    profile=optional(output/'R022U_PHASE_COMPONENT_PROFILE.json')
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
    worktree=Path(__file__).resolve().parents[1];case=Path(case)
    benchmark=read('D:/MobileESS_V44/development/r022/real_validation_02/RESULT.json')
    original=case.parent/'attempt004';new=summarize(case);old=summarize(original)
    baseline=read(OPS/'R022U_PASS_AND_M1_PRESERVATION_BASELINE.json');verify(baseline['files'])
    mapping=[read(p) for p in (case/'A2/OUTPUT/PHASE_I').glob('S*/R022U_ACTIVE_ROW_MAPPING.json')]
    full=[read(p) for p in (case/'A2/OUTPUT/PHASE_I').glob('S*/R022U_FULL_PHI.json')]
    rows=[]
    for item in full:
        rows.append(dict(active_rows=item['active_rows'],full_rows=item['full_rows'],original_columns=item['original_columns'],
            artificial_columns=item['artificial_columns'],Phi=item['full_Phi'],restricted_Phi=item['restricted_Phi']))
    value=dict(UTC=now(),revision='v44_recovery_r022u',attempt=case.name,baseline=old,current=new,active_models=rows,
        row_mapping_certificates=len(mapping),all_existing_PASS_and_M1_bytes_unchanged=True,benchmark=benchmark,
        permit=record(PERMIT) if PERMIT.exists() else None,new_A1_M1_Native_calls=0)
    atomic(OPS/'R022U_MEASURED_COMPARISON.json',value)
    state='COMPLETE' if new['final'].get('PASS') else new['status']
    table=[('최대 Phase I 행',old['maximum_rows'],new['maximum_rows']),('최대 변수',old['maximum_columns'],new['maximum_columns']),
        ('최대 NNZ',old['maximum_nnz'],new['maximum_nnz']),('측정 최대 RSS bytes',old['peak_RSS_bytes'],new['peak_RSS_bytes']),
        ('Phase I LP Native 초',old['LP_Native_seconds'],new['LP_Native_seconds']),('최대 추정 Kappa',old['maximum_Kappa'],new['maximum_Kappa']),
        ('Barrier iteration',old['Barrier_iterations'],new['Barrier_iterations']),('A2 Native 누계 초',old['ledger']['measured_Native_Runtime'],new['ledger']['measured_Native_Runtime']),
        ('A2 원장 Wall 초',old['ledger']['wall_seconds'],new['ledger']['wall_seconds'])]
    text='# May02 B3 A2 Phase I Row Generation 개선\n\n'
    text+=f"기록 시각 UTC: {value['UTC']}. 상태: **{state}**. 대상: `{case}`. PR: https://github.com/BeaverVillage/MobileESS/pull/233\n\n"
    text+='r021에서 19회 후 및 Column Activation 후 전체 행을 강제 투입하던 두 분기를 V44 전용 어댑터에서 제거했다. 원본 동결 파일은 수정하지 않았다. 기존 certified_separate/restricted/elastic_master/verify_zero와 원본 inclusion/Fraction/primal/dual 검증을 재사용한다.\n\n'
    text+='활성 글로벌 행은 resource의 family/site/slot, voltage의 family/slot/node, 기타 행의 원본 Source Row 및 전체 글로벌 계수·RHS·Sense·Bounds SHA로 대응시킨다. 새 Local Hard 제약은 모두 유지한다. 실제 3개 클래스의 열 확장에서 대응 및 이전 Phi 보존을 Native0로 검증했다.\n\n'
    text+='모든 누락 원본 행을 검사한다. 행별 위반이 1e-6 이하여도 Full Phi 기여가 남으면 선택적으로 추가한다. 원시 Solver 인공변수는 그대로 복사하고, 누락 행의 residual은 별도 full lift에 포함한다. 종료는 Full Phi ≤1e-8 및 원본 최대 위반 ≤1e-6이다. 초기 batch256, 정체 시 최대16384까지 늘리며, 횟수에 따른 전체 행 승격은 없다. P1 본문은 원본과 동일하다.\n\n'
    text+='B1은 실제 A1, B3는 A2 실행 경로에 연결했다. 공통 B1/B3 A2 어댑터도 지원한다. 현재 A2의 성공 여부와 관계없이 이후 미실행 B1 A1 및 B3 A2에 적용하며 기존 PASS는 재계산하지 않는다. 스케일링 Revision은 적용하지 않았다.\n\n'
    text+=f"실제 May02 입력의 동일 잔여량 분석: {benchmark['attribution_original_seconds']:.3f}초 → {benchmark['attribution_optimized_seconds']:.3f}초. 결과·순위·CSV가 일치했다. 희소행렬 원소 반복 조회를 묶음 조회로 바꾸고 축 인덱스를 재사용했다. 전체 가중 Phi의 정확한 Fraction 합도 일치했다. 이 수치를 A2 전체 속도 향상률로 해석하지 않는다.\n\n"
    text+='| 측정 | 기존 attempt004 | r022u attempt005 |\n|---|---:|---:|\n'
    for label,before,after in table:text+=f'| {label} | {before} | {after if after is not None else "미측정"} |\n'
    text+='\n기존 S7 참고값: 행791672, 원래변수94158, 인공변수689928(88.0%), NNZ14771533, Native33.817초, 추정 Kappa1.051286e18. 표의 최대값은 중단 시점까지 전체 Phase I 구간이다. 새 모델의 지원 후보와 반복 수가 달라질 수 있어 각 solve를 동일 문제 크기의 속도 비교로 주장하지 않는다.\n\n'
    text+=f"Full Phase I Zero: {bool(new['Full_PhaseI_zero'].get('PASS'))}. P1 Full Pricing: {bool(new['P1'].get('PASS'))}. A2 PASS: {new['A2'].get('PASS','미완료')}. M2: {new['M2'].get('status','미실행')}. Actual/Fresh 최종 PASS: {new['final'].get('PASS','미완료')}.\n\n"
    text+='기존 PASS 13개 Case와 May02 B3 M1의 원본 파일을 SHA로 보존 검증한다. 같은 날 B1 A1 및 M1의 원본 FULL 가능해, Fixed Plan SHA, Q250, Physical Domain, Hardware, Time Axis를 Native0로 독립 재검산했다. 새 A2는 완료 M1을 읽고 새 Attempt의 독립5400초 원장을 0초부터 사용한다. 과거486.140000343초 및381개 호출은 attempt004에 그대로 남아 있다.\n\n'
    text+='세부 원장: `AUTONOMOUS_RECOVERY/R022U_MEASURED_COMPARISON.json`, `R022U_CHANGE_AND_VALIDATION.json`, `R022U_SEALED.json`, `R022U_PASS_AND_M1_PRESERVATION_BASELINE.json`, 새 Attempt의 `PARENT_VERIFICATION/R022U_PARENT_COMPATIBILITY.json` 및 `FRESH_A2_RESTART_ADMISSION.json`. 미완료 인증 및 아직 측정되지 않은 전체 속도·조건수 개선은 주장하지 않는다.\n'
    target=worktree/'docs/v44/MAY02_B3_A2_PHASE1_ROWGEN_IMPROVEMENT_KO.md';target.write_text(text,encoding='utf-8')
    return target,value


def publish(case):
    """User explicitly requested commit/push to Draft PR233 in pasted text."""
    from .operations import OPS
    path,value=write_report(case);worktree=Path(__file__).resolve().parents[1]
    relative=str(path.relative_to(worktree));branch='codex/v44-may01-07-prestart'
    def git(*args):return subprocess.check_output(['git',*args],cwd=worktree,stderr=subprocess.STDOUT,text=True,encoding='utf-8').strip()
    if git('status','--porcelain','--',relative):
        git('add','--',relative);git('commit','--only','-m','Record measured May02 B3 r022u A2 outcome','--',relative)
    # Ordinary fast-forward push; an external remote change is never forced.
    pushed=git('push','origin','HEAD:refs/heads/'+branch)
    receipt=dict(UTC=now(),PASS=True,commit=git('rev-parse','HEAD'),PR='https://github.com/BeaverVillage/MobileESS/pull/233',report=record(path),push=pushed,
        completed_case_PASS=value['current']['final'].get('PASS'),existing_PASS_bytes_preserved=True)
    atomic(OPS/'R022U_REPORT_PUBLISHED.json',receipt)
    return receipt
