"""Read-only active cohort view. No writes to scientific results or old ledgers."""
from pathlib import Path
from copy import deepcopy
import json,hashlib,math
from functools import lru_cache
REGISTRY=Path('D:/MobileESS_V44/runtime/ACTIVE_EQUIPMENT_LEDGER.json')
B3_DAYS={'2025-05-29','2025-05-30'}
B2_DAYS={f'2025-05-{n:02d}' for n in range(22,32)}

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def verified(receipt):
 p=Path(receipt['path']);raw=p.read_bytes()
 if len(raw)!=receipt['bytes'] or hashlib.sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('ACTIVE_RESULT_RECEIPT_MISMATCH:'+str(p))
 return json.loads(raw.decode('utf-8-sig'))

def result_and_audit(job):
 result=verified(job['result'])
 if job['status']!='PASS' and not (job.get('audit') or result.get('independent_audit')):return result,dict(PASS=False)
 audit=verified(job.get('audit') or result['independent_audit'])
 if job['status']=='PASS':
  if result.get('PASS') is not True or audit.get('PASS') is not True:raise ValueError('UNVERIFIED_ACTIVE_PASS')
  if job['arm']=='B3':
   if not all(audit[k]['PASS'] is True for k in ('Actual120','Fresh120','MESS_SOC_PCS_routes','frozen_plan')):raise ValueError('B3_ALL_INDEPENDENT_GATES_REQUIRED')
   if result.get('Frozen_plan_unchanged') is not True or audit.get('Planning_optimization_calls')!=0:raise ValueError('B3_FROZEN_PLAN_REQUIRED')
  elif job['arm']=='B2':
   if audit['independent_Fresh120']['PASS'] is not True or audit['MESS_SOC_PCS_routes']['PASS'] is not True or audit['original_M1_FULL_replay'] is not True:raise ValueError('B2_FULL_PHYSICAL_GATES_REQUIRED')
 return result,audit

@lru_cache(maxsize=64)
def b2_evaluation96(path,expected_sha,size):
 """Measure only D-day; the independent PASS gate still covers all 120 slots."""
 raw=verified(dict(path=path,sha256=expected_sha,bytes=size))
 rows=raw.get('physical_steps',[])
 if (raw.get('prefix_slots')!=24 or raw.get('evaluation_slots')!=96 or
     len(rows)!=120 or [r.get('slot') for r in rows]!=list(range(120))):
  raise ValueError('MONITOR_FRESH96_EXACT_AXIS_REQUIRED')
 peak=-1.;peak_slot=None;peak_element=None
 for row in rows[24:]:
  found=False
  for current in row['full_physical']['currents']:
   if not current['element'].lower().startswith('line.'):continue
   amps=current['current_A'];rating=current['NormalAmps']
   if not math.isfinite(amps) or not math.isfinite(rating) or amps<0 or rating<=0:
    raise ValueError('MONITOR_INVALID_LINE_CURRENT')
   ratio=amps/rating
   if not math.isfinite(current['loading_pu']) or abs(ratio-current['loading_pu'])>1e-6:
    raise ValueError('MONITOR_LINE_CURRENT_RATIO_MISMATCH')
   found=True
   if ratio>peak:peak,peak_slot,peak_element=ratio,row['slot'],current['element']
  if not found:raise ValueError('MONITOR_LINE_CURRENT_MEASUREMENTS_REQUIRED')
 return dict(maximum_line_loading_pu=peak,physical_slots=96,prefix_slots_excluded=24,
             peak_slot=peak_slot,peak_element=peak_element)

def evaluation_loading(arm,audit):
 if audit.get('evaluation96'):return audit['evaluation96']
 if arm=='B2' and audit.get('raw'):
  r=audit['raw'];return b2_evaluation96(r['path'],r['sha256'],r['bytes'])
 # A Fresh120 maximum must never substitute for the daily 96-slot metric.
 return {}

def apply(value,alive,registry=REGISTRY):
 if not Path(registry).exists():return value
 ledger=read(registry)
 if ledger.get('B3_fixed_recovery_PASS') is not True:return value
 value=deepcopy(value);jobs=ledger['jobs'];updates={}
 for j in jobs:
  if j['arm']=='B3' and j['day'] in B3_DAYS:updates[j['day'],j['arm']]=j
  elif j['arm']=='B2' and j['day'] in B2_DAYS and j.get('equipment_version'):updates[j['day'],j['arm']]=j
 details={}
 for key,j in updates.items():
  if j.get('result') and j['status'] in ('PASS','ACTUAL_FAILED','FAILED'):
   result,audit=result_and_audit(j);details[key]=(result,audit)
 cases=value.get('cases',[])
 labels={'PASS':'COMPLETE','BASELINE_RUNNING':'RUNNING','BASELINE_QUEUED':'READY','QUEUED':'READY','ACTUAL_FAILED':'FAILED','FAILED':'FAILED'}
 for c in cases:
  key=c['day'],c['arm']
  if key in updates:
   c.clear();c.update(updates[key],status=labels.get(updates[key]['status'],updates[key]['status']))
 for row in value.get('case_line_loading',{}).get('rows',[]):
  if row.get('scope')!='current':continue
  for cell in row.get('cells',[]):
   key=row['day'],cell['arm']
   if key not in updates:continue
   j=updates[key];pair=details.get(key)
   if pair:
    result,audit=pair;f=evaluation_loading(j['arm'],audit)
    percent=100*f['maximum_line_loading_pu'] if 'maximum_line_loading_pu' in f else None
    passed=j['status']=='PASS' and result['PASS'] and audit['PASS']
    cell.update(percent=percent,physical_pass=bool(passed),tone='pass' if passed else 'fail',
     state='Fresh PASS · 825 kVA' if passed else 'Fresh FAIL · 825 kVA',case_root=j['case_root'],result=j['result'],
     reason='기존 750 kVA 계획·실행궤적 고정, 전력 재계산, Actual120·독립 Fresh120 검증' if j['arm']=='B3' else '825 kVA 신규 M1 및 Actual/Fresh 검증',
     equipment_version=j['equipment_version'],measurement_slots=96,prefix_slots_excluded=24)
   else:
    running=j['status']=='BASELINE_RUNNING'
    progress=j.get('progress') or {}
    cell.update(percent=None,physical_pass=False,tone='live' if running else 'pending',state=(progress.get('stage','실행 중') if running else '대기')+' · 825 kVA',reason='29·30일 B3 검증 통과 후 날짜별 1-worker 실행')
 state=ledger.get('B2_state') or {};live=[]
 for j in jobs:
  if j['status']!='BASELINE_RUNNING':continue
  p=Path(j['case_root'])/'START.json';identity=read(p) if p.exists() else {}
  if alive(identity):live.append(dict(day=j['day'],arm=j['arm'],pid=identity['pid'],worker_slot=1,campaign_root=ledger['B2_root']))
 lease=state.get('lease') or {};coordinator_alive=alive(lease)
 passed=sum(j['status']=='PASS' for j in jobs);failed=sum(j['status'] in ('ACTUAL_FAILED','FAILED','EXCLUDED') for j in jobs)
 running=len(live);total=len(jobs);done=passed+failed
 stage=''
 for j in jobs:
  if j['status']=='BASELINE_RUNNING':stage=(j.get('progress') or {}).get('stage','시작 중')
 complete=state.get('phase')=='COMPLETE'
 status='29·30일 B3 Fresh PASS · B2 22~31일 '+('완료' if complete else '순차 실행' if coordinator_alive else '자동 시작 대기')
 value.update(cases=cases,run_id='V44 · 활성 설비 원장 · 5월 22~31일',state='COMPLETE' if complete else 'RUNNING' if coordinator_alive else 'READY',
  status=status,completed=passed,failed=failed,pending=max(0,total-done-running),total_dates=total,
  workers=live,last_reported_workers=[],coordinator_alive=coordinator_alive,worker_alive=bool(live),
  Actual_paused_by_user=False,Actual_auto_start_armed=not complete,
  day=(live[0]['day']+' · B2 · '+stage) if live else '29·30일 B3 고정계획 재검증 완료',
  detail='기존 750 kVA FAIL은 감사 원장에 보존 · 활성 B3 결과는 검증된 825 kVA 결과',
  reason='',tone='#059669',count_text=f'활성 결과 종료 {done} / {total}건',progress_percent=100*done/total,
  progress_summary=f'PASS {passed} · 실패 {failed} · 실행 {running}/1 · B3 29·30일 825 kVA 검증 완료',
  metrics_visible=False,build=dict(visible=False,percent=0,current_percent=0,steps=[]),steps=[],
  equipment_active_ledger=str(registry),archived_failure_evidence=ledger['superseded_failures'],monitor_read_only=True)
 summary=value.setdefault('campaign_summary',{})
 summary.update(phase=ledger['phase'],phase_label=status,actual_running=int(bool(live) and 'ACTUAL' in stage),planning_running=int(bool(live) and 'M1' in stage),actual_failed=failed,actual_passed=passed,actual_workers=1,coordinator_alive=coordinator_alive,stale_workers=0,auto_start_armed=not complete)
 note=[status,'B3 29·30일: 원래 750 kVA AIDC·MESS 계획 및 Actual 궤적 고정 · 재최적화 0회 · 공통 변압기 825 kVA',
  'Actual120 고정궤적 AC 재생 + 별도 엔진 독립 Fresh120 · SOC/PCS/이동/전력 재계산 검증',
  'B2: 22→31일 날짜별 M1→Actual/Fresh · 1-worker · Planning 0.95~1.05 pu',
  'B0/B1 및 나머지 B3 결과는 기존 원장 그대로이며, 전체 Arm이 동일 설비인 공식 비교 완료를 뜻하지 않습니다.',
  '이전 750 kVA 및 재최적화 825 kVA FAIL은 감사 원장에 보존']
 for key in sorted(details):
  result,audit=details[key]
  if key[1]=='B3':
   f=audit['Fresh120'];note.append(f"{key[0]} B3 · Fresh {'PASS' if f['PASS'] else 'FAIL'} · V {f['voltage_min_pu']:.6f}~{f['voltage_max_pu']:.6f} pu · 최대 변압기 {100*f['maximum_transformer_kVA_loading_pu']:.3f}%")
 if live:note.append(live[0]['day']+' B2 · '+stage+' · PID '+str(live[0]['pid']))
 value['solver_note']='\n'.join(note)
 ticks=value.get('actual_tick_details') or {}
 for t in ticks.get('rows',[]):
  key=t.get('day'),t.get('arm')
  if key in details and key[1]=='B3':t.update(state='검증 완료 · 825 kVA',actual_control_complete=True,worker_alive=False,pid=None,actual_slot_position=120)
 value['case_line_loading']['history_warning']='활성 B3 05/29·05/30은 기존 계획+825 kVA 검증 결과 · 다른 Arm의 설비 버전은 개별 원장 참조'
 from active_runtime import connect
 return connect(value,ledger,alive)

