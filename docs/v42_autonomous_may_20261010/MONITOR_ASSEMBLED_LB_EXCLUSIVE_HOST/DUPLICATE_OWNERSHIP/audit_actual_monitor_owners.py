"""Read-only OS ownership audit, including accepted HTTP connection owner."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import socket
import subprocess
import time

import psutil

OUT = Path(__file__).resolve().parent
ROOT = Path(r'D:\v42_may_restart_20261010_02')


def record(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def proc(pid):
    try:
        p = psutil.Process(pid)
        return dict(PID=pid, created=p.create_time(), command=p.cmdline(), cwd=p.cwd(),
            status=p.status(), connections=[dict(local=list(c.laddr), remote=list(c.raddr),
                status=c.status, fd=c.fd) for c in p.net_connections(kind='tcp')])
    except psutil.Error as error:
        return dict(PID=pid, error=type(error).__name__ + ':' + str(error))


def connection_owners(client_port):
    return [dict(PID=c.pid, status=c.status, local=list(c.laddr), remote=list(c.raddr))
            for c in psutil.net_connections(kind='tcp') if c.laddr and c.laddr.port == 8794
            and c.raddr and c.raddr.port == client_port]


def http_owner_sample():
    with socket.create_connection(('127.0.0.1', 8794), timeout=10) as client:
        port = client.getsockname()[1]
        client.sendall(b'GET /api/status HTTP/1.1\r\nHost: 127.0.0.1:8794\r\n')
        owners = []
        for _ in range(20):
            owners = connection_owners(port)
            if owners:
                break
            time.sleep(.05)
        client.sendall(b'Connection: close\r\n\r\n')
        blocks = []
        while True:
            block = client.recv(65536)
            if not block:
                break
            blocks.append(block)
        raw = b''.join(blocks)
        header, body = raw.split(b'\r\n\r\n', 1)
        value = json.loads(body)
        return dict(client_port=port, accepted_connection_owners=owners,
            response_status=header.split(b'\r\n')[0].decode('ascii'),
            response_body_SHA=hashlib.sha256(body).hexdigest(),
            snapshot_UTC=value.get('snapshot_UTC'), runtime_root=value.get('runtime_root'),
            supervisor_alive=value.get('supervisor_alive'), live_worker_count=value.get('live_worker_count'),
            first3=[dict(day=row['day'], status=row['B2']['status'], current_attempt=row['B2']['current_attempt'],
                bounds={name:row['B2']['bounds'].get(name) for name in ('UB','LB','gap','status','error')})
                for row in value['rows'][:3]])


def main():
    metadata_path = ROOT / 'AUTONOMOUS_MONITOR_SERVER.json'
    before = dict(processes=[proc(pid) for pid in (102084, 7340)], metadata=record(metadata_path),
        metadata_document=json.loads(metadata_path.read_text()),
        target_listeners=[dict(PID=c.pid, status=c.status, local=list(c.laddr)) for c in
            psutil.net_connections(kind='tcp') if c.laddr and c.laddr.port == 8794 and c.status == 'LISTEN'])
    samples = [http_owner_sample() for _ in range(3)]
    netstat = subprocess.check_output(['netstat', '-ano', '-p', 'tcp'], text=True, encoding='utf8', errors='replace')
    netstat_rows = [row.strip() for row in netstat.splitlines() if ':8794' in row]
    after = dict(processes=[proc(pid) for pid in (102084, 7340)], metadata=record(metadata_path))
    checks = dict(both_exact_owned_hosts_observed=all(p.get('cwd') == r'D:\MobileESS_v42_autonomous'
        and p.get('command', [])[4:] == ['-m','v42_autonomous_monitor.host',str(ROOT),'--port','8794']
        for p in before['processes']), metadata_unchanged=before['metadata'] == after['metadata'],
        all_connections_have_unique_observed_owner=all(len(s['accepted_connection_owners']) == 1 for s in samples),
        all_healthy_three_workers=all(s['supervisor_alive'] and s['live_worker_count'] == 3 for s in samples))
    payload = dict(UTC=datetime.now(timezone.utc).isoformat(), read_only=True, checks=checks,
        before=before, after=after, accepted_HTTP_samples=samples, netstat_8794_rows=netstat_rows,
        producer=record(__file__), Native_optimize_calls=0, model_constructions=0,
        process_mutations=0, limitations=['Accepted connection ownership identifies these samples only.',
            'No claim that only one matching host exists; metadata is last writer, not exclusive ownership.'])
    path = OUT / 'ACTUAL_MONITOR_8794_DUPLICATE_OWNER_READONLY_AUDIT.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(checks=checks, samples=[dict(owners=s['accepted_connection_owners'],
        snapshot_UTC=s['snapshot_UTC']) for s in samples], netstat=netstat_rows, receipt=record(path))))


if __name__ == '__main__':
    main()
