"""Independent local HTTP observer; no production process lifecycle control."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import socket
import threading
import uuid

import psutil
from .monitor import view


class ExclusiveMonitorHTTPServer(ThreadingHTTPServer):
    """A second Windows observer must not share and overwrite this address."""
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def atomic(path, value):
    temporary = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Snapshot:
    def __init__(self, root, interval=5.):
        self.root, self.interval = Path(root), interval
        self.payload, self.error = None, None
        self.mutex = threading.Lock()
        self.stop = threading.Event()

    def refresh(self):
        try:
            payload = json.dumps(view(self.root), ensure_ascii=False, allow_nan=False).encode('utf8')
            with self.mutex:
                self.payload, self.error = payload, None
        except Exception as error:
            with self.mutex:
                self.error = str(error)

    def loop(self):
        while not self.stop.is_set():
            self.refresh()
            self.stop.wait(self.interval)

    def get(self):
        with self.mutex:
            if self.error or self.payload is None:
                return 503, json.dumps(dict(read_only=True, error=self.error or 'SNAPSHOT_LOADING')).encode('utf8')
            return 200, self.payload


def run(root, port=8794):
    root = Path(root).resolve()
    if port in (8791, 8793):
        raise PermissionError('EXISTING_MONITOR_PORT_PRESERVED')
    if not (root / 'SUPERVISOR_STATE.json').is_file():
        raise ValueError('PRODUCTION_SUPERVISOR_STATE_REQUIRED')
    observer = Snapshot(root)
    index = Path(__file__).with_name('index.html').read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path in ('/', '/index.html'):
                code, payload, mime = 200, index, 'text/html; charset=utf-8'
            elif path in ('/api/status', '/api/health'):
                code, payload = observer.get()
                mime = 'application/json; charset=utf-8'
            else:
                self.send_error(404)
                return
            try:
                self.send_response(code)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ExclusiveMonitorHTTPServer(('127.0.0.1', int(port)), Handler)
    server.daemon_threads = True
    observer.refresh()
    thread = threading.Thread(target=observer.loop, daemon=True, name='production-observer')
    thread.start()
    proc = psutil.Process()
    receipt = dict(URL=f'http://127.0.0.1:{port}/', read_only=True,
                   UTC=datetime.now(timezone.utc).isoformat(), runtime_root=str(root),
                   process=dict(PID=proc.pid, created=proc.create_time(), command=proc.cmdline()),
                   display_version='V42_AUTONOMOUS_MONITOR_V1', snapshot_interval_seconds=5.)
    atomic(root / 'AUTONOMOUS_MONITOR_SERVER.json', receipt)
    try:
        server.serve_forever()
    finally:
        observer.stop.set()
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('--port', type=int, default=8794)
    args = parser.parse_args()
    run(args.root, args.port)
