"""Real isolated sockets prove duplicate refusal before metadata replacement."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import socket
import threading
import time
from urllib.request import urlopen

import pytest

from v42_autonomous_monitor import host


def root_files(tmp_path):
    (tmp_path / 'SUPERVISOR_STATE.json').write_text('{"isolated_socket_test":true}')
    (tmp_path / 'AUTONOMOUS_MONITOR_SERVER.json').write_bytes(b'{"existing_owned_display":"preserve"}\n')
    return {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


def unchanged(tmp_path, before):
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


def test_exclusive_option_and_duplicate_actual_bind_refused(tmp_path):
    before = root_files(tmp_path)
    with host.ExclusiveMonitorHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as first:
        assert first.allow_reuse_address is False
        assert first.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        if os.name == 'nt':
            assert first.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) == 1
        port = first.server_address[1]
        with pytest.raises(OSError):
            host.run(tmp_path, port)
        with pytest.raises(OSError):
            ThreadingHTTPServer(('127.0.0.1', port), BaseHTTPRequestHandler)
    unchanged(tmp_path, before)


def test_legacy_reusable_owner_prevents_new_exclusive_start(tmp_path):
    before = root_files(tmp_path)
    with ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as first:
        with pytest.raises(OSError):
            host.run(tmp_path, first.server_address[1])
    unchanged(tmp_path, before)


@pytest.mark.parametrize('port', [8791, 8793])
def test_protected_existing_ports_rejected_without_bind_or_metadata(tmp_path, monkeypatch, port):
    before = root_files(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('NO_BIND_TO_PROTECTED_PORT')
    monkeypatch.setattr(host, 'ExclusiveMonitorHTTPServer', forbidden)
    with pytest.raises(PermissionError, match='EXISTING_MONITOR_PORT_PRESERVED'):
        host.run(tmp_path, port)
    unchanged(tmp_path, before)


def test_missing_production_state_rejected_before_bind(tmp_path, monkeypatch):
    metadata = tmp_path / 'AUTONOMOUS_MONITOR_SERVER.json'
    metadata.write_bytes(b'preserve')
    def forbidden(*args, **kwargs):
        raise AssertionError('NO_BIND_WITHOUT_ROOT_STATE')
    monkeypatch.setattr(host, 'ExclusiveMonitorHTTPServer', forbidden)
    with pytest.raises(ValueError, match='PRODUCTION_SUPERVISOR_STATE_REQUIRED'):
        host.run(tmp_path, 0)
    assert metadata.read_bytes() == b'preserve'


def test_successful_real_isolated_http_owner_receipt_after_bind(tmp_path, monkeypatch):
    root_files(tmp_path)
    created = []
    errors = []
    payload = dict(read_only=True, isolated_test=True, healthy=True)
    monkeypatch.setattr(host, 'view', lambda root: payload)
    original = host.ExclusiveMonitorHTTPServer

    class OneRequestServer(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.timeout = 3
            created.append(self)
        def serve_forever(self):
            self.handle_request()

    monkeypatch.setattr(host, 'ExclusiveMonitorHTTPServer', OneRequestServer)
    def run():
        try:
            host.run(tmp_path, 0)
        except Exception as error:
            errors.append(repr(error))
    worker = threading.Thread(target=run)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        metadata = tmp_path / 'AUTONOMOUS_MONITOR_SERVER.json'
        while time.monotonic() < deadline:
            current = json.loads(metadata.read_text())
            if current.get('process') and created:
                break
            time.sleep(.01)
        else:
            raise AssertionError('ISOLATED_HOST_OWNER_RECEIPT_TIMEOUT')
        port = created[0].server_address[1]
        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3) as reply:
            assert reply.status == 200 and json.load(reply) == payload
        assert current['process']['PID'] == os.getpid()
        assert current['runtime_root'] == str(tmp_path.resolve())
        assert current['read_only'] is True
    finally:
        worker.join(timeout=5)
    assert not worker.is_alive() and not errors
