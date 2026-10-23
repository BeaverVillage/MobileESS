"""V2_add journals in the existing read-only monitor."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import ast,json,hashlib,time,math
import psutil
BASE=Path('D:/ChatGPT/Mobile ESS 2')
RUN=BASE/'V2_add_runtime/static_complete'
H=RUN/'optimization_20261023'
OUT=BASE/'V2_add/docs/v2_add/static_complete'
CHAINS={'B0':('REFERENCE','ACTUAL','FRESH'),'B1':('A1','ACTUAL','FRESH'),'B2':('REFERENCE','K48_M1','M1','ACTUAL','FRESH'),'B3':('A1_REUSE','K48_M1','M1','A2','K48_M2','M2','ACTUAL','FRESH')}
LABEL={'PASS':'통과','COMPLETE':'완료','RUNNING':'진행 중','FAIL':'검증 오류','BLOCKED':'차단','QUEUED':'대기'}
_cache={};_process_cache=(0,[])
def read(path):
 p=Path(path)
 try:
  st=p.stat();key=(st.st_size,st.st_mtime_ns);old=_cache.get(str(p))
  if old and old[0]==key:return old[1]
  if st.st_size>32*1024**2:raise ValueError('MONITOR_JSON_TOO_LARGE')
  v=json.loads(p.read_text(encoding='utf-8-sig'));_cache[str(p)]=(key,v);return v
 except FileNotFoundError:return {}
def tail(path,limit=4096):
 try:
  with Path(path).open('rb') as f:f.seek(0,2);f.seek(max(0,f.tell()-limit));return f.read().decode('utf8',errors='replace')
 except OSError:return ''
def number(v):return float(v) if isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) else None
def text(v):return '—' if number(v) is None else f'{v:.6f}'
def gap(v):return '—' if number(v) is None else f'{100*v:.3f}%'
def processes():
 global _process_cache
 if time.monotonic()-_process_cache[0]<4:return _process_cache[1]
 found=[]
 for p in psutil.process_iter(['pid','name','cmdline','create_time']):
  try:
   i=p.info;args=i['cmdline'] or [''];cmd=' '.join(args)
   if i['name'].lower()!='python.exe' or '.venv\\scripts\\python.exe' in args[0].lower():continue
   module='-m' in args and args[args.index('-m')+1].startswith('v2_add_preflight.')
   operator=any(Path(a).name in ('replay_sequence.py','post_replay_canaries.py','complete_preparation_and_launch.py','replay_native0.py') and str(H).lower() in a.lower() for a in args)
   direct='-c' in args and 'from v2_add_preflight.stage_m_validator_fixture import certify' in args[args.index('-c')+1]
   if direct:
    parents=p.parents()[:2]
    direct=any('replay_sequence.py' in ' '.join(parent.cmdline()) and str(H).lower() in ' '.join(parent.cmdline()).lower() for parent in parents)
   if not module and not operator and not direct:continue
   cpu=p.cpu_times()
   found.append(dict(pid=i['pid'],process_created=i['create_time'],command=cmd,
    age_seconds=max(0.,time.time()-i['create_time']),CPU_seconds=cpu.user+cpu.system,
    waiting=any(t in cmd for t in ('replay_sequence.py','post_replay_canaries.py','complete_preparation_and_launch.py'))))
  except (psutil.Error,AttributeError,TypeError):continue
 _process_cache=(time.monotonic(),found);return found
def validations():
 rows=[]
 for script,journal,group in (('replay_sequence.py','SEQUENTIAL_REPLAY_STATE.json','Native0 / FULL / Handler'),('post_replay_canaries.py','POST_REPLAY_STATE.json','수치 실행 / 최종 연결')):
  known={r['name']:r for r in read(H/journal).get('steps',[])}
  tree=ast.parse((H/script).read_text(encoding='utf8'))
  jobs=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='jobs' for t in n.targets))
  for item in jobs.elts:
   name=item.elts[0].value;row=dict(known.get(name,{}));row.update(name=name,group=group,status=row.get('status','QUEUED'))
   row['detail']=tail(row.get('log') or H/('POST_'+name+'.log'),1800) if row['status'] in ('RUNNING','FAIL') else ''
   rows.append(row)
 return rows
def native(folder,stage,live):
 name='NATIVE_RUNTIME_LEDGER.json' if stage in ('A1','A2') else 'K48_NATIVE_LEDGER.json' if stage.startswith('K48_') else 'JOINT_NATIVE_LEDGER.json'
 ceiling=7200 if stage in ('A1','A2') else 300 if stage.startswith('K48_') else 3600 if stage in ('M1','M2') else 0
 d=read(folder/name) if ceiling else {};paid=number(d.get('measured_Native_Runtime')) or 0.
 return dict(measured=paid,ceiling=ceiling,remaining=max(0.,ceiling-paid),inflight=bool(d.get('inflight')),
  text=f'{paid:.1f} / {ceiling} s'+(' · 호출 중' if live and d.get('inflight') else '') if ceiling else 'Native 차감 없음',ledger=str(folder/name) if ceiling else None)
def stage(root,arm,name,alive,owner=None):
 folder=root/'2025-05-01'/arm/name;a=read(root/'CONTROL'/arm/(name+'_ACTIVE_ATTEMPT.json'))
 attempt=Path(a['path']) if a.get('path') else folder
 if not attempt.resolve().is_relative_to(root.resolve()):raise ValueError('ONLY_CURRENT_V2_RUNTIME_ALLOWED')
 c=read(folder/'CHECKPOINT.json');result=c.get('result') or read(attempt/'RESULT.json');failure=read(folder/'FAILURE.json');started=read(attempt/'START.json')
 status='COMPLETE' if c.get('status')=='COMPLETE' else 'BLOCKED' if failure else 'RUNNING' if attempt.exists() else 'QUEUED'
 if status=='COMPLETE':
  sha=hashlib.sha256(json.dumps({k:v for k,v in c.items() if k!='checkpoint_sha'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  if sha!=c.get('checkpoint_sha') or result.get('PASS') is not True:status='BLOCKED';failure={'error':'CHECKPOINT_RESULT_SHA_OR_PASS_DRIFT'}
 connected=alive(started or owner or {});b={}
 for line in reversed(tail(attempt/'GLOBAL_CONTROL/GLOBAL_GAP_TRACE.jsonl',32768).splitlines()):
  try:b=json.loads(line);break
  except ValueError:continue
 s=dict(stage=name,status=status,label=LABEL.get(status,status),root=str(attempt),Native=native(attempt,name,connected),
  UB=result.get('UB',result.get('global_UB',result.get('Global_UB',b.get('Global_UB')))),LB=result.get('LB',result.get('global_LB',result.get('Global_LB',b.get('Global_LB')))),Gap=result.get('certified_gap',result.get('Global_Gap',b.get('Global_Gap'))),
  costs=read(attempt/'STAGE_COSTS.json') or result.get('execution_costs',{}),error=failure.get('error'),pid=started.get('pid'),worker_alive=connected,
  case_sha=result.get('case_sha'),reused_exact_A1=result.get('reused_exact_A1') is True,B1_A1_result_sha=result.get('B1_A1_result_sha'),
  gap_certified=bool(result.get('global_gap_certified') or b.get('global_gap_certified')),
  FULL_feasible=result.get('FULL_feasible') is True)
 if name in ('A1','A2','A1_REUSE'):
  g=number(result.get('certified_gap'))
  s['gap_certified']=bool(s['FULL_feasible'] and result.get('independent_Global_LB_validated') and g is not None and 0<=g<=.005)
 if name in ('A1','A2') and attempt.exists():
  from bound_details import a_bounds,number as fraction_number
  bounds=a_bounds(attempt);s.update(UB=bounds['UB'],LB=bounds['LB'],Gap=bounds['relative_gap'],gap_certified=bounds['gap_certified'])
  phi=read(attempt/'OUTPUT/PHASE_I_TRACE.json').get('trajectory',[])
  zero=read(attempt/'OUTPUT/PHASE_I_ZERO_CERTIFICATE.json')
  s['phase_I']=dict(Phi=fraction_number(phi[-1].get('exact_Phi',phi[-1].get('Phi'))) if phi else None,zero_PASS=zero.get('PASS') is True)
 if name=='FRESH' and status=='COMPLETE':
  rr=result.get('settled_tick_results',[])
  if rr:
   f=rr[-1];s['physical']=dict(Vmin=f.get('Vmin'),Vmax=f.get('Vmax'),line_percent=100*f['rho_global'] if number(f.get('rho_global')) is not None else None,PASS=f.get('PASS'))
 return s
def preparation_build(prep,workers):
 build=dict(visible=False,steps=[])
 if not any(r['name']=='A2_Native0_after' and r['status']=='RUNNING' for r in prep):return build
 worker=next((p for p in workers if 'v2_add_preflight.stage_a_canary A2' in p['command']),None)
 if not worker:return build
 candidates=[p for p in (RUN/'stage_integration/A2').glob('ORIGINAL_P1*/MODEL_BUILD_DETAIL.json') if p.stat().st_mtime>=worker['process_created']]
 if not candidates:return build
 path=max(candidates,key=lambda p:p.stat().st_mtime_ns);d=read(path)
 stamp=d.get('build_detail_UTC')
 updated=datetime.fromisoformat(stamp).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST') if stamp else '—'
 count=d.get('physical_classes_complete',0)
 return dict(visible=True,label='A2 · 전체 원본 모델 준비',percent=None,percent_label=f'물리 도메인 {count} / 117',
  detail=f"현재: {d.get('build_function','준비 중')}\n모델 준비 {d.get('model_preparation_seconds',0):.1f} s · Native 호출 {d.get('Native_calls',0)}회\n갱신 {updated}",
  percent_scope='물리 도메인 생성 개수이며 전체 검증 완료율과 별도입니다. 이후 전체 Native 블록·독립 검증이 이어집니다.',steps=[])
def apply(value,alive):
 prep=validations();control=read(H/'PREPARE_AND_LAUNCH_STATE.json');ps=processes()
 root=Path(control.get('official_root',RUN/'official_stage_campaign/May01_20261023_after_execution_checks'))
 if not root.resolve().is_relative_to((RUN/'official_stage_campaign').resolve()):raise ValueError('OFFICIAL_ROOT_DRIFT')
 official=(root/'CAMPAIGN_INPUT_IDENTITY.json').exists();coordinator=any('complete_preparation_and_launch.py' in p['command'] and alive(p) for p in ps)
 owner=next((p for p in ps if 'complete_preparation_and_launch.py' in p['command'] and alive(p)),None)
 if official and owner:owner['waiting']=False
 rows=[dict(arm=arm,stages=[stage(root,arm,name,alive,owner) for name in chain]) for arm,chain in CHAINS.items()]
 flat=[s for r in rows for s in r['stages']];current=next((dict(s,arm=r['arm']) for r in rows for s in r['stages'] if s['status']=='RUNNING'),None)
 state=control.get('status','WAITING_REQUIRED_EXECUTION_CHECKS');running=[r for r in prep if r['status']=='RUNNING'];errors=[r for r in prep if r['status']=='FAIL']
 done=sum(r['status']=='PASS' for r in prep);completed=sum(s['status']=='COMPLETE' for s in flat)
 if errors or state=='BLOCKED_WITH_PRESERVED_EVIDENCE':status='필수 검증 오류 · 공식 실행 보류';tone='#dc2626'
 elif official:status='May01 공식 캠페인 실행 중' if coordinator else '공식 실행 프로세스 확인 필요';tone='#2563eb' if coordinator else '#d97706'
 else:status='필수 검증 진행 중' if running else '실행 전 최종 검증 대기';tone='#2563eb'
 if state=='OFFICIAL_CAMPAIGN_RETURNED':status='May01 캠페인 처리 종료';tone='#059669' if all(r['status']=='COMPLETE' for r in control.get('results',[])) else '#d97706'
 label=f"{current['arm']} · {current['stage']}" if official and current else running[0]['name'] if running else status
 budget=current['Native'] if official and current else {}
 numerical=[read(OUT/n) for n in ('ISOLATED_NUMERICAL_CANARY_20261023.json','A1_ISOLATED_NUMERICAL_CANARY_20261023.json')]
 details=dict(available=True,label=status,phase=state,official_campaign_started=official,preparation=prep,preparation_pass=done,preparation_total=len(prep),
  rows=rows,workers=ps,worker_count=1,coordinator_alive=coordinator,official_root=str(root),error=control.get('error'),
  current_validation_process=next((p for p in ps if not p['waiting']),None),
  A1_preparation=read(OUT/'A1_ORIGINAL_P1_FULL_PREPARATION.json').get('PASS') is True,
  timing_authority=read(OUT/'A_STAGE_R043_TIMING_AUTHORITY_20261023.json').get('PASS') is True,
  official_measured_Native_seconds=sum(s['Native']['measured'] for s in flat),diagnostic_Native_optimize_calls=sum(v.get('diagnostic_Native_optimize_calls',0) for v in numerical),
  B3_A1_source='B1.A1 · 같은 날짜/입력/Source/FULL/Gap/SHA 필수',budgets=dict(A1=7200,A2=7200,K48=300,Joint=3600,Joint_call=300),memory_information_only=True)
 return dict(active_experiment='V2_add',run_id='V2_add · IEEE8500 · 2025.05.01 · B0 / B1 / B2 / B3',monitor_read_only=True,v2_add_details=details,state=state,status=status,tone=tone,
  root=str(root) if official else str(H),day='May01 · '+label,detail='B3 A1은 B1 FULL 결과 재사용 · Planning96 → Actual120 → 독립 Fresh120',
  count_text=f'완료 Stage {completed}/{len(flat)}' if official else f'검증 {done}/{len(prep)}',progress_percent=100*(completed/len(flat) if official else done/len(prep)),
  progress_summary=f'필수 검증 {done}/{len(prep)} · '+('공식 실행 중' if official else '공식 최적화 시작 전'),
  used_text=budget.get('text','공식 Native 0초 · 준비/격리 진단과 구분'),remaining_text=f"남은 Native {budget['remaining']:.1f} s" if budget.get('ceiling') else '검증 종료 후 B0 → B1 → B2 → B3',
  budget_label='V2_add · '+(current['stage'] if current else '실행 예산'),budget_cap='A1/A2 각 7200 s · K48 각 300 s 별도 · Joint 각 3600 s / 단일 300 s',
  metrics_visible=bool(current and current['stage'] in ('A1','A2','M1','M2')),incumbent=text(current['UB']) if current else '—',bound=text(current['LB']) if current else '—',gap=gap(current['Gap']) if current else '—',
  stage_bounds=[dict(stage=r['arm']+'.'+s['stage'],ub_text=text(s['UB']),lb_text=text(s['LB']),gap_text=gap(s['Gap']),status=s['label']) for r in rows for s in r['stages'] if s['status']!='QUEUED'],
  metrics_label='현재 공식 Case · FULL UB / 독립 Global LB',bound_details=dict(lines=['최종 FULL 수용과 Global Gap 인증을 구분합니다. 격리 검증 값은 공식 결과에 포함하지 않습니다.']),
  loading_label='현재 공식 Arm · 독립 Fresh120 물리 결과',line_loading=dict(text='공식 결과 대기',note='전체 선로·전압·변압기 및 Prefix24 + 평가96 검사'),
  steps=[dict(label=r['arm'],style='pass' if all(s['status']=='COMPLETE' for s in r['stages']) else 'active' if any(s['status']=='RUNNING' for s in r['stages']) else '') for r in rows],
  build=preparation_build(prep,ps),reason=control.get('error') or (errors[0]['detail'] if errors else ''),
  solver_note='Worker 1 · A Threads 1 / M Threads 4 · A Gap 0.5% / M Gap 3%\nNative 측정 Runtime만 차감 · 모델 생성/검증 Wall/CPU 별도\nRAM은 정보용 · 숫자 기준 진입 거부/중단 없음\nIEEE8500 Balanced Source-YY · BG2 · GPU780 · AIDC12 / STA12 · MESS8 · Actual SVR3',
  worker_alive=any(not p['waiting'] and alive(p) for p in ps),coordinator_alive=coordinator)
