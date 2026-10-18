"""Update and restart only the external read-only HTTP monitor."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,os,re,shutil,subprocess,sys,time,urllib.request
import psutil

REPO=Path(__file__).resolve().parents[1]
MONITOR=Path('D:/MobileESS_V43/development/monitor_partial')
RUNTIME=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')


def once(source,old,new):
    if source.count(old)!=1:raise ValueError('MONITOR_BOUNDARY_DRIFT:'+old[:100])
    return source.replace(old,new)


def transform(source):
    source=once(source,'from a_stage_details import details as a_stage_details',
        'from a_stage_details import details as a_stage_details\nfrom bound_details import a_bounds, m_bounds, display_fields, stage_rows')
    begin=source.index('def m_view(');end=source.index('\ndef forecast_view(',begin)
    part=source[begin:end]
    part=once(part,"    ub = bounds.get('Global_UB')\n    lb = bounds.get('Global_LB')\n    gap = bounds.get('Global_Gap')",
        "    bound_evidence=m_bounds(attempt)\n    ub,lb,gap=(bound_evidence[k] for k in ('UB','LB','relative_gap'))")
    part=once(part,'    return value',"    value.update(display_fields(bound_evidence))\n    value['solver_note']+='\\n'+'\\n'.join(bound_evidence['lines'])\n    return value")
    source=source[:begin]+part+source[end:]
    begin=source.index('def campaign_worker_view(');end=source.index('\ndef campaign_view(',begin)
    part=source[begin:end]
    part=once(part,'native_display={};stage_details=None','native_display={};stage_details=None;bound_evidence=None')
    part=once(part,"        gap=result.get('certified_gap',p.get('certified_gap'))",
        "        bound_evidence=a_bounds(folder)\n        ub,lb,gap=(bound_evidence[k] for k in ('UB','LB','relative_gap'))")
    part=once(part,'        phase=stage_details[\'title\'];detail=f\'{stage} · {phase}\'',
        "        stage_details['bounds']=bound_evidence\n        stage_details['lines']+=bound_evidence['lines']\n        phase=stage_details['title'];detail=f'{stage} · {phase}'")
    part=once(part,'    return dict(**native_display,','    value=dict(**native_display,')
    part=part.rstrip()+"\n    if bound_evidence is not None:value.update(display_fields(bound_evidence))\n    return value\n\n"
    source=source[:begin]+part+source[end:]
    source=once(source,'cases=status.get(\'cases\',[]);workers=status.get(\'workers\',[]);details=[];views=[]',
        "cases=status.get('cases',[]);workers=status.get('workers',[]);details=[];views=[];bound_history=[]")
    source=once(source,'        details.append(line)','        bound_history.extend(stage_rows(case,stage))\n        details.append(line)')
    source=once(source,'workers=workers,cases=cases,case_line_loading=case_loading_table(campaign,cases),',
        'workers=workers,cases=cases,stage_bounds=bound_history,case_line_loading=case_loading_table(campaign,cases),')
    # Add a scoped detail line and stage history without changing scientific UI inputs.
    source=once(source,'    return html.encode(\'utf8\')', '''    extra_card='''+repr('''<section id="bounds-history-card" class="card" hidden><h2 style="font-size:18px">현재 Case 단계별 UB · LB</h2><p class="muted">UB·LB는 정격 대비 비율 ρ · 단계별 고정 계획이 다릅니다.</p><div style="overflow:auto"><table class="bounds-table"><thead><tr><th>단계</th><th>FULL UB</th><th>독립 LB</th><th>Global Gap</th><th>상태</th></tr></thead><tbody id="bounds-history-body"></tbody></table></div></section>''')+'''
    extra_script='''+repr('''function renderStageBounds(rows){
const card=document.getElementById('bounds-history-card'),body=document.getElementById('bounds-history-body');
card.hidden=!Array.isArray(rows)||!rows.length;if(card.hidden)return;
body.replaceChildren(...rows.map(row=>{const tr=document.createElement('tr');
for(const value of [row.stage,row.ub_text,row.lb_text,row.gap_text,row.status]){const td=document.createElement('td');td.textContent=value;tr.append(td);}
tr.title=[row.attempt,row.scope,row.source].join(' · ');return tr;}));}
''')+'''
    html=html.replace('</style>','.metrics .metric strong{font-size:19px;overflow-wrap:anywhere}.bounds-table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums;margin-top:12px}.bounds-table td,.bounds-table th{padding:9px 5px;border-bottom:1px solid #e7ecf3;text-align:left}.bounds-table th{white-space:nowrap}#bound-explanation{white-space:pre-line;line-height:1.6;margin-top:10px}</style>')
    html=html.replace('<div id="reason">',extra_card+'<div id="reason">')
    html=html.replace('<div class="metrics">','<div class="muted" id="metrics-scope"></div><div class="metrics">')
    html=html.replace('<div id="solver-note"','<div id="bound-explanation" class="muted"></div><div id="solver-note"')
    html=html.replace('<span class="muted">현재 해</span>','<span class="muted">검증 FULL UB</span>')
    html=html.replace('async function refresh(){',extra_script+'async function refresh(){')
    html=html.replace("$('inc').textContent=s.incumbent;", "renderStageBounds(s.stage_bounds);$('metrics-scope').textContent=s.metrics_label||'현재 단계';$('bound-explanation').textContent=s.bound_details?.lines?.join(String.fromCharCode(10))||'현재 단계 결과 수집 대기';$('inc').textContent=s.incumbent;")
    return html.encode('utf8')''')
    compile(source,'monitor_binding.py','exec')
    return source


def validate_ui(source,evidence):
    function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='existing_index')
    namespace=dict(Path=Path,ROOT=Path('D:/v44_may01_07_prepare_20261016'))
    exec(compile(ast.Module(body=[function],type_ignores=[]),'monitor_ui_preflight','exec'),namespace)
    html=namespace['existing_index']().decode('utf-8')
    script='\n'.join(re.findall(r'<script[^>]*>(.*?)</script>',html,re.S))
    path=Path(evidence)/'preflight_inline.js';path.write_text(script,encoding='utf-8')
    subprocess.run(['C:/Program Files/nodejs/node.exe','--check',str(path)],check=True,capture_output=True)
    assert 'renderStageBounds(s.stage_bounds)' in script
    return html


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    evidence=RUNTIME/'AUTONOMOUS_RECOVERY'/('MONITOR_BOUNDS_'+stamp);evidence.mkdir()
    processes=[];workers=[]
    for p in psutil.process_iter(['name','cmdline','create_time']):
        try:
            cmd=p.info['cmdline'] or []
            if str(MONITOR/'monitor_binding.py') in cmd and cmd[-1]=='8795':processes.append(p)
            if '--worker' in cmd and any('v44_recovery_' in item for item in cmd):
                workers.append(dict(pid=p.pid,created=p.create_time(),affinity=p.cpu_affinity()))
        except psutil.Error:pass
    if len(processes)!=1 or len(workers)!=1:raise RuntimeError('EXACT_MONITOR_AND_LIVE_WORKER_REQUIRED')
    request=json.loads(next((RUNTIME/'AUTONOMOUS_RECOVERY/requests').glob('2025-05-02_B3_attempt015.json')).read_text(encoding='utf-8-sig'))
    if any(Path(r['path']).resolve()==(MONITOR/'monitor_binding.py').resolve() for r in request['sources']):
        raise PermissionError('MONITOR_IS_A_SEALED_WORKER_SOURCE')
    original=(MONITOR/'monitor_binding.py').read_text(encoding='utf-8-sig')
    source=original if '--helper-only' in sys.argv else transform(original)
    source=source.replace("s.bound_details?.lines?.join('\\n')","s.bound_details?.lines?.join(String.fromCharCode(10))")
    validate_ui(source,evidence)
    shutil.copy2(MONITOR/'monitor_binding.py',evidence/'monitor_binding.before.py')
    (MONITOR/'bound_details.py').write_bytes((REPO/'v44_monitor_bounds/bounds.py').read_bytes())
    (MONITOR/'monitor_binding.py').write_text(source,encoding='utf-8')
    (evidence/'monitor_binding.after.py').write_text(source,encoding='utf-8')
    monitor=processes[0];command=monitor.cmdline();cwd=monitor.cwd();env=monitor.environ()
    monitor.terminate();monitor.wait(timeout=10)
    with (evidence/'stdout.log').open('ab') as out,(evidence/'stderr.log').open('ab') as err:
        proc=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    status=None
    for _ in range(30):
        if proc.poll() is not None:raise RuntimeError('MONITOR_RESTART_FAILED:'+str(proc.returncode))
        try:
            with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=3) as response:status=json.load(response)
            if status.get('stage_bounds'):break
        except (OSError,ValueError):pass
        time.sleep(.25)
    assert status and status.get('stage_bounds'),'LIVE_BOUNDS_NOT_RETURNED'
    for w in workers:
        p=psutil.Process(w['pid']);assert p.create_time()==w['created'] and p.cpu_affinity()==w['affinity']
    with urllib.request.urlopen('http://127.0.0.1:8795/',timeout=3) as response:html=response.read().decode('utf8')
    assert 'bounds-history-card' in html and 'renderStageBounds(s.stage_bounds)' in html
    (evidence/'LIVE_AFTER.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    proof=dict(PASS=True,URL='http://127.0.0.1:8795/',monitor_pid=proc.pid,old_monitor_pid=monitor.pid,
        workers_untouched=workers,stage=status.get('stage'),stage_bounds=status['stage_bounds'],
        only_monitor_restarted=True,scientific_source_or_Native_ledger_modified=False,
        helper_sha256=hashlib.sha256((MONITOR/'bound_details.py').read_bytes()).hexdigest())
    (evidence/'RESULT.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(PASS=True,evidence=str(evidence),monitor_pid=proc.pid,stage=status.get('stage'),
        rows=[dict(stage=r['stage'],UB=r['UB'],LB=r['LB'],gap=r['gap_text'],status=r['status']) for r in status['stage_bounds']]),ensure_ascii=False))


if __name__=='__main__':main()
