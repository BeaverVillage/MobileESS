"""Bind V43 journals to the existing PR189 monitor server and screen.

No solver, worker dispatch, scientific writes, or new HTML/UI. Label-only
substitutions make the original one-arm screen show its actual May01 scope.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import inspect
import json
import sys
import time

import psutil

from v43.common import DOC, ROOT, RUNS, read, record, atomic, now


def optional(path):
    try:
        return read(path)
    except (OSError, ValueError):
        return {}


def seconds_since(stamp):
    try:
        return max(0., time.time()-datetime.fromisoformat(stamp).timestamp())
    except (ValueError, TypeError):
        return None


def display_number(value):
    return format(value, '.8g') if isinstance(value, (float, int)) else '—'


def elapsed(value):
    if value is None:return '—'
    seconds=max(0,int(value));minutes,seconds=divmod(seconds,60);hours,minutes=divmod(minutes,60)
    return f'{hours}시간 {minutes:02d}분 {seconds:02d}초' if hours else f'{minutes}분 {seconds:02d}초'


def live_native(ledger,progress,kind):
    measured=ledger.get('measured_Native_Runtime',0.) or 0.
    if progress.get('budget_kind')==kind:
        measured=max(measured,progress.get('Native_Runtime',0.) or 0.)
    return measured


def m_view(root,attempt_override=None):
    cp = read(DOC/'CHECKPOINT.json')
    attempt = Path(attempt_override or cp.get('active_attempt') or cp['B2_last_attempt'])
    is_v44='MobileESS_V44' in str(attempt)
    joint_cap=900. if is_v44 else 1800.
    start = optional(attempt/'START.json')
    heartbeat = optional(attempt/'HEARTBEAT.json')
    progress = optional(attempt/'progress.json')
    result = optional(attempt/'RESULT.json')
    lower = optional(attempt/'K48_NATIVE_LEDGER.json')
    joint = optional(attempt/'JOINT_NATIVE_LEDGER.json')
    alive = False
    cpu, rss = None, None
    try:
        proc = psutil.Process(start['pid'])
        alive = proc.create_time() == start['process_created'] and proc.is_running()
        if alive:
            cpu, rss = sum(proc.cpu_times()[:2]), proc.memory_info().rss
    except (psutil.Error, KeyError):
        pass
    trace = attempt/'GLOBAL_CONTROL/GLOBAL_GAP_TRACE.jsonl'
    bounds = {}
    if trace.is_file():
        # The last complete append-only record, never a restricted solver bound.
        for line in trace.read_text(encoding='utf8').splitlines():
            try:
                bounds = json.loads(line)
            except ValueError:
                pass
    k_used = live_native(lower,progress,'K48_SEPARATE')
    j_used = live_native(joint,progress,'PLANNING_NATIVE')
    used = k_used+j_used
    age = seconds_since(heartbeat.get('UTC') or progress.get('UTC') or start.get('UTC'))
    terminal = bool(result)
    error = result.get('error')
    implementation_error=bool(error or result.get('implementation_errors') or result.get('M_stage_execution_PASS') is False)
    state = ('FAIL' if implementation_error else 'PASS' if result.get('global_gap_certified') else
        'FULL_FEASIBLE_GAP_NOT_CERTIFIED' if result.get('FULL_feasible') else 'NO_FULL_SOLUTION') if terminal else 'STALE' if alive and (age is None or age>30) else 'RUNNING' if alive else 'DISCONNECTED'
    phase = progress.get('phase', 'WAITING_FOR_FIRST_REPORT')
    iterations=sorted((attempt/'COMMON_M_PR222').glob('ITERATION_*'))
    iteration=iterations[-1].name.rsplit('_',1)[-1].lstrip('0') or '0' if iterations else '—'
    pool_ready=bool(iterations and (iterations[-1]/'POOL.json').is_file())
    inflight=bool(progress.get('inflight'))
    kind=progress.get('budget_kind')
    model_done=(attempt/('BINARY_STAGE_CHECKPOINT.json' if is_v44 else 'NATIVE0_CERTIFICATION.json')).is_file()
    lower_done=(attempt/'LOWER_STAGE_RESULT.json').is_file()
    upper_done=(attempt/'UPPER_STAGE_RESULT.json').is_file()
    if terminal:phase_label='M1 실행 종료'
    elif kind=='PLANNING_NATIVE' and joint:
        phase_label='Joint 최적화 계산 중' if inflight else 'FULL 해 검산 · 다음 후보 준비'
    elif kind=='K48_SEPARATE' and not lower_done:phase_label='K16 → K32 → K48 독립 하한 계산 중'
    elif phase=='ADAPTIVE_BEAM_FOUR_DIRECT_JOINT':phase_label='Beam 후보 생성 · Joint 모델 준비'
    elif not model_done:phase_label='원본 모델 생성 · Native0 검증 중'
    else:phase_label='MESS 후보·최적화 준비 중'
    if is_v44 and lower_done and not upper_done and kind!='PLANNING_NATIVE':
        phase_label='K48 종료 · Beam 후보 생성 / Joint 준비 중'
    if not model_done:
        phase_label={'M_ORIGINAL_MODEL_BUILD':'원본 FULL 물리 모델 구성 중',
            'M_EXISTING_COMPACT_STATIC_PRESOLVE':'Compact 완료 · 기존 정적 Presolve 중',
            'M_BUILD_COMPLETE':'원본 Transport·Case SHA 검산 중'}.get(phase,phase_label)
        if is_v44 and (attempt/'INHERITED_MATHEMATICAL_CASE_IDENTITY.json').exists():
            phase_label='원본 제약 동등성 통과 · Case SHA 및 K16 준비'
        elif is_v44 and (attempt/'ORIGINAL_DOMAIN_EQUIVALENCE.json').exists():
            phase_label='원본 제약 동등성 통과 · Binary 행렬 저장 중'
    detail=f'{phase_label} · 반복 {iteration}' if iterations else phase_label
    if terminal:
        detail = 'B2 M1 · '+result.get('status', state)
    ub = bounds.get('Global_UB')
    lb = bounds.get('Global_LB')
    gap = bounds.get('Global_Gap')
    wall = result.get('wall_seconds') if terminal else seconds_since(start.get('UTC'))
    remaining = max(0., 300-k_used)+max(0., joint_cap-j_used)
    report_age=seconds_since(progress.get('UTC'))
    calls_k=len(lower.get('calls',[]));calls_j=len(joint.get('calls',[]))
    activity=f'Native 실행 중 ({"Joint" if kind=="PLANNING_NATIVE" else "K48"})' if inflight else 'Native 호출 사이: 검산·후보 준비'
    note = (f'Worker PID {start.get("pid", "—")} · {"정상 생존" if alive else "종료 / 연결 확인 필요"}'
            f'\nHeartbeat {display_number(age)}초 전 · 계산 보고 {display_number(report_age)}초 전'
            f'\n전체 경과 {elapsed(wall)} · CPU 누적 {elapsed(cpu)} · Worker RAM {rss/2**30:.2f} GB' if rss is not None else
            f'Worker PID {start.get("pid", "—")} · 전체 경과 {elapsed(wall)}')
    note+=(f'\nK48 {k_used:.1f} / 300초 · Joint {j_used:.1f} / {joint_cap:,.0f}초 (진행 중 Runtime 포함)'
            f'\n완료 Native 호출 K48 {calls_k}회 · Joint {calls_j}회 · {activity}'
            '\n남은 시간은 Native 계산 예산이며, 전체 종료 예상시간이 아닙니다.'
            '\n독립 Global LB만 표시 · 제한 후보 Pool ObjBound는 승격하지 않음'
            '\nActual/Fresh96: 별도 지시 전 실행 보류 · B1 Known 연구 정책: 구현만 완료')
    loading = dict(text=f'{ub*100:.3f}%', note='FULL 검증 Planning UB · 실제 Actual/Fresh 부하율과 별개') if ub is not None else dict(text='FULL 해 검산 대기',note='미검증 Solver 후보는 인증 UB로 표시하지 않습니다.')
    mem = psutil.virtual_memory()
    labels = [('모델·Native0',model_done),('K48 하한',lower_done),('Beam 후보',pool_ready),
              ('Joint 최적화',upper_done),('최종 검산',terminal and not implementation_error)]
    done_count=sum(passed for _,passed in labels)
    active=next((i for i,(_,passed) in enumerate(labels) if not passed),None)
    status_labels=dict(FAIL='오류 · 복구 필요',PASS='목표 Gap 달성',RUNNING='계산 진행 중',STALE='Worker 생존 · heartbeat 지연',
        DISCONNECTED='Worker 연결 확인 필요',FULL_FEASIBLE_GAP_NOT_CERTIFIED='종료 · FULL 해 있음 / Gap 미달',NO_FULL_SOLUTION='종료 · FULL 해 없음')
    current_used,current_cap=(j_used,joint_cap) if joint else (k_used,300.)
    budget_pct=min(100.,100*current_used/current_cap)
    remaining_note=f'목표 Gap 3% · 현재 {gap*100:.3f}%'+(' · 목표 미달' if gap>.03 else ' · 목표 달성') if gap is not None else 'FULL 검증 해 대기 · 목표 Gap 3%'
    value=dict(status=status_labels[state],
        tone='#dc2626' if state=='FAIL' else '#d97706' if state in ('STALE','DISCONNECTED','FULL_FEASIBLE_GAP_NOT_CERTIFIED','NO_FULL_SOLUTION') else '#059669',
        run_id='V43 · '+attempt.name, root=str(attempt),completed=int(state=='PASS'),failed=int(state=='FAIL'),
        timeout=0,pending=int(not terminal),total_dates=1,day='B2 · May01 · M1',detail=detail,
        count_text=f'{done_count} / 5단계 완료',progress_percent=100*done_count/5,
        progress_summary=remaining_note+' · Actual/Fresh96 실행 보류',
        used=used,remaining=remaining,incumbent=display_number(ub),bound=display_number(lb),
        gap=f'{gap*100:.3f}%' if gap is not None else '—',line_loading=loading,
        steps=[dict(label=label,style='pass' if passed else 'fail' if state=='FAIL' and i==active else 'active' if alive and i==active else '')
               for i,(label,passed) in enumerate(labels)],
        solver_note=note,reason=error or '',ram=f'여유 {mem.available/2**30:.1f} / {mem.total/2**30:.1f} GB',
        updated=datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S KST'),
        build=dict(visible=not terminal,percent=budget_pct,current_percent=budget_pct,done=0,total=0,
                   label=('Joint' if joint else 'K48')+' Native 예산 사용',
                   detail=f'{current_used:.1f} / {current_cap:,.0f}초 사용 · {activity}',
                   percent_scope='예산 소모율 · 작업 완료율/예상 종료시간 아님',steps=[]),
        worker_alive=alive,worker_PID=start.get('pid'),heartbeat_age=age,
        telemetry_only=True,source_attempt=str(attempt),state=state,
        K48_Native_seconds=k_used,Joint_Native_seconds=j_used,Native_inflight=inflight,
        refresh_interval_seconds=1,solver_report_age_seconds=report_age,raw_phase=phase)
    if not model_done:
        value['build'].update(label=phase_label,percent=None,current_percent=None,
            detail='Native 최적화 전 구성 단계 · '+elapsed(wall)+' 경과',
            percent_scope='모델 구성 완료율/종료시간은 추정하지 않음')
    return value


def forecast_view():
    """Read the existing seven independent Forecast journals, without dispatch."""
    base=Path('D:/MobileESS_V44/runtime/svr11_revision01')
    active=optional(base/'FORECAST_ACTIVE.json')
    cohort=Path(active.get('group',str(base/'FORECAST_PARALLEL_MAY02_07')))
    if not (cohort/'REQUEST.json').exists():return None
    request=optional(cohort/'REQUEST.json');processes=optional(cohort/'PROCESSES.json').get('processes',{})
    rows=[]
    for number in range(1,8):
        day=f'2025-05-{number:02d}'
        folder=(base/'models' if number==1 else Path(request.get('models_root',str(base/'models'))))/day
        generation=optional(folder/'MODEL_GENERATION_PROGRESS.json')
        started=request.get('existing_May01',{}) if number==1 else optional(cohort/day/'START.json')
        result=optional(cohort/day/'RESULT.json') if number!=1 else {}
        certificate=optional(base/'inputs'/day/'SVR11_INPUT_READY.json')
        count=generation.get('completed_slots',len(list(folder.glob('SLOT_*.json'))));pid=started.get('pid');live=False;rss=cpu=0.
        try:
            proc=psutil.Process(pid)
            live=proc.is_running() and abs(proc.create_time()-started['process_created'])<.001
            if live:rss=proc.memory_info().rss;cpu=sum(proc.cpu_times()[:2])
        except (psutil.Error,KeyError,TypeError):pass
        failed=result.get('PASS') is False
        state='완료' if certificate.get('PASS') else '오류' if failed else '계산 중' if live else '연결 확인'
        rows.append(dict(day=day,pid=pid,live=live,completed_slots=96 if certificate.get('PASS') else count,
            complete=bool(certificate.get('PASS')),failed=failed,state=state,rss=rss,cpu=cpu,
            physical_solves=generation.get('physical_solves',0),error=result.get('error','')))
    count=sum(r['completed_slots'] for r in rows);done=sum(r['complete'] for r in rows)
    failures=[r for r in rows if r['failed']];active=sum(r['live'] for r in rows)
    memory=psutil.virtual_memory();pct=100*count/(7*96)
    notes=[f"May{r['day'][-2:]} · {r['completed_slots']}/96 · {r['state']} · PID {r['pid'] or '—'}"
        +(f" · RAM {r['rss']/2**30:.2f} GB" if r['live'] else '') for r in rows]
    value=dict(status='Forecast 오류 확인 필요' if failures else 'Forecast 계수 생성 완료' if done==7 else 'SVR11 Forecast 병렬 생성 중',
        tone='#dc2626' if failures else '#059669',run_id='V44 · SVR11 · May01~07 Forecast',
        root=str(base),completed=done,failed=len(failures),timeout=0,pending=7-done,total_dates=7,
        day='SVR11 · 7일 Forecast 계수 생성',detail=f'날짜별 독립 worker {active}개 생존 · 완료 {done}/7일',
        count_text=f'{count} / 672슬롯 완료',progress_percent=pct,
        progress_summary=f'May01 유지 + May02~07 6-worker · 완료 {done}/7일 · Actual/최적화 실행 0회',
        used=count,remaining=672-count,used_text=f'완료 {count}슬롯',remaining_text=f'남은 {672-count}슬롯',
        incumbent='실행 안 함',bound='실행 안 함',gap='해당 없음',
        line_loading=dict(text='물리 인증 대기',note='Forecast 국소 계수 생성은 Actual/Fresh96 안전 PASS가 아닙니다.'),
        steps=[dict(label=f"May{r['day'][-2:]} {r['completed_slots']}/96",style='pass' if r['complete'] else 'fail' if r['failed'] else 'active' if r['live'] else '') for r in rows],
        solver_note='\n'.join(notes)+'\n\n모든 날짜: SVR11 11뱅크 / RegControl 40개 · 독립 Native TIME prefix'
            +'\nForecast만 사용 · Actual 관측/Tap/Queue 읽기 0회 · 엔진 상태 공유 없음'
            +'\n기존 7-Reg B2 결과는 과거 결과로 보존 · 현재 V44 결과로 재사용하지 않음',
        reason='\n'.join(f"{r['day']}: {r['error']}" for r in failures),
        ram=f"worker 합계 {sum(r['rss'] for r in rows)/2**30:.2f} GB · 여유 {memory.available/2**30:.1f} / {memory.total/2**30:.1f} GB",
        updated=datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S KST'),
        build=dict(visible=True,percent=pct,current_percent=pct,done=count,total=672,
            label='7일 전기계수 생성',detail=f'완료된 슬롯 {count}/672 · 생존 worker {active}개',
            percent_scope='완료 슬롯 비율 · 슬롯마다 계산량이 달라 시간 완료율/ETA가 아닙니다.',steps=[]),
        worker_alive=active>0,state='FAILED' if failures else 'COMPLETE' if done==7 else 'RUNNING',
        telemetry_only=True,refresh_interval_seconds=1,forecast_days=rows)
    if done==7:
        short=base/'PHYSICAL_DRIVER_SHORT_PREFIX001'
        progress=optional(short/'PROGRESS.json');result=optional(short/'RESULT.json');error=optional(short/'FAILURE.json')
        start=optional(short/'START.json');completed=progress.get('completed',[])
        checks=[('2025-05-01',arm) for arm in ('B0','B1','B2','B3')]+[(f'2025-05-{n:02d}','B2') for n in range(2,8)]
        current=checks[min(len(completed),len(checks)-1)];finished=bool(result)
        value.update(status='최소 물리 Driver 오류' if error else '최소 물리 연결 검사 완료 · FULL Case 인증 대기' if finished else 'Forecast 완료 · 최소 실제 물리 검사 중',
            tone='#dc2626' if error else '#d97706' if finished else '#059669',
            day='V44 · 40-RegControl Native TIME 최소 검사',
            detail=f"{current[0]} {current[1]} · 24-slot prefix + 첫 평가슬롯 · 완료 {len(completed)}/10건" if not finished else '짧은 연결 검사 종료 · Actual96/Fresh96 본 실행 0회',
            progress_summary='Forecast 7/7일 · 672/672슬롯 완료 · 최소 물리 검사 '+str(len(completed))+'/10건',
            solver_note=value['solver_note']+'\n\n최소 물리 검사 PID '+str(start.get('pid','—'))
                +'\nIssue GPU 고정 진단 부하 · 실제 Job 캠페인/Fresh96 안전 인증 아님'
                +'\nV44 전체 상태: PRESTART_BLOCKED · 새 FULL Case 및 C1 증거 대기',
            build=dict(visible=True,percent=100*len(completed)/10,current_percent=100*len(completed)/10,
                done=len(completed),total=10,label='최소 실제 물리 Driver 검사',detail='완료 '+str(len(completed))+'/10건',
                percent_scope='검사 건수 기준 · 전체 캠페인 완료율 아님',steps=[]),
            reason=error.get('error',''),state='PHYSICAL_DRIVER_ERROR' if error else 'PRESTART_BLOCKED' if finished else 'SHORT_PHYSICAL_CHECK_RUNNING')
    return value


def pilot_view(root):
    pointer=optional(Path('D:/MobileESS_V44/runtime/ACTIVE_MAY01_B2_PILOT.json'))
    if not pointer:return None
    pilot=Path(pointer['root']);case=pilot/'2025-05-01/B2/attempt001'
    value=m_view(root,case/'M1')
    start=optional(case/'START.json');progress=optional(case/'progress.json');result=optional(case/'RESULT.json')
    live=False;rss=0.
    try:
        proc=psutil.Process(start['pid']);live=proc.create_time()==start['process_created'] and proc.is_running()
        if live:rss=proc.memory_info().rss
    except (psutil.Error,KeyError):pass
    phase=progress.get('stage','STARTING');actual=optional(case/'ACTUAL/RESULT.json')
    ap=optional(case/'ACTUAL/progress.json');m=optional(case/'M1/RESULT.json')
    finished=bool(result);failed=finished and not result.get('PASS');actual_pass=actual.get('Actual96_execution_PASS')
    fresh_pass=actual.get('Fresh96_physical_PASS');ticks=ap.get('completed_control_ticks',0)
    no_full=finished and m.get('M_stage_execution_PASS') is True and m.get('FULL_feasible') is False
    physical_fail=finished and actual_pass is True and fresh_pass is False
    execution_error=failed and not no_full and not physical_fail
    detail=value['detail'] if phase=='M1' else ap.get('phase',phase)
    if finished:detail=result.get('status','COMPLETE')+' · '+result.get('error','')
    note=value['solver_note'].replace('Actual/Fresh96: 별도 지시 전 실행 보류','정상 FULL 가능해면 Gap 미달이어도 FCFS Actual/Fresh96로 자동 인계')
    note+=f'\n\nMay01 B2 단일 실행 PID {start.get("pid","—")} · '+('생존' if live else '종료')
    note+=f'\n현재 단계 {phase} · Worker RAM {rss/2**30:.2f} GB · SVR11 11뱅크 / RegControl 40개'
    note+='\n7일 Forecast 672/672 완료 · 짧은 물리 검사 10/10 PASS · 다른 날짜 자동 실행 없음'
    note+='\nPlanning Gap 인증과 Actual/Fresh 물리 결과는 별도 · B1/B3 전체 캠페인 인증은 대기'
    if actual:note+=f'\nActual {actual_pass} · Fresh {fresh_pass}'
    value.update(run_id='V44 · May01 B2 · SVR11',root=str(case),day='B2 · May01 · '+phase,
        status='May01 B2 종료 · FULL 가능해 미확보' if no_full else 'May01 B2 완료 · 물리 제약 위반' if physical_fail else 'May01 B2 실행 오류' if execution_error else 'May01 B2 완료' if finished else 'May01 B2 실행 중',
        tone='#dc2626' if failed else '#059669',detail=detail,reason=result.get('error',''),
        completed=int(finished and not execution_error),failed=int(execution_error),pending=int(not finished),
        worker_alive=live,worker_PID=start.get('pid'),state='NO_FULL_SOLUTION' if no_full else 'COMPLETE_PHYSICAL_FAIL' if physical_fail else 'FAILED' if execution_error else 'COMPLETE' if finished else 'RUNNING' if live else 'DISCONNECTED',
        progress_summary='May01 B2 한 건 · K48 300초 + Joint 900초 · FULL 가능해 → Actual/Fresh96',
        solver_note=note)
    if phase!='M1':
        value.update(count_text=('완료' if finished else f'Actual {ticks}/120 제어시각'),
            build=dict(visible=not finished,percent=100*ticks/120,current_percent=100*ticks/120,
                done=ticks,total=120,label='FCFS Actual / 독립 Fresh',detail=detail,
                percent_scope='Actual 제어시각 기준 · 독립 Fresh 진행은 별도',steps=[]))
    if no_full:
        value.update(reason='정상 Native 시간 종료 · FULL 정수 가능해 없음 · Actual/Fresh 미실행',
            detail=m.get('status','NO_FULL_FEASIBLE_INCUMBENT'),count_text='Planning 종료 · Actual/Fresh 미실행',
            tone='#d97706',progress_summary='K48/Joint 예산 종료 · Gap 미달 인계 거부가 아닌 FULL 해 미확보',
            build=dict(visible=False,percent=100.,current_percent=100.,done=1,total=1,
                label='M1 종료',detail='FULL 가능해 미확보',percent_scope='최적화 종료 · 전체 평가 PASS 아님',steps=[]))
    return value


def campaign_view(root):
    pointer=optional(Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json'))
    if not pointer:return None
    campaign=Path(pointer['root']);status=optional(campaign/'CAMPAIGN_STATUS.json')
    lease=optional(campaign/'COORDINATOR_LEASE.json');live=False
    try:live=abs(psutil.Process(lease['pid']).create_time()-lease['process_created'])<.001
    except (psutil.Error,KeyError):pass
    cases=status.get('cases',[]);workers=status.get('workers',[]);details=[];views=[]
    for worker in workers:
        base=campaign/worker['day']/worker['arm']
        attempts=sorted(p for p in base.glob('attempt[0-9][0-9][0-9]') if p.is_dir())
        if not attempts:continue
        case=attempts[-1];progress=optional(case/'progress.json');stage=progress.get('stage','STARTING')
        process=optional(case/'START.json');is_live=False;rss=None
        try:
            proc=psutil.Process(worker['pid'])
            is_live=abs(proc.create_time()-process['process_created'])<.001
            if is_live:rss=proc.memory_info().rss/2**30
        except (psutil.Error,KeyError):pass
        label=f"{worker['day'][5:]} {worker['arm']} · Slot {worker['worker_slot']} · PID {worker['pid']}"
        line=label+' · '+stage+(' · 생존' if is_live else ' · 프로세스 확인 필요')
        if rss is not None:line+=f' · RAM {rss:.2f} GB'
        if stage in ('M1','M2'):
            value=m_view(root,case/stage);views.append(value)
            line+='\n  '+value['detail']
            line+=f" · K48 {value['K48_Native_seconds']:.1f}/300s · Joint {value['Joint_Native_seconds']:.1f}/900s"
            line+=f"\n  FULL UB {value['incumbent']} · 독립 LB {value['bound']} · Gap {value['gap']}"
        elif stage=='ACTUAL_FRESH':
            p=optional(case/'ACTUAL/progress.json');hb=optional(case/'ACTUAL/HEARTBEAT.json')
            line+=f"\n  {p.get('phase','준비')} · 제어시각 {p.get('completed_control_ticks',0)}/120"
            age=seconds_since(hb.get('UTC'))
            if age is not None:line+=f' · heartbeat {age:.0f}초 전'
        details.append(line)
    finished=sum(r['status'] in ('COMPLETE','FAILED','BLOCKED','INPUT_NOT_READY') for r in cases)
    passed=sum(r['status']=='COMPLETE' for r in cases)
    failed=sum(r['status'] in ('FAILED','BLOCKED','INPUT_NOT_READY') for r in cases)
    labels={'READY':'대기','RUNNING':'실행','COMPLETE':'완료','FAILED':'실패','BLOCKED':'차단','INPUT_NOT_READY':'입력 미준비'}
    overview=[]
    for day in (f'2025-05-{i:02d}' for i in range(1,8)):
        states={r['arm']:labels.get(r['status'],r['status']) for r in cases if r['day']==day}
        overview.append(day[5:]+'  '+' · '.join(a+':'+states.get(a,'대기') for a in ('B0','B1','B2','B3')))
    value=views[0] if views else dict(used=0,remaining=0,incumbent='—',bound='—',gap='—',line_loading={},
        steps=[],build=dict(visible=False,percent=0,current_percent=0,steps=[]))
    phase=optional(campaign/'PHASE.json').get('lane','B2')
    mem=psutil.virtual_memory()
    note='B2 2-worker: 5월 1~7일 먼저 → Main 1-worker: 날짜별 B0→B1→B3\n'
    note+='Planning: 원본 7-Reg / 추가 SVR0 · Actual/Fresh: SVR12 / 43-Reg\n'
    note+='\n'.join(details or ['Worker 배정 대기'])+'\n\n날짜별 28 Case\n'+'\n'.join(overview)
    note+='\n\n완료는 해당 Case 결과 기준 · Planning Gap과 Fresh 물리 PASS는 별도입니다.'
    return dict(value,status='캠페인 실행 중' if live and workers else '캠페인 대기' if live else '캠페인 종료' if finished==28 else 'Coordinator 확인 필요',
        tone='#059669' if live else '#d97706',run_id='V44 · V43 Planning + SVR12 Actual',root=str(campaign),
        day=('B2 2-worker' if phase=='B2' else 'Main 1-worker')+' · '+str(len(workers))+'개 실행',
        detail=' / '.join(d.split(' · Slot')[0] for d in details) or '실행 상태 확인 중',
        completed=passed,failed=failed,pending=28-finished,total_dates=28,timeout=0,
        count_text=f'{finished} / 28 Case 종료',progress_percent=100*finished/28,
        progress_summary=f'PASS {passed} · 실패/차단 {failed} · 대기/실행 {28-finished} · B2 먼저, Main 이후',
        solver_note=note,reason='' if live or finished==28 else 'Coordinator PID/생성시각 확인 필요',
        ram=f'여유 {mem.available/2**30:.1f} / {mem.total/2**30:.1f} GB',
        worker_alive=bool(workers and live),state='RUNNING' if live else 'COMPLETE' if finished==28 else 'DISCONNECTED',
        workers=workers,cases=cases,refresh_interval_seconds=1,snapshot_timestamp=now(),
        updated=datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S KST'))


def view(root):
    campaign=campaign_view(root)
    if campaign is not None:return campaign
    pilot=pilot_view(root)
    if pilot is not None:return pilot
    forecast=forecast_view()
    if forecast is not None:return forecast
    cp=read(DOC/'CHECKPOINT.json')
    if cp.get('current_stage')!='B2_ACTUAL_FRESH':return m_view(root)
    attempt=Path(cp['active_attempt'])
    parent=Path(cp['B2_M1_result']['path']).parent
    value=m_view(root,parent)
    result=optional(attempt/'RESULT.json');progress=optional(attempt/'progress.json')
    start=optional(attempt/'START.json');heartbeat=optional(attempt/'HEARTBEAT.json')
    live=False;rss=None
    try:
        process=psutil.Process(start['pid']);live=process.create_time()==start['process_created'] and process.is_running()
        if live:rss=process.memory_info().rss
    except (psutil.Error,KeyError):pass
    phase=progress.get('phase','INITIALIZATION_AND_SOURCE_PREPARE')
    ticks=progress.get('completed_control_ticks',0)
    finished=bool(result)
    actual_pass=result.get('Actual96_execution_PASS') is True
    fresh_pass=result.get('Fresh96_physical_PASS') is True
    failed=finished and result.get('PASS') is not True
    execution_error=finished and (bool(result.get('error')) or not actual_pass)
    physical_fail=finished and actual_pass and not fresh_pass
    labels=[dict(label='M1 FULL 동결',style='pass'),
        dict(label='FCFS Actual 120슬롯',style='pass' if actual_pass or 'FRESH' in phase else 'active' if live else ''),
        dict(label='독립 Fresh AC96',style='pass' if fresh_pass else 'fail' if failed else 'active' if live and 'FRESH' in phase else '')]
    status='B2 실행 완료 · 전압 위반' if physical_fail else 'B2 Actual/Fresh 실행 오류' if execution_error else 'B2 Actual/Fresh 완료 · Planning Gap 미인증' if finished else 'B2 Actual/Fresh 실행 중' if live else 'B2 Worker 상태 확인 필요'
    detail=('B2 FCFS Actual · '+str(ticks)+' / 120 제어시각' if 'FCFS' in phase else
        'B2 독립 Fresh AC 계산 중' if 'FRESH' in phase else 'B2 Source·초기 상태 준비 중')
    if finished:detail=f'Actual 실행 {"PASS" if actual_pass else "FAIL"} · Fresh 물리 {"PASS" if fresh_pass else "FAIL"}'
    done=3 if finished and actual_pass and not execution_error else 1+int(actual_pass)+int(fresh_pass)
    value.update(status=status,tone='#dc2626' if failed else '#059669',run_id='V43 · '+attempt.name,
        root=str(attempt),source_attempt=str(attempt),day='B2 · May01 · Actual/Fresh',detail=detail,
        completed=int(finished and not execution_error),failed=int(execution_error),physical_failed=int(physical_fail),pending=int(not finished),
        count_text=f'{done} / 3단계 완료',progress_percent=100*done/3,
        progress_summary='M1 FULL 해로 후속 실행 · Planning Gap 38.080% 미인증 · 재최적화 0회',
        steps=labels,reason=result.get('error',''),worker_alive=live,worker_PID=start.get('pid'),
        heartbeat_age=seconds_since(heartbeat.get('UTC')),state='EXECUTION_ERROR' if execution_error else 'COMPLETE_PHYSICAL_FAIL' if physical_fail else 'COMPLETE' if finished else 'RUNNING' if live else 'DISCONNECTED',
        build=dict(visible=not finished,percent=100*ticks/120,current_percent=100*ticks/120,
            done=ticks,total=120,label='FCFS Actual / 독립 Fresh',detail=detail,
            percent_scope='FCFS 제어시각 진행률 · Fresh 완료율은 별도',steps=[]),
        solver_note=f'Actual Worker PID {start.get("pid","—")} · {"생존" if live else "종료"}'
            +f'\nRAM {rss/2**30:.2f} GB' if rss is not None else f'Actual Worker PID {start.get("pid","—")}')
    value['solver_note']+='\nM1 가능해·P/Q/경로 동결 · 추가 Optimize 0회\nB0 R0/Q50 + 원본 FCFS · Pre-site/Time-shifting/Migration 제어 없음\nActual/Fresh PASS와 Planning Global Gap 인증은 별개'
    return value


def existing_index():
    path = ROOT/'v42_pr134_b1/monitor_index.html'
    html = path.read_text(encoding='utf8')
    # Same DOM/CSS/rendering; only pre-existing campaign labels and constants.
    for old, new in [('B1 · 5월 캠페인','B2 · V43 May01'),('2025.05.01 — 05.31','2025.05.01 · MESS 최적화'),
                     (' / 31일',' / 1일'),('/31)','/1)'),('A-stage 예산','K48 + Joint Native 예산'),
                     ('3,600 s','300 + 1,800 s'),('하한 · BestBd','독립 Global LB')]:
        html = html.replace(old, new)
    for old,new in [
        ('전체 진행','현재 B2 진행'),
        ("s.completed+' / 1일'","s.count_text"),
        ("'완료 '+s.completed+'일 · timeout '+s.timeout+'일 · 실패 '+s.failed+'일 · 남은 '+s.pending+'일'","s.progress_summary"),
        ("(100*s.completed/1)","s.progress_percent"),
        ("'모델 수립 · '+b.label","b.label"),
        ("b.current_percent===null?'단계 완료 '+Math.round(b.percent)+'%':b.percent.toFixed(1)+'%'","Number.isFinite(b.percent)?b.percent.toFixed(1)+'%':'측정 대기'"),
        ("b.percent_scope+' · 실제 완료 기준'","b.percent_scope"),
        ('현재 최대 선로부하율','FULL 검증 Planning 최대 부하율'),
        ('최적성 Gap','독립 Global Gap'),
        ('setTimeout(()=>controller.abort(),900)','setTimeout(()=>controller.abort(),3000)')]:
        if html.count(old)!=1:raise ValueError('MONITOR_PARTIAL_UI_BOUNDARY_DRIFT:'+old)
        html=html.replace(old,new)
    if Path('D:/MobileESS_V44/runtime/svr11_revision01/FORECAST_PARALLEL_MAY02_07/REQUEST.json').exists():
        for old,new in [('B2 · V43 May01','V44 · SVR11 Forecast'),
            ('2025.05.01 · MESS 최적화','2025.05.01 — 05.07 · 날짜별 독립 계수 생성'),
            ('현재 B2 진행','현재 Forecast 진행'),('K48 + Joint Native 예산','Forecast 슬롯 진행'),
            ('300 + 1,800 s','7일 × 96슬롯'),('FULL 검증 Planning 최대 부하율','Actual/Fresh 물리 검증'),
            ('독립 Global LB','Global LB'),
            ("'사용 '+fmt(s.used)+' s'","s.used_text||('사용 '+fmt(s.used)+' s')"),
            ("'남은 '+fmt(s.remaining)+' s'","s.remaining_text||('남은 '+fmt(s.remaining)+' s')")]:
            html=html.replace(old,new)
    if Path('D:/MobileESS_V44/runtime/ACTIVE_MAY01_B2_PILOT.json').exists():
        for old,new in [('V44 · SVR11 Forecast','V44 · May01 B2 · SVR11'),
            ('2025.05.01 — 05.07 · 날짜별 독립 계수 생성','2025.05.01 · 단일 B2 실행'),
            ('현재 Forecast 진행','현재 May01 B2 진행'),('Forecast 슬롯 진행','K48 + Joint Native 예산'),
            ('7일 × 96슬롯','300 + 900 s')]:html=html.replace(old,new)
    if Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json').exists():
        for old,new in [('V44 · May01 B2 · SVR11','V44 · 5월 캠페인'),
            ('2025.05.01 · 단일 B2 실행','2025.05.01 — 05.07 · V43 Planning / SVR12 Actual'),
            ('현재 May01 B2 진행','28 Case 진행'),('Actual/Fresh 물리 검증','현재 Worker Planning 최대 부하율')]:
            html=html.replace(old,new)
    return html.encode('utf8')


def run(root, port=8795):
    from v42_pr134_b1 import monitor as original
    source = inspect.getsource(original.run)
    old = "payload=(Path(__file__).parent/'monitor_index.html').read_bytes()"
    if source.count(old) != 1:
        raise ValueError('EXISTING_MONITOR_HTML_BOUNDARY_DRIFT')
    namespace = dict(original.run.__globals__, view=view, existing_index=existing_index)
    exec(compile(source.replace(old, 'payload=existing_index()'), str(ROOT/'v42_pr134_b1/monitor.py'), 'exec'), namespace)
    Path(root).mkdir(parents=True, exist_ok=True)
    atomic(Path(root)/'V43_MONITOR_BINDING.json', dict(URL=f'http://127.0.0.1:{port}/',UTC=now(),
        monitor_source=record(ROOT/'v42_pr134_b1/monitor.py'),UI_source=record(ROOT/'v42_pr134_b1/monitor_index.html'),
        binding_source=record(__file__),new_HTML_files=0,read_only=True,checkpoint=str(DOC/'CHECKPOINT.json')))
    namespace['run'](root, port)


if __name__ == '__main__':
    run(RUNS/'monitor', int(sys.argv[1]) if len(sys.argv)>1 else 8795)
