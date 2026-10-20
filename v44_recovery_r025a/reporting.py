"""Publish measured outcomes without conflating UB feasibility and gap certification."""
from pathlib import Path
import subprocess
from v44.common import read,record,atomic,now


def write_report(case):
    case=Path(case);stage=case/'A2';result=read(stage/'RESULT.json');ledger=read(stage/'NATIVE_RUNTIME_LEDGER.json')
    root=Path(__file__).resolve().parents[1];path=root/'docs/v44/NATIVE60_PHASE400_UB_POLICY_KO.md'
    text='# V44 r025a Native60 / Phase400 / 검증된 UB 동결\n\n'
    text+='B1·B3의 모든 미실행 A1/A2 및 현재 May02 B3 A2에 적용한다. 총 측정 Native3600초, Phase I 누적 Native400초. Phase I 미완료 시 P1도 생략하고 원래 제약·정수형의 INTEGER_CONTROL을 실행한다. 인공변수 없이 독립 원본 제약·정수성·물리 검증을 통과한 최선 UB만 동결하고 다음 단계로 넘긴다. 전역 LB/gap 미인증을 명시한다. 검증된 가능해가 없으면 false PASS 없이 해당 날짜를 보류하고 다음 날짜를 진행한다.\n\n'
    text+='현재 A2는 attempt007의 측정 Native342.1169981956482초와 저장된 지원을 승계한다. A1/M1 및 기존 PASS, Raw, Native 원장을 보존하며 시계를 초기화하지 않는다. M2/Actual/Fresh의 물리 검증은 유지한다.\n\n'
    text+='최근 A2 상태: '+str(result.get('classification'))+'; Native '+str(ledger['measured_Native_Runtime'])+'초; UB '+str(result.get('UB'))+'; LB '+str(result.get('LB'))+'; gap '+str(result.get('certified_gap'))+'.\n'
    path.write_text(text,encoding='utf-8');return path,dict(result=result,ledger=ledger)


def publish(case):
    from .operations import OPS
    path,value=write_report(case);root=Path(__file__).resolve().parents[1];relative=str(path.relative_to(root))
    def git(*a):return subprocess.check_output(['git',*a],cwd=root,stderr=subprocess.STDOUT,text=True,encoding='utf-8').strip()
    if git('status','--porcelain','--',relative):
        git('add','--',relative);git('commit','--only','-m','Record r025a bounded A-stage measured outcome','--',relative)
    pushed=git('push','origin','HEAD:refs/heads/codex/v44-may01-07-prestart')
    atomic(OPS/'R025A_REPORT_PUBLISHED.json',dict(UTC=now(),PASS=True,commit=git('rev-parse','HEAD'),report=record(path),push=pushed))
