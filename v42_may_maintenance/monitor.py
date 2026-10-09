"""A read-only extension of the live monitor without editing frozen source."""
import argparse, json, urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from v42_may_campaign.common import atomic,process,now,d_path
from .check import optional,age

SECTION='''<section class="card"><h2>Codex 매시간 점검</h2><p id="maintenance-last">점검 기록 수신 중</p><p id="maintenance-state"></p><p>원본 캠페인 모니터 · 정상 Solver 유지 · 읽기 전용 유지보수 상태</p></section>'''
SCRIPT='''<script>
async function maintenanceRefresh(){try{const r=await fetch('/api/maintenance',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();document.getElementById('maintenance-last').textContent='마지막 점검 '+(s.last_check_KST||'아직 없음');document.getElementById('maintenance-state').textContent=(s.last_action||'대기')+' · 열린 원인 '+Object.values(s.pending_issues||{}).filter(x=>x.status==='OPEN').length+' · 점검 '+(s.checks||0)+'회';}catch(e){document.getElementById('maintenance-state').textContent='유지보수 기록 수신 지연';}}
setInterval(maintenanceRefresh,1000);maintenanceRefresh();</script>'''


def enrich(campaign,status):
    """Live elapsed time comes from dispatch, never an old progress sample."""
    for worker in status.get('workers',[]):
        elapsed=age(worker.get('started_UTC'))
        if elapsed is not None:worker.update(wall_seconds=elapsed,remaining_seconds=max(0.,5400-elapsed))
        ledger=optional(Path(worker.get('request','')).parent/'NATIVE_RUNTIME_LEDGER.json')
        if not worker.get('Native_Runtime_seconds') and not ledger.get('inflight'):
            worker['Native_Runtime_seconds']=ledger.get('measured_Native_Runtime')
    mapping={w.get('worker_slot'):w for w in status.get('workers',[]) if w.get('arm')=='B2'}
    status['worker_slots']=[mapping.get(w['worker_slot'],w) for w in status.get('worker_slots',[])]
    active=status.get('workers',[{}])[0] if status.get('workers') else {}
    if active:status.update(wall_seconds=active.get('wall_seconds'),remaining_seconds=active.get('remaining_seconds'),
        Native_Runtime_seconds=active.get('Native_Runtime_seconds'))
    return status


def run(campaign,storage,port=8794):
    campaign=d_path(campaign);storage=d_path(storage)
    if port in (8791,8793):raise PermissionError('FROZEN_MONITOR_PORT_MUST_BE_PRESERVED')
    original='http://127.0.0.1:8793/'
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                if self.path in ('/','/index.html'):
                    with urllib.request.urlopen(original,timeout=10) as response:body=response.read().decode('utf-8')
                    body=body.replace('</header>','</header>'+SECTION,1).replace('</body>',SCRIPT+'</body>',1)
                    data=body.encode('utf-8');mime='text/html; charset=utf-8'
                elif self.path=='/api/status':
                    with urllib.request.urlopen(original+'api/status',timeout=10) as response:value=json.load(response)
                    data=json.dumps(enrich(campaign,value),ensure_ascii=False,allow_nan=False).encode();mime='application/json; charset=utf-8'
                elif self.path=='/api/maintenance':
                    data=json.dumps(optional(storage/'MAINTENANCE_STATE.json'),ensure_ascii=False).encode();mime='application/json; charset=utf-8'
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except Exception as error:self.send_error(503,str(error))
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    atomic(storage/'MAINTENANCE_MONITOR_PROCESS.json',process())
    atomic(storage/'MAINTENANCE_MONITOR_STATUS.json',dict(URL=f'http://127.0.0.1:{port}/',UTC=now(),process=process(),
        original_monitor_unchanged=True,read_only=True,optimizer_controls=False))
    server.serve_forever()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--storage',required=True);p.add_argument('--port',type=int,default=8794)
    a=p.parse_args();run(a.campaign,a.storage,a.port)
