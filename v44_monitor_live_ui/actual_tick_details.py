"""Read the active campaign's preparation and Actual journals in place."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import math
import psutil
from v44_monitor_live import read,actual_state

def live(identity):
    try:return abs(psutil.Process(identity['pid']).create_time()-identity['process_created'])<.001
    except (psutil.Error,KeyError,TypeError):return False

def slot_position(progress,day):
    stamp=progress.get('control_time_seconds')
    if isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp):return None
    issue=(datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))-timedelta(hours=6)).timestamp()
    return max(0,min(120,int((stamp-issue)//900)+1))

def row(job):
    case=Path(job['case_root']) if job.get('case_root') else None
    progress,heartbeat,_=actual_state(case,job['arm']) if case else ({},{},{})
    root_progress=read(case/'progress.json') if case else {}
    result=read(case/'ACTUAL/RESULT.json') if case else {}
    final=read(case/'RESULT.json') if case else {}
    start=(read(case/'ACTUAL_START.json') or read(case/'START.json')) if case else {}
    started=bool(progress or result or (case and ((case/'ACTUAL/START.json').exists() or (case/'ACTUAL_START.json').exists())))
    running=live(start) if started else False
    ticks=progress.get('completed_control_ticks')
    ticks=ticks if type(ticks) is int and ticks>=0 else None if started else 0
    phase=str(progress.get('phase',''))
    fresh='FRESH' in phase.upper()
    control_done=fresh or final.get('PASS') is True or result.get('Actual96_PASS') is True or result.get('Actual96_execution_PASS') is True
    failed=bool(final.get('error') or result.get('error') or job.get('status') in ('PRE_FAILED','ACTUAL_FAILED'))
    excluded=job.get('status')=='EXCLUDED'
    if final.get('PASS') is True:state='완료'
    elif excluded:state='Actual 제외 · 준비/검증 실패'
    elif failed:state='오류'
    elif fresh:state='Fresh 검증 중' if running else 'Fresh 종료 · 결과 확인'
    elif started:state='Actual 실행 중' if running else 'Actual 프로세스 확인'
    elif job.get('status')=='PREPARED':state='Actual 준비 완료 · 대기'
    elif job.get('status')=='PREPARING':state=(root_progress.get('stage') or '계획')+' 준비 중'
    else:state='준비 대기'
    active_stage=root_progress.get('stage') or ('ACTUAL_FRESH' if started else '대기')
    stage_root=case/active_stage if case else None
    ledger=read(stage_root/'NATIVE_RUNTIME_LEDGER.json') if stage_root else {}
    used=ledger.get('measured_Native_Runtime');cap=ledger.get('Native_ceiling_seconds',5400)
    native=f'{used:.1f} / {cap:g}s' if isinstance(used,(int,float)) else '—'
    if case and active_stage in ('M1','M2'):
        k=read(stage_root/'K48_NATIVE_LEDGER.json').get('measured_Native_Runtime',0)
        j=read(stage_root/'JOINT_NATIVE_LEDGER.json').get('measured_Native_Runtime',0)
        native=f'K48 {k:.1f}/300s · Joint {j:.1f}/900s'
    raw_error=job.get('exclusion_reason') or final.get('error') or result.get('error') or ''
    reason=('원본 R0 명단과 입력 명단 불일치' if 'ORIGINAL_R0_ROSTER_REQUIRED' in raw_error else raw_error)
    identity=(read(case/'ACTUAL_START.json') if started else read(case/'START.json')) if case else {}
    pid=identity.get('pid') if live(identity) else None
    return dict(day=job['day'],arm=job['arm'],state=state,completed_control_ticks=ticks,
        actual_slot_position=120 if control_done else slot_position(progress,job['day']),
        actual_started=started,actual_control_complete=control_done,worker_alive=running,excluded=excluded,
        phase=phase,updated=progress.get('UTC') or heartbeat.get('UTC'),
        case_root=str(case) if case else None,attempt=case.name if case else None,
        pid=pid,active_stage=active_stage,native_budget=native,reason=reason,raw_error=raw_error,
        preparation_status=job.get('status'),Actual_current_AC_calls=progress.get('current_AC_calls'))

def details(campaign):
    current=read(Path(campaign)/'OPERATIONS/BATCH_STATE.json')
    if current:
        rows=[row(j) for j in current.get('jobs',[])]
        days=sorted({j['day'] for j in current.get('jobs',[])})
        return dict(rows=rows,total=len(rows),started=sum(r['actual_started'] for r in rows),
            control_complete=sum(r['actual_control_complete'] for r in rows),
            completed_control_ticks=sum(r['completed_control_ticks'] or 0 for r in rows),excluded=sum(r['excluded'] for r in rows),
            prepared=sum(j['status']=='PREPARED' for j in current['jobs']),phase=current.get('phase'),
            date_range=days[0][5:]+' ~ '+days[-1][5:] if days else '',
            count_basis='COMPLETED_CONTROLLER_CALLBACKS_CAN_REPEAT_AT_SAME_PHYSICAL_TIME',
            slot_basis='LAST_REPORTED_CONTROL_TIME_24_PREFIX_PLUS_96_EVALUATION')
    ops=Path(campaign)/'AUTONOMOUS_RECOVERY'
    batch=read(ops/'R038_BATCH_STATE.json')
    repair=read(ops/'R039_B1_ACTUAL_REQUEST.json')
    if not batch or not repair:return None
    jobs=[dict(day=repair['day'],arm=repair['arm'],case_root=repair['case_root'],status='REPAIR')]+batch.get('jobs',[])
    rows=[row(j) for j in jobs]
    return dict(rows=rows,total=len(rows),started=sum(r['actual_started'] for r in rows),
        control_complete=sum(r['actual_control_complete'] for r in rows),
        completed_control_ticks=sum(r['completed_control_ticks'] or 0 for r in rows),excluded=sum(r['excluded'] for r in rows),
        count_basis='COMPLETED_CONTROLLER_CALLBACKS_CAN_REPEAT_AT_SAME_PHYSICAL_TIME',
        slot_basis='LAST_REPORTED_CONTROL_TIME_24_PREFIX_PLUS_96_EVALUATION')

CARD='''<details id="actual-ticks-card" class="card" hidden>
<summary id="actual-ticks-title" style="font-size:14px;font-weight:600;cursor:pointer">실행 상세 보기</summary>
<p id="actual-ticks-summary" class="muted" style="margin:10px 0"></p>
<div class="case-loading-scroll"><table class="case-loading-table" aria-label="현재 캠페인 날짜 비교군별 준비 및 Actual 세부 진행">
<thead><tr><th>날짜 · 비교군</th><th>현재 상태 · 단계</th><th>완료 Native / 예산</th><th>완료 제어틱</th><th>진행 제어시각</th><th>Worker</th><th>제외 / 오류 사유</th></tr></thead>
<tbody id="actual-ticks-body"></tbody></table></div>
<p class="muted" style="font-size:11px;margin-top:12px">제어틱은 완료된 콜백 수이며 같은 시각에 반복되어 120을 넘을 수 있습니다. 제어시각은 Prefix 24 + 평가 96슬롯 기준입니다.</p>
</details>'''

SCRIPT='''function renderActualTicks(data){
const card=document.getElementById('actual-ticks-card'),body=document.getElementById('actual-ticks-body');
card.hidden=!Array.isArray(data?.rows);if(card.hidden)return;
document.getElementById('actual-ticks-summary').textContent='Actual 시작 '+data.started+'/'+data.total+'건 · 제어 종료 '+data.control_complete+'/'+data.total+'건 · 제외 '+(data.excluded||0)+'건 · 완료 제어틱 합계 '+data.completed_control_ticks.toLocaleString()+'회';
document.getElementById('actual-ticks-title').textContent='실행 상세 보기 · '+data.total+'건 준비 및 Actual 진행';
body.replaceChildren(...data.rows.map(row=>{const tr=document.createElement('tr');
const values=[row.day.slice(5).replace('-','/')+' '+row.arm,row.state+' · '+(row.active_stage||'—'),row.native_budget||'—',Number.isInteger(row.completed_control_ticks)?row.completed_control_ticks.toLocaleString()+'회':'수신 대기',Number.isFinite(row.actual_slot_position)?row.actual_slot_position+' / 120':'—',row.pid?'PID '+row.pid:'—',row.reason||'—'];
values.forEach((value,index)=>{const cell=document.createElement(index===0?'th':'td');if(index===0)cell.scope='row';cell.textContent=value;tr.append(cell);});
tr.title=[row.attempt,row.pid?'PID '+row.pid:'',row.updated?'마지막 제어 보고 '+row.updated:'',row.raw_error||''].filter(Boolean).join(' · ');return tr;}));}
'''

def extend_html(html):
    for anchor in ('<div id="reason">','async function refresh(){',"$('status').textContent=s.status;"):
        if html.count(anchor)!=1:raise ValueError('ACTUAL_TICKS_MONITOR_BOUNDARY_DRIFT:'+anchor)
    html=html.replace('<div id="reason">',CARD+'<div id="reason">')
    html=html.replace('async function refresh(){',SCRIPT+'async function refresh(){')
    return html.replace("$('status').textContent=s.status;","renderActualTicks(s.actual_tick_details);\n$('status').textContent=s.status;")
