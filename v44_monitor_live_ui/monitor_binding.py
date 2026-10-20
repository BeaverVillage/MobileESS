"""Bind V43 journals to the existing PR189 monitor server and screen.

No solver, worker dispatch, scientific writes, or new HTML/UI. Label-only
substitutions make the original one-arm screen show its actual May01 scope.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import inspect
from functools import lru_cache
import hashlib
import json
import math
import re
import sys
import time

import psutil
from a_stage_details import details as a_stage_details
from v44_monitor_live import actual_state
from actual_tick_details import details as remaining_actual_ticks, extend_html as actual_ticks_html
from bound_details import a_bounds, m_bounds, display_fields, stage_rows

from v43.common import DOC, ROOT, RUNS, read, record, atomic, now


def optional(path):
    try:
        return read(path)
    except (OSError, ValueError):
        return {}


def campaign_batch(campaign):
    batch=optional(Path(campaign)/'OPERATIONS/BATCH_STATE.json') or optional(Path(campaign)/'AUTONOMOUS_RECOVERY/R038_BATCH_STATE.json')
    aux=parallel_b0(campaign)
    if aux:
        updates={(j['day'],j['arm']):j for j in aux.get('jobs',[])}
        batch=dict(batch,jobs=[dict(j,**updates.get((j['day'],j['arm']),{})) for j in batch.get('jobs',[])])
        if batch.get('phase')=='USER_STOPPED':batch['phase']='B0_PARALLEL_SERIAL'
    return batch


def parallel_b0(campaign):
    if optional(Path(campaign)/'OPERATIONS/R048_MONTH_B0/STATE.json').get('main_adopted'):return {}
    aux=optional(Path(campaign)/'OPERATIONS/R047_B0_PARALLEL/STATE.json')
    return aux if aux.get('phase') not in (None,'MERGED_B2_SERIAL') else {}


def campaign_days(campaign):
    manifest=optional(Path(campaign)/'DOCUMENTS/SEVEN_DAY_INPUT_MANIFEST.json')
    days=[r['day'] for r in manifest.get('days',[])]
    if not days:days=sorted({j['day'] for j in campaign_batch(campaign).get('jobs',[])})
    return days or [f'2025-05-{i:02d}' for i in range(1,8)]


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


def a_native_display(folder,ledger,alive):
    """Completed Runtime is exact; an active call is a rounded log estimate."""
    completed=ledger.get('measured_Native_Runtime',0.) or 0.
    inflight=ledger.get('inflight') if alive else None
    value=dict(Native_completed_seconds=completed,Native_current_call_seconds=None,
        Native_inflight=bool(inflight),Native_live_estimated=False,Native_log_age_seconds=None)
    if not inflight:return value
    component=inflight.get('component','');track=inflight.get('track','')
    if not all(re.fullmatch(r'[A-Z0-9_]+',v) for v in (component,track)):return value
    log=Path(folder)/f"{len(ledger.get('calls',[])):04d}_{track}_{component}_NATIVE.log"
    try:
        started=datetime.fromisoformat(inflight['UTC']).timestamp();stat=log.stat()
        if stat.st_mtime<started:return value
        with log.open('rb') as stream:
            stream.seek(max(0,stat.st_size-65536));tail=stream.read().decode('utf8',errors='replace')
        # No wall-clock interpolation: only time actually emitted by Gurobi.
        matches=re.findall(r'(?m)\b(\d+(?:\.\d+)?)s\s*$',tail)
        if not matches:return value
        current=max(map(float,matches))
        if not math.isfinite(current) or current>max(0.,time.time()-started)+5.:return value
        value.update(Native_current_call_seconds=current,Native_live_estimated=True,
            Native_log_age_seconds=max(0.,time.time()-stat.st_mtime),
            Native_live_basis='GUROBI_LOG_ROUNDED_CALL_RUNTIME',Native_live_log=str(log))
    except (OSError,ValueError,KeyError,TypeError):pass
    return value


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
    restored=(attempt/'BINARY_RESTORE_RECEIPT.json').is_file()
    model_done=(attempt/('BINARY_STAGE_CHECKPOINT.json' if is_v44 else 'NATIVE0_CERTIFICATION.json')).is_file() or restored
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
    if restored and not progress:
        phase_label='체크포인트 행렬 복원 완료 · K48 재사용 / Joint 준비 중'
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
    bound_evidence=m_bounds(attempt)
    ub,lb,gap=(bound_evidence[k] for k in ('UB','LB','relative_gap'))
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
    value.update(display_fields(bound_evidence))
    value['solver_note']+='\n'+'\n'.join(bound_evidence['lines'])
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


@lru_cache(maxsize=64)
def corrective_fresh_loading(path, expected_sha, size, modified_ns):
    # Parse the completed C1 Fresh once; keep no large physical graph in memory.
    raw=Path(path).read_bytes()
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise ValueError('MONITOR_FRESH_RECEIPT_SHA_MISMATCH')
    fresh=json.loads(raw);rows=fresh.get('physical_steps',[])[24:]
    if fresh.get('prefix_slots')!=24 or fresh.get('evaluation_slots')!=96 or len(rows)!=96:
        raise ValueError('MONITOR_FRESH96_EXACT_AXIS_REQUIRED')
    if [r.get('slot') for r in rows]!=list(range(24,120)):
        raise ValueError('MONITOR_FRESH96_SLOT_AXIS_DRIFT')
    peak=max(float(r['maximum_phase_line_loading']) for r in rows)
    return dict(peak_line_phase_loading=peak,Fresh_actual_slots=96,
        Fresh96_physical_PASS=fresh.get('PASS') is True and all(r.get('PASS') for r in rows))


def case_loading_table(campaign, cases):
    """Latest attempt's completed Fresh96 measurement, never a Planning UB."""
    campaign=Path(campaign)
    status = {(r['day'], r['arm']): r['status'] for r in cases}
    jobs={(j['day'],j['arm']):j for j in campaign_batch(campaign).get('jobs',[])}
    sequential=(campaign/'OPERATIONS/SEQUENCE_EXECUTION_PERMIT.json').exists()
    labels = {'READY':'대기', 'RUNNING':'계산 중', 'COMPLETE':'결과 확인',
        'FAILED':'실패', 'BLOCKED':'차단', 'BLOCKED_DEPENDENCY':'의존성 차단',
        'INPUT_NOT_READY':'입력 미준비', 'INTERRUPTED_BY_USER':'중단',
        'PRE_ACTUAL_READY':'Actual 준비 완료', 'EXCLUDED':'Actual 제외','PREPARED_HELD':'준비 · 보류'}
    handoff=optional(Path(campaign)/'AUTONOMOUS_RECOVERY/CURRENT_HANDOFF.json')
    retry_pending=bool(handoff.get('pending_revision') and (Path(campaign)/'AUTONOMOUS_RECOVERY/R008_HANDOVER_HEARTBEAT.json').exists())
    rows = []
    for day in campaign_days(campaign):
        cells = []
        for arm in ('B0', 'B1', 'B2', 'B3'):
            attempts = sorted(p for p in (Path(campaign)/day/arm).glob('attempt[0-9][0-9][0-9]') if p.is_dir())
            cell = dict(arm=arm, percent=None, state=labels.get(status.get((day,arm),'READY'),'대기'),
                physical_pass=None, attempt=attempts[-1].name if attempts else None,tone='pending',reason='')
            job=jobs.get((day,arm),{});job_status=job.get('status')
            if job_status=='EXCLUDED':cell.update(state='실패 제외',tone='fail',reason=job.get('exclusion_reason','준비/검증 실패'))
            elif job_status=='PREPARED':cell.update(state='Actual 대기',tone='ready')
            elif job_status=='BASELINE_QUEUED' or sequential and arm in ('B0','B2') and job_status=='PENDING':
                cell.update(state='후속 대기',reason='B1·B3 종료 후 날짜별 Planning → Actual/Fresh 1-worker')
            elif job_status=='PENDING':cell['state']='Planning 대기'
            elif job_status in ('PREPARING','ACTUAL_RUNNING','BASELINE_RUNNING'):
                case=Path(job['case_root']);progress=optional(case/'progress.json');stage=progress.get('stage','준비')
                if stage=='ACTUAL_FRESH':
                    activity,_,_=actual_state(case,arm)
                    cell.update(state='Fresh 검증 중' if 'FRESH' in str(activity.get('phase','')).upper() else 'Actual 실행 중',tone='live')
                else:cell.update(state=f'{stage} 계산 중',tone='live')
            elif job_status=='ACTUAL_FAILED':cell.update(state='Actual 실패',tone='fail',reason=job.get('exclusion_reason','결과 확인 필요'))
            if attempts:
                attempt = attempts[-1]
                result = optional(attempt/'RESULT.json') or optional(attempt/'ACTUAL/RESULT.json')
                if arm in ('B1','B3') and result.get('variants',{}).get('C1'):
                    variant=result['variants']['C1'];fresh_record=variant.get('Fresh',{})
                    if variant.get('Fresh96_physical_PASS') is not None and fresh_record.get('path'):
                        try:
                            stat=Path(fresh_record['path']).stat()
                            summary=corrective_fresh_loading(fresh_record['path'],fresh_record['sha256'],stat.st_size,stat.st_mtime_ns)
                            result=dict(result,**summary)
                        except (OSError,ValueError,KeyError,TypeError):
                            cell['state']='Fresh 결과 검증 대기'
                loading = result.get('peak_line_phase_loading')
                if (isinstance(loading, (int,float)) and not isinstance(loading, bool)
                        and math.isfinite(loading) and loading >= 0 and result.get('Fresh_actual_slots') == 96):
                    physical_pass = result.get('Fresh96_physical_PASS') is True
                    cell.update(percent=100*loading, physical_pass=physical_pass,
                        state='Fresh PASS' if physical_pass else 'Fresh FAIL',tone='pass' if physical_pass else 'fail')
            if arm=='B3' and day=='2025-05-01' and cell['state']=='실패' and retry_pending:
                cell['state']='이전 실패 · 복구 대기'
            cells.append(cell)
        rows.append(dict(day=day, cells=cells,scope='current',current_start=not rows))
    history=[];history_warning=''
    cache=campaign/'OPERATIONS/COMPLETED_WEEK_LOADING_TABLE.json'
    proof=optional(campaign/'OPERATIONS/COMPLETED_WEEK_LOADING_TABLE_RECEIPT.json')
    if proof:
        try:
            if record(cache)!=proof:raise ValueError('HISTORICAL_TABLE_SHA_MISMATCH')
            completed=read(cache)
            if not completed.get('source_results_and_Fresh_SHA_verified'):raise ValueError('HISTORICAL_FRESH_VERIFICATION_REQUIRED')
            current_dates={r['day'] for r in rows}
            history=[r for r in completed['rows'] if r['day'] not in current_dates]
        except (OSError,ValueError,KeyError):history_warning='이전 완료 결과 검증 대기'
    return dict(basis='ACTUAL_FRESH96_MAX_LINE_PHASE_LOADING',rows=history+rows,
        historical_rows=len(history),current_rows=len(rows),history_warning=history_warning,
        completed_date_range=(history[0]['day'][5:].replace('-','/')+'~'+history[-1]['day'][5:].replace('-','/')) if history else '',
        current_date_range=rows[0]['day'][5:].replace('-','/')+'~'+rows[-1]['day'][5:].replace('-','/') if rows else '')


def actual_slot_position(progress, day):
    # The callback counter includes repeated event batches at the same time.
    # Only the dated physical clock is an Actual slot axis.
    stamp=progress.get('control_time_seconds')
    if not isinstance(stamp,(int,float)) or not math.isfinite(stamp):return None
    issue=(datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))-timedelta(hours=6)).timestamp()
    return max(0,min(120,int((stamp-issue)//900)+1))


def campaign_worker_view(case, worker, stage, alive):
    """Read only the active arm/stage; never borrow the prior B2 view."""
    arm=worker['arm']; day=worker['day']; actual=stage=='ACTUAL_FRESH'
    folder=case/('ACTUAL' if actual else stage)
    p=optional(folder/'progress.json');hb=optional(folder/'HEARTBEAT.json')
    actual_activity={}
    if actual:p,hb,actual_activity=actual_state(case,arm)
    result=optional(folder/'RESULT.json');start=optional(case/'START.json')
    age=seconds_since(hb.get('UTC') or p.get('UTC') or start.get('UTC'))
    ticks=p.get('completed_control_ticks',0);phase=p.get('phase','입력·모델 준비')
    slot=actual_slot_position(p,day)
    fresh='FRESH' in phase.upper(); ac=p.get('current_AC_calls',0)
    native_display={};stage_details=None;bound_evidence=None
    if not actual and stage not in ('A1','A2'):
        label={'REFERENCE':'원본 R0 기준 계획 구성','A1_REUSE':'동일 날짜 B1 A1 검증·재사용',
            'PRE_ACTUAL_READY':'동결 계획 검증 완료 · 전체 준비 대기','STARTING':'Worker 진입 · 입력 및 Source SHA 검증'}.get(stage,stage+' 준비')
        return dict(used=None,remaining=None,used_text='최적화 Native 호출 없음',remaining_text='단계 준비/검증 중',
            budget_label='참조 계획·입력 준비',budget_cap='Native 예산 해당 없음',incumbent='—',bound='—',gap='—',
            metrics_visible=False,metrics_label='참조 계획·입력 준비',line_loading=dict(text='Fresh96 결과 대기',note='Actual/Fresh 완료 후 측정'),
            loading_label='Actual/Fresh96 최대 선로 부하율',steps=[],
            build=dict(visible=True,percent=None,current_percent=None,done=0,total=0,label=label,detail=label,
                percent_label='단계 준비 중',percent_scope='파일·검증 단계 · 전체 완료율 미산정',steps=[]),detail=label,
            worker_PID=worker['pid'],heartbeat_age=age,stage=stage,arm=arm,attempt=case.name,
            solver_note=f"{day} {arm} {case.name} · {stage} · PID {worker['pid']}\n{label}")
    if actual:
        label='독립 Fresh AC96' if fresh else 'Actual 제어·Current AC'
        slot_text='Actual 120슬롯 종료' if fresh else f'Actual 슬롯 {slot}/120 처리' if slot is not None else 'Actual 슬롯 시각 대기'
        detail=f'{label} · {slot_text} · 제어 콜백 {ticks}회 · Current AC {ac:,}회'
        if 'completed_probe_calls' in actual_activity:
            probe_age=actual_activity['activity_age_seconds']
            detail+=f" · 전체 AC 검증 완료 {actual_activity['completed_probe_calls']:,}회 ({probe_age:.0f}초 전)"
        if actual_activity.get('event_age_seconds') is not None:
            detail+=f" · 마지막 제어 보고 {actual_activity['event_age_seconds']:.0f}초 전"
        budget_label='Actual / 독립 Fresh 진행';budget_cap='24 Prefix + 평가 96슬롯'
        used_text=f'Current AC {ac:,}회';remaining_text=slot_text
        percent=100. if fresh else 100*max(0,(slot or 1)-1)/120
        build=dict(visible=True,percent=percent,current_percent=percent,done=120 if fresh else slot or 0,total=120,
            label=label,detail=detail,percent_scope='물리 시각으로 계산한 Actual 슬롯 · 콜백 수와 별도 · Fresh96 PASS는 완료 후 검증',steps=[])
        used=remaining=None;ub=lb=gap=None
        labels={'B0':['기준 계획','Actual','Fresh AC96'],'B1':['A1 동결','Actual','Fresh AC96'],
            'B2':['기준 계획','M1 동결','Actual','Fresh AC96'],
            'B3':['A1 재사용','M1','A2','M2 동결','Actual','Fresh AC96']}[arm]
        current=len(labels)-1 if fresh else len(labels)-2
    else:
        ledger=optional(folder/'NATIVE_RUNTIME_LEDGER.json')
        native_display=a_native_display(folder,ledger,alive)
        completed=native_display['Native_completed_seconds'];current_call=native_display['Native_current_call_seconds']
        used=completed+(current_call or 0.);cap=ledger.get('Native_ceiling_seconds',5400.)
        remaining=max(0.,cap-used);ub=result.get('UB',p.get('UB'));lb=result.get('LB',p.get('LB'))
        bound_evidence=a_bounds(folder)
        ub,lb,gap=(bound_evidence[k] for k in ('UB','LB','relative_gap'))
        budget_label=f'{stage} Native 예산';budget_cap=f'{cap:,.0f} s · 독립 Gap 0.5%'
        estimated=native_display['Native_live_estimated']
        used_text=f'약 {used:.1f} s · 진행 포함' if estimated else f'완료 누적 {completed:.1f} s'
        remaining_text=f'{"약 " if estimated else ""}남은 {remaining:.1f} s'
        inflight=ledger.get('inflight') if alive else None
        phase=({'PHASE_I':'Phase I · 가능해 구성','LOCAL_PRICING':'작업 후보 탐색','ORIGINAL_P1':'원본 목적함수 최적화'}.get(inflight.get('component'),inflight.get('component')) if inflight else '후보·모델 준비 / 독립 검산')
        detail=f'{stage} · {phase}'
        if inflight:
            detail+=f' · 완료 누적 {completed:.1f}초 + 현재 호출 '+(f'약 {current_call:.0f}초 (Solver 로그 기준)' if estimated else '진행 중 · Runtime 로그 대기')
        stage_details=a_stage_details(folder,worker,ledger,native_display,alive)
        stage_details['bounds']=bound_evidence
        stage_details['lines']+=bound_evidence['lines']
        phase=stage_details['title'];detail=f'{stage} · {phase}'
        build=dict(visible=True,percent=None,current_percent=None,done=0,total=0,
            label=f'{stage} 세부 진행',percent_label='전체 완료율 미산정',detail='\n'.join(stage_details['lines']),
            percent_scope='완료율·종료시각은 미산정 · 표본 작업은 비정지 관측 · 단계 완료 기록과 별도',steps=stage_details['steps'])
        labels=['A1','Actual','Fresh AC96'] if arm=='B1' else ['A1 재사용','M1','A2','M2','Actual','Fresh AC96']
        current=labels.index(stage) if stage in labels else 0
    steps=[dict(label=x,style='pass' if i<current else 'active' if i==current and alive else '') for i,x in enumerate(labels)]
    value=dict(**native_display,a_stage_details=stage_details,used=used,remaining=remaining,used_text=used_text,remaining_text=remaining_text,
        budget_label=budget_label,budget_cap=budget_cap,incumbent=display_number(ub),bound=display_number(lb),
        gap=f'{gap*100:.3f}%' if isinstance(gap,(int,float)) else '—',
        metrics_visible=not actual,metrics_label='현재 단계 Planning UB / 독립 LB / Gap' if not actual else 'Actual/Fresh 단계 · 최적화 Gap 해당 없음',
        line_loading=dict(text='Fresh96 결과 대기',note='완료 전 Actual/Fresh 최대 부하율을 PASS 결과로 표시하지 않습니다.'),
        loading_label='Actual/Fresh96 최대 선로 부하율',steps=steps,build=build,detail=detail,
        worker_PID=worker['pid'],heartbeat_age=age,stage=stage,arm=arm,attempt=case.name,
        source_attempt=str(case),raw_phase=phase,current_AC_calls=ac if actual else None,
        actual_control_ticks=ticks if actual else None,actual_slot_position=slot if actual else None,
        actual_activity=actual_activity,
        solver_note=f"{day} {arm} {case.name} · {stage} · PID {worker['pid']}\n{detail}\nHeartbeat {display_number(age)}초 전")
    if bound_evidence is not None:value.update(display_fields(bound_evidence))
    return value


def campaign_view(root):
    pointer=optional(Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json'))
    if not pointer:return None
    campaign=Path(pointer['root']);status=optional(campaign/'CAMPAIGN_STATUS.json')
    lease=optional(campaign/'COORDINATOR_LEASE.json');live=False
    try:live=abs(psutil.Process(lease['pid']).create_time()-lease['process_created'])<.001
    except (psutil.Error,KeyError):pass
    batch=campaign_batch(campaign);week2=(campaign/'OPERATIONS/BATCH_STATE.json').exists()
    month=optional(campaign/'OPERATIONS/R048_MONTH_B0/STATE.json')
    aux=parallel_b0(campaign)
    if aux:
        active=[]
        for w in aux.get('workers',[]):
            try:
                if abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001:active.append(w)
            except (psutil.Error,KeyError):pass
        status=dict(status,cases=batch.get('jobs',[]),workers=status.get('workers',[])+active)
        try:live=live or abs(psutil.Process(aux['lease']['pid']).create_time()-aux['lease']['process_created'])<.001
        except (psutil.Error,KeyError):pass
    if month:
        combined={w['pid']:w for w in status.get('workers',[])}
        for w in month.get('workers',[]):
            try:
                if abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001:combined[w['pid']]=w
            except (psutil.Error,KeyError):pass
        status=dict(status,workers=list(combined.values()))
        try:live=live or abs(psutil.Process(month['lease']['pid']).create_time()-month['lease']['process_created'])<.001
        except (psutil.Error,KeyError):pass
    aliases=dict(PENDING='READY',PREPARING='RUNNING',PREPARED='PRE_ACTUAL_READY',PASS='COMPLETE',ACTUAL_RUNNING='RUNNING',ACTUAL_FAILED='FAILED',BASELINE_QUEUED='READY',BASELINE_RUNNING='RUNNING')
    cases=[dict(r,status=aliases.get(r['status'],r['status'])) for r in status.get('cases',[])]
    workers=[dict(w,worker_slot=w.get('worker_slot') or next((j.get('parallel_slot',1) for j in batch.get('jobs',[]) if (j['day'],j['arm'])==(w['day'],w['arm'])),1)) for w in status.get('workers',[])]
    details=[];views=[];bound_history=[]
    for worker in workers:
        base=Path(worker.get('campaign_root',str(campaign)))/worker['day']/worker['arm']
        attempts=sorted(p for p in base.glob('attempt[0-9][0-9][0-9]') if p.is_dir())
        if not attempts:continue
        case=attempts[-1];progress=optional(case/'progress.json');stage=progress.get('stage','STARTING')
        process=(optional(case/'ACTUAL_START.json') or optional(case/'START.json')) if stage=='ACTUAL_FRESH' else optional(case/'START.json');is_live=False;rss=None
        try:
            proc=psutil.Process(worker['pid'])
            is_live=abs(proc.create_time()-process['process_created'])<.001
            if is_live:rss=proc.memory_info().rss/2**30
        except (psutil.Error,KeyError):pass
        label=f"{worker['day'][5:]} {worker['arm']} · Slot {worker['worker_slot']} · PID {worker['pid']}"
        line=label+' · '+stage+(' · 생존' if is_live else ' · 프로세스 확인 필요')
        if rss is not None:line+=f' · RAM {rss:.2f} GB'
        if stage in ('M1','M2'):
            value=m_view(root,case/stage)
            value.update(stage=stage,arm=worker['arm'],attempt=case.name,budget_label=f'{stage} K48 + Joint Native 예산',budget_cap='300 + 900 s',loading_label=f'{stage} FULL 검증 Planning 최대 부하율')
            value['detail']=value['detail'].replace('B2 M1',worker['arm']+' '+stage).replace('M1 실행 종료',stage+' 실행 종료')
            value['steps']=[dict(x,label=x['label'].replace('Joint 최적화',stage+' Joint')) for x in value['steps']]
            value['solver_note']=value['solver_note'].split('\nActual/Fresh96:')[0]
            views.append(value)
            line+='\n  '+value['detail']
            line+=f" · K48 {value['K48_Native_seconds']:.1f}/300s · Joint {value['Joint_Native_seconds']:.1f}/900s"
            line+=f"\n  FULL UB {value['incumbent']} · 독립 LB {value['bound']} · Gap {value['gap']}"
        elif stage=='ACTUAL_FRESH':
            actual_view=campaign_worker_view(case,worker,stage,is_live);views.append(actual_view)
            line+='\n  '+actual_view['detail']
            age=actual_view['heartbeat_age']
            if age is not None:line+=f' · heartbeat {age:.0f}초 전'
        else:
            view=campaign_worker_view(case,worker,stage,is_live);views.append(view)
            line+='\n  '+view['detail']
        bound_history.extend(stage_rows(case,stage))
        details.append(line)
    finished=sum(r['status'] in ('COMPLETE','FAILED','BLOCKED','INPUT_NOT_READY','EXCLUDED') for r in cases)
    passed=sum(r['status']=='COMPLETE' for r in cases)
    failed=sum(r['status'] in ('FAILED','BLOCKED','INPUT_NOT_READY') for r in cases)
    labels={'READY':'대기','RUNNING':'실행','COMPLETE':'완료','FAILED':'실패','BLOCKED':'차단','INPUT_NOT_READY':'입력 미준비','INTERRUPTED_BY_USER':'사용자 중단','PRE_ACTUAL_READY':'Actual 준비 완료','EXCLUDED':'Actual 제외'}
    overview=[]
    for day in campaign_days(campaign):
        states={r['arm']:labels.get(r['status'],r['status']) for r in cases if r['day']==day}
        overview.append(day[5:]+'  '+' · '.join(a+':'+states.get(a,'대기') for a in ('B0','B1','B2','B3')))
    value=views[0] if views else dict(used=0,remaining=0,incumbent='—',bound='—',gap='—',line_loading={},
        steps=[],build=dict(visible=False,percent=0,current_percent=0,steps=[]))
    phase=optional(campaign/'PHASE.json').get('lane','B2')
    mem=psutil.virtual_memory()
    m_threads=pointer.get('M_Threads',1)
    serial=m_threads in (2,4) and pointer.get('Workers')==1
    note=('전체 1-worker: B2 5월 1~7일 순차 → Main 날짜별 B0→B1→B3\n'
          f'B2/B3 M단계: Solver {m_threads}-thread · Barrier · Joint Gap 3%\n') if serial else 'B2 2-worker: 5월 1~7일 먼저 → Main 1-worker: 날짜별 B0→B1→B3\n'
    if pointer.get('Q_limit_kvar')==250:
        note+='차량별 Q ±250 kvar · PCS 400 kVA / P 300 kW 유지 · A 단계 1-thread\n'
    note+='Planning: 원본 7-Reg / 추가 SVR0 · Actual/Fresh: SVR12 / 43-Reg\n'
    if pointer.get('fresh_M_from_zero'):
        note+='새 M 시도: K48 0부터 300초 + Joint 0부터 900초 · 호출 cap 300초\n'
        note+='M1/M2 Joint 내부 Gap 3% · Root Barrier 유지 · May02 Crossover 수치 안정화\n'
        note+='이전 M 해·원장 사용량을 가져오지 않습니다. 날짜마다 독립 Worker 1개입니다.\n'
    elif pointer.get('fresh_Joint_budget')==900:
        note+='Joint 새 예산 900초를 0부터 · 단일 호출 cap 300초 · 완료 K48만 재사용\n'
        note+='이전 Joint 시도의 사용량은 새 900초 예산에서 차감하지 않습니다.\n'
    elif pointer.get('Joint_call_cap')==300:
        note+='Joint 단일 호출 cap 300초 · 총예산 900초 · K48 완료 결과 재사용\n'
        note+='Native 사용량에는 이전 Attempt의 정산 사용량이 포함됩니다.\n'
    if views and value.get('stage')=='ACTUAL_FRESH':
        arm=value.get('arm');fixed={'B0':'기준 AIDC 계획 · MESS 없음',
            'B1':'A1 AIDC 계획 동결 · MESS 없음',
            'B2':'기준 AIDC + M1 MESS 계획 동결',
            'B3':'A2 AIDC + M2 MESS 계획 동결'}.get(arm,'동결 계획')
        note=f'{arm} Actual/Fresh · {fixed}\n새 A/M 최적화 호출 없음 · 독립 ActualContext에서 실제 부하/GPU 재생\nNative AUTO/TIME · Prefix24 + 평가96 · SVR12 / RegControl43\n'
    elif phase!='B2':
        note='현재 Main: 같은 날짜 B0 → B1 → B3 · 독립 Worker 1개\n'+note
    r038=batch
    if r038:
        ready=sum(j['status']=='PREPARED' for j in r038['jobs'])
        excluded=sum(j['status']=='EXCLUDED' for j in r038['jobs'])
        if r038['phase']=='PREPARE_SERIAL':
            note=f'남은 7건 Actual 직전까지 1-worker 순차 준비 · 준비 완료 {ready}/7 · 제외 {excluded}건\n모든 준비 시도 종료 후 정상 건만 P-core Actual/Fresh 병렬 실행 · 한 건 실패는 다른 건을 막지 않습니다.\n'
        else:
            note=f"{r038['phase']} · 독립 Actual/Fresh worker {len(workers)} · 제외 {excluded}건\n검증된 정상 건만 전체 P-core 배치 · 실행 중 오류도 건별 격리\nA/M 계획은 동일 Case에서 동결 · Actual/Fresh 물리 판정 유지\n"
    actual_user_stop=optional(campaign/'AUTONOMOUS_RECOVERY/STOP_AUTONOMY.json').get('stop_running_Actual') is True
    actual_hold=actual_user_stop and r038.get('phase')=='PRE_ACTUAL_USER_HOLD'
    actual_auto_start=bool(optional(campaign/'AUTONOMOUS_RECOVERY/CURRENT_HANDOFF.json').get('Actual_auto_start_authorization')) and optional(campaign/'AUTONOMOUS_RECOVERY/STOP_AUTONOMY.json').get('reason')=='USER_ACTUAL_PAUSED_PREPARATION_REPAIR_ALLOWED'
    summary={}
    if week2:
        jobs=batch.get('jobs',[]);phase=batch.get('phase','PREPARE_SERIAL');total=len(jobs)
        ready=sum(j['status']=='PREPARED' for j in jobs);excluded=sum(j['status']=='EXCLUDED' for j in jobs)
        resolved=sum(j['status'] in ('PREPARED','EXCLUDED','PASS','ACTUAL_RUNNING','ACTUAL_FAILED') for j in jobs)
        planning_running=sum(j['status']=='PREPARING' for j in jobs)
        planning_pending=sum(j['status']=='PENDING' for j in jobs)
        actual_running=sum(j['status']=='ACTUAL_RUNNING' for j in jobs)
        actual_failed=sum(j['status']=='ACTUAL_FAILED' for j in jobs)
        dispatch_stop=optional(campaign/'OPERATIONS/STOP.json')
        actual_user_stop=(bool(dispatch_stop) or phase=='USER_STOPPED') and not dispatch_stop.get('operational_transition')
        actual_hold=False;actual_auto_start=phase in ('PREPARE_SERIAL','MAIN_PREPARE_SERIAL') and not actual_user_stop
        barrier=optional(campaign/'OPERATIONS/ALL_PREPARATIONS_RESOLVED.json') or optional(campaign/'OPERATIONS/B1_B3_PREPARATIONS_RESOLVED.json')
        actual_ready=len(barrier.get('ready',[])) if barrier else ready
        phase_label={'PREPARE_SERIAL':'Planning 1-worker 준비 중','MAIN_PREPARE_SERIAL':'Planning 1-worker 준비 중','ACTUAL_PARALLEL':'Actual/Fresh 최대 7-worker 실행','MAIN_ACTUAL_PARALLEL':'Actual/Fresh 최대 7-worker 실행','BASELINE_SEQUENTIAL':'Planning → Actual/Fresh 1-worker 순차 실행','COMPLETE':'캠페인 완료','USER_STOPPED':'사용자 중단'}.get(phase,phase)
        if aux:phase_label='기존 Actual + B0 전용 1-worker 병렬 실행' if actual_running else 'B0 전용 1-worker 날짜순 실행'
        summary=dict(phase=phase,phase_label=phase_label,total=total,planning_resolved=resolved,
            prepared_waiting=ready,planning_running=planning_running,planning_pending=planning_pending,
            excluded=excluded,actual_running=actual_running,actual_failed=actual_failed,actual_passed=passed,
            actual_eligible=actual_ready,barrier_resolved=barrier.get('all_preparations_resolved',False),
            prepare_workers=1,actual_workers=7,auto_start_armed=actual_auto_start,
            date_start=campaign_days(campaign)[0],date_end=campaign_days(campaign)[-1])
        if phase in ('PREPARE_SERIAL','MAIN_PREPARE_SERIAL'):
            note=(f'V44 r043 · 2025년 5월 8~14일 · 7일 × B0~B3 = {total}건\n'
                f'Planning 1-worker: 준비 완료 {ready} · 실패 제외 {excluded} · 실행 {planning_running} · 대기 {planning_pending}\n'
                f'준비 판정 확정 {resolved}/{total}건 · 전체 시도 종료 후 정상 건만 Actual/Fresh 최대 7-worker 자동 실행\n')
        else:
            note=(f'V44 r043 · 2025년 5월 8~14일 · {phase_label}\n'
                f'Actual 대상 {actual_ready} · PASS {passed} · Actual 실패 {actual_failed} · 실행 {actual_running} · 실패 제외 {excluded}\n'
                f'전체 준비 판정 {resolved}/{total}건 종료 · 동결된 계획으로 독립 Actual/Fresh 실행\n')
        note+='A 단계 1-thread · M 단계 4-threads · K48 300초 + Joint 900초 · Q ±250 kvar\nPlanning 7-Reg · Actual SVR12 / 43-Reg · Prefix 24 + 평가 96슬롯\n'
        if aux:note+='B0 추가 1-worker: 05/08 → 05/14 날짜순 Reference → Actual → Fresh · B2는 기존 Actual/B0 종료 후 1-worker 자동 실행\n'
        for job in jobs:
            if job.get('exclusion_reason'):note+=f"제외/오류 {job['day']} {job['arm']}: {job['exclusion_reason']}\n"
    if actual_user_stop:note=('Actual 현재 대기 · 모든 Planning 준비 시도 종료 후 정상 건만 최대 7-worker 자동 시작\n' if actual_auto_start else 'Actual 사용자 중단 · Planning 복구/준비만 허용 · Actual 자동 재개 차단\n')+note
    note+='\n'.join(details or ['Worker 배정 대기'])+'\n\n날짜별 28 Case\n'+'\n'.join(overview)
    note+='\n\n완료는 해당 Case 결과 기준 · Planning Gap과 Fresh 물리 PASS는 별도입니다.'
    stopped=pointer.get('status')=='STOPPED_BY_USER' or status.get('status')=='STOPPED_BY_USER'
    if stopped:note='사용자 요청으로 캠페인 중단 · 자동 재시작 차단 · 기존 Raw 보존\n'+note
    response=dict(value,status=('Planning 준비 완료 · Actual 자동 시작 대기' if actual_auto_start else 'Planning 준비 완료 · Actual 사용자 보류') if actual_hold else '사용자 요청으로 중단' if stopped else '캠페인 실행 중' if live and workers else '캠페인 대기' if live else '캠페인 종료' if finished==28 else 'Coordinator 확인 필요',
        tone='#059669' if live else '#d97706',run_id='V44 · V43 Planning + SVR12 Actual',root=str(campaign),
        day=(f"{workers[0]['day']} · {workers[0]['arm']} · {value.get('stage','단계 준비')}" if workers else '현재 Worker 배정 대기'),
        detail='캠페인 프로세스 종료 · 자동 재시작 차단' if stopped else (value.get('attempt','')+' · '+value['detail'] if value.get('detail') else '') or ' / '.join(d.split(' · Slot')[0] for d in details) or '실행 상태 확인 중',
        completed=passed,failed=failed,pending=28-finished,total_dates=28,timeout=0,
        count_text=f'{finished} / 28 Case 종료',progress_percent=100*finished/28,
        progress_summary=f'PASS {passed} · 실패/차단 {failed} · 진행 {len(workers)} · 대기 {28-finished-len(workers)} · 현재 {phase}',
        solver_note=note,reason='USER_EXPLICIT_STOP' if stopped else '' if live or finished==28 else 'Coordinator PID/생성시각 확인 필요',
        ram=f'여유 {mem.available/2**30:.1f} / {mem.total/2**30:.1f} GB',
        worker_alive=bool(workers and live),state='STOPPED_BY_USER' if stopped else 'RUNNING' if live else 'COMPLETE' if finished==28 else 'DISCONNECTED',
        workers=workers,cases=cases,Actual_paused_by_user=actual_user_stop,Actual_auto_start_armed=actual_auto_start,actual_tick_details=remaining_actual_ticks(campaign),stage_bounds=bound_history,case_line_loading=case_loading_table(campaign,cases),
        refresh_interval_seconds=1,snapshot_timestamp=now(),
        updated=datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S KST'))
    if week2:
        prep=phase in ('PREPARE_SERIAL','MAIN_PREPARE_SERIAL')
        response.update(campaign_summary=summary,run_id='V44 r043 · 5월 8~14일 캠페인',
            status=summary['phase_label'] if live or phase in ('COMPLETE','USER_STOPPED') else 'Coordinator 연결 확인 필요',
            count_text=f'Planning 준비 판정 {resolved} / {total}건' if prep else f'Actual/Fresh 종료 {passed+actual_failed} / {summary["actual_eligible"]}건',
            progress_percent=100*resolved/total if prep else 100*(passed+actual_failed)/summary['actual_eligible'] if summary['actual_eligible'] else 100 if phase=='COMPLETE' else 0,
            progress_summary=(f'준비 완료 {ready} · 실패 제외 {excluded} · Planning 실행 {planning_running}/1 · 대기 {planning_pending} · Actual 자동 시작 대기' if prep else
                f'PASS {passed} · Actual 실패 {actual_failed} · 실행 {actual_running}/7 · 준비 완료 대기 {ready} · 제외 {excluded}'),
            Actual_paused_by_user=actual_user_stop,Actual_auto_start_armed=actual_auto_start,
            excluded=excluded,failed=actual_failed,pending=planning_pending if prep else ready,
            state='COMPLETE' if phase=='COMPLETE' else 'STOPPED_BY_USER' if actual_user_stop else 'RUNNING' if live else 'DISCONNECTED')
        if aux:
            b0_running=sum(j['arm']=='B0' and j['status']=='BASELINE_RUNNING' for j in jobs)
            response['campaign_summary'].update(B0_parallel_workers=b0_running,B0_parallel_limit=1,B2_parallel=False)
            response['progress_summary']+=f' · B0 {b0_running}/1 추가 실행'
    if month:
        month_jobs=month.get('jobs',[]);b0_live=[w for w in month.get('workers',[]) if w['arm']=='B0']
        done=sum(j['status']=='PASS' for j in month_jobs);blocked=[j for j in month_jobs if j['status']=='EXCLUDED']
        response['campaign_summary'].update(B0_month_end='2025-05-31',B0_parallel_workers=len(b0_live),B0_parallel_limit=1,
            B0_month_PASS=done,B0_month_excluded=len(blocked),other_new_arms_held=True)
        response['status']='기존 캠페인 유지 · B0 05/31까지 추가 1-worker'
        response['progress_summary']=f'기존 캠페인 PASS {passed}/28 · 실행 {len(workers)} · 추가 B0 PASS {done}/17 · 입력 제외 {len(blocked)}'
        response['solver_note']+='\n추가 B0: 05/15 → 05/31 날짜순 1-worker · 이후 날짜 B1/B2/B3 준비·보류\n'
        for j in blocked:response['solver_note']+=f"입력 제외 {j['day']} B0: {j.get('exclusion_reason','')}\n"
        table=response['case_line_loading'];roots=sorted({j['campaign_root'] for j in month_jobs})
        for future in roots:
            rows=optional(Path(future)/'CAMPAIGN_STATUS.json').get('cases',[])
            extra=case_loading_table(Path(future),rows)
            existing={r['day'] for r in table['rows']};table['rows']+=[r for r in extra['rows'] if r['day'] not in existing]
        table.update(current_rows=len(table['rows'])-table.get('historical_rows',0),current_date_range='05/08~05/31')
    return response


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
        ("b.current_percent===null?'단계 완료 '+Math.round(b.percent)+'%':b.percent.toFixed(1)+'%'","b.percent_label||(Number.isFinite(b.percent)?b.percent.toFixed(1)+'%':'측정 대기')"),
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
    if Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json').exists():
        html=html.replace('K48 + Joint Native 예산</span><span>300 + 900 s</span>',
            '현재 단계</span><span id="stage-budget-cap">—</span>')
        html=html.replace('현재 단계</span><span id="stage-budget-cap">',
            '<span id="stage-budget-label">현재 단계</span></span><span id="stage-budget-cap">')
        html=html.replace('현재 Worker Planning 최대 부하율</span>',
            '<span id="stage-loading-label">현재 단계 최대 선로 부하율</span></span>')
        html=html.replace("$('run').textContent=s.run_id;", """$('run').textContent=s.run_id;
if($('stage-budget-label'))$('stage-budget-label').textContent=s.budget_label||'현재 단계';
if($('stage-budget-cap'))$('stage-budget-cap').textContent=s.budget_cap||'—';
if($('stage-loading-label'))$('stage-loading-label').textContent=s.loading_label||'현재 단계 최대 선로 부하율';
document.querySelector('.metrics').style.display=s.metrics_visible===false?'none':'grid';
$('steps').style.gridTemplateColumns='repeat('+Math.min(6,Math.max(1,s.steps.length))+',1fr)';""")
        html=html.replace("$('build-bar').style.width=b.percent+'%'", "$('build-bar').className=Number.isFinite(b.percent)?'bar':'bar unknown';$('build-bar').style.width=Number.isFinite(b.percent)?b.percent+'%':'25%'")
    # Extend the existing screen in place; the original template stays pinned.
    table = '''<section id="case-loading-card" class="card" hidden>
<h2 style="font-size:18px">날짜·비교군별 최대 선로 부하율</h2>
<p class="muted" style="margin-bottom:14px">Actual 부하 기반 Fresh96 · 모든 선로·상 중 최대 · 정격 대비 %</p>
<p id="case-loading-scope" class="muted" style="font-size:11px;margin-bottom:12px"></p>
<div class="case-loading-scroll"><table class="case-loading-table" aria-label="날짜와 비교군별 Fresh96 최대 선로 부하율">
<thead><tr><th scope="col">날짜</th><th scope="col">B0</th><th scope="col">B1</th><th scope="col">B2</th><th scope="col">B3</th></tr></thead>
<tbody id="case-loading-body"></tbody></table></div>
<p class="muted" style="font-size:11px;margin-top:12px">계산 완료 시 자동 갱신 · Planning 최대 부하율 및 Gap 인증과 별도</p>
</section>'''
    style = '''#build-detail{white-space:pre-line;line-height:1.65} .case-loading-scroll{overflow-x:auto}.case-loading-table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.case-loading-table th,.case-loading-table td{padding:11px 5px;text-align:center;border-bottom:1px solid #e7ecf3;white-space:nowrap}
.case-loading-table thead th{font-size:12px;background:#f4f6fa;color:#64748b}.case-loading-table tbody th{font-size:13px;font-weight:600}
.case-loading-table tr:last-child td,.case-loading-table tr:last-child th{border-bottom:0}.case-loading-table strong{display:block;font-size:16px;font-weight:600}
.case-loading-table small{display:block;font-size:10px;margin-top:3px}.case-loading-pass{color:#059669}.case-loading-fail{color:#dc2626}.case-loading-pending{color:#94a3b8}
.case-loading-live{color:#2563eb}.case-loading-ready{color:#0f766e}.case-loading-current-start th,.case-loading-current-start td{border-top:2px solid #cbd5e1}
@media(max-width:480px){.case-loading-table th,.case-loading-table td{padding:10px 3px}.case-loading-table strong{font-size:14px}}'''
    script = '''function renderCaseLoading(data){
const card=document.getElementById('case-loading-card'),body=document.getElementById('case-loading-body');
card.hidden=!Array.isArray(data?.rows);if(card.hidden)return;
document.getElementById('case-loading-scope').textContent=[data.completed_date_range?'완료 결과 '+data.completed_date_range:'',data.current_date_range?'현재 캠페인 '+data.current_date_range:'',data.history_warning||''].filter(Boolean).join(' · ');
body.replaceChildren(...data.rows.map(row=>{const tr=document.createElement('tr'),day=document.createElement('th');
if(row.current_start&&data.historical_rows)tr.className='case-loading-current-start';
day.scope='row';day.textContent=row.day.slice(5).replace('-','/');tr.append(day);
for(const cell of row.cells){const td=document.createElement('td'),measured=Number.isFinite(cell.percent);
td.className=measured?(cell.physical_pass?'case-loading-pass':'case-loading-fail'):'case-loading-'+(cell.tone||'pending');
td.title=[row.day,cell.arm,cell.attempt||'',cell.state,cell.reason||''].filter(Boolean).join(' · ');
const value=document.createElement('strong'),state=document.createElement('small');value.textContent=measured?cell.percent.toFixed(3)+'%':'—';state.textContent=cell.state;td.append(value,state);
tr.append(td);}return tr;}));}
'''
    for anchor in ('</style>', '<div id="reason">', 'async function refresh(){', "$('status').textContent=s.status;"):
        if html.count(anchor) != 1:raise ValueError('MONITOR_LOADING_TABLE_BOUNDARY_DRIFT:'+anchor)
    html=html.replace('</style>',style+'\n</style>')
    anchor='<section class="card"><h2 id="day">'
    if html.count(anchor)!=1:raise ValueError('MONITOR_PRIMARY_LOADING_TABLE_ANCHOR_DRIFT')
    html=html.replace(anchor,table+'\n'+anchor)
    html=html.replace('async function refresh(){',script+'\nasync function refresh(){')
    html=html.replace("$('status').textContent=s.status;","renderCaseLoading(s.case_line_loading);\n$('status').textContent=s.status;")
    extra_card='<section id="bounds-history-card" class="card" hidden><h2 style="font-size:18px">현재 Case 단계별 UB · LB</h2><p class="muted">UB·LB는 정격 대비 비율 ρ · 단계별 고정 계획이 다릅니다.</p><div style="overflow:auto"><table class="bounds-table"><thead><tr><th>단계</th><th>FULL UB</th><th>독립 LB</th><th>Global Gap</th><th>상태</th></tr></thead><tbody id="bounds-history-body"></tbody></table></div></section>'
    extra_script="function renderStageBounds(rows){\nconst card=document.getElementById('bounds-history-card'),body=document.getElementById('bounds-history-body');\ncard.hidden=!Array.isArray(rows)||!rows.length;if(card.hidden)return;\nbody.replaceChildren(...rows.map(row=>{const tr=document.createElement('tr');\nfor(const value of [row.stage,row.ub_text,row.lb_text,row.gap_text,row.status]){const td=document.createElement('td');td.textContent=value;tr.append(td);}\ntr.title=[row.attempt,row.scope,row.source].join(' · ');return tr;}));}\n"
    html=html.replace('</style>','.metrics .metric strong{font-size:19px;overflow-wrap:anywhere}.bounds-table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums;margin-top:12px}.bounds-table td,.bounds-table th{padding:9px 5px;border-bottom:1px solid #e7ecf3;text-align:left}.bounds-table th{white-space:nowrap}#bound-explanation{white-space:pre-line;line-height:1.6;margin-top:10px}</style>')
    html=html.replace('<div id="reason">',extra_card+'<div id="reason">')
    html=html.replace('<div class="metrics">','<div class="muted" id="metrics-scope"></div><div class="metrics">')
    html=html.replace('<div id="solver-note"','<div id="bound-explanation" class="muted"></div><div id="solver-note"')
    html=html.replace('<span class="muted">현재 해</span>','<span class="muted">검증 FULL UB</span>')
    html=html.replace('async function refresh(){',extra_script+'async function refresh(){')
    html=html.replace("$('inc').textContent=s.incumbent;", "renderStageBounds(s.stage_bounds);$('metrics-scope').textContent=s.metrics_label||'현재 단계';$('bound-explanation').textContent=s.bound_details?.lines?.join(String.fromCharCode(10))||'현재 단계 결과 수집 대기';$('inc').textContent=s.incumbent;")
    pointer=optional(Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json'))
    current=Path(pointer['root']) if pointer.get('root') else None
    if current and (current/'OPERATIONS/BATCH_STATE.json').exists():
        days=campaign_days(current);date_text=days[0].replace('-','.')+' — '+days[-1][5:].replace('-','.')
        html=html.replace('2025.05.01 — 05.07 · V43 Planning / SVR12 Actual',date_text+' · Planning 1 worker → Actual 최대 7 workers')
        html=html.replace('V44 · 5월 캠페인','V44 r043 · 5월 8~14일 캠페인')
        html=html.replace('28 Case 진행','현재 캠페인 단계 진행')
    return actual_ticks_html(html).encode('utf8')


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
