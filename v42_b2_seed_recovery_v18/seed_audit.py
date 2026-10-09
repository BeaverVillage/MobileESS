"""Read persisted files/process identity; never attaches to a running Solver."""
import argparse
from pathlib import Path
import psutil
from .common import read, now, sha, atomic


def snapshot(root):
    root = Path(root).resolve()
    actives = read(root/'ACTIVES_V13.json')['workers']
    rows = []
    for key, active in sorted(actives.items()):
        if active['arm'] != 'B2':
            continue
        request_path = Path(active['request'])
        request = read(request_path)
        attempt = request_path.parent
        if not attempt.is_relative_to(root/'dates'/'B2'/active['day']):
            raise ValueError('ACTIVE_REQUEST_OUTSIDE_DATE')
        ledger_path = attempt/'NATIVE_RUNTIME_LEDGER.json'
        ledger, progress = read(ledger_path), read(attempt/'progress.json')
        process = active['worker']
        try:
            proc = psutil.Process(process['PID'])
            alive = proc.is_running() and abs(proc.create_time()-process['created']) < .01
            cpu = proc.cpu_times()
            cpu_seconds = cpu.user + cpu.system if alive else None
        except psutil.Error:
            alive, cpu_seconds = False, None
        completed = ledger.get('calls', [])
        inflight = ledger.get('inflight')
        # Completed-call attributes cannot describe a different in-flight call.
        metrics = dict(SolCount='UNKNOWN', incumbent='UNKNOWN', BestBd='UNKNOWN',
            Native_Gap='UNKNOWN', root='UNKNOWN', node='UNKNOWN')
        if inflight is None and completed:
            last = completed[-1]
            metrics.update(SolCount=last.get('SolCount','UNKNOWN'),
                incumbent=last.get('Native_incumbent','UNKNOWN'),
                BestBd=last.get('Native_BestBd','UNKNOWN'),
                Native_Gap=last.get('Native_Gap','UNKNOWN'), node=last.get('Native_NodeCount','UNKNOWN'))
            metrics = {k:'UNKNOWN' if v is None else v for k,v in metrics.items()}
        logs = [dict(path=str(p), bytes=p.stat().st_size) for p in attempt.glob('*NATIVE.log')]
        output = Path(request['output'])
        rows.append(dict(day=active['day'], PID=process['PID'], alive_same_process=alive,
            cumulative_CPU_seconds=cpu_seconds, callback_reported_Native_Runtime=progress.get('Native_Runtime','UNKNOWN'),
            progress_UTC=progress.get('timestamp_UTC'), completed_Native_Runtime=ledger['measured_Native_Runtime'],
            phase=progress.get('phase'), inflight=inflight, Native=metrics, logs=logs,
            independent_certificates=[p.name for p in output.glob('*CERTIFICATE*.json')],
            request_SHA=sha(request_path), ledger_SHA_at_read=sha(ledger_path),
            seed_identity=read(output/'SAME_DAY_SEED_MODEL_IDENTITY.json')))
    return dict(UTC=now(), read_only=True, additional_Native_calls=0, solver_interrupts=0,
        active_root=str(root), workers=rows, bottleneck='UNKNOWN_NO_LIVE_INCUMBENT_OR_NODE_TELEMETRY',
        unavailable_is_not_zero=True, ledger_and_progress_are_nontransactional_snapshots=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root'); parser.add_argument('report')
    args = parser.parse_args()
    root, report = Path(args.root).resolve(), Path(args.report).resolve()
    if report.is_relative_to(root) or report.is_relative_to(root.parents[2]):
        raise PermissionError('REPORT_MUST_BE_OUTSIDE_ACTIVE_CHECKOUT')
    atomic(report, snapshot(root))


if __name__ == '__main__':
    main()
