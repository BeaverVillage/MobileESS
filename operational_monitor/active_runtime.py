"""Bind every monitor panel to the active equipment journal. Strictly read only."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from copy import deepcopy
import math
from bound_details import read,m_bounds,display_fields,stage_rows
from actual_tick_details import row as original_tick_row

def age(stamp):
 try:return max(0.,datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(stamp).timestamp())
 except (ValueError,TypeError):return None

def native(ledger,progress,kind):
 completed=ledger.get('measured_Native_Runtime',0.) or 0.
 current=progress.get('Native_Runtime')
 context=ledger.get('stage_context')
 matched=bool(context and context==progress.get('stage_context') and progress.get('budget_kind')==kind)
 if matched and isinstance(current,(float,int)) and not isinstance(current,bool) and math.isfinite(current):
  return max(completed,current),completed
 return completed,completed

def m_panel(case,stage,identity):
 folder=case/stage;p=read(folder/'progress.json')
 k=read(folder/'K48_NATIVE_LEDGER.json');j=read(folder/'JOINT_NATIVE_LEDGER.json')
 ku,kc=native(k,p,'K48_SEPARATE');ju,jc=native(j,p,'PLANNING_NATIVE')
 remaining=max(0.,300.-ku)+max(0.,900.-ju)
 bounds=m_bounds(folder)
 restored=(folder/'BINARY_RESTORE_RECEIPT.json').exists()
 model=(folder/'BINARY_STAGE_CHECKPOINT.json').exists() or restored
 lower=(folder/'LOWER_STAGE_RESULT.json').exists()
 joint=bool(j.get('inflight'));kflight=bool(k.get('inflight'))
 iterations=sorted((folder/'COMMON_M_PR222').glob('ITERATION_*'))
 iteration=int(iterations[-1].name.split('_')[-1]) if iterations else 0
 if joint:phase='Joint 최적화 계산 중'
 elif kflight:phase='K16 → K32 → K48 독립 하한 계산 중'
 elif lower:phase='FULL 해 검산 · Beam 후보 및 Joint 준비'
 elif model:phase='독립 K48 하한 준비'
 else:phase='원본 모델 구성 · Native0 검증'
 detail=f'{stage} · {phase}'+(f' · 반복 {iteration}' if iteration else '')
 budget='Joint' if lower or j else 'K48';used=ju if budget=='Joint' else ku;cap=900. if budget=='Joint' else 300.
 labels=['기준 계획','M1 최적화','Actual120','독립 Fresh120']
 telemetry=display_fields(bounds)
 telemetry.update(used=ku+ju,remaining=remaining,used_text=f'K48 {ku:.1f} s · Joint {ju:.1f} s',
  remaining_text=f'남은 Native 예산 {remaining:.1f} s',budget_label=f'{stage} Native 사용량',budget_cap='K48 300 s + Joint 900 s',
  stage=stage,arm='B2',root=str(case),source_attempt=str(case),attempt=case.name,worker_PID=identity['pid'],
  detail=detail,heartbeat_age=age(p.get('UTC')),solver_report_age_seconds=age(p.get('UTC')),
  raw_phase=phase,Native_inflight=joint or kflight,K48_Native_seconds=ku,Joint_Native_seconds=ju,
  Native_completed_seconds=kc+jc,Native_runtime_basis='MEASURED_LEDGER_PLUS_MATCHING_NATIVE_CALLBACK',
  Native_old_clocks_reused=bool(k.get('authorization',{}).get('old_native_clocks_reused') or j.get('authorization',{}).get('old_native_clocks_reused')),
  line_loading=dict(text='Fresh96 결과 대기',note='Actual 및 독립 Fresh 검증 완료 후 표시'),loading_label='Actual/Fresh96 최대 선로 부하율',
  steps=[dict(label=label,style='pass' if i==0 else 'active' if i==1 else '') for i,label in enumerate(labels)],
  build=dict(visible=True,percent=min(100.,100*used/cap),current_percent=min(100.,100*used/cap),
   label=f'{budget} Native 예산 사용',detail=f'{detail}\nK48 {ku:.1f} / 300 s · Joint {ju:.1f} / 900 s',
   percent_scope='Native 예산 소모율 · 전체 완료율 및 종료 예상시간과 별도',steps=[]),
  stage_bounds=stage_rows(case,stage),current_AC_calls=None,actual_control_ticks=None,actual_slot_position=None)
 telemetry['solver_note']=(f"{case.parent.parent.name} B2 {case.name} · {stage} · PID {identity['pid']}\n{detail}"
  f"\nK48 완료 {kc:.1f} s · Joint 완료 {jc:.1f} s · 진행 중 Runtime은 Native 콜백 수신값만 반영"
  +'\n'+('기존 Native 사용량 승계 · 재설정 없음' if telemetry['Native_old_clocks_reused'] else '현재 시도의 Native 원장 사용')
  +'\n'+ '\n'.join(bounds['lines']))
 return telemetry

def connect(value,ledger,alive):
 import monitor_binding as binding
 value=deepcopy(value);state=ledger.get('B2_state') or {};jobs=ledger['jobs']
 lease=state.get('lease') or {};connected=alive(lease);phase=state.get('phase')
 updates={(j['day'],j['arm']):j for j in jobs if j['arm']=='B2' and j.get('equipment_version')}
 live=[];active=None
 for key,job in updates.items():
  if job['status']!='BASELINE_RUNNING' or not job.get('case_root'):continue
  case=Path(job['case_root']);identity=read(case/'START.json')
  if alive(identity) and identity.get('pid')==job.get('pid'):
   progress=read(case/'progress.json') or job.get('progress') or {}
   stage=progress.get('stage','STARTING')
   live.append(dict(day=job['day'],arm='B2',pid=identity['pid'],process_created=identity['process_created'],worker_slot=1,campaign_root=ledger['B2_root'],case_root=str(case),stage=stage))
   active=(job,case,identity,stage)
 value.update(workers=live,worker_alive=bool(live),coordinator_alive=connected,root=ledger['B2_root'],
  active_state_source=state.get('state_path') or (str(Path(ledger['B2_root'])/'IO_RECOVERY_STATUS.json') if 'IO_FIXED' in str(phase) else str(Path(ledger['B2_root'])/'SEQUENCE_STATUS.json')),
  active_state_UTC=state.get('UTC'),active_state_age_seconds=age(state.get('UTC')),active_commit_sha=state.get('commit_sha'))
 # The scientific job remains FAILED; a diagnosed retry queued by the live
 # recovery coordinator is displayed as pending, never as a Fresh verdict.
 retry=set()
 for key,job in updates.items():
  if job['status'] not in ('ACTUAL_FAILED','FAILED') or not job.get('case_root'):continue
  case=Path(job['case_root']);m=read(case/'M1/RESULT.json')
  diagnosed=m.get('implementation_errors')==["FileNotFoundError(2, 'No such file or directory')"]
  if connected and phase=='B2_IO_FIXED_SERIAL_FULL_CASES' and active and job['day']>active[0]['day'] and diagnosed:retry.add(key)
 rows=[];oldrows={(r['day'],r['arm']):r for r in (value.get('actual_tick_details') or {}).get('rows',[])}
 for job in jobs:
  key=job['day'],job['arm']
  if key in updates:
   row=original_tick_row(job);case=Path(job['case_root']) if job.get('case_root') else None
   who=read(case/'START.json') if case else {};live_worker=alive(who) and who.get('pid')==job.get('pid')
   root_progress=read(case/'progress.json') if case else {};stage=root_progress.get('stage','대기')
   row.update(worker_alive=live_worker,pid=who.get('pid') if live_worker else None,active_stage=stage,
    updated=row.get('updated') or root_progress.get('UTC'),preparation_status=job['status'])
   if key in retry:row.update(state='M1 저장 오류 · 복구 대기',preparation_status='RECOVERY_QUEUED',active_stage='M1 복구 대기')
   elif job['status']=='BASELINE_RUNNING' and live_worker:
    if not row['actual_started']:row.update(state=stage+' 실행 중',active_stage=stage)
    if active and key==(active[0]['day'],'B2') and stage in ('M1','M2'):
     panel=m_panel(case,stage,who);row['native_budget']=panel['used_text'];row['updated']=read(case/stage/'progress.json').get('UTC') or root_progress.get('UTC')
   elif job['status']=='BASELINE_RUNNING':row.update(state='프로세스 연결 끊김',pid=None,worker_alive=False)
  elif key[1]=='B3' and key[0] in ('2025-05-29','2025-05-30'):
   row=dict(day=key[0],arm='B3',state='검증 완료 · 825 kVA',completed_control_ticks=None,control_tick_text='고정궤적 AC 검증',actual_slot_position=120,
    actual_started=True,actual_control_complete=True,worker_alive=False,excluded=False,phase='INDEPENDENT_FIXED_PLAN_AC120',
    updated=read(Path(job['case_root'])/'RESULT.json').get('finished_UTC'),case_root=job['case_root'],attempt=Path(job['case_root']).name,
    pid=None,active_stage='Actual120 · 독립 Fresh120 PASS',native_budget='재최적화 0회',reason='',raw_error='',preparation_status='PASS',Actual_current_AC_calls=None)
  else:row=oldrows.get(key)
  if row:rows.append(row)
 ticks=dict(value.get('actual_tick_details') or {},rows=rows,total=len(rows),phase=phase,
  started=sum(r.get('actual_started',False) for r in rows),control_complete=sum(r.get('actual_control_complete',False) for r in rows),
  completed_control_ticks=sum(r.get('completed_control_ticks') or 0 for r in rows),excluded=sum(r.get('excluded',False) for r in rows),prepared=0)
 value['actual_tick_details']=ticks
 for c in value.get('cases',[]):
  key=c['day'],c['arm']
  if key in retry:c.update(status='READY',display_status='RECOVERY_QUEUED',retry_queued=True)
  elif key in updates and c.get('status')=='RUNNING' and not any(w['day']==c['day'] for w in live):c['status']='DISCONNECTED'
 for table_row in value.get('case_line_loading',{}).get('rows',[]):
  if table_row.get('scope')!='current':continue
  for cell in table_row.get('cells',[]):
   key=table_row['day'],cell['arm']
   if key not in updates:continue
   job=updates[key];case=Path(job['case_root']) if job.get('case_root') else None
   error=read(case/'RESULT.json').get('error') if case else None
   if key in retry:cell.update(state='M1 저장 오류 · 복구 대기',tone='pending',physical_pass=False,percent=None,reason='이전 오류 증거 보존 · 22일 완료 후 동일 Native 사용량으로 복구 예정')
   elif error and not (case/'ACTUAL/RESULT.json').exists():cell.update(state='M1 실행 오류 · Fresh 미실행',tone='fail',physical_pass=False,percent=None,reason=error)
   elif job['status']=='BASELINE_RUNNING':
    row=next(r for r in rows if (r['day'],r['arm'])==key)
    cell.update(state=row['state']+' · 825 kVA',tone='live' if row['worker_alive'] else 'pending',case_root=job['case_root'],attempt=case.name,reason='현재 활성 시도 및 실제 PID/생성시각 기준')
 # Clear every old per-worker metric before installing the current panel.
 value.update(used=None,remaining=None,used_text='실행 Worker 대기',remaining_text='현재 단계 대기',incumbent='—',bound='—',gap='—',
  stage_bounds=[],bound_details=dict(lines=[]),metrics_visible=False,metrics_label='현재 단계',steps=[],build=dict(visible=False,percent=None,current_percent=None,steps=[]),
  stage=None,arm=None,attempt=None,worker_PID=None,source_attempt=None,heartbeat_age=None,solver_report_age_seconds=None,
  line_loading=dict(text='Fresh96 결과 대기',note='검증된 현재 결과만 표시'),loading_label='Actual/Fresh96 최대 선로 부하율',
  budget_label='현재 단계',budget_cap='—',current_AC_calls=None,actual_control_ticks=None,actual_slot_position=None)
 note=value.get('solver_note','')
 if active:
  job,case,identity,stage=active
  if stage in ('M1','M2'):panel=m_panel(case,stage,identity)
  else:panel=binding.campaign_worker_view(case,dict(day=job['day'],arm='B2',pid=identity['pid']),'ACTUAL_FRESH' if 'ACTUAL' in stage else 'REFERENCE',True)
  value.update(panel);value['solver_note']=panel.get('solver_note','')+'\n\n'+note
  value.update(day=f"{job['day']} · B2 · {stage}",root=str(case))
  if stage not in ('M1','M2'):value['stage_bounds']=stage_rows(case,stage)
 else:value['solver_note']=note
 failed=sum(j['status'] in ('ACTUAL_FAILED','FAILED','EXCLUDED') and (j['day'],j['arm']) not in retry for j in jobs)
 passed=sum(j['status']=='PASS' for j in jobs);done=passed+failed;total=len(jobs)
 value.update(completed=passed,failed=failed,pending=max(0,total-done-len(live)),retry_queued=len(retry),count_text=f'활성 결과 종료 {done} / {total}건',
  progress_percent=100*done/total if total else 0,progress_summary=f'PASS {passed} · 실패 {failed} · 실행 {len(live)}/1 · 오류 복구 대기 {len(retry)}',
  updated=datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S KST'))
 summary=value.setdefault('campaign_summary',{})
 summary.update(actual_running=int(bool(active) and 'ACTUAL' in active[3]),planning_running=int(bool(active) and active[3] in ('M1','M2')),
  actual_failed=failed,actual_passed=passed,coordinator_alive=connected,actual_workers=1,phase=phase,retry_queued=len(retry))
 if not connected and phase!='COMPLETE':
  value.update(state='DISCONNECTED',status='B2 복구 Coordinator 연결 끊김',tone='#d97706',reason='활성 복구 원장의 PID/생성시각과 실제 프로세스가 일치하지 않음',Actual_auto_start_armed=False)
  summary['auto_start_armed']=False
 return value
