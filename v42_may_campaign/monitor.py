"""Read-only extension of the existing localhost HTTP/one-second monitor."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import time

from v42_pr134_b1.common import atomic, read, process, same_process, now
from .coordinator import AXIS, counts, key, load_manifest, runtime_path, read_actives, worker_snapshot


def optional_json(path, default=None):
    try:
        return read(path) if Path(path).is_file() else ({} if default is None else default)
    except (ValueError, OSError):
        return {} if default is None else default


def first_value(mapping, *names):
    for name in names:
        if mapping.get(name) is not None:
            return mapping[name]
    return None


def view(root):
    root = runtime_path(root)
    manifest = load_manifest(root, verify=False)
    live = optional_json(root / 'CAMPAIGN_STATUS.json')
    heartbeat = optional_json(root / 'COORDINATOR_HEARTBEAT.json')
    checkpoint = optional_json(root / 'CHECKPOINT.json')
    if not checkpoint:
        checkpoint = dict(state='STATUS_UNAVAILABLE' if (root / 'CHECKPOINT.json').exists() else 'READY',
                          dates={key(arm, day): dict(arm=arm, day=day, status='PENDING', attempts=0)
                                 for arm, day in AXIS})
    active = optional_json(root / 'ACTIVE.json', live.get('active', {}))
    try:
        actives = read_actives(root)
        workers = [worker_snapshot(row) for row in actives.values()]
    except (OSError, ValueError, PermissionError, KeyError):
        actives, workers = {}, []
    worker_slots = [next((row for row in workers if row['arm'] == 'B2' and row.get('worker_slot', 1) == slot),
                        dict(worker_slot=slot, arm='B2', day=None, PID=None, phase='IDLE',
                             worker_alive=False, progress={}, resource={}, heartbeat={})) for slot in range(1, 4)]
    progress = live.get('progress', {})
    report_age = None
    if active.get('request'):
        request = optional_json(active['request'])
        if request.get('progress'):
            progress_path = Path(request['progress'])
            progress = optional_json(progress_path, progress)
            if progress_path.is_file():
                report_age = max(0.0, time.time() - progress_path.stat().st_mtime)
    stamp = heartbeat.get('timestamp_UTC')
    age = max(0.0, time.time() - datetime.fromisoformat(stamp).timestamp()) if stamp else None
    alive = same_process(heartbeat.get('process', {}))
    worker_alive = same_process(active.get('worker', {}))
    state = checkpoint['state']
    status = ('완료' if state == 'COMPLETE' else '실행 중' if alive and age is not None and age < 30
              else '갱신 지연' if alive else '대기' if state == 'READY' else 'Coordinator 연결 끊김')
    native = first_value(progress, 'cumulative_native_runtime', 'Native_Runtime_seconds', 'Native_Runtime', 'native_seconds', 'native_runtime')
    wall = first_value(progress, 'wall_seconds', 'Wall_Time', 'wall_elapsed_seconds', 'elapsed_wall_seconds')
    # During model generation the Coordinator can report elapsed date Wall
    # from its immutable start timestamp without inventing solver runtime.
    if wall is None and active.get('started_UTC'):
        wall = max(0.0, time.time() - datetime.fromisoformat(active['started_UTC']).timestamp())
    remaining = first_value(progress, 'remaining_wall_seconds', 'remaining_seconds')
    if remaining is None and isinstance(wall, (int, float)):
        remaining = max(0.0, 5400.0 - wall)
    arm = active.get('arm')
    totals = counts(checkpoint)
    rows = list(checkpoint['dates'].values())
    monitor = optional_json(root / 'MONITOR_PROCESS.json')
    watchdog = optional_json(root / 'WATCHDOG_STATUS.json')
    return dict(
        run_id=manifest['run_id'], state=state, status=status,
        tone='#059669' if state == 'COMPLETE' or alive else '#d97706',
        current_phase=arm, current_day=active.get('day'),
        total_arm_dates=62, completed=totals['completed'], totals=totals,
        B1=counts(checkpoint, 'B1'), B2=counts(checkpoint, 'B2'),
        date_tables={a: [r for r in rows if r['arm'] == a] for a in ('B1', 'B2')},
        B2_requires_all_B1_terminal=True,
        B2_ready=counts(checkpoint, 'B1')['completed'] == 31,
        transition=optional_json(root / 'B1_TO_B2_TRANSITION_VERIFICATION.json'),
        Coordinator_PID=heartbeat.get('process', {}).get('PID'),
        Worker_PID=active.get('worker', {}).get('PID'),
        worker_identity=active.get('worker'), worker_alive=worker_alive, coordinator_alive=alive,
        workers=workers, worker_slots=worker_slots, Worker_PIDs=[row['PID'] for row in workers],
        B1_parallel_workers=1, B2_parallel_workers=3,
        Monitor_PID=monitor.get('PID'), watchdog=watchdog,
        solver_phase=first_value(progress, 'phase', 'solver_phase'),
        Native_Runtime_seconds=native, wall_seconds=wall, remaining_seconds=remaining,
        wall_budget_seconds=5400, native_budget_seconds=5400, target_gap=0.005 if arm == 'B1' else 0.03,
        UB=first_value(progress, 'UB', 'incumbent', 'valid_UB', 'best_ub'),
        Native_BestBd=first_value(progress, 'Native_BestBd', 'BestBd', 'native_best_bound'),
        independent_Global_LB=first_value(progress, 'independent_Global_LB', 'global_lb', 'certified_global_lb'),
        Certified_Gap=first_value(progress, 'Certified_Gap', 'certified_gap', 'global_gap'),
        Planning_max_line_loading=first_value(progress, 'Planning_max_line_loading', 'planning_rho_max'),
        Fresh_AC_max_line_loading=first_value(progress, 'Fresh_AC_max_line_loading', 'rho_max_AC'),
        voltage_violations=first_value(progress, 'voltage_violations', 'voltage_violation_count'),
        current_violations=first_value(progress, 'current_violations', 'line_current_violation_count'),
        transformer_violations=first_value(progress, 'transformer_violations', 'transformer_kva_violation_count'),
        resource=live.get('resource', {}), heartbeat_age_seconds=age, solver_report_age_seconds=report_age,
        last_error=checkpoint.get('last_error') or optional_json(root / 'COORDINATOR_ERROR.json') or None,
        last_update_UTC=live.get('timestamp_UTC'), snapshot_timestamp=now(),
        refresh_interval_seconds=1, read_only=True, optimizer_controls=False,
        progress=progress, runtime_root=str(root), Threads=1, P2_calls=0,
    )


def run(root, port=None):
    root = runtime_path(root)
    manifest = load_manifest(root, verify=False)
    port = int(port if port is not None else manifest.get('monitor_port', 8793))
    if port == 8791:
        raise PermissionError('LEGACY_MONITOR_PORT_MUST_BE_PRESERVED')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                if self.path in ('/', '/index.html'):
                    payload = (Path(__file__).parent / 'monitor_index.html').read_bytes()
                    mime = 'text/html; charset=utf-8'
                elif self.path == '/api/status':
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
            except Exception as error:
                self.send_error(503, str(error))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    atomic(root / 'MONITOR_PROCESS.json', process())
    atomic(root / 'MONITOR_SERVER.json', dict(URL=f'http://127.0.0.1:{port}/', UTC=now(),
                                            process=process(), read_only=True))
    server.serve_forever()


if __name__ == '__main__':
    run(sys.argv[1])
