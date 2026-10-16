from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import pytest

from v43.common import atomic


def test_concurrent_build_and_construction_status_publish_complete_json(tmp_path):
    target = tmp_path / 'progress.json'
    def publish(n):
        for i in range(20):
            atomic(target, dict(writer=n, sequence=i, payload=list(range(100))))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(publish, range(4)))
    result = json.loads(target.read_text())
    assert result['sequence'] == 19
    assert result['payload'] == list(range(100))
    assert list(tmp_path.glob('*.tmp')) == []


def test_real_windows_reader_sharing_collision_is_retried(tmp_path):
    target = tmp_path / 'progress.json'
    atomic(target, dict(version=1))
    opened = threading.Event()
    def reader():
        with target.open('rb') as stream:
            opened.set()
            time.sleep(.025)
            assert json.load(stream)['version'] == 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(reader)
        assert opened.wait(1)
        atomic(target, dict(version=2))
        pending.result()
    assert json.loads(target.read_text()) == dict(version=2)


def test_invalid_json_does_not_damage_last_status_or_leave_temp_file(tmp_path):
    target = tmp_path / 'progress.json'
    atomic(target, dict(version=1))
    with pytest.raises(ValueError):
        atomic(target, dict(runtime=float('nan')))
    assert json.loads(target.read_text()) == dict(version=1)
    assert list(tmp_path.glob('*.tmp')) == []
