"""Read-only monitor HTTP service with one snapshot producer and live PID checks."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import argparse,json,os,sys,time,threading,traceback,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psutil

HOME=Path(__file__).resolve().parent
MONITOR=Path('D:/MobileESS_V43/development/monitor_partial')
SOURCE=Path('D:/v44_may01_07_prepare_20261016')
sys.path[:0]=[str(MONITOR),str(SOURCE)]
import monitor_binding as binding

def now():return datetime.now(timezone.utc).isoformat()

def same_process(identity):
    try:
        process=psutil.Process(identity['pid'])
        return process.is_running() and abs(process.create_time()-identity['process_created'])<.001
    except (psutil.Error,KeyError,TypeError,ValueError):return False

def normalize(value,campaign,batch,lease,alive=same_process):
    value=deepcopy(value);campaign=Path(campaign)
    jobs=batch.get('jobs',[]);lookup={(j['day'],j['arm']):j for j in jobs}
    observed=[];stale=[]
    for worker in value.get('workers',[]):
        job=lookup.get((worker['day'],worker['arm']),{})
        root=Path(job.get('case_root',campaign/worker['day']/worker['arm']/'__missing__'))
        identity=binding.optional(root/'ACTUAL_START.json') if job.get('status')=='ACTUAL_RUNNING' else binding.optional(root/'START.json')
        (observed if identity.get('pid')==worker.get('pid') and alive(identity) else stale).append(worker)
    live_keys={(w['day'],w['arm']) for w in observed}
    stale_keys={(w['day'],w['arm']) for w in stale}
    coordinator_alive=alive(lease)
    value.update(workers=observed,last_reported_workers=stale,coordinator_alive=coordinator_alive,
        worker_alive=bool(observed),monitor_read_only=True)
    days=sorted({j['day'] for j in jobs})
    date_range=(days[0][5:].replace('-','/')+'~'+days[-1][5:].replace('-','/')) if days else ''
    if days:
        value['run_id']=f'V44 · 5월 {int(days[0][-2:])}~{int(days[-1][-2:])}일 캠페인'
        value['total_dates']=len(jobs)
        value['solver_note']=value.get('solver_note','').replace('2025년 5월 8~14일',f'2025년 5월 {int(days[0][-2:])}~{int(days[-1][-2:])}일').replace('날짜별 28 Case',f'날짜별 {len(jobs)} Case')
    for case in value.get('cases',[]):
        if (case['day'],case['arm']) in stale_keys and case.get('status')=='RUNNING':case['status']='DISCONNECTED'
    for row in value.get('case_line_loading',{}).get('rows',[]):
        if row.get('scope')!='current':continue
        for cell in row.get('cells',[]):
            if (row['day'],cell['arm']) in stale_keys and cell.get('percent') is None:
                cell.update(state='프로세스 종료',tone='pending',reason='마지막 실행 기록은 있으나 동일 PID/생성시각의 프로세스가 없음')
    for row in (value.get('actual_tick_details') or {}).get('rows',[]):
        if (row['day'],row['arm']) in stale_keys and not row.get('actual_control_complete'):
            row.update(state='프로세스 종료',worker_alive=False,pid=None)
    summary=value.get('campaign_summary')
    if summary is not None:
        actual_live=sum(lookup[(w['day'],w['arm'])].get('status')=='ACTUAL_RUNNING' for w in observed)
        planning_live=sum(lookup[(w['day'],w['arm'])].get('status')=='PREPARING' for w in observed)
        summary.update(actual_running=actual_live,planning_running=planning_live,
            stale_workers=len(stale),coordinator_alive=coordinator_alive,actual_workers=7,
            date_range=date_range)
        if batch.get('phase')=='MAIN_ACTUAL_PARALLEL':
            main=[j for j in jobs if j['arm'] in ('B1','B3')]
            passed=sum(j['status']=='PASS' for j in main)
            failed=sum(j['status']=='ACTUAL_FAILED' for j in main)
            eligible=summary.get('actual_eligible',len(main))
            summary['actual_passed']=passed
            value.update(count_text=f'Actual/Fresh 종료 {passed+failed} / {eligible}건',
                progress_percent=100*(passed+failed)/eligible if eligible else 0,
                progress_summary=f'PASS {passed} · Actual 실패 {failed} · 실행 {actual_live}/7 · 준비 완료 대기 {summary.get("prepared_waiting",0)} · 연결 끊김 {len(stale)}')
    if not coordinator_alive and batch.get('phase') not in ('COMPLETE','USER_STOPPED'):
        value.update(state='DISCONNECTED',status='캠페인 프로세스 연결 끊김',tone='#d97706',
            detail=f'실제 Worker {len(observed)}개 · 마지막 기록 Worker {len(stale)}개 · 계산 재개 필요',
            reason='Coordinator PID/생성시각 불일치 · 모니터 응답 정상',Actual_auto_start_armed=False)
        if summary is not None:summary['auto_start_armed']=False
        if not observed:
            value['build']=dict(visible=False,percent=0,current_percent=0,steps=[])
            value['metrics_visible']=False
            value['steps']=[dict(step,style='') for step in value.get('steps',[])]
            for field in ('used_text','remaining_text'):
                if value.get(field):value[field]='마지막 기록 · '+value[field]
    if summary is not None:
        labels=dict(READY='대기',RUNNING='실행',COMPLETE='완료',FAILED='실패',
            DISCONNECTED='프로세스 종료',PRE_ACTUAL_READY='Actual 준비 완료',EXCLUDED='제외')
        lines=[value['run_id'],f"기록된 단계 {batch.get('phase')} · Coordinator {'생존' if coordinator_alive else '프로세스 없음'}",
            f"실제 Actual 실행 {summary['actual_running']}/7 · Planning 실행 {summary['planning_running']}/1 · 마지막 기록에만 남은 Worker {len(stale)}개",
            '모니터 연결 정상 · 원본 계산 원장을 변경하지 않는 조회 화면']
        if batch.get('phase')=='MAIN_ACTUAL_PARALLEL':
            lines.append(f"Actual/Fresh PASS {summary['actual_passed']} / 대상 {summary.get('actual_eligible',0)} · 준비 완료 대기 {summary.get('prepared_waiting',0)}")
        if stale:
            lines.append('\n종료된 Worker의 마지막 기록')
            ticks={(r['day'],r['arm']):r for r in (value.get('actual_tick_details') or {}).get('rows',[])}
            for worker in stale:
                row=ticks.get((worker['day'],worker['arm']),{})
                lines.append(f"{worker['day']} {worker['arm']} · PID {worker['pid']} 없음 · 마지막 제어시각 {row.get('actual_slot_position','—')}/120 · 기록 {row.get('updated') or '없음'}")
        lines.append(f'\n날짜별 {len(jobs)} Case')
        for day in days:
            states={c['arm']:labels.get(c['status'],c['status']) for c in value.get('cases',[]) if c['day']==day}
            lines.append(day[5:]+'  '+' · '.join(arm+':'+states.get(arm,'대기') for arm in ('B0','B1','B2','B3')))
        lines.append('\n완료 및 물리 PASS는 원본 결과 기준 · 모니터 수신과 계산 프로세스 생존은 별도입니다.')
        value['solver_note']='\n'.join(lines)
    return value

def snapshot():
    # The same server now reads ONLY the active iteration2 journals. Old r043
    # snapshots and B0/B1/B2 comparison results cannot leak into this response.
    from iteration2_details import apply as iteration_details
    value=iteration_details({},same_process)
    memory=psutil.virtual_memory();value['ram']=f'여유 {memory.available/2**30:.1f} / {memory.total/2**30:.1f} GB'
    return value

def index():
    page=binding.existing_index()
    if isinstance(page,bytes):page=page.decode('utf8')
    # Edit the existing template/cards/refresh loop in place; no second page,
    # endpoint or monitor. Remove the historical comparison card entirely.
    for pattern,replacement in (
        (r'<title>.*?</title>','<title>V44_iteration2 · 2025년 5월</title>'),
        (r'<h1>.*?</h1>','<h1>V44_iteration2 · 5월 캠페인</h1>'),
        (r'(<header><div><h1>.*?</h1>)<p>.*?</p>',r'\1<p>2025.05.01 — 05.31 · M2 → A3 → M3 → A4 → M4 → Actual / Fresh120</p>'),
        (r'<section id="case-loading-card".*?</section>',''),
        (r'function renderCaseLoading\(data\)\{.*?(?=function renderStageBounds)','')):
        page,count=re.subn(pattern,replacement,page,count=1,flags=re.S)
        if count!=1:raise ValueError('EXISTING_ITERATION2_TEMPLATE_ANCHOR_DRIFT:'+pattern)
    page=page.replace('renderCaseLoading(s.case_line_loading);','')
    page=page.replace('현재 캠페인 단계 진행','iteration2 · 31일 완료 현황').replace('— / 1일','— / 31일')
    page=page.replace('현재 Case 단계별 UB · LB','현재 날짜 · iteration2 단계별 UB / LB')
    page=page.replace('날짜 · 비교군','날짜 · iteration2').replace('날짜 비교군별 준비 및 Actual','iteration2 날짜별 준비 및 Actual')
    page=page.replace('완료 Native / 예산','Native 사용량 / 예산').replace('마지막 제어 보고 ','마지막 단계 보고 ')
    page=page.replace('Fresh96','Fresh120').replace('Fresh AC96','Fresh AC120')
    page=page.replace('<div id="steps"', '<p id="iteration2-policy" class="muted" style="margin-top:10px;line-height:1.8"></p><p id="iteration2-phase" class="muted" style="line-height:1.8"></p><div id="steps"',1)
    page=page.replace('</style>',
        '.budget{flex-wrap:wrap;gap:8px}.budget>*{min-width:0;overflow-wrap:anywhere}#used{font-size:15px}.budget .remaining{font-size:18px}'
        '.iteration2-stage-table td{min-width:110px;vertical-align:top}.iteration2-stage-table small{display:block;margin-top:5px}'
        '.iteration2-stage-table details>div{margin-top:6px}.iteration2-stage-table{font-variant-numeric:tabular-nums}'
        '@media(max-width:600px){.budget{align-items:flex-start;flex-direction:column}}</style>',1)
    detail=(HOME/'iteration2_details.html').read_text(encoding='utf8')
    script=(HOME/'iteration2_details.js').read_text(encoding='utf8')
    if page.count('<footer>')!=1 or page.count('async function refresh(){')!=1:raise ValueError('EXISTING_MONITOR_DETAIL_ANCHOR_DRIFT')
    page=page.replace('<footer>',detail+'\n<footer>')
    page=page.replace('async function refresh(){',script+'\nasync function refresh(){')
    page=page.replace('renderActualTicks(s.actual_tick_details);','renderActualTicks(s.actual_tick_details);\nrenderIteration2(s.iteration2_details);')
    if 'r043' in page or 'case-loading-body' in page:raise ValueError('HISTORICAL_MONITOR_UI_LEAK')
    return page.encode('utf8')

class SnapshotStore:
    def __init__(self):self.lock=threading.Lock();self.value=None;self.timestamp=None;self.error=None
    def refresh(self):
        try:
            value=snapshot()
            with self.lock:self.value=value;self.timestamp=time.monotonic();self.error=None
        except Exception as error:
            report=dict(UTC=now(),error=repr(error),traceback=traceback.format_exc())
            binding.atomic(HOME/'API_ERROR.json',report)
            with self.lock:self.error=repr(error)
    def response(self):
        with self.lock:
            if self.value is None:return 503,dict(status='모니터 상태 준비 중',error=self.error,monitor_read_only=True)
            value=deepcopy(self.value);age=time.monotonic()-self.timestamp;error=self.error
        value.update(monitor_snapshot_age_seconds=round(age,3),monitor_response_UTC=now())
        if error or age>10:
            value.update(status='모니터 상태 갱신 오류',state='MONITOR_ERROR',reason=error or '상태 스냅샷 갱신 지연',tone='#d97706')
        return 200,value

def _run(port=8795):
    store=SnapshotStore()
    def refresh_loop():
        while True:
            started=time.monotonic()
            try:store.refresh()
            except Exception as error:
                binding.atomic(HOME/'ITERATION2_READ_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
                with store.lock:store.error=repr(error)
            time.sleep(max(.05,1-(time.monotonic()-started)))
    threading.Thread(target=refresh_loop,name='read_only_snapshot',daemon=True).start()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                path=self.path.split('?',1)[0]
                if path in ('/','/index.html'):
                    payload=index();code=200;mime='text/html; charset=utf-8'
                elif path=='/api/status':
                    code,value=store.response();payload=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8');mime='application/json; charset=utf-8'
                else:code=404;payload=b'{"error":"not found"}';mime='application/json; charset=utf-8'
            except Exception as error:
                binding.atomic(HOME/'HTTP_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
                code=503;payload=json.dumps(dict(status='모니터 조회 오류',error=repr(error)),ensure_ascii=False).encode('utf8');mime='application/json; charset=utf-8'
            try:
                self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(payload)))
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        def log_message(self,*args):pass
    class ExclusiveServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            import socket
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    server=ExclusiveServer(('127.0.0.1',port),Handler)
    identity=dict(PID=os.getpid(),created=psutil.Process().create_time(),command=psutil.Process().cmdline(),UTC=now(),read_only=True,URL=f'http://127.0.0.1:{port}/')
    binding.atomic(HOME/'MONITOR_PROCESS.json',identity)
    binding.atomic(binding.RUNS/'monitor/MONITOR_PROCESS.json',identity)
    server.serve_forever()

def run(port=8795):
    # Windows SO_REUSEADDR permits duplicate listeners on the same address.
    # Hold one OS lock for the complete service lifetime and bind exclusively.
    guard=(HOME/'MONITOR_SERVICE.lock').open('a+b')
    try:
        guard.seek(0,2)
        if guard.tell()==0:guard.write(b'0');guard.flush()
        guard.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(guard.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        _run(port)
    finally:guard.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8795);args=parser.parse_args();run(args.port)


