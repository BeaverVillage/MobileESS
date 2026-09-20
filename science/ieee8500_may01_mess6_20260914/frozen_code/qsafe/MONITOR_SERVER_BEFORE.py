"""Read-only live B2/B3 monitor. No scheduler or experiment writes."""
import json,time,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psutil
HOME=Path(__file__).absolute().parent
W=HOME.parents[1]
RUN=W/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
BASE=W/'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913'
def read(p):
 try:return json.loads(p.read_text(encoding='utf-8-sig'))
 except (OSError,ValueError):return None
def process(pid):
 if not pid:return {'alive':False}
 try:
  p=psutil.Process(pid);v={'pid':pid,'alive':p.is_running()}
  try:v.update(rss_gib=p.memory_info().rss/2**30,cpu_seconds=sum(p.cpu_times()[:2]))
  except psutil.Error:pass
  return v
 except psutil.Error:return {'pid':pid,'alive':False}
def status():
 sup=read(RUN/'SUPERVISOR_STATUS.json') or {};live=read(RUN/'STATUS.json') or {}
 stage=sup.get('stage','');policy='B2' if 'B2' in stage else 'B3'
 if stage.startswith('actual_worker'):live=read(RUN/f'actual_{policy}/STATUS.json') or live
 clk=read(RUN/'SEARCH_CLOCK.json') or {};inc=read(RUN/'DEADLINE_INCUMBENT.json') or {}
 elapsed=max(0,min(14400,time.perf_counter()-clk['start_monotonic'])) if clk else 0
 failure=read(RUN/'SUPERVISOR_FAILURE.json')
 if not failure:
  for f in ['B2_FAILURE.json','B3_M1_FAILURE.json','A1_WORKER_FAILURE.json','A1_SUPERVISOR_FAILURE.json','MF_FAILURE.json','actual_B2/FAILURE.json','actual_B3/FAILURE.json']:
   r=read(RUN/f)
   if r:failure=r;break
 checks=[]
 for p in (RUN/'B3_A1/timed_checkpoints').glob('*.json'):
  r=read(p)
  if r:checks.append(dict(label=p.stem,seconds=r.get('target_seconds'),P1=r.get('P1')))
 checks.sort(key=lambda r:r['seconds'] or 0)
 rows=[];oldDA=read(BASE/'DA_RESULT.json') or {}
 for p in ['B0','B1','B2','B3']:
  old=p in ['B0','B1']
  da=oldDA.get(p) if old else (read(RUN/p/'FINAL_AUTHORITY.json') or {}).get('AC')
  ac=read((BASE/'actual'/p if old else RUN/('actual_'+p)/p)/'COMPLETE.json') or {}
  rows.append(dict(policy=p,fleet='OFF' if old else '6대',DA=(da or {}).get('max_phase_line_loading_pu'),Actual=ac.get('summary',{}).get('max_phase_line_loading_pu'),feasible=ac.get('AC_feasible'),interventions=ac.get('Q_intervention_slots'),unresolved=ac.get('ROBUST_Q_ONLY_UNRESOLVED_slots')))
 b2done=(RUN/'B2/COMPLETE.json').exists();b2ac=(RUN/'actual_B2/COMPLETE.json').exists();m1done=(RUN/'B3_M1/COMPLETE.json').exists();a1done=(RUN/'FOUR_HOUR_A1_INCUMBENT.json').exists();mfdone=(RUN/'B3/COMPLETE.json').exists();b3ac=(RUN/'actual_B3/COMPLETE.json').exists()
 completed=[b2done,b2ac,m1done,a1done,mfdone,b3ac]
 labels=['B2 · MESS search','B2 · Actual / QSAFE','B3 · M1','B3 · A1 4시간','B3 · MF','B3 · Actual / QSAFE']
 current=next((i for i,v in enumerate(completed) if not v),6)
 a1=read(RUN/'A1_WORKER_PROCESS.json') or {}
 pid=a1.get('pid') if stage=='a1_supervisor' else sup.get('worker_pid')
 return dict(now=time.time(),run=str(RUN),supervisor=sup,live=live,worker=process(pid),failure=failure,clock=clk,elapsed=elapsed,incumbent=inc,checkpoints=checks,results=rows,steps=[dict(name=n,state='complete' if completed[i] else 'running' if i==current else 'pending') for i,n in enumerate(labels)],current=current,complete=(RUN/'RESULT.json').exists(),authorization=read(RUN/'PRODUCTION_AUTHORIZATION.json'))
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  route=self.path.split('?')[0]
  if route=='/api/status':body=json.dumps(status(),ensure_ascii=False).encode();kind='application/json'
  elif route in ('/','/index.html'):body=(HOME/'index.html').read_bytes();kind='text/html'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
if __name__=='__main__':
 s=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 (HOME/'SERVER.json').write_text(json.dumps(dict(pid=os.getpid(),port=s.server_port,url=f'http://127.0.0.1:{s.server_port}',run=str(RUN)),indent=2),encoding='utf-8')
 s.serve_forever()
