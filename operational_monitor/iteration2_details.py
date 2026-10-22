"""Read-only iteration details inside the existing V44 r043 monitor."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import json,hashlib,math
from bound_details import read,a_bounds,m_bounds,display_fields,text,gap_text
from active_runtime import native,age,m_panel

ROOT=Path('D:/MobileESS_V44/runtime/V44_iteration2')
STAGES=('M2','A3','M3','A4','M4')
CORE={s:'A2' if s.startswith('A') else 'M2' for s in STAGES}
LABELS=dict(WAIT_B2='기존 B2 종료 대기',WAIT_B2_RESOURCES='기존 B2 자원 해제 대기',
 PLANNING_SERIAL='31일 Planning 순차 실행',RESOURCE_WAIT_PLANNING='Planning 자원 대기',
 PLANNING_FAILED_ACTUAL_HELD='Planning 검증 필요 · Actual 차단',ACTUAL_PARALLEL='Actual120 / 독립 Fresh120 병렬 실행',
 RESOURCE_WAIT_ACTUAL='Actual 메모리·디스크 대기',WAIT_EXISTING_OWN_WORKERS='기존 Worker 자연 종료 확인',
 REPORTING='31일 비교 결과 정리',COMPLETE='31일 실행 종료',SUPERVISOR_ERROR='실행 감독기 오류')
_cache={}

def verified(receipt):
 if not isinstance(receipt,dict) or not all(k in receipt for k in ('path','bytes','sha256')):raise ValueError('HASHED_RECEIPT_REQUIRED')
 p=Path(receipt['path'])
 if not p.resolve().is_relative_to(ROOT.resolve()):raise ValueError('ONLY_ITERATION2_EVIDENCE_ALLOWED')
 stat=p.stat();key=(str(p),receipt['bytes'],receipt['sha256'],stat.st_size,stat.st_mtime_ns)
 if key not in _cache:
  raw=p.read_bytes()
  if len(raw)!=receipt['bytes'] or hashlib.sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('RECEIPT_SHA_DRIFT:'+str(p))
  _cache[key]=json.loads(raw.decode('utf-8-sig'))
  if len(_cache)>1024:
   value=_cache[key];_cache.clear();_cache[key]=value
 return _cache[key]

def stage(day,name,item):
 status=item.get('status','QUEUED');row=dict(stage=name,status=status,label='대기',root=item.get('root'),error=item.get('error'),
  UB=None,LB=None,Gap=None,Native_seconds=None,case_sha=None,plan_sha=None,voltage_band=[.955,1.045] if name in ('M2','M3') else [.95,1.05] if name=='M4' else None)
 if status=='PASS':
  try:
   public=verified(item['result']);core=verified(public['core_result'])
   if not (public.get('PASS') and public.get('original_FULL_PASS') and public.get('stage')==name and public.get('day')==day and core.get('FULL_feasible')):raise ValueError('EXACT_FULL_STAGE_REQUIRED')
   if name.startswith('A') and not (public.get('new_AIDC_FULL_optimization') and (core.get('Native_seconds') or 0)>0 and core.get('independent_Global_LB_validated') and 0<=core.get('certified_gap',1)<=.005):raise ValueError('NEW_A_FULL_SOLVE_REQUIRED')
   row.update(label='FULL PASS',UB=public.get('UB'),LB=public.get('LB'),Gap=public.get('Gap'),Native_seconds=public.get('Native_seconds'),case_sha=public.get('case_sha'),plan_sha=public.get('plan_sha'),commit_sha=public.get('commit_sha'))
  except (OSError,ValueError,KeyError,TypeError) as error:row.update(status='VERIFY_ERROR',label='검증 오류',error=repr(error))
 elif status=='RUNNING':row['label']='실행 중'
 elif status in ('FAILED','ENTRY_FAILED','BLOCKED'):row['label']='실행 오류' if item.get('error') else 'FULL 미수용'
 return row

def actual(day,item):
 row=dict(status=item.get('status','QUEUED'),label='31일 M4 검증 대기',Fresh_PASS=None,overall_PASS=None,root=item.get('root'),error=item.get('error'))
 if item.get('result'):
  try:
   result=verified(item['result'])
   if result.get('day')!=day:raise ValueError('ACTUAL_DATE_DRIFT')
   if result.get('independent_audit'):
    audit=verified(result['independent_audit']);fresh=audit.get('independent_Fresh120',{})
    row.update(Fresh_PASS=fresh.get('PASS') is True,overall_PASS=bool(result.get('PASS') and audit.get('PASS')),
     Vmin=fresh.get('voltage_min_pu'),Vmax=fresh.get('voltage_max_pu'),
     line_percent=100*audit['evaluation96']['maximum_line_loading_pu'] if audit.get('evaluation96') else None,
     transformer_percent=100*fresh['maximum_transformer_kVA_loading_pu'] if 'maximum_transformer_kVA_loading_pu' in fresh else None)
    row.update(status='PASS' if row['overall_PASS'] else 'FAILED',label='Fresh / 종합 PASS' if row['overall_PASS'] and row['Fresh_PASS'] else 'Fresh PASS · 종합 미통과' if row['Fresh_PASS'] else 'Fresh FAIL')
   else:row.update(status='FAILED' if result.get('error') else 'VERIFY_ERROR',label='검증 미완료',error=result.get('error'))
  except (OSError,ValueError,KeyError,TypeError) as error:row.update(status='VERIFY_ERROR',label='검증 오류',error=repr(error))
 elif row['status']=='RUNNING':row['label']='실행 중'
 elif row['status'] in ('FAILED','BLOCKED'):row['label']='실행 오류 · Fresh 미검증'
 return row

def details(alive):
 state=read(ROOT/'STATE.json')
 if not state:return dict(available=False)
 rows=[];workers=[]
 for job in state.get('jobs',[]):
  stages=[stage(job['day'],s,job.get('stages',{}).get(s,{})) for s in STAGES]
  frozen=False
  if job.get('M4_freeze'):
   try:frozen=bool(verified(job['M4_freeze']).get('PASS') and all(s['status']=='PASS' for s in stages))
   except (OSError,ValueError,KeyError,TypeError):pass
  rows.append(dict(day=job['day'],status=job['status'],stages=stages,M4_frozen=frozen,actual=actual(job['day'],job.get('actual',{})),error=job.get('error')))
 for identity in state.get('workers',[]):
  case=Path(identity['root']);start=read(case/'START.json');connected=bool(alive(identity) and alive(start) and start.get('pid')==identity.get('pid') and start.get('process_created')==identity.get('process_created'))
  public=identity.get('stage');folder=case/CORE.get(public,'ACTUAL');p=read(folder/'progress.json') or read(case/'progress.json')
  worker=dict(day=identity.get('day'),stage=public,pid=identity['pid'],process_created=identity['process_created'],root=str(case),alive=connected,
   progress=p,age_seconds=age(p.get('UTC')),slot=read(identity.get('request',{}).get('path','__absent__')).get('parallel_actual_slot'))
  if public in CORE:
   bounds=(a_bounds if public.startswith('A') else m_bounds)(folder);worker.update(bounds=bounds)
   if public.startswith('M'):
    k=read(folder/'K48_NATIVE_LEDGER.json');j=read(folder/'JOINT_NATIVE_LEDGER.json');ku,kc=native(k,p,'K48_SEPARATE');ju,jc=native(j,p,'PLANNING_NATIVE')
    worker.update(Native_seconds=ku+ju,Native_completed_seconds=kc+jc,Native_text=f'K48 {ku:.1f} s · Joint {ju:.1f} s')
   else:
    ledger=read(folder/'NATIVE_RUNTIME_LEDGER.json');worker.update(Native_completed_seconds=ledger.get('measured_Native_Runtime'),Native_text='누적 Native '+text(ledger.get('measured_Native_Runtime'))+' s')
  workers.append(worker)
 phase=state.get('phase');slots=[dict(slot=i,status='대기',day=None,pid=None) for i in range(1,8)]
 for w in workers:
  if w['stage']=='ACTUAL' and isinstance(w.get('slot'),int) and 1<=w['slot']<=7:slots[w['slot']-1].update(status='실행 중' if w['alive'] else '프로세스 종료',day=w['day'],pid=w['pid'])
 return dict(available=True,phase=phase,label=LABELS.get(phase,phase),rows=rows,workers=workers,slots=slots,
  planning_pass=sum(r['M4_frozen'] for r in rows),actual_pass=sum(r['actual']['overall_PASS'] is True for r in rows),
  supervisor_alive=alive(state.get('supervisor',{})),coordinator_alive=alive(state.get('lease',{})),
  UTC=state.get('UTC'),age_seconds=age(state.get('UTC')),resources=state.get('resources'),error=state.get('error'),
  state_path=str(ROOT/'STATE.json'),commit_sha=state.get('commit_sha'),all31_M4_verified=len(rows)==31 and all(r['M4_frozen'] for r in rows))

def apply(value,alive):
 value=deepcopy(value)
 try:data=details(alive)
 except Exception as error:data=dict(available=True,label='후속 원장 조회 오류',rows=[],workers=[],slots=[],error=repr(error),planning_pass=0,actual_pass=0)
 value['iteration2_details']=data
 # While the current B2 worker/coordinator runs, all existing primary cards
 # continue to describe it. The new experiment is an in-page follow-up detail.
 if not data.get('available') or value.get('worker_alive') or value.get('coordinator_alive') or data.get('phase') in (None,'WAIT_B2','WAIT_B2_RESOURCES'):return value
 live=[w for w in data['workers'] if w['alive']];phase=data.get('phase');planning=phase and ('PLANNING' in phase or phase=='WAIT_EXISTING_OWN_WORKERS')
 completed=data['planning_pass'] if planning else data['actual_pass']
 value.update(active_experiment='V44_iteration2',run_id='V44 r043 · V44_iteration2 · 2025.05.01~31 · B3',
  status=data['label'],state='COMPLETE' if phase=='COMPLETE' else 'BLOCKED' if phase=='PLANNING_FAILED_ACTUAL_HELD' else 'RUNNING' if data.get('coordinator_alive') else 'DISCONNECTED',
  tone='#d97706' if phase in ('PLANNING_FAILED_ACTUAL_HELD','SUPERVISOR_ERROR') else '#059669' if phase=='COMPLETE' else '#2563eb',
  root=str(ROOT),day='2025년 5월 B3 · '+data['label'],detail='원본 A1/M1/A2 재사용 → M2 → 신규 A3 → M3 → 신규 A4 → M4 → Actual120 / 독립 Fresh120',
  workers=live,worker_alive=bool(live),coordinator_alive=data.get('coordinator_alive'),active_state_source=data['state_path'],active_state_age_seconds=data['age_seconds'],active_commit_sha=data['commit_sha'],
  count_text=('M4 검증 ' if planning else 'Actual/Fresh PASS ')+f'{completed} / 31일',progress_percent=100*completed/31,
  progress_summary=f"M4 동결 {data['planning_pass']}/31 · Actual/Fresh PASS {data['actual_pass']}/31 · 실행 {len(live)}/{'1' if planning else '7'}",
  used_text='현재 단계 대기',remaining_text='기록된 예산 유지',metrics_visible=False,incumbent='—',bound='—',gap='—',steps=[],stage_bounds=[],
  build=dict(visible=False,percent=None,steps=[]),reason=data.get('error') or '',solver_note='동일 V44 r043 모니터 · 31일 M4 검증 이전 Actual 차단 · MESS 4대 · 기존 예산 및 FULL 검증 유지')
 if live:
  w=live[0];case=Path(w['root']);name=w['stage']
  if name in CORE and name.startswith('M'):
   panel=m_panel(case,CORE[name],dict(pid=w['pid']));panel.update(stage=name,arm='B3',budget_label=name+' Native 예산')
   panel['detail']=panel['detail'].replace('M2',name);panel['solver_note']=panel['solver_note'].replace(' B2 ',' B3 ').replace('M2',name)
  else:
   import monitor_binding as binding
   panel=binding.campaign_worker_view(case,dict(day=w['day'],arm='B3',pid=w['pid']),CORE.get(name,'ACTUAL_FRESH'),True)
   panel.update(stage=name,arm='B3')
   for field in ('detail','budget_label','solver_note'):
    if field in panel:panel[field]=panel[field].replace('A2',name) if name.startswith('A') else panel[field].replace('Fresh AC96','Fresh AC120')
  value.update(panel,day=f"{w['day']} · B3 · {name}",root=str(case))
  current=STAGES.index(name) if name in STAGES else len(STAGES)
  value['steps']=[dict(label=s,style='pass' if i<current else 'active' if i==current else '') for i,s in enumerate(STAGES+('Actual/Fresh',))]
  row=next(r for r in data['rows'] if r['day']==w['day'])
  value['stage_bounds']=[dict(stage=s['stage'],ub_text=text(s['UB']),lb_text=text(s['LB']),gap_text=gap_text(s['Gap']),status=s['label'],attempt='',scope='해당 Stage 원본 FULL',source=s.get('root') or '') for s in row['stages'] if s['status']!='QUEUED']
  if name in CORE:
   value.update(display_fields(w['bounds']));value['metrics_label']=name+' 검증 UB / 독립 LB / Global Gap'
   for entry in value['stage_bounds']:
    if entry['stage']==name:entry.update(ub_text=w['bounds']['ub_text'],lb_text=w['bounds']['lb_text'],gap_text=w['bounds']['gap_text'])
 else:value['worker_PID']=None
 # Keep the original execution-detail table connected too after handover.
 from actual_tick_details import row as original_tick
 ticks=[]
 for row in data['rows']:
  a=row['actual'];status='ACTUAL_RUNNING' if a['status']=='RUNNING' else 'PASS' if a['overall_PASS'] else 'ACTUAL_FAILED' if a['status']=='FAILED' else 'PREPARED' if row['M4_frozen'] else 'PREPARING'
  tick=original_tick(dict(day=row['day'],arm='B3',case_root=a.get('root'),status=status))
  if a['status'] in ('PASS','FAILED','VERIFY_ERROR'):tick['state']=a['label']
  current=next((w for w in live if w['day']==row['day']),None)
  if current:
   tick.update(active_stage=current['stage'],pid=current['pid'],worker_alive=True,native_budget=current.get('Native_text','신규 최적화 없음'))
  elif not a.get('root'):tick.update(active_stage='M4 동결' if row['M4_frozen'] else next((s['stage'] for s in row['stages'] if s['status']!='PASS'),'대기'),native_budget='—')
  ticks.append(tick)
 value['actual_tick_details']=dict(rows=ticks,total=31,phase=phase,started=sum(r['actual_started'] for r in ticks),control_complete=sum(r['actual_control_complete'] for r in ticks),completed_control_ticks=sum(r['completed_control_ticks'] or 0 for r in ticks),excluded=0,prepared=data['planning_pass'])
 return value
