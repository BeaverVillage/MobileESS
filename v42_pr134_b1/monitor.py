"""Prior B1 UI, fresh 1s read-only snapshot. No optimizer/control policy."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import sys,time,math
from datetime import timedelta
from .common import *

def view(root):
    live=read(root/'B1_LIVE_STATUS.json');hb=read(root/'B1_HEARTBEAT.json');cp=read(root/'CHECKPOINT.json');active=live.get('active') or {};progress=live.get('progress') or {}
    request=read(active['request']) if active.get('request') else {};output=Path(request.get('output','__missing__'));progress_path=Path(request.get('progress','__missing__'))
    if progress_path.is_file():progress=read(progress_path)
    stage=active.get('stage');day=active.get('day');age=max(0,time.time()-datetime.fromisoformat(hb['timestamp_UTC']).timestamp())
    alive=same_process(hb['process']);worker_alive=same_process(active.get('worker',{}));used=progress.get('cumulative_native_runtime',0.)
    report_age=max(0,time.time()-progress_path.stat().st_mtime) if progress_path.is_file() else None
    state=live['state'];status='완료' if state=='COMPLETE' else '실행 중' if alive and age<30 else '갱신 지연' if alive else '계산 연결 끊김'
    def num(value):return format(value,'.7g') if isinstance(value,(int,float)) and math.isfinite(value) else '—'
    loading={};pass_files=sorted(output.glob('PASS_*_RECEIPT.json'))
    if pass_files:
        receipt=read(pass_files[-1]);rho=receipt.get('physical',{}).get('P1_rho')
        if rho is not None:loading=dict(text=f'{rho*100:.3f}%',note='검증된 현재 Planning 최대 선로 부하율')
    completed=[]
    for d,r in cp['dates'].items():
        if r['status']!='PASS':continue
        entry=cp['stages'].get(d+'/VALIDATION',{})
        if entry.get('receipt'):
            result=read(entry['receipt']);summary=result['physical']['summary']
            maximum=summary.get('rho_max_AC')
            if maximum is not None:completed.append(maximum)
    if stage in ('FRESH_AC','VALIDATION') and day:
        entry=cp['stages'].get(day+'/FRESH_AC',{})
        if entry.get('receipt'):
            result=read(entry['receipt']);summary=result.get('summary',{})
            maxline=summary.get('rho_max_AC')
            if maxline is not None:loading=dict(text=f'{maxline*100:.3f}%',note='검증된 Fresh Actual 최대 선로 부하율')
    labels=dict(A1='계획 수립',PLANNING_FREEZE='계획 확정',ACTUAL='실제 운영',FRESH_AC='전력 해석',VALIDATION='최종 검증')
    phases=dict(MODEL_BUILD='모델 생성',EXACT_COMPRESSION='정확 압축',INDEPENDENT_EXACT_VERIFIER='독립 증명 검증',MATERIALIZE_COMPRESSED_NATIVE='압축 native 모델 생성',
        rho='선로 부하율 최적화',migration_count='이동 횟수 최소화',shift_magnitude='시간 변경 최소화',prestart_relocation='배치 변경 최소화')
    detail=phases.get(progress.get('phase'),labels.get(stage,'다음 날짜 준비'))
    if progress.get('objective_pass'):detail+=f' · {progress["objective_pass"]}/4 목적'
    if progress.get('OpenDSS_slot') is not None:detail+=f' · {progress["OpenDSS_slot"]}/96'
    if progress.get('classes_required') is not None:built=progress.get('classes_complete',0);required=progress['classes_required']
    else:built=progress.get('jobs_complete',0);required=progress.get('jobs_required',0)
    mem=psutil.virtual_memory();gap=progress.get('gap')
    steps=[dict(label=label,style='pass' if cp['stages'].get(str(day)+'/'+s,{}).get('status')=='PASS' else 'active' if stage==s and state=='RUNNING' else '') for s,label in labels.items()]
    note=f'worker PID {active.get("worker",{}).get("PID","—")} · heartbeat {age:.1f}초 전'
    if report_age is not None:note+=f'\nsolver/build 마지막 보고 {report_age:.1f}초 전 · 값은 마지막 실제 보고 기준'
    return dict(status=status,tone='#059669' if alive else '#dc2626',run_id=live['run_id'],root=str(root),completed=live['PASS_days'],failed=live['failed_days'],timeout=live['timeout_days'],pending=live['pending_days'],total_dates=31,
        day=datetime.fromisoformat(day).strftime('%m월 %d일') if day else '—',detail=detail,used=used,remaining=max(0,BUDGET-used),
        incumbent=num(progress.get('incumbent')),bound=num(progress.get('BestBd')),gap=f'{gap*100:.2f}%' if isinstance(gap,(int,float)) else '—',steps=steps,
        line_loading=loading,actual_completed_mean_max_line_loading=float(np.mean(completed)) if completed else None,
        worker_alive=worker_alive,worker_PID=active.get('worker',{}).get('PID'),heartbeat_age=age,solver_report_age_seconds=report_age,solver_note=note,
        ram=f'여유 {mem.available/2**30:.1f} / {mem.total/2**30:.1f} GB · 정보 전용',memory_information_only=True,
        updated=datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S'),reason='',refresh_interval_seconds=1,snapshot_timestamp=now(),
        build=dict(visible=stage=='A1',percent=100*built/required if required else 0,current_percent=100*built/required if required else None,
            done=built,total=required,label=f'{built:,} / {required:,}' if required else detail,detail=detail,
            percent_scope='현재 단계의 실제 카운터' if required else '완료 영수증 대기; 추정 진행률 없음',steps=[]))

def run(root,port=8791):
    root=Path(root)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                if self.path in ('/','/index.html'):payload=(Path(__file__).parent/'monitor_index.html').read_bytes();mime='text/html; charset=utf-8'
                elif self.path=='/api/status':payload=json.dumps(view(root),ensure_ascii=False).encode();mime='application/json; charset=utf-8'
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
            except Exception as e:self.send_error(503,str(e))
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);atomic(root/'MONITOR_PROCESS.json',process());server.serve_forever()

if __name__=='__main__':
    from datetime import timedelta
    run(sys.argv[1])
