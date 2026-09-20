"""Read-only live B2/B3 monitor. No scheduler or experiment writes."""
import json,time,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import psutil
HOME=Path(__file__).absolute().parent
W=HOME.parents[1]
RUN=W/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
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
 sup=read(RUN/'SUPERVISOR_STATUS.json') or {};live=read(RUN/'STATUS.json') or {}
 stage=sup.get('stage','');policy='B2' if 'B2' in stage else 'B3'
 if stage.startswith('actual_worker') or stage=='b3_actual_shell':live=read(RUN/f'actual_{policy}/STATUS.json') or live
 clk=read(RUN/'SEARCH_CLOCK.json') or {};inc=read(RUN/'DEADLINE_INCUMBENT.json') or {}
 elapsed=max(0,min(14400,time.perf_counter()-clk['start_monotonic'])) if clk else 0
 failure=read(RUN/'B3_CONTINUATION_FAILURE.json') or read(RUN/'SUPERVISOR_FAILURE.json')
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
  if p=='B2' and (read(SHELL/'B2_ACTUAL_COMPLETE.json') or {}).get('status')=='PASS':ac=read(SHELL/'B2/COMPLETE.json') or ac
  rows.append(dict(policy=p,fleet='OFF' if old else '6대',DA=(da or {}).get('max_phase_line_loading_pu'),Actual=ac.get('summary',{}).get('max_phase_line_loading_pu'),feasible=ac.get('AC_feasible'),interventions=ac.get('Q_intervention_slots'),unresolved=ac.get('ROBUST_Q_ONLY_UNRESOLVED_slots')))
 b2done=(RUN/'B2/COMPLETE.json').exists();b2ac=(RUN/'actual_B2/COMPLETE.json').exists();m1done=(RUN/'B3_M1/COMPLETE.json').exists();a1done=(RUN/'FOUR_HOUR_A1_INCUMBENT.json').exists();mfdone=(RUN/'B3/COMPLETE.json').exists();b3ac=(RUN/'actual_B3/COMPLETE.json').exists()
 completed=[b2done,b2ac,m1done,a1done,mfdone,b3ac]
 if (read(SHELL/'B2_ACTUAL_COMPLETE.json') or {}).get('status')=='PASS':completed[1]=True
 labels=['B2 · MESS search','B2 · Actual / QSAFE','B3 · M1','B3 · A1 4시간','B3 · MF','B3 · Actual / QSAFE']
 current=next((i for i,v in enumerate(completed) if not v),6)
 a1=read(RUN/'A1_WORKER_PROCESS.json') or {}
 pid=a1.get('pid') if stage in ('a1_supervisor','a1_alias_supervisor') else sup.get('worker_pid')
 result=dict(now=time.time(),run=str(RUN),supervisor=sup,live=live,worker=process(pid),failure=failure,clock=clk,elapsed=elapsed,incumbent=inc,checkpoints=checks,results=rows,steps=[dict(name=n,state='complete' if completed[i] else 'running' if i==current else 'pending') for i,n in enumerate(labels)],current=current,complete=(RUN/'RESULT.json').exists(),authorization=read(RUN/'PRODUCTION_AUTHORIZATION.json'))
 fast=W/'independent_screening/IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913'
 fast_process=read(fast/'ACTUAL_PROCESS.json')
 if fast_process and stage=='actual_worker_B2':
  live=read(fast/'STATUS.json') or {};failed=read(fast/'ACTUAL_FAILURE.json');proc=process(fast_process['pid'])
  final=read(fast/'B2/COMPLETE.json') or {};done=read(fast/'B2_ACTUAL_COMPLETE.json') or {}
  result.update(run=str(fast),live=live,worker=proc,failure=failed,supervisor=dict(status='FAILED' if failed else 'RUNNING' if proc['alive'] else 'COMPLETE' if done else 'STOPPED',stage='actual_worker_B2 · QSAFE deviation shells',worker_pid=fast_process['pid']),qsafe_problematic_slot=read(fast/'SLOT_RESULT.json'))
  if final:result['results'][2].update(Actual=final.get('summary',{}).get('max_phase_line_loading_pu'),feasible=final.get('AC_feasible'),interventions=final.get('Q_intervention_slots'),unresolved=final.get('ROBUST_Q_ONLY_UNRESOLVED_slots'))
  result['steps'][1]['state']='complete' if done.get('status')=='PASS' else 'running' if proc['alive'] else 'pending'
  if done:result['steps'][2]['state']='pending'
 energy_failure=read(RUN/'b3_actual_energy_diagnostic_20260914_v2/INDEPENDENT_VERIFICATION.json')
 raw_actual_failure=read(RUN/'actual_B3/FAILURE.json') or {}
 if energy_failure and 'ACTUAL_TRAVEL_ENERGY_BOUND_FAILURE' in raw_actual_failure.get('error','') and not b3ac:
  detail=(f"B3 Actual 물리 에너지 부족: {energy_failure['vehicle']}, slot {energy_failure['slot']} "
          f"({energy_failure['display_slot']}번째). 이동 후 {energy_failure['available_after_travel_kWh']:.9f} kWh < "
          f"440 kWh, 부족 {energy_failure['shortfall_Wh']:.6f} Wh. A1 4시간·MF 완료. Actual AC/QSAFE 시작 전 중단; 고정 P/에너지 한계 유지.")
  result['failure']=dict(error=detail,classification=energy_failure['status'],raw_failure=raw_actual_failure)
  result['live']=dict(result['live'],stage='B3_ACTUAL:PHYSICAL_ENERGY_INFEASIBLE',status='BLOCKED_PHYSICAL',search_stopped=True)
  result['energy_failure']=energy_failure
 # A separately authorized Actual replay supersedes the historical stopped run
 # only in this read-only view. Historical files and certificates stay intact.
 restart=read(RUN/'ENERGY_EXCEPTION_RUN.json')
 if restart:
  actual=RUN/'actual_B3_energy_exception_20260914'
  current_live=read(actual/'STATUS.json') or {}
  accepted=read(actual/'USER_ACCEPTED_COMPLETE.json') or {}
  final=read(actual/'B3/COMPLETE.json') or {}
  preflight=read(RUN/'b3_energy_continue_preflight_20260914/PREFLIGHT.json') or {}
  new_failure=read(actual/'FAILURE.json')
  if restart.get('status')=='FAILED':new_failure=new_failure or restart
  finished=bool(accepted) and not new_failure
  worker=process(restart.get('worker_pid'))
  checkpoint=read(actual/'B3/Q_ACCEPTED_CHECKPOINT.json') or {}
  slots=max(current_live.get('slots_complete',0),checkpoint.get('slots',0))
  if final:slots=96
  result.update(run=str(actual),supervisor=restart,live=current_live,worker=worker,
                failure=new_failure,complete=finished,current=6 if finished else 5,
                energy_exception=accepted or preflight,energy_exception_authorized=True,
                actual_elapsed=max(0,(restart.get('completed_unix') or time.time())-restart.get('started_unix',current_live.get('updated_unix',time.time()))),
                actual_slots=slots,actual_checkpoint=checkpoint,
                a1_complete=a1done,elapsed=14400 if a1done else elapsed)
  result.pop('energy_failure',None)
  for i,s in enumerate(result['steps']):s['state']='complete' if completed[i] or (i==5 and finished) else 'running' if i==5 else 'pending'
  if final:
   result['results'][3].update(Actual=final.get('summary',{}).get('max_phase_line_loading_pu'),
     feasible=final.get('AC_feasible'),interventions=final.get('Q_intervention_slots'),
     unresolved=final.get('ROBUST_Q_ONLY_UNRESOLVED_slots'),energy_exception=True)
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
