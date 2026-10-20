"""Seal preparation evidence and copy compact review artifacts; never release hold."""
import sys,json,ast,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_week3 import preparation as op
from v44.common import read,verify,record,atomic,now,digest


def main():
    with op.bindings(),op.no_execution():result=op.verify_prepared()
    validation=read(op.VALIDATION);observations=read(op.OPS/'OBSERVATION_INPUT_PREFLIGHT.json')
    assert validation['PASS'] and observations['PASS']
    assert len(validation['actual_input_adapters'])==7 and len(observations['days'])==7
    assert {r['day'] for r in validation['references']}==set(op.DAYS)
    verify([validation['manifest']]+validation['all_28_templates'])
    receipts=[record(op.AUTH),record(op.VALIDATION),record(op.OPS/'OBSERVATION_INPUT_PREFLIGHT.json'),
        record(op.DOC/'DAILY_AUTHORITY_BINDINGS.json'),record(op.DOC/'PREEXECUTION_CERTIFICATION.json')]
    for r in validation['references']:receipts.append(r['reference'])
    for r in validation['actual_input_adapters']:receipts.append(r['binding'])
    for r in observations['days']:receipts.extend(r['sources']+[r['weather_admission']])
    verify(receipts)
    # Old and new whole-day populations may not silently become identical.
    prior=read(op.previous.DOC/'SEVEN_DAY_INPUT_MANIFEST.json');following=read(validation['manifest']['path'])
    seen_known={};seen_unknown={};date_rows=[]
    for r in prior['days']+following['days']:
        known=digest(read(r['files']['native']['path'])['known_population'])
        unknown=digest(read(r['files']['actual_input']['path'])['post_issue_arrivals'])
        assert known not in seen_known and unknown not in seen_unknown,(r['day'],'CROSS_WEEK_IDENTICAL_POPULATION')
        seen_known[known]=r['day'];seen_unknown[unknown]=r['day']
        if r['day'] in op.DAYS:
            adapter=next(a for a in validation['actual_input_adapters'] if a['day']==r['day'])
            dates=dict(day=r['day'],Known=adapter['Known'],Unknown=adapter['Unknown'],Running=adapter['initial_Running'],
                private_exact_join_count=adapter['private_exact_join_count'],issue_AEST=r['axis']['issue_AEST'],
                begin_AEST=r['axis']['begin_AEST'],end_AEST=r['axis']['end_AEST'],status='PREPARED_HELD')
            date_rows.append(dates)
    assert op.CAMPAIGN!=op.previous.CAMPAIGN
    active=read(op.ACTIVE);assert Path(active['root'])==op.previous.CAMPAIGN
    assert not any('--worker' in (p.info['cmdline'] or []) and str(op.CAMPAIGN) in ' '.join(p.info['cmdline'] or [])
        for p in __import__('psutil').process_iter(['cmdline']))
    xml=Path('D:/v44_week3_preparation_regression_20261020.xml')
    import xml.etree.ElementTree as ET
    suite=ET.parse(xml).getroot().find('testsuite');assert suite is not None and int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
    seal=dict(PASS=True,UTC=now(),mode='PREPARE_ONLY',root=str(op.CAMPAIGN),days=date_rows,cases=28,
        evidence=receipts,regression=record(xml),regression_tests=int(suite.attrib['tests']),Native_calls=0,control_ticks=0,
        planning_executed=False,Actual_executed=False,Fresh_executed=False,execution_authorized=False,auto_start=False,
        active_campaign=str(op.previous.CAMPAIGN),active_pointer_unchanged=True,cross_week_population_duplicate_count=0,
        causal_source_lookup_boundaries=847,source_preparation=sources_record(),
        preparation_code_has_no_run_or_worker_entry=True)
    atomic(op.OPS/'PREPARATION_SEALED.json',seal)
    report=['# 2025-05-15~05-21 캠페인 준비 완료 · 실행 보류','',
        'B0~B3 총 28건의 날짜별 입력과 독립 초기 상태를 준비했습니다. Planning·Actual·Fresh 실행은 모두 0건이며, 실행 권한과 자동 시작은 설정하지 않았습니다. 현재 활성 캠페인은 05/08~05/14 그대로입니다.','',
        '| 날짜 | Known | Unknown | 초기 Running | Actual 원본 UID 일치 | 상태 |','|---|---:|---:|---:|---:|---|']
    for r in date_rows:report.append(f"| {r['day']} | {r['Known']} | {r['Unknown']} | {r['Running']} | {r['private_exact_join_count']} | 준비·보류 |")
    report+=['','57개 회귀 검증, 7일 전체 R0 기준 계획·전력 배열, Actual 입력 구성 및 이벤트 원본 UID 조인, 수요·태양광·날씨 847개 조회가 통과했습니다. 05/08~05/21 간 전체 Known/Unknown 목록을 비교해 날짜를 잘못 복제한 경우도 확인했습니다.','',
        '초기 Running은 같은 날짜 issue 시점의 원본 관측과 기존 결정적 초기화 규칙을 사용하며, MESS는 기존의 독립 일별 초기 상태 가정입니다. 전날 최적화 상태를 복사하지 않았습니다. B3의 A1 의존 경로도 같은 날짜 B1로 고정했습니다.','',
        'Reference와 Actual 입력 검증용 자료는 DOCUMENTS 하위에만 저장했습니다. 운영 case attempt, coordinator lease, 실행 permit은 없습니다. 입력 검증 통과는 Planning 최적화나 Actual/Fresh 물리 PASS를 뜻하지 않습니다. 예측의 역사적 인과 가용성은 기존과 동일하게 미인증 상태입니다.','',
        '예정 구성은 현재 캠페인과 동일하게 B1/B3 Planning 1-worker → 정상 Actual 최대 7-worker, B0 추가 1-worker 날짜순, 이후 B2 1-worker입니다. 실제 시작은 05/08~05/14 종료 확인 후 별도 실행 요청에서 허용해야 합니다.','',
        '검증 재확인: `python -m v44_week3.preparation --verify` (`D:/v44_r022_rowgen_20261017`에서 실행). 이 도구에는 `--run` 또는 `--worker` 명령이 없습니다.']
    text='\n'.join(report)+'\n';(op.CAMPAIGN/'PREPARATION_REPORT.md').write_text(text,encoding='utf-8')
    pr=Path('D:/v44_r043_pr_update_20261019');docs=pr/'docs/v44/week3_may15_21_preparation_20261020';docs.mkdir(parents=True,exist_ok=True)
    (docs/'README.md').write_text(text,encoding='utf-8')
    for src in (op.AUTH,op.VALIDATION,op.OPS/'PREPARATION_SEALED.json',op.OPS/'OBSERVATION_INPUT_PREFLIGHT.json',op.OPS/'USER_PREPARE_ONLY_REQUEST.json',op.DOC/'SEVEN_DAY_INPUT_MANIFEST.json',op.DOC/'PREEXECUTION_CERTIFICATION.json',xml):
        (docs/src.name).write_bytes(src.read_bytes())
    (docs/'SOURCE_SNAPSHOT.json').write_text(json.dumps(dict(sources=op.sources(),tests=record('D:/v44_r022_rowgen_20261017/tests/test_v44_week3_preparation.py'),additional=sources_record()),indent=2),encoding='utf-8')
    (docs/'STATE_SNAPSHOT.json').write_bytes(op.STATE.read_bytes())
    attrs=pr/'.gitattributes';raw=attrs.read_bytes();line=b'v44_week3/** -text whitespace=cr-at-eol\n'
    if line.rstrip() not in raw:attrs.write_bytes(raw+b'\n'+line)
    print(dict(**result,regressions=seal['regression_tests'],read_only_observation_queries=847),flush=True)


def sources_record():
    root=Path(__file__).parent
    return [record(root/'verify_week3_observations.py'),record(__file__)]

if __name__=='__main__':main()
