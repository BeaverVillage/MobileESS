"""Native=0 Windows lifetime probe. No scientific model or campaign is called."""
import argparse
import ctypes
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .common import atomic, read, process, now, d_path, environment
from v42_pr134_b1.detach import ancestry, windows_policy

BREAKAWAY_FLAGS = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                   | subprocess.CREATE_BREAKAWAY_FROM_JOB)


def creation_flags_for_job(job):
    # Task Scheduler's observed non-kill outer job may forbid breakaway. It
    # belongs to the OS service, so inherited membership is recorded openly.
    # A caller-controlled kill-on-close job may never be inherited silently.
    if not job.get('in_any_job') or job.get('breakaway_ok') or job.get('silent_breakaway_ok'):
        return BREAKAWAY_FLAGS
    if job.get('kill_on_job_close') is False:
        return subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    raise PermissionError('CANNOT_INHERIT_UNKNOWN_OR_KILL_ON_CLOSE_NONBREAKAWAY_JOB')


def job_information():
    """Read current-process membership and immediate-job limit flags only."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    kernel.IsProcessInJob.restype = ctypes.c_int
    member = ctypes.c_int()
    if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(member)):
        raise OSError(ctypes.get_last_error(), 'IsProcessInJob')
    result = dict(in_any_job=bool(member.value), limit_flags=None, kill_on_job_close=None,
                  breakaway_ok=None, silent_breakaway_ok=None,
                  query_scope='CURRENT_PROCESS_IMMEDIATE_JOB; membership tests any job')
    if not member.value:
        result.update(kill_on_job_close=False, breakaway_ok=False, silent_breakaway_ok=False)
        return result

    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32),
                    ('SchedulingClass', ctypes.c_uint32)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                     'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    kernel.QueryInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                 ctypes.c_uint32, ctypes.c_void_p]
    kernel.QueryInformationJobObject.restype = ctypes.c_int
    limits = Extended()
    if not kernel.QueryInformationJobObject(None, 9, ctypes.byref(limits), ctypes.sizeof(limits), None):
        result['query_error'] = ctypes.get_last_error()
        return result
    flags = limits.BasicLimitInformation.LimitFlags
    result.update(limit_flags=flags, limit_flags_hex=hex(flags), kill_on_job_close=bool(flags & 0x2000),
                  breakaway_ok=bool(flags & 0x0800), silent_breakaway_ok=bool(flags & 0x1000))
    return result


def observation():
    own = process()
    return dict(process=own, ancestry=ancestry(own['PID']), job=job_information(),
                resource_policy=windows_policy(own['PID']), UTC=now(), Native_optimize_calls=0)


def launcher(root, seconds=20):
    root = d_path(root)
    environment(root)
    receipt = observation()
    atomic(root / 'LAUNCHER_PROCESS.json', receipt)
    creation_flags = creation_flags_for_job(receipt['job'])
    command = [sys.executable, '-B', '-X', 'utf8', '-m', 'v42_may_campaign.process_probe',
               'child', '--root', str(root), '--seconds', str(seconds)]
    try:
        with (root / 'child.stdout.log').open('ab') as stdout, (root / 'child.stderr.log').open('ab') as stderr:
            child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                     stdout=stdout, stderr=stderr, creationflags=creation_flags)
            child_identity = process(child.pid)
        atomic(root / 'LAUNCHER_RESULT.json', dict(PASS=True, process=receipt['process'], child=child_identity,
              child_command=command, creation_flags=creation_flags, creation_flags_hex=hex(creation_flags),
              launcher_will_exit_now=True, UTC=now(), Native_optimize_calls=0))
        # Return normally: the OS checker must observe the actual launcher gone
        # while the independently created child continues its own heartbeat.
        return 0
    except BaseException as error:
        atomic(root / 'LAUNCHER_RESULT.json', dict(PASS=False, error=str(error), type=type(error).__name__,
              process=receipt['process'], creation_flags=creation_flags, UTC=now(), Native_optimize_calls=0))
        raise


def child(root, seconds=20):
    root = d_path(root)
    environment(root)
    receipt = observation()
    atomic(root / 'CHILD_PROCESS.json', receipt)
    started = time.monotonic()
    counter = 0
    while time.monotonic() - started < seconds:
        counter += 1
        atomic(root / 'CHILD_HEARTBEAT.json', dict(process=receipt['process'], heartbeat_number=counter,
              timestamp_UTC=now(), Native_optimize_calls=0, phase='NATIVE_ZERO_PROCESS_LIFETIME_PROBE'))
        time.sleep(1)
    atomic(root / 'CHILD_COMPLETE.json', dict(PASS=True, process=receipt['process'], heartbeat_count=counter,
          UTC=now(), Native_optimize_calls=0, exit='NATURAL_COMPLETION_NO_TERMINATION'))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('launch', 'child'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args(argv)
    root = d_path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    sys.stdout = (root / (args.mode + '.stdout.log')).open('a', encoding='utf-8', buffering=1)
    sys.stderr = (root / (args.mode + '.stderr.log')).open('a', encoding='utf-8', buffering=1)
    try:
        return (launcher if args.mode == 'launch' else child)(root, args.seconds)
    except BaseException as error:
        atomic(root / (args.mode.upper() + '_ERROR.json'), dict(error=str(error), type=type(error).__name__,
              traceback=traceback.format_exc(), UTC=now(), Native_optimize_calls=0))
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
