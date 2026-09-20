"""Read-only live B2/B3 monitor. No scheduler or experiment writes."""
import json,time,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psutil
HOME=Path(__file__).absolute().parent
W=HOME.parents[1]
RUN=W/'RESITING_SCREEN/IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916'
BASE=W/'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913'
SHELL=W/'independent_screening/IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913'
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
 sup=read(RUN/'SUPERVISOR_STATUS.json') or {};live=read(RUN/'STATUS.json') or {};stage=sup.get('stage','');now=time.time()
 role='B3_A1' if stage=='B3_A1' else 'B1'
 clk=read(RUN/'SEARCH_CLOCK.json') or {}
 if stage not in ('B1','B3_A1') or clk.get('start_unix',0)<sup.get('updated_unix',0):clk={}
 elapsed=max(0,min(14400,now-clk['start_unix'])) if clk else 0
 inc=read(RUN/'DEADLINE_INCUMBENT.json') or {}
 if inc.get('published_elapsed') is None:inc={}
 checks=[]
 for p in (RUN/role/'timed_checkpoints').glob('*.json'):
  r=read(p)
  if r:checks.append(dict(label=p.stem,seconds=r.get('target_seconds'),P1=r.get('P1')))
 checks.sort(key=lambda r:r['seconds'] or 0)
 rows=[]
 paths={'B0':('B0_REPLAY/AC_VALIDATION.json','B0/Fresh/AC_VALIDATION.json'),'B1':('B1/final_exact/AC_VALIDATION.json','B1/Fresh/AC_VALIDATION.json'),'B2':('B2/final_exact/AC_VALIDATION.json','B2/Fresh/AC_VALIDATION.json'),'B3':('B3/final_exact/AC_VALIDATION.json','B3/independent_clean_exact/AC_VALIDATION.json')}
 for policy,(dp,fp) in paths.items():
  da=read(RUN/dp) or {};fresh=read(RUN/fp) or {}
  if policy=='B2' and da.get('status')=='FAIL':da=read(RUN/'B2/physical_closure/accepted_clean_exact/AC_VALIDATION.json') or da
  metrics=fresh.get('metrics',{});slots=fresh.get('slots',[]);witness=max(slots,key=lambda r:r['max_phase_line_loading_pu']) if slots else {}
  rows.append(dict(policy=policy,fleet='OFF' if policy in ('B0','B1') else '6대',DA=da.get('metrics',{}).get('max_phase_line_loading_pu'),Fresh=metrics.get('max_phase_line_loading_pu'),Vmin=metrics.get('Vmin_pu'),Vmax=metrics.get('Vmax_pu'),txI=metrics.get('max_transformer_phase_current_pu'),txS=metrics.get('max_transformer_winding_kva_pu'),critical_slot=witness.get('slot'),critical_line=witness.get('line_witness'),feasible=fresh.get('status')=='PASS' if fresh else None))
 final=read(RUN/'FULL_RESULT.json') or {}
 done=[rows[0]['feasible'] is True,*[(RUN/r/'COMPLETE.json').exists() for r in ('B1','B2','B3_M1','B3_A1','B3')],bool(final)]
 labels=['B0 · 96-slot / Fresh','B1 · AIDC 4시간','B2 · route / PQ','B3 · M1 route / PQ','B3 · A1 4시간','B3 · MF / Fresh','최종 결과 집계']
 current={'B1':1,'B2':2,'B3_M1':3,'B3_A1':4,'B3_MF':5}.get(stage,0 if stage=='ELECTRICAL_PREPARATION' else 6)
 if final:current=7
 bounds=len(list((RUN/(role+'_electrical_rows')).glob('bounds_*.npz')));active=len(list((RUN/(role+'_electrical_rows')).glob('active_data_*.npz')))
 failure=sup if sup.get('status')=='FAILED' else None
 fleet=read(RUN/'FLEET_AUTHORITY.json') or {}
 result=dict(now=now,run=str(RUN),supervisor=sup,live=live,worker=process(sup.get('worker_pid')),failure=failure,clock=clk,clock_role=role,elapsed=elapsed,incumbent=inc,checkpoints=checks,results=rows,steps=[dict(name=n,state='complete' if done[i] else 'running' if i==current else 'pending') for i,n in enumerate(labels)],current=current,complete=bool(final),authorization=dict(initial=fleet.get('initial_locations',{})),preparation=dict(bounds_slots=bounds,active_slots=active),system=dict(available_ram_gib=psutil.virtual_memory().available/2**30),spatial_audit='SUPERSEDED_NONBLOCKING_DIAGNOSTIC',transport_preserved=(read(RUN/'INPUT_AUTHORITY_AUDIT.json') or {}).get('status')=='PASS',final=final,Actual=False)
 actual_root=RUN/'Actual_B012';actual=read(actual_root/'STATUS.json');ap=read(RUN/'ACTUAL_B012_PROCESS.json') or {}
 if actual:
  completed=read(actual_root/'CAMPAIGN_COMPLETE.json');fail=read(actual_root/'TECHNICAL_FAILURE.json')
  result.update(live=actual,worker=process(ap.get('pid')),Actual=True,complete=bool(completed),failure=fail,clock={},clock_role='Actual',elapsed=0,checkpoints=[])
  result['current']=['B0','B1','B2'].index(actual.get('policy','B0')) if not completed else 3
  result['steps']=[dict(name=p+' · Actual',state='complete' if (actual_root/p/'COMPLETE.json').exists() else 'running' if actual.get('policy')==p else 'pending') for p in ['B0','B1','B2']]
  for row in result['results']:
   done_actual=read(actual_root/row['policy']/'COMPLETE.json') or {};metric=done_actual.get('summary',{})
   row.update(Actual=metric.get('max_phase_line_loading_pu'),Actual_PASS=done_actual.get('AC_feasible'))
 return result

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  route=self.path.split('?')[0]
  if route=='/api/status':body=json.dumps(status(),ensure_ascii=False).encode();kind='application/json'
  elif route in ('/','/index.html'):body=(HOME/'index.html').read_bytes();kind='text/html'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
if __name__=='__main__':
 import sys
 s=ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1]) if len(sys.argv)>1 else 0),Handler)
 (HOME/'SERVER.json').write_text(json.dumps(dict(pid=os.getpid(),port=s.server_port,url=f'http://127.0.0.1:{s.server_port}',run=str(RUN)),indent=2),encoding='utf-8')
 s.serve_forever()
