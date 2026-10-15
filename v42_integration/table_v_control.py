"""Durable cooperative cancellation of one Table V execution directory."""
import json
import os
from pathlib import Path
from time import time

STOP_FILE = 'CAMPAIGN_STOP_REQUEST.json'


class CampaignStopped(RuntimeError):
    pass


def stop_request(output, *, reason):
    root = Path(output).resolve()
    if not root.is_dir() or not reason:
        raise ValueError('EXISTING_EXECUTION_AND_STOP_REASON_REQUIRED')
    target = root / STOP_FILE
    record = dict(schema='TABLE_V_USER_STOP_REQUEST_V1', reason=reason,
                  execution_root=str(root), requested_epoch_seconds=time(), requester_pid=os.getpid())
    try:
        with target.open('x', encoding='utf8') as stream:
            json.dump(record, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return json.loads(target.read_text(encoding='utf8'))
    return record


def require_running(output):
    if (Path(output) / STOP_FILE).exists():
        raise CampaignStopped('TABLE_V_CAMPAIGN_STOP_REQUESTED')
