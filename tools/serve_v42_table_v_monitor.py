"""Local read-only Table V monitor. Never imports a solver or modifies raw IO.

8794 is the test default. The supervisor alone switches the existing8793
service after preserving it; this tool never stops or edits another process.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import time
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION01'
ARMS = ('B0','B1','B2','B3')


def read_small(path):
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > 16*1024*1024:
            return {}
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def unwrap(value):
    return value.get('result', value) if isinstance(value, dict) else {}


def digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                     allow_nan=False,default=str).encode()).hexdigest()


def attempt_folder(source, arm):
    base=(Path(source)/arm).resolve()
    pointer=read_small(base/'LATEST_ATTEMPT.json')
    if not pointer:return base, None
    name=pointer.get('name','')
    target=Path(pointer.get('path','')).resolve()
    if (not name.startswith('ATTEMPT') or not name.replace('_','').isalnum()
            or target != base/name or pointer.get('prior_attempts_preserved') is not True
            or pointer.get('Native_budget_reset') is not False):
        raise ValueError('INVALID_SOURCE_CONFINED_LATEST_ATTEMPT_POINTER')
    return target, pointer


def state(source):
    source = Path(source).resolve()
    contract = read_small(source/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json')
    planning = read_small(source/'PLANNING_NATIVE_LEDGER.json')
    k48 = read_small(source/'K48_NATIVE_LEDGER.json')
    now = time.time()
    calls = planning.get('calls', []) + k48.get('calls', [])
    rows = []
    for arm in ARMS:
        folder,pointer = attempt_folder(source,arm)
        outcome = read_small(folder/'ARM_OUTCOME.json')
        progress_path = folder/'LIVE_PROGRESS.json'
        progress = read_small(progress_path)
        actual = unwrap(read_small(folder/'ACTUAL_RESULT.json'))
        fresh = unwrap(read_small(folder/'FRESH_AC_RESULT.json'))
        cert = fresh.get('official_certificate', {})
        resource = read_small(folder/'WALL_RAM_RESOURCE_REPORT.json')
        inflight = next((d.get('inflight') for d in (planning,k48)
                         if (d.get('inflight') or {}).get('stage_context', {}).get('arm') == arm), None)
        active = next((d.get('active_stage_context') for d in (planning,k48)
                       if (d.get('active_stage_context') or {}).get('arm') == arm), None)
        native = [r for r in calls if r.get('stage_context', {}).get('arm') == arm
                  and r.get('solver','').startswith('GUROBI')]
        runtime_known = all(finite(r.get('Native_Runtime')) for r in native)
        native_seconds = sum(r['Native_Runtime'] for r in native) if runtime_known else None
        current_case = (bool(contract) and actual.get('source_identity') == contract.get('source_identity')
            and actual.get('source_sha') == contract.get('source_sha')
            and actual.get('evaluation_case_sha') == digest(actual.get('evaluation_case_payload'))
            and actual.get('arm') == arm)
        cert_current = (current_case and cert.get('case_sha') == actual.get('evaluation_case_sha')
            and cert.get('initial_state_sha') == contract.get('common_initial_state_sha')
            and cert.get('MESS_plan_sha') == actual.get('MESS_plan_sha')
            and cert.get('actual_trace') == actual.get('actual_trace')
            and cert.get('slots') == 96 and cert.get('official_Full96') is True
            and fresh.get('executed_slots') == 96
            and cert.get('certificate_sha') == digest({k:v for k,v in cert.items() if k!='certificate_sha'}))
        maximum = cert.get('maximum_phase_line_loading') if cert_current else None
        if not finite(maximum): maximum = None
        elapsed = outcome.get('wall_seconds')
        if elapsed is None and finite(progress.get('elapsed_wall_seconds')):
            elapsed = progress['elapsed_wall_seconds'] + max(0., now-progress_path.stat().st_mtime)
        current = active.get('stage') if active else progress.get('stage')
        phase = progress.get('progress')
        if isinstance(phase, dict): phase = phase.get('phase', phase.get('status', ''))
        last_progress_phase = phase
        completed_phase = failed_phase = None
        if inflight:
            current = inflight['stage_context']['stage']
            phase = 'NATIVE_OPTIMIZE_RUNNING'
        elif outcome:
            if outcome.get('status') == 'FULL_PASS':
                completed_phase = progress.get('stage')
                current, phase = 'COMPLETED', 'ARM_COMPLETED'
            else:
                failed_phase = outcome.get('failed_stage', progress.get('stage'))
                current, phase = failed_phase, 'ARM_FAILED'
        build_stage = failed_phase or (progress.get('stage') if completed_phase else current)
        build_rows = [r for r in calls if r.get('solver') == 'BUILD'
            and r.get('stage_context', {}).get('arm') == arm
            and r.get('stage_context', {}).get('stage') == build_stage
            and finite(r.get('measured_seconds'))]
        build_wall = sum(r['measured_seconds'] for r in build_rows) if build_rows else None
        native_inflight_wall = max(0.,now-inflight['started_epoch_seconds']) if inflight and finite(inflight.get('started_epoch_seconds')) else None
        metrics = actual.get('receipt', {})
        statuses = dict(arm=outcome.get('status', 'RUNNING' if progress or active else 'WAITING'),
            Actual96=actual.get('status', 'NOT_RUN'), Fresh96=fresh.get('status', 'NOT_RUN'))
        rows.append(dict(arm=arm, computing='Reference' if arm in ('B0','B2') else 'Full E1/FLEX30/R1',
            MESS='OFF' if arm in ('B0','B1') else 'ON', statuses=statuses,
            current_stage=current, current_phase=phase, last_progress_phase=last_progress_phase,
            completed_phase=completed_phase, failed_phase=failed_phase,
            elapsed_wall_seconds=elapsed,
            completed_model_preprocessing_wall_seconds=build_wall,
            preprocessing_status='COMPLETED_RECORDED_MODEL_BUILD' if build_rows else 'NOT_RECORDED',
            Native_seconds=native_seconds if planning else None, Native_calls=len(native) if planning else None,
            completed_Native_Runtime_seconds=native_seconds if planning else None,
            Native_calls_completed=len(native) if planning else None,
            Native_calls_inflight=1 if inflight else 0,
            Native_calls_started=len(native)+(1 if inflight else 0) if planning else None,
            last_completed_Native_status=native[-1].get('status') if native else None,
            last_completed_Native_status_name={2:'OPTIMAL',3:'INFEASIBLE',4:'INF_OR_UNBD',
                5:'UNBOUNDED',9:'TIME_LIMIT',11:'INTERRUPTED'}.get(native[-1].get('status')) if native else None,
            active_Native_elapsed_seconds=native_inflight_wall,
            current_Native_call_wall_seconds=native_inflight_wall,
            current_Native_Runtime_pending=bool(inflight),
            current_call_wall_is_not_final_Native_Runtime=bool(inflight),
            executed_actual_slots=actual.get('executed_actual_slots') if current_case else None,
            executed_fresh_slots=fresh.get('executed_slots') if cert_current else None,
            maximum_actual_phase_line_loading_pu=maximum,
            maximum_actual_phase_line_loading_percent=100*maximum if maximum is not None else None,
            physical_metric_scope='CURRENT_FULL96_SETTLED_FULL_NETWORK_ACTUAL_TRACE' if cert_current else 'WAITING_FOR_CURRENT_FULL96_FRESH',
            physical_raw_replay_report_scope='SOURCE_CASE_HEADER_BOUND_DISPLAY_NOT_NEW_CERTIFICATE',
            voltage_min_pu=cert.get('voltage_min_pu') if cert_current else None,
            voltage_max_pu=cert.get('voltage_max_pu') if cert_current else None,
            physical_status=cert.get('status') if cert_current else 'NOT_RUN',
            actual_compute_GPUh=metrics.get('actual_compute_GPUh') if current_case else None,
            peak_RSS_bytes=resource.get('peak_RSS_bytes'), peak_private_bytes=resource.get('peak_private_bytes'),
            failure_stage=outcome.get('failed_stage'), failure_reason=outcome.get('error'),
            case_sha=actual.get('evaluation_case_sha') if current_case else None,
            current_attempt=pointer.get('name') if pointer else 'ORIGINAL',
            prior_attempts_preserved=True if pointer else None,
            prior_original_status=read_small(source/arm/'ARM_OUTCOME.json').get('status') if pointer else None))
    evidence=[]
    for name in ('MAY01_TABLE_V_FOUR_ARM_CONTRACT.json','MAY01_COMMON_INITIAL_STATE_CERTIFICATE.json',
                 'MAY01_FLEXIBILITY_POLICY_FREEZE.json','PLANNING_NATIVE_LEDGER.json','K48_NATIVE_LEDGER.json'):
        if (source/name).is_file(): evidence.append(dict(label=name,relative_path=name))
    for arm in ARMS:
        folder,pointer=attempt_folder(source,arm)
        for name in ('ARM_OUTCOME.json','ACTUAL_RESULT.json','FRESH_AC_RESULT.json','PLANNING_STAGE_RESULTS.json'):
            if (folder/name).is_file(): evidence.append(dict(label=arm+'/'+(pointer['name']+'/' if pointer else '')+name,
                                                            relative_path=str((folder/name).relative_to(source)).replace('\\','/')))
    reports=[]
    for directory in sorted(source.parent.glob('REPORT*')):
        if directory.is_dir():
            for p in sorted(directory.iterdir()):
                if p.is_file() and p.suffix in ('.md','.csv','.json'):
                    reports.append(dict(label=directory.name+'/'+p.name,relative_path=directory.name+'/'+p.name))
    return dict(schema='TABLE_V_LOCAL_READ_ONLY_MONITOR_V1',source=str(source),
        observed_UTC=datetime.now(timezone.utc).isoformat(), arms=rows, order=list(ARMS),
        source_case=contract.get('source_identity'), source_sha=contract.get('source_sha'),
        official_clock='900s ×96 original settle_slot → measure_full_network',
        P2_calls=0,R2='HOLD',Worker=1,Threads=1,total_native_limit_enabled=False,total_native_limit_seconds=None,
        stage_limits=dict(A1_A2_Native_seconds_per_arm_stage=5400,M1_M2_Native_seconds_per_arm_stage=1800,
                          K48_Native_seconds_separate_per_M_stage=300),
        Native_timeout_only=True,Build_HiGHS_Actual_AC_excluded_from_Native_timeout=True,
        substep_diagnostics_are_official_gate=False,continuous_time_safety_claimed=False,
        Planning_rho_displayed_as_Actual_loading=False,old_RC03_metrics_read=False,
        inflight=dict(planning=planning.get('inflight'),K48=k48.get('inflight')),
        evidence=evidence,reports=reports,refresh_seconds=5)


HTML = r'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>May01 Table V · Actual96 / Fresh96</title><style>
body{font:15px system-ui,sans-serif;background:#111820;color:#e6edf3;margin:28px}h1{font-size:25px}p{line-height:1.65;color:#b8c7d5}table{border-collapse:collapse;width:100%;margin:18px 0;background:#19242f}th,td{padding:12px;border-bottom:1px solid #324354;text-align:left}th{color:#aaccdd;font-size:13px}td{font-variant-numeric:tabular-nums}.metric{font-size:20px;font-weight:650}a{color:#8dccff}details{margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.muted{color:#8ea2b5}.bad{color:#ffb5a9}.good{color:#90e0bb}#updated{font-size:13px}#failure{white-space:pre-wrap;color:#ffb5a9}</style>
<h1>May01 Table V — 네 Arm 실제 실행</h1><p id="updated">현재 실행 자료를 읽는 중…</p>
<p>Reference / Full E1·FLEX30·R1 × MESS OFF / ON. P2 0 · R2 HOLD · Worker 1 · Threads 1.<br>
Timeout: A1/A2 각 Arm·Stage Native 5,400초 / M1/M2 1,800초. <b>합산 총량 제한 없음</b>; K48 별도 원장. Build·HiGHS·Actual·AC는 Native timeout에서 제외.</p>
<h2>Actual 최대 선로·상 부하율</h2><p>현재 Case의 Actual trace를 원래 15분×96 clock으로 settle 후 측정한 Full-network Fresh AC 값입니다. Planning ρ와 구분합니다. Fresh 완료 전 값은 대기 상태입니다. % = 100 × pu.</p>
<table><thead><tr><th>Arm</th><th>Computing / MESS</th><th>Actual / Fresh</th><th>Actual 최대 선로·상 (%)</th><th>Vmin / Vmax (pu)</th><th>공식 물리 판정</th></tr></thead><tbody id="physical"></tbody></table>
<h2>실행 진행</h2><table><thead><tr><th>Arm</th><th>결과</th><th>현재 Stage / Phase</th><th>전체 경과</th><th>완료 전처리 wall</th><th>완료 Native Runtime</th><th>Gurobi 호출</th><th>현재 호출 wall<br>(Runtime 확정 전)</th><th>Actual Compute GPUh</th><th>Peak RSS</th></tr></thead><tbody id="progress"></tbody></table>
<p>최적화가 진행 중이면 현재 Phase는 NATIVE_OPTIMIZE_RUNNING입니다. 전처리 완료 후 마지막 콜백 이름이 남아 있어도 전처리가 계속 진행되는 뜻은 아닙니다. 완료 Native Runtime 0초·완료 0회와 현재 진행 1회는 구분합니다. 진행 호출의 wall은 반환 후 확정되는 Native Runtime과 다릅니다.<br>전체 wall은 Native·Build·Actual·AC를 포함합니다. 하위 시간을 다시 더하지 않습니다. Substep은 별도 진단이며 공식 PASS/FAIL을 대신하지 않습니다. 이 화면은 새로운 물리 인증서를 발급하지 않습니다.</p>
<div id="failure"></div><details><summary>Report / evidence</summary><ul id="links"></ul></details><details><summary>Source / Case</summary><pre id="identity"></pre></details>
<script>
const el=id=>document.getElementById(id); const fmt=(x,d=2)=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(d):'대기';
const seconds=x=>typeof x==='number'?Math.floor(x/3600)+'h '+Math.floor(x%3600/60)+'m '+Math.floor(x%60)+'s':'—';
function row(body,values,metricIndex=-1){let tr=document.createElement('tr');values.forEach((v,i)=>{let td=document.createElement('td');td.textContent=v==null?'—':String(v);if(i===metricIndex)td.className='metric';tr.appendChild(td)});body.appendChild(tr)}
async function refresh(){try{let response=await fetch('/api/state',{cache:'no-store'});if(!response.ok)throw Error(response.status);let s=await response.json();el('physical').replaceChildren();el('progress').replaceChildren();el('links').replaceChildren();let failures=[];
s.arms.forEach(a=>{row(el('physical'),[a.arm,a.computing+' / '+a.MESS,(a.executed_actual_slots??0)+'/96 · '+(a.executed_fresh_slots??0)+'/96',fmt(a.maximum_actual_phase_line_loading_percent)+' %',fmt(a.voltage_min_pu,4)+' / '+fmt(a.voltage_max_pu,4),a.physical_status],3);row(el('progress'),[a.arm+' '+a.current_attempt,a.statuses.arm,(a.current_stage??'대기')+' / '+(a.current_phase??''),seconds(a.elapsed_wall_seconds),typeof a.completed_model_preprocessing_wall_seconds==='number'?fmt(a.completed_model_preprocessing_wall_seconds,3)+' s (완료)':'—',seconds(a.completed_Native_Runtime_seconds),'완료 '+(a.Native_calls_completed??'—')+'회 / 진행 '+a.Native_calls_inflight+'회'+(a.last_completed_Native_status!=null?' · '+a.last_completed_Native_status+' '+(a.last_completed_Native_status_name??''):''),seconds(a.current_Native_call_wall_seconds)+(a.current_Native_Runtime_pending?' (Runtime 미확정)':''),fmt(a.actual_compute_GPUh),typeof a.peak_RSS_bytes==='number'?(a.peak_RSS_bytes/1073741824).toFixed(2)+' GiB':'—']);if(a.failure_reason)failures.push(a.arm+' '+a.failure_stage+': '+a.failure_reason)});
for(let group of [['evidence',s.evidence],['report',s.reports]])for(let item of group[1]){let li=document.createElement('li'),a=document.createElement('a');a.textContent=item.label;a.href='/'+group[0]+'/'+encodeURIComponent(item.relative_path);a.target='_blank';a.rel='noopener';li.appendChild(a);el('links').appendChild(li)}
el('failure').textContent=failures.join('\n');el('identity').textContent=JSON.stringify({Source:s.source,SourceSHA:s.source_sha,Case:s.source_case},null,2);el('updated').textContent='5초 갱신 · '+s.observed_UTC+' · 현재 EXECUTION01만 표시';
}catch(error){el('updated').textContent='현재 자료 읽기 오류: '+error.message}}refresh();setInterval(refresh,5000);
</script></html>'''


def handler(source):
    source = Path(source).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, content, content_type='text/plain; charset=utf-8', status=200):
            if isinstance(content, str):content=content.encode('utf8')
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma','no-cache')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(content)

        def do_GET(self):
            path=urlsplit(self.path).path
            if path in ('/','/index.html'):
                return self.send(HTML,'text/html; charset=utf-8')
            if path=='/api/state':
                return self.send(json.dumps(state(source),ensure_ascii=False,allow_nan=False),'application/json; charset=utf-8')
            for route,base in (('/evidence/',source),('/report/',source.parent)):
                if path.startswith(route):
                    relative=unquote(path[len(route):]);target=(base/relative).resolve()
                    try:target.relative_to(base)
                    except ValueError:return self.send('Outside evidence root',status=403)
                    if (not target.is_file() or target.suffix.lower() not in ('.json','.csv','.md','.log')
                            or route=='/report/' and not target.relative_to(base).parts[0].startswith('REPORT')):
                        return self.send('Evidence not found',status=404)
                    content_type='application/json; charset=utf-8' if target.suffix=='.json' else 'text/plain; charset=utf-8'
                    return self.send(target.read_bytes(),content_type)
            return self.send('Not found',status=404)
    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT)
    parser.add_argument('--port',type=int,default=8794)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.source))
    print(json.dumps(dict(status='READ_ONLY_MONITOR_LISTENING',host='127.0.0.1',port=args.port,
                          source=str(args.source.resolve())),ensure_ascii=False),flush=True)
    server.serve_forever(poll_interval=.5)
