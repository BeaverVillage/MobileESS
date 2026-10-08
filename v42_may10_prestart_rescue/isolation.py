"""May12 read-only identity gate and strictly independent write namespace."""
from pathlib import Path
import json
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_may10_prestart_exact_rescue_20261008'
STATIC = ROOT.parent / 'may10-prestart-exact-rescue-static'
TEMP = ROOT.parent / 'may10-prestart-exact-rescue-temp'


class ResourceIsolationPending(RuntimeError):
    pass


def assert_write_path(path):
    target = Path(path).resolve()
    if not any(target.is_relative_to(p.resolve()) for p in (OUT, STATIC, TEMP)):
        raise PermissionError('RESCUE_OUTPUT_OUTSIDE_INDEPENDENT_NAMESPACE')
    return target


def protected_process_active(identity=None):
    identity = identity or json.loads((OUT / 'MAY12_PROTECTED_PROCESS_IDENTITY.json').read_text(encoding='utf8'))
    try:
        process = psutil.Process(identity['pid'])
        # PID reuse does not authorize touching any process. It only means
        # this protected execution is no longer identified by this PID.
        return process.create_time() == identity['created_unix'] and process.is_running()
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def require_large_resource_isolation():
    if protected_process_active():
        raise ResourceIsolationPending('RESOURCE_ISOLATION_PENDING: MAY12_PROCESS_STILL_ACTIVE')
