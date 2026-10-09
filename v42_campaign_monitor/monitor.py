"""Live display clocks and evidence-backed build milestones; no solver writes."""
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sys
import time

from v42_may_campaign import monitor as original
from v42_pr134_b1.common import atomic, process, now

_cpu_samples={}
_rss_peaks={}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def take(mapping, *names):
    return next((mapping[n] for n in names if finite(mapping.get(n))), None)


def age(stamp, epoch):
    try:
        return max(0., epoch - datetime.fromisoformat(stamp).timestamp()) if stamp else None
    except (ValueError, TypeError):
        return None


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def build_progress(arm, progress, output):
    """Count confirmed stages, never convert elapsed budget into completion."""
    output = Path(output)
    phase = progress.get('phase', '')
    builder = progress.get('builder_phase', '')
    audit = original.optional_json(output / 'STATIC/DATA/SCIENTIFIC_JOB_CLASS_AUDIT.json')
    jobs = take(audit, 'jobs')
    classes = take(audit, 'class_count')
    counters = {}
    for label, names in (
        ('모델 구성 작업', ('jobs_modelled',)),
        ('입력 처리(마지막 보고)', ('jobs_complete',)),
        ('전체 작업', ('total_jobs',)),
        ('변수', ('partial_variables', 'variables', 'cols')),
        ('제약식', ('partial_constraints', 'constraints', 'rows')),
        ('비영 계수', ('partial_nonzeros', 'nonzeros', 'nnz')),
        ('이진 변수', ('partial_binary_count', 'binary_count')),
        ('연속 변수', ('partial_continuous_count', 'continuous_count')),
        ('생성 옵션', ('complete_option_binaries_added',)),
        ('전체 옵션', ('total_authorized_complete_options',)),
    ):
        value = take(progress, *names)
        if value is not None:
            counters[label] = value
    if jobs is not None:
        counters['전체 작업'] = jobs
    if classes is not None:
        counters['전체 클래스'] = classes
    downstream = (phase.startswith('M_ADAPTIVE_') or phase in (
        'PHASE_I', 'ORIGINAL_P1', 'LOCAL_PRICING', 'INTEGER_CONTROL',
        'M_SAME_DAY_P1_INTEGER_SEED', 'M_SAME_DAY_FULL_LP_EXACT_LB',
        'P1_CERTIFICATION_COMPLETE', 'PLANNING_FIXED_DECISION_FREEZE',
        'ACTUAL_FIXED_DECISION_MATERIALIZATION', 'ACTUAL_SOURCE_MATERIALIZATION',
        'FRESH_OPENDSS_ORIGINAL_96_SLOT_REPLAY') or
        bool(original.optional_json(output / ('A_PREPARE_RECEIPT.json' if arm == 'B1' else 'M_CASE_VERIFICATION.json')).get('PASS')))
    complete = downstream or phase == 'A_STATIC_CASE_VERIFIED'
    if arm == 'B1':
        labels = ['날짜 입력', '계통·물리 도메인 준비', '원본 모델 조립', '클래스별 완전 블록', '구조 검증']
        data_done = (output / 'STATIC/DATA/DATA.pkl').is_file()
        domain_done = (output / 'ACTIVE_SCIENTIFIC_FIXED_SEMANTICS.json').is_file()
        model_done = builder in ('MODEL_BUILD_COMPLETE', 'COMPLETE_NATIVE_BLOCK') or phase == 'A_COMPLETE_NATIVE_BLOCKS'
        block_dir = output / 'STATIC/FULL_BLOCKS'
        blocks = len(list(block_dir.glob('*.pkl.gz'))) if block_dir.is_dir() else 0
        required = take(progress, 'classes_required') or classes
        block_phase = builder == 'COMPLETE_NATIVE_BLOCK' or phase == 'A_COMPLETE_NATIVE_BLOCKS'
        if block_phase:
            blocks = max(blocks, take(progress, 'classes_complete') or 0)
        blocks_done = bool(required and blocks >= required)
        confirmed = 5 if complete else 4 if blocks_done else 3 if model_done else 2 if domain_done or builder == 'MODEL_BUILD_ENTER' else 1 if data_done else 0
        fraction = blocks / required if block_phase and required else None
        if block_phase:
            counters['완료 블록'] = blocks
            if required:
                counters['전체 블록'] = required
    else:
        labels = ['날짜 입력', '원본 모델 조립', '정적 압축', '구조 검증']
        confirmed = len(labels) if complete else 2 if phase == 'M_EXISTING_COMPACT_STATIC_PRESOLVE' else 1 if phase == 'M_ORIGINAL_MODEL_BUILD' else 0
        fraction = None
    steps = [dict(label=label, state='done' if i < confirmed else 'active' if i == confirmed else 'pending')
             for i, label in enumerate(labels)]
    # Completion means confirmed milestones, explicitly not estimated build work.
    return dict(complete=complete, confirmed_steps=confirmed, total_steps=len(labels),
                percent=100. * confirmed / len(labels), basis='confirmed_milestones',
                current=labels[min(confirmed, len(labels) - 1)] if not complete else '모델 생성 완료',
                steps=steps, counters=counters, block_fraction=fraction, jobs=jobs, classes=classes,
                phase=phase, builder_phase=builder or None)


def enrich_worker(row, epoch):
    result = dict(row)
    request = original.optional_json(row.get('request', '')) if row.get('request') else {}
    progress = dict(row.get('progress') or {})
    stamp = progress.get('timestamp_UTC')
    report_age = age(stamp, epoch)
    reported_wall = take(progress, 'wall_seconds', 'Wall_Time', 'wall_elapsed_seconds', 'elapsed_wall_seconds')
    elapsed = age(row.get('started_UTC') or request.get('started_UTC'), epoch)
    # The monitor clock advances even during a long, silent original builder call.
    wall = max(elapsed or 0., reported_wall or 0.) if row.get('worker_alive') else reported_wall
    hb_age = age(row.get('heartbeat_timestamp_UTC') or (row.get('heartbeat') or {}).get('timestamp_UTC'), epoch)
    ledger = original.optional_json(Path(request['result']).parent / 'NATIVE_RUNTIME_LEDGER.json') if request.get('result') else {}
    output=Path(request.get('output',row.get('output','')))
    detail=original.optional_json(output/'MODEL_BUILD_DETAIL.json')
    prepared=original.optional_json(output/('A_PREPARE_RECEIPT.json' if row.get('arm')=='B1' else 'M_CASE_VERIFICATION.json'))
    native = take(progress, 'cumulative_native_runtime', 'Native_Runtime_seconds', 'Native_Runtime', 'native_seconds')
    if native is None:
        native = take(ledger, 'measured_Native_Runtime')
    target = .005 if row.get('arm') == 'B1' else .03
    # Generic solver gap/BestBd are never promoted into an independent certificate.
    ub = take(progress, 'UB', 'valid_UB', 'best_ub')
    lb = take(progress, 'independent_Global_LB', 'Certified_Global_LB', 'global_LB', 'certified_global_lb')
    gap = take(progress, 'Certified_Gap', 'certified_gap')
    if gap is None and finite(ub) and finite(lb) and ub > 0 and lb <= ub:
        gap = max(0., (ub - lb) / abs(ub))
    planning = take(progress, 'Planning_max_line_loading', 'planning_rho_max')
    fresh = take(progress, 'Fresh_AC_max_line_loading', 'rho_max_AC')
    preparation=take(prepared,'preparation_wall_seconds')
    if preparation is None:
        preparation=take(detail,'model_preparation_seconds')
        if preparation is not None and row.get('worker_alive') and not prepared.get('PASS'):
            preparation+=age(detail.get('build_detail_UTC'),epoch) or 0.
    costs=ledger.get('costs',[])
    prep_costs=[r.get('exclusive_non_native_wall_seconds',r.get('wall_seconds',0.)) for r in costs
        if r.get('kind')=='model_preparation' or 'model_build' in r.get('kind','') or r.get('kind') in ('exact_price_build','full96_prices')]
    if prep_costs:preparation=sum(prep_costs)
    validation=sum(r.get('exclusive_non_native_wall_seconds',r.get('wall_seconds',0.)) for r in costs
        if r.get('kind')=='integer_physical_validation' or 'replay' in r.get('kind','') or 'Global_LB' in r.get('kind',''))
    cpu=(row.get('resource') or {}).get('CPU_seconds');worker_id=str(row.get('worker',{}))
    rss=(row.get('resource') or {}).get('RSS')
    if finite(rss):_rss_peaks[worker_id]=max(_rss_peaks.get(worker_id,0),rss)
    cpu_delta=None;cpu_window=None
    if finite(cpu):
        samples=_cpu_samples.setdefault(worker_id,[]);samples.append((epoch,cpu))
        while len(samples)>1 and epoch-samples[0][0]>120:samples.pop(0)
        cpu_window=epoch-samples[0][0];cpu_delta=cpu-samples[0][1]
    fresh_time=take(progress,'evaluation_wall_seconds','Fresh_AC_seconds')
    if fresh_time is None and progress.get('evaluation_started_UTC'):
        fresh_time=age(progress['evaluation_started_UTC'],epoch)
    remaining=max(0.,5400.-(native or 0.))
    result.update(progress=progress, wall_seconds=wall, reported_wall_seconds=reported_wall,
                  remaining_seconds=remaining,native_remaining_seconds=remaining,
                  model_preparation_seconds=preparation,validation_seconds=validation,
                  Fresh_AC_seconds=fresh_time,build_detail=detail,
                  bottleneck_function=detail.get('build_function'),
                  CPU_delta_seconds=cpu_delta,CPU_observation_seconds=cpu_window,
                  observed_peak_RSS_bytes=_rss_peaks.get(worker_id),
                  last_internal_progress_UTC=stamp,
                  native_budget_violation=finite(native) and native>5400.,
                  policy_version=request.get('policy_version','LEGACY_WALL_POLICY'),
                  heartbeat_age_seconds=hb_age, solver_report_age_seconds=report_age,
                  Native_Runtime_seconds=native, Native_calls=len(ledger.get('calls', [])),
                  native_inflight=bool(ledger.get('inflight')), target_gap=target,
                  UB=ub, independent_Global_LB=lb, Certified_Gap=gap,
                  Planning_max_line_loading=planning, Fresh_AC_max_line_loading=fresh,
                  phase=progress.get('phase', row.get('phase')),
                  report_delayed=report_age is not None and report_age > 30.,
                  heartbeat_recent=hb_age is not None and hb_age < 15.,
                  build=build_progress(row.get('arm'), progress, request.get('output', row.get('output', ''))))
    return result


def view(root):
    snapshot = original.view(root)
    epoch = time.time()
    snapshot['workers'] = [enrich_worker(row, epoch) for row in snapshot['workers']]
    snapshot['worker_slots'] = [next((r for r in snapshot['workers'] if r.get('arm') == 'B2' and r.get('worker_slot') == slot),
                                    dict(worker_slot=slot, arm='B2', day=None, phase='IDLE', worker_alive=False))
                                for slot in range(1, 4)]
    if snapshot['workers']:
        primary = snapshot['workers'][0]
        for name in ('wall_seconds', 'remaining_seconds', 'Native_Runtime_seconds', 'UB', 'independent_Global_LB',
                     'Certified_Gap', 'Planning_max_line_loading', 'Fresh_AC_max_line_loading', 'solver_report_age_seconds'):
            snapshot[name] = primary[name]
    snapshot.update(display_version='20261009.2', server_epoch=epoch,wall_budget_seconds=None,
                    campaign_percent=100. * snapshot['completed'] / snapshot['total_arm_dates'],
                    completion_basis='terminal_dates', telemetry_only=True,
                    frozen_campaign_sources_modified=False)
    return clean(snapshot)


def run(root, port=None):
    root = original.runtime_path(root)
    manifest = original.load_manifest(root, verify=False)
    port = int(port if port is not None else manifest.get('monitor_port', 8793))
    if port == 8791:
        raise PermissionError('LEGACY_MONITOR_PORT_MUST_BE_PRESERVED')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?', 1)[0]
            try:
                if path in ('/', '/index.html'):
                    payload = Path(__file__).with_name('index.html').read_bytes()
                    mime = 'text/html; charset=utf-8'
                elif path == '/api/status':
                    payload = json.dumps(view(root), ensure_ascii=False, allow_nan=False).encode('utf-8')
                    mime = 'application/json; charset=utf-8'
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                self.send_error(503, str(error))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    atomic(root / 'MONITOR_PROCESS.json', process())
    atomic(root / 'MONITOR_SERVER.json', dict(URL=f'http://127.0.0.1:{port}/', UTC=now(), process=process(),
                                            read_only=True, display_version='20261009.1'))
    server.serve_forever()


if __name__ == '__main__':
    run(sys.argv[1])
