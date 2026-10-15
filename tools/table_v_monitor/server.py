"""Read-only monitor adapter; deliberately outside the frozen solver checkout."""
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import argparse
import hashlib
import json
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION05'
sys.path.insert(0, str(REPO))
from tools import serve_v42_table_v_monitor as core
from v42_integration.table_v_memory import memory_sample
import psutil

PHASES = {
    'SEMANTIC_CLASS_SOURCE_AUDIT': '현재 날짜 계약·입력 검증',
    'EXACT_SEMANTIC_CLASS_EQUIVALENCE': '수학적 Class 동등성 검증',
    'EXACT_LOCAL_SUM_ASSEMBLY': '검증된 Class 행렬 집계',
    'EXACT_REDUNDANT_ROW_PROOF': '중복 제약 동치성 검증',
    'SEMANTIC_CLASS_PRICING_CACHE': '전체 Pricing 블록 준비',
    'VERIFIED_CLASS_DW_NATIVE0_PASS': '압축 검증 완료 · DW 준비 완료',
    'ORIGINAL_SOURCE_DOMAIN_AUDIT': 'E1 계약·입력 검증',
    'INDEPENDENT_PHYSICAL_DOMAIN_REPLAY': 'GPU·WAN·서비스 Domain 검증',
    'INDEPENDENT_DOMAIN_AND_COMPLETE_GRAPH_SHA_PASS': 'Domain 검증 완료',
    'ORIGINAL_REFERENCE_ASSEMBLY': 'DW 기준 행렬 구성',
    'ORIGINAL_FULL_REFERENCE_MATH_EQUIVALENCE': 'FULL ↔ DW 수학적 동일성 검증',
    'ORIGINAL_FULL_REFERENCE_MATH_EQUIVALENCE_PASS': 'FULL ↔ DW 동일성 검증 완료',
    'ORIGINAL_V6_COMPACT_SOURCE_BUILD': 'DW Compact 모델 생성',
    'ORIGINAL_COMPACT_CONSTRUCTED_LOCAL_WITNESS': 'DW 초기 실행 가능점 검증',
    'COMPLETE_SOURCE_PRICING_ROSTER': '전체 Pricing 블록 준비',
    'ORIGINAL_FULL_AND_COMPLETE_DW_NATIVE0_PASS': 'DW 준비 완료 · 최적화 모델 연결',
    'AUTHORIZED_DOMAIN_GEOMETRY': '허용 Domain 생성',
    'NATIVE_BINDINGS': 'FULL 모델 연결',
    'ACTUAL': 'Actual 96슬롯 실행',
    'FRESH_AC': '정착 Fresh AC 96슬롯 검증',
}
_samples = {}
_lock = threading.Lock()


def process_sample(pid, source, previous=None, now=None):
    now = time.time() if now is None else now
    try:
        process = psutil.Process(pid)
        command = process.cmdline()
        # PID reuse and unrelated Python processes must never count as this run.
        if not any('run_v42_production_campaign.py' in s or 'run_v42_table_v.py' in s for s in command):
            return {'alive': False, 'pid': pid, 'reason': 'OWNER_COMMAND_MISMATCH'}
        token = str(source).replace('\\', '/').lower()
        if not any(token in s.replace('\\', '/').lower() or str(source.name).lower() in s.lower() for s in command):
            return {'alive': False, 'pid': pid, 'reason': 'OWNER_EXECUTION_MISMATCH'}
        info = process.memory_info()
        cpu = sum(process.cpu_times()[:2])
        created = process.create_time()
        key = (pid, created)
        with _lock:
            old = _samples.get(key)
            percent = 100 * (cpu-old[1])/(now-old[0]) if old and now > old[0] else None
            _samples[key] = (now, cpu)
        return dict(alive=process.is_running(), pid=pid, CPU_one_core_percent=percent,
                    CPU_seconds=cpu, RSS_bytes=info.rss, private_bytes=getattr(info, 'private', None),
                    started_epoch=created, elapsed_seconds=max(0, now-created))
    except (psutil.Error, TypeError, ValueError):
        return dict(alive=False, pid=pid, reason='OWNER_NOT_AVAILABLE')


def preserved_b0(source):
    pointer = core.read_small(source/'PRESERVED_B0_BASELINE.json')
    record = pointer.get('outcome', {})
    if not pointer.get('baseline_preserved') or not record:
        return None
    path = Path(record.get('path', ''))
    try:
        raw = path.read_bytes()
        if len(raw) != record.get('bytes') or hashlib.sha256(raw).hexdigest() != record.get('sha256'):
            return dict(status='EVIDENCE_MISMATCH', historical=True)
        outcome = json.loads(raw)
        actual = core.unwrap(outcome.get('actual', {}))
        fresh = core.unwrap(outcome.get('fresh', {}))
        return dict(status=outcome.get('status'), historical=True, sha_verified=True,
                    actual_slots=actual.get('executed_actual_slots'), fresh_slots=fresh.get('executed_slots'),
                    current_release_recertified=False, evidence=str(path))
    except (OSError, ValueError):
        return dict(status='EVIDENCE_UNAVAILABLE', historical=True)


def phase_for(folder, row, inflight, built):
    if row.get('raw_arm_status'):
        return dict(code=row['current_phase'], label='실행 완료' if row['raw_arm_status']=='FULL_PASS' else '실행 중단', source='ARM_OUTCOME')
    if inflight:
        label = inflight.get('label', '')
        if ':DW:PHASE_I' in label:
            title = 'DW Phase I 최적화'
        elif ':DW:ORIGINAL_P1' in label:
            title = 'DW P1 최적화'
        elif ':DW:LOCAL_PRICING' in label:
            title = 'DW Pricing 최적화'
        elif 'K48' in label:
            title = 'K48 하한 검증'
        elif row.get('current_stage', '').startswith('M'):
            title = 'MESS Joint MILP 최적화'
        else:
            title = 'FULL 정수 MILP 최적화'
        return dict(code='NATIVE_OPTIMIZE_RUNNING', label=title, source='NATIVE_LEDGER', native_label=label)
    stage = row.get('current_stage') or ''
    dwpath = folder/stage/'DW/NATIVE0_PREPARATION_PROGRESS.json'
    dw = core.read_small(dwpath) if stage in ('A1','A2') else {}
    if dw:
        code = dw.get('phase', '')
        return dict(code=code, label=PHASES.get(code, code), source='DW_PREPARATION',
                    record_epoch=dwpath.stat().st_mtime,
                    completed=dw.get('classes_complete',dw.get('classes')), required=dw.get('classes_required',dw.get('required_classes')))
    if stage in ('A1','A2') and built:
        return dict(code='DW_PREPARATION_PENDING', label='DW 입력 준비', source='BUILD_LEDGER')
    value = core.read_small(folder/'LIVE_PROGRESS.json')
    p = value.get('progress') or {}
    if not isinstance(p, dict): p = {'phase': str(p)}
    code = p.get('phase') or row.get('current_phase') or 'WAITING'
    return dict(code=code, label=PHASES.get(code, code if code!='WAITING' else '실행 대기'), source='LIVE_PROGRESS',
                completed=p.get('jobs_complete',p.get('units_complete')),
                required=p.get('jobs_required',p.get('units_required')))


def certified_bounds(folder, stage, context):
    case = context.get('stage_case_sha')
    if not case or stage not in ('A1','A2'): return dict(LB=None, UB=None, gap_percent=None)
    result = core.read_small(folder/stage/'P1_ONLY_RESULT.json')
    dw = core.read_small(folder/stage/'DW/DW_RESULT.json') or result.get('DW', {})
    lower = dw.get('Global_LB') if (dw.get('case_sha')==case and dw.get('LB_certified') is True
                    and dw.get('full_domain_pricing_complete') is True) else None
    upper = result.get('objective') if result.get('case_sha')==case and result.get('FULL_feasible') is True else None
    if result.get('case_sha')==case and result.get('Original_Integer_Bound_Certificate'):
        from v42_integration.table_v_a_control import verified_integer_lower
        integer=verified_integer_lower(result)
        if integer is not None:lower=max(v for v in (lower,integer) if v is not None)
    gap = (upper-lower)/upper*100 if (core.finite(lower) and core.finite(upper) and upper>0 and lower<=upper) else None
    return dict(LB=lower, UB=upper, gap_percent=gap)


def state(source=SOURCE):
    source = Path(source).resolve()
    value = core.state(source)
    planning = core.read_small(source/'PLANNING_NATIVE_LEDGER.json')
    k48 = core.read_small(source/'K48_NATIVE_LEDGER.json')
    now = time.time()
    value['monitor_version'] = 'SIMPLE_READ_ONLY_20261015'
    plan=core.read_small(source/'PRODUCTION_LAUNCH_PLAN.json')
    value['run_arms']=plan.get('run_arms',[])
    value['execution_superseded']=(source/'SUPERSESSION02/SUPERSESSION_RECEIPT.json').is_file()
    audit=Path(r'D:\v42_month_compression_native0_20261015\ALL31')
    value['compression_audit']=dict(core.read_small(audit/'PROGRESS.json'),
        complete=bool(core.read_small(audit/'COMPLETE.json')),
        results=core.read_small(audit/'MONTH_RESULTS.json'))
    value['historical_B0'] = preserved_b0(source)
    recovery=core.read_small(REPO/'docs/v42_phase_gap_recovery_20261015/RESULTS.json')
    value['phase_policy_recovery']=recovery if source.name=='EXECUTION07' else {}
    value['system'] = memory_sample()
    value['archived_native_seconds'] = planning.get('archived_native_seconds_excluded_from_current_cycle')
    for row in value['arms']:
        arm = row['arm']
        folder, _ = core.attempt_folder(source, arm)
        active = next((ledger for ledger in (planning,k48) if
            (ledger.get('inflight') or {}).get('stage_context', {}).get('arm')==arm), None)
        active = active or next((ledger for ledger in (planning,k48) if
            ((ledger.get('inflight') or {}).get('stage_context') or ledger.get('active_stage_context') or {}).get('arm')==arm), {})
        flight = active.get('inflight')
        context = (flight or {}).get('stage_context') or active.get('active_stage_context') or {}
        stage = row.get('current_stage') or ''
        budget_ledger = k48 if active is k48 else planning
        calls = [r for r in budget_ledger.get('calls', []) if r.get('stage_context', {}).get('arm')==arm
                 and r.get('stage_context', {}).get('stage')==stage
                 and r.get('stage_context', {}).get('source_sha')==value.get('source_sha')]
        builds = [r for r in calls if r.get('solver')=='BUILD']
        row['phase_display'] = phase_for(folder, row, flight, bool(builds))
        if stage in ('A1','A2'):
            candidates=list((folder/stage/'DW').glob('PHASE_I/S*/*/SOLVER_PROGRESS.json'))
            row['solver_progress']=core.read_small(max(candidates,key=lambda p:p.stat().st_mtime)) if candidates else {}
            row['phase_I_trace']=core.read_small(folder/stage/'DW/PHASE_I_TRACE.json')
        row['phase_display']['age_seconds'] = max(0, now-row['phase_display']['record_epoch']) if row['phase_display'].get('record_epoch') else None
        pid = active.get('active_stage_owner_pid') or (flight or {}).get('pid')
        if not pid and not row.get('raw_arm_status') and stage:
            pid=core.read_small(source/'EXECUTION_LAUNCH_OWNER.json').get('pid')
        row['process'] = process_sample(pid, source, now=now) if pid else dict(alive=False,pid=None)
        natives = [r for r in calls if r.get('solver','').startswith('GUROBI')]
        row['stage_budget'] = dict(
            cap=budget_ledger.get('authorization_document', {}).get('stage_caps_seconds', {}).get(arm+':'+stage),
            kind='K48 별도' if budget_ledger is k48 else 'Planning',
            used=sum(r['Native_Runtime'] for r in natives) if all(core.finite(r.get('Native_Runtime')) for r in natives) else None,
            completed_calls=len(natives), inflight=bool(flight),
            call_wall=max(0,now-flight['started_epoch_seconds']) if flight and core.finite(flight.get('started_epoch_seconds')) else None)
        row['bounds'] = certified_bounds(folder, stage, context)
        row['mess_search']=(core.read_small(folder/stage/'COOPERATIVE_SEARCH/COMMON_M_PR222/ADAPTIVE_PROGRESS.json') or
            core.read_small(folder/stage/'COMMON_M_PR222/ADAPTIVE_PROGRESS.json')) if stage.startswith('M') else None
        if stage.startswith('M'):
            mr=core.read_small(folder/stage/'TABLE_V_M_RESULT.json')
            combined=core.read_small(folder/stage/'COOPERATIVE_GLOBAL_ASSESSMENT.json')
            assessment=combined.get('M_stage_assessment') or core.read_small(folder/(stage+'_K48')/'TABLE_V_M_K48_ASSESSMENT.json')
            if mr.get('case_sha')==context.get('stage_case_sha') and mr.get('FULL_validated'):
                row['bounds']['UB']=mr.get('BEST_GLOBAL_UB')
                if assessment.get('stage_case_sha')==mr['case_sha'] and assessment.get('Global_LB_valid'):
                    row['bounds'].update(LB=assessment.get('Global_LB'),gap_percent=None if assessment.get('relative_global_gap') is None else assessment['relative_global_gap']*100)

        row['model_build_seconds'] = sum(r.get('measured_seconds',0) for r in builds) if builds else None
        model = core.read_small(folder/stage/'NATIVE0_FULL_FLEX_MODEL_CERTIFICATE.json') if stage else {}
        row['model_size'] = {k:model.get(k) for k in ('rows','columns','nonzeros','full_physical_domains')}
        profile=core.read_small(folder/stage/'DW/CLASS_COMPRESSION_BUILD_PROFILE.json') if stage else {}
        row['compression']=dict(profile,Job_count=model.get('full_physical_domains')) if profile else None
    return value


def handler(source):
    base = core.handler(source)
    class Handler(base):
        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path in ('/','/index.html'):
                    return self.send(Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
                if path=='/api/state':
                    return self.send(json.dumps(state(source),ensure_ascii=False,allow_nan=False), 'application/json; charset=utf-8')
                return super().do_GET()
            except (OSError, ValueError, KeyError, TypeError) as error:
                return self.send(json.dumps({'error':str(error)},ensure_ascii=False), 'application/json; charset=utf-8', 503)
    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--port',type=int,default=8794)
    args=parser.parse_args()
    print(json.dumps(dict(status='READ_ONLY_MONITOR',port=args.port,source=str(args.source))),flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.source)).serve_forever()
