"""Capture live dispatch and compact preparation evidence for the existing PR."""
import sys,json,psutil,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r048 import operations as op
from v44_week4 import preparation as prep
from v44.common import read,record,verify,atomic,now


def main():
    op.authority();state=read(op.STATE);assert len(state['workers'])==1 and state['workers'][0]['arm']=='B0'
    w=state['workers'][0];assert op.alive(w)
    original=[81396,82008,88464,89480,89656]
    identities=[dict(pid=p,process_created=psutil.Process(p).create_time()) for p in original]
    case=Path(next(j for j in state['jobs'] if j['day']==w['day'])['case_root'])
    assert (case/'progress.json').exists()
    status=json.load(urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=20))
    assert len(status['workers'])==6 and len(status['case_line_loading']['rows'])==31
    validate=read(prep.VALIDATION);observations=read(prep.OPS/'OBSERVATION_INPUT_PREFLIGHT.json')
    assert len(validate['actual_input_adapters'])==10 and len(validate['all_case_templates'])==40
    blocked=[r['day'] for r in observations['days'] if not r['PASS']];assert blocked==['2025-05-23']
    assert all(j['status']=='PREPARED_HELD' for j in read(prep.STATE)['jobs'] if j['arm']!='B0')
    live=dict(PASS=True,meaning='Dispatch/preservation evidence; new B0 Actual/Fresh result pending',UTC=now(),
        source=op.sources(),authorization=record(op.AUTH),coordinator=state['lease'],B0_worker=w,main_workers_preserved=identities,
        progress=read(case/'progress.json'),heartbeat=read(case/'ACTUAL/HEARTBEAT.json') if (case/'ACTUAL/HEARTBEAT.json').exists() else None,
        B0_affinity=psutil.Process(w['pid']).cpu_affinity(),B0_dates=len(state['jobs']),eligible=16,excluded=blocked,
        month_end='2025-05-31',monitor_rows=31,new_other_arms_held=True,prepared_new_cases=40,old_B0_completed=read(op.old.AUX_STATE)['jobs'])
    atomic(op.HOME/'LIVE_DISPATCH_VERIFIED.json',live)
    rows=[]
    for r in validate['actual_input_adapters']:
        rows.append(f"| {r['day']} | {r['Known']} | {r['Unknown']} | {r['initial_Running']} | {'입력 차단: 기상 원본 공백' if r['day'] in blocked else '준비 완료'} |")
    report='\n'.join(['# 5/22~5/31 캠페인 준비 및 5/31까지 B0 추가 실행','',
        'B0~B3 40건의 날짜별 입력·독립 초기 상태·R0 및 전력 배열·Actual 원본 이벤트 UID 조인을 준비했습니다. 새 날짜의 B1/B2/B3는 실행하지 않고 보류합니다.','',
        'B0는 기존 5/8~5/14의 7건 PASS를 유지하고, 5/15~5/31에 전용 1-worker를 추가했습니다. 정상 16개 날짜는 Reference → Actual → 독립 Fresh를 같은 worker에서 마친 뒤 다음 날짜로 진행합니다. 기존 B1/B3 Actual 5개와 후속 B2 1-worker는 유지합니다.','',
        '| 날짜 | Known | Unknown | 초기 Running | 입력 상태 |','|---|---:|---:|---:|---|',*rows,'',
        '5/23은 원본 기상 자료의 2025-05-22 15:00/16:00 UTC 관측에 기압과 wet-bulb 값이 없습니다. 3개 경계 조회에서 마지막 정상 관측의 나이가 7200초를 넘습니다. 원본 NOAA CSV도 확인했으며 같은 시간에 완전한 대체 관측은 없었습니다. 값을 보간하거나 기존 신선도 기준을 변경하지 않고 해당 날짜 B0를 입력 차단으로 제외합니다. 다른 9일은 기상·수요·태양광 조회를 통과했습니다.','',
        '최종 검증 70개 통과. 10일 1210개 읽기 전용 조회 중 1207개 통과, 위 3개 실패를 명시했습니다. 데이터 준비에서는 Native 최적화 및 제어 시뮬레이션을 실행하지 않았습니다. 별도 B0-only permit으로 실제 B0만 실행합니다.','',
        '첫 추가 실행의 Reference 어댑터는 늦은 import가 이미 패치된 자기 함수를 원본으로 캡처하여 재귀 오류가 났습니다. r048a는 모든 worker에서 기존 r045 원본 참조를 먼저 import합니다. 실제 날짜 입력을 사용하는 Native0 검증으로 재현 경로를 확인했습니다. 5/15·5/16의 실패 attempt001을 보존하고 attempt002에서 재개하며, 실행 전에 차단된 5/17은 원래의 미실행 attempt001을 사용합니다.','',
        'r047의 이미 끝난 B0 대기 controller만 자연 종료하고 새 r048 coordinator로 인계했습니다. 현재 r046 Actual worker는 종료·재시작하지 않았습니다. 기존 Actual이 자연 종료하면 원래 7개 B0 PASS를 본 캠페인에 합치고, 기존 B2 1-worker를 새 월말 B0와 병렬로 이어갑니다.','',
        '모니터는 기존 주소 http://127.0.0.1:8795/ 와 날짜 × B0/B1/B2/B3 표를 유지하고 31행으로 확장했습니다. 입력 준비 통과와 미래 Planning/Actual/Fresh PASS는 별도입니다.'])+'\n'
    (prep.CAMPAIGN/'PREPARATION_REPORT.md').write_text(report,encoding='utf-8')
    pr=Path('D:/v44_r043_pr_update_20261019');docs=pr/'docs/v44/r048_month_b0_20261020';docs.mkdir(parents=True,exist_ok=True)
    (docs/'README.md').write_text(report,encoding='utf-8')
    for folder in ('v44_recovery_r048','v44_week4'):
        target=pr/folder;target.mkdir(exist_ok=True)
        for p in (Path('D:/v44_r022_rowgen_20261017')/folder).glob('*.py'):(target/p.name).write_bytes(p.read_bytes())
    (pr/'v44_recovery_r048a.py').write_bytes(Path('D:/v44_r022_rowgen_20261017/v44_recovery_r048a.py').read_bytes())
    (pr/'tests/test_v44_recovery_r048a.py').write_bytes(Path('D:/v44_r022_rowgen_20261017/tests/test_v44_recovery_r048a.py').read_bytes())
    (pr/'tests/test_v44_recovery_r048.py').write_bytes(Path('D:/v44_r022_rowgen_20261017/tests/test_v44_recovery_r048.py').read_bytes())
    (pr/'v44_monitor_live_ui/monitor_binding.py').write_bytes(Path('D:/MobileESS_V43/development/monitor_partial/monitor_binding.py').read_bytes())
    for p in Path(__file__).parent.glob('*r048*.py'):(pr/'validation_tools/campaign_preparation'/p.name).write_bytes(p.read_bytes())
    p=Path(__file__).with_name('verify_week4_observations.py');(pr/'validation_tools/campaign_preparation'/p.name).write_bytes(p.read_bytes())
    for p in (op.AUTH,op.HOME/'VALIDATION.json',op.HOME/'SOURCE_SNAPSHOT.json',op.HOME/'USER_REQUEST.json',op.HOME/'MONITOR_VERIFIED.json',op.HOME/'LIVE_DISPATCH_VERIFIED.json',Path('D:/v44_r048_regression_20261020.xml')):
        (docs/p.name).write_bytes(p.read_bytes())
    for p in (op.HOME/'R048A_REFERENCE_FIX_AUTHORIZATION.json',op.HOME/'R048A_VALIDATION.json',Path('D:/v44_r048a_regression_20261020.xml')):
        (docs/p.name).write_bytes(p.read_bytes())
    for p in (prep.AUTH,prep.VALIDATION,prep.DOC/'SEVEN_DAY_INPUT_MANIFEST.json',prep.OPS/'OBSERVATION_INPUT_PREFLIGHT.json',prep.OPS/'B0_EXECUTION_PERMIT.json',prep.DOC/'B0_PREEXECUTION_CERTIFICATION.json',prep.OPS/'PREPARATION_EXTENSION_REVIEW.json'):
        (docs/p.name).write_bytes(p.read_bytes())
    attrs=pr/'.gitattributes';data=attrs.read_bytes()
    for folder in ('v44_recovery_r048','v44_week4'):
        line=(folder+'/** -text whitespace=cr-at-eol\n').encode()
        if line.rstrip() not in data:data+=b'\n'+line
    line=b'v44_recovery_r048a.py -text whitespace=cr-at-eol\n'
    if line.rstrip() not in data:data+=b'\n'+line
    attrs.write_bytes(data)
    print(dict(PASS=True,worker=w,main_workers=len(identities),monitor_rows=31,blocked=blocked,case_progress=live['progress']),flush=True)

if __name__=='__main__':main()
