"""Reuse the existing Table V screen for independent V42.2 arm attempts.

Reads original evidence in place. Does not launch solvers or write ledgers.
"""
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import argparse
import json
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools.table_v_monitor import server as screen

DEFAULT = REPO / 'docs/v42_2_campaign_20261016'
_validation_cache = {}


def validation_summary(path):
    stamp = (path.stat().st_mtime_ns, path.stat().st_size)
    cached = _validation_cache.get(str(path))
    if cached and cached[0] == stamp:
        return dict(cached[1])
    if stamp[1] > 64*1024*1024:
        return dict(folder=path.parent.name, status='RESULT_TOO_LARGE_TO_READ')
    result = json.loads(path.read_text(encoding='utf-8-sig'))
    rows = [{k:r.get(k) for k in ('arm','stage','status','source_sha')} for r in result.get('rows', [])]
    summary = dict(folder=path.parent.name, status=result.get('status'), tests=result.get('tests'),
        source_sha=result.get('source_sha') or (rows[0].get('source_sha') if rows else None), rows=rows)
    _validation_cache[str(path)] = (stamp, summary)
    return dict(summary)


def state(campaign=DEFAULT):
    campaign = Path(campaign).resolve()
    checkpoint = screen.core.read_small(campaign/'CHECKPOINT.json')
    current_source = checkpoint.get('current_uncommitted_scientific_source_sha')
    value = screen.state(campaign)
    rows, history, evidence = [], {}, []
    for arm in ('B1', 'B2', 'B3'):
        folders = sorted((campaign/'ATTEMPTS'/arm).glob('ATTEMPT[0-9][0-9][0-9]'))
        records = []
        for folder in folders:
            ledger = screen.core.read_small(folder/'PLANNING_NATIVE_LEDGER.json')
            calls = [c for c in ledger.get('calls', []) if c.get('solver', '').startswith('GUROBI')]
            records.append(dict(attempt=folder.name, Native_calls=len(calls),
                exact_Native_seconds=sum(c['Native_Runtime'] for c in calls) if all(
                    screen.core.finite(c.get('Native_Runtime')) for c in calls) else None,
                Native_Runtime_bounds_seconds=ledger.get('Native_Runtime_bounds_seconds'),
                status=screen.core.read_small(folder/arm/'ARM_OUTCOME.json').get('status',
                    'RUNNING' if ledger.get('inflight') else 'PREPARED_ONLY')))
        history[arm] = records
        folder = folders[-1] if folders else campaign/'ATTEMPTS'/arm/'NOT_STARTED'
        row = next(r for r in screen.state(folder)['arms'] if r['arm'] == arm)
        ledger = screen.core.read_small(folder/'PLANNING_NATIVE_LEDGER.json')
        pid = ledger.get('active_stage_owner_pid') or (ledger.get('inflight') or {}).get('pid')
        if pid and not row['process']['alive']:
            try:
                process = screen.psutil.Process(pid)
                command = process.cmdline()
                identity = screen.core.read_small(folder/'V42_2_ATTEMPT_AUTHORITY.json')
                if (any('run_v42_2_campaign.py' in arg for arg in command)
                        and '--arm' in command and command[command.index('--arm')+1] == arm
                        and '--attempt' in command and int(command[command.index('--attempt')+1]) == identity.get('attempt')):
                    memory = process.memory_info()
                    row['process'] = dict(alive=True, pid=pid, RSS_bytes=memory.rss,
                        elapsed_seconds=time.time()-process.create_time())
            except (screen.psutil.Error, ValueError, IndexError):
                pass
        row['current_attempt'] = folder.name if folders else None
        row['display_status'] = ('PASS' if row.get('raw_arm_status') == 'FULL_PASS' else
            '중단 · 미인증' if row.get('raw_arm_status') else
            '실행 중' if row['process']['alive'] else '입력 준비만 완료' if folders else '미실행')
        row['phase_display']['label'] = row['phase_display'].get('label') or '실행 대기'
        row['attempt_history'] = records
        row['stage_budget']['runtime_bounds'] = records[-1].get('Native_Runtime_bounds_seconds') if records else None
        rows.append(row)
        if folders:
            for name in ('PLANNING_NATIVE_LEDGER.json', 'K48_NATIVE_LEDGER.json',
                         arm+'/ARM_OUTCOME.json', arm+'/PLANNING_STAGE_RESULTS.json'):
                path = folder/name
                if path.is_file():
                    evidence.append(dict(label=arm+'/'+folder.name+'/'+name,
                        relative_path=path.relative_to(campaign).as_posix()))
    validation = {}
    for prefix, result_name in (('B1_NATIVE0_', 'RESULT.json'), ('M_NATIVE0_', 'RESULT.json'),
                                ('REGRESSION', 'RESULTS.json')):
        completed = sorted(p for p in campaign.glob(prefix+'*') if (p/result_name).is_file())
        if completed:
            path = completed[-1]/result_name
            validation[prefix] = validation_summary(path)
            proof_source = validation[prefix].get('source_sha')
            validation[prefix]['current_source_matches'] = proof_source == current_source if proof_source else None
            evidence.append(dict(label=path.parent.name+'/'+path.name,
                relative_path=path.relative_to(campaign).as_posix()))
    for name in ('CHECKPOINT.json', 'STATE.json'):
        if (campaign/name).is_file(): evidence.append(dict(label=name, relative_path=name))
    diagnostic = dict(alive=False, pid=checkpoint.get('active_PID'))
    try:
        process = screen.psutil.Process(diagnostic['pid'])
        command = process.cmdline()
        output_name = Path(checkpoint.get('active_output', '')).name
        if (output_name and any(output_name in arg for arg in command)
                and any(Path(arg).name in ('audit_v42_2_m_seedless.py', 'audit_v42_aidc_compression.py') for arg in command)):
            diagnostic.update(alive=True, elapsed_seconds=time.time()-process.create_time(),
                RSS_bytes=process.memory_info().rss, scope='NATIVE0_PREPARATION_NOT_ARM_OPTIMIZATION')
    except (screen.psutil.Error, TypeError, ValueError):
        pass
    value.update(source=str(campaign), arms=rows, order=['B1','B2','B3'], run_arms=['B1','B2','B3'],
        observed_UTC=datetime.now(timezone.utc).isoformat(), evidence=evidence,
        source_sha=current_source,
        source_case=None, historical_B0=None, compression_audit={}, phase_policy_recovery={},
        monitor_version='V42_2_INDEPENDENT_ATTEMPTS_READ_ONLY', attempt_history=history,
        validation=validation, checkpoint=checkpoint,
        active_stage=checkpoint.get('active_stage'), diagnostic_process=diagnostic,
        Native0_is_not_FULL_or_Actual_PASS=True)
    return value


def html():
    value = Path(__file__).with_name('index.html').read_text(encoding='utf8')
    value = value.replace('May01 실행 현황', 'V42.2 · May01 실행 현황')
    value = value.replace("const status=a=>", "const status=a=>a.display_status||")
    value = value.replace("||s.arms[1];", "||s.arms[0];")
    value = value.replace("function render(s){", """function render(s){
 const cp=s.checkpoint||{}, reg=s.validation?.REGRESSION||{};
 const a=s.validation?.B1_NATIVE0_||{};
 $('compression-audit').textContent='현재 작업: '+(s.active_stage==='FRESH_CURRENT_SOURCE_M_NATIVE0_04'?'최신 Source의 M-stage Native0 검증':s.active_stage||'확인 중')+
   (s.diagnostic_process?.alive?' · 검증 프로세스 실행 중, PID '+s.diagnostic_process.pid:' · 검증 프로세스 대기/종료')+
   ' · '+a.folder+' 행렬 검증 완료 (FULL 인증 아님) · 회귀검사 '+(reg.tests??'—')+' '+(reg.status??'대기');
""")
    value = value.replace("+' 승인 · B0 기존 결과 보존'", "+' 순차 실행 · 완료 비교군은 원장 기준 표시'")
    value = value.replace("text('callwall',b.inflight?", """if(b.runtime_bounds){
  text('native',fmt(b.runtime_bounds.lower,1)+'–'+fmt(b.runtime_bounds.upper,1)+'초');
  text('remaining','재부팅 중단 · 정확한 Runtime 미확정');
 }
 text('callwall',b.inflight?""")
    value = value.replace("scope:'읽기 전용 화면", "validation:s.validation,attempt_history:s.attempt_history,active_stage:s.active_stage,diagnostic_process:s.diagnostic_process,scope:'읽기 전용 화면")
    return value.encode('utf8')


def handler(campaign):
    base = screen.core.handler(campaign)
    class Handler(base):
        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                if path in ('/', '/index.html'):
                    return self.send(html(), 'text/html; charset=utf-8')
                if path == '/api/state':
                    return self.send(json.dumps(state(campaign), ensure_ascii=False, allow_nan=False),
                                     'application/json; charset=utf-8')
                return super().do_GET()
            except (OSError, ValueError, KeyError, TypeError) as error:
                return self.send(json.dumps(dict(error=str(error))), 'application/json', 503)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=DEFAULT)
    parser.add_argument('--port', type=int, default=8793)
    args = parser.parse_args()
    print(json.dumps(dict(status='READ_ONLY_MONITOR', source=str(args.source), port=args.port)), flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.source)).serve_forever()
