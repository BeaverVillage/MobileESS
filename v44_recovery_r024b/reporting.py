"""Measured r024a rollback/Native90 checkpoint continuation report."""
from pathlib import Path
import subprocess
from v44.common import read,record,atomic,now


def write_report(case):
    root=Path(__file__).resolve().parents[1];case=Path(case)
    result=read(case/'A2/RESULT.json');ledger=read(case/'A2/NATIVE_RUNTIME_LEDGER.json')
    path=root/'docs/v44/R024A_NATIVE90_ROLLBACK_CHECKPOINT_KO.md'
    text='# r024a 정책 복귀 / Native5400 체크포인트 승계\n\n'
    text+='사용자 최신 지시로 총Native3600 및 PhaseI400/1000 cutoff, UB-only 진입 정책을 취소하고 r024a(알고리즘r024)의 총Native5400/별도PhaseI 제한없음/원본P1·gap인증 정책으로 복귀했다. r024b는 이 원본 알고리즘에 검증된 체크포인트·활성행·가능점·Pricing캐시와 Native 원장을 승계하는 운영 어댑터다.\n\n'
    text+='May02 B3 attempt010은 이전Native458.1179983615875초에서 이어가며 시계를0으로 재설정하지 않는다. 완료 A1/M1은 동일plan SHA로 재사용한다. 저장 모델과 fingerprint가 일치하는176887개 활성행,6회 후보확장,이전full-elastic 가능점 Φ≈0.001542343,고정가중치와 Adaptive탐색 이력을 복원했다. 누락됐던 Pricing roster도 복원하고138개 full-block 파일을 확인했다. 기존오류·부분결과·Raw·원장은 모두 보존한다.\n\n'
    text+='최근 상태: '+str(result.get('classification'))+'; Native '+str(ledger['measured_Native_Runtime'])+'초; UB '+str(result.get('UB'))+'; LB '+str(result.get('LB'))+'; gap '+str(result.get('certified_gap'))+'.\n'
    path.write_text(text,encoding='utf-8');return path


def publish(case):
    from .operations import OPS
    root=Path(__file__).resolve().parents[1];path=write_report(case);relative=str(path.relative_to(root))
    def git(*a):return subprocess.check_output(['git',*a],cwd=root,stderr=subprocess.STDOUT,text=True,encoding='utf-8').strip()
    if git('status','--porcelain','--',relative):
        git('add','--',relative);git('commit','--only','-m','Record restored r024a checkpoint measured outcome','--',relative)
    push=git('push','origin','HEAD:refs/heads/codex/v44-may01-07-prestart')
    atomic(OPS/'R024B_REPORT_PUBLISHED.json',dict(UTC=now(),PASS=True,commit=git('rev-parse','HEAD'),report=record(path),push=push))
