"""Share byte-identical raw audit storage after the requested May02 B3 boundary."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import argparse
import time

from v44.common import read, record, verify, atomic, digest, now
from v44.locks import alive, exclusive_lock, process_identity
from v44_recovery_r034 import operations as previous
from v44_actual_record_light import SharedControlEncoding
from v44_actual_queue_light import install as queue_install
from v44_actual_content_store import install as content_install, cleanup as cleanup_raw

base = previous.base
CAMPAIGN, OPS, PERMIT = base.CAMPAIGN, base.OPS, base.PERMIT
ENTRY = 'v44_recovery_r035.operations'
ALGORITHM = previous.ALGORITHM
POLICY = 'R035_EXACT_SHARED_RAW_STORAGE_AND_QUEUE_READ_REUSE'
AMENDMENT = OPS/'R035_EXACT_STORAGE_AUTHORIZATION.json'
HOLD_REASON = 'R035_EXACT_STORAGE_AFTER_MAY02_B3'
latest = base.latest
RAW_ROOT = CAMPAIGN.parent/'AC_AUDIT'/'svr11_revision01'
CLEANUP_CASE = CAMPAIGN/'2025-05-02'/'B3'/'attempt015'


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))] + [
        record(Path(__file__).resolve().parents[1]/name) for name in
        ('v44_actual_record_light.py','v44_actual_queue_light.py','v44_actual_content_store.py')]


def authority():
    value = read(AMENDMENT)
    verify(value['sources']+[value['previous_authorization'], value['validation']])
    if (value['sources'] != sources() or value['policy'] != POLICY or
            value['previous_authorization'] != record(previous.AMENDMENT) or
            value.get('native_checkpoint_fast_path') is not False or
            not read(value['validation']['path'])['PASS']):
        raise PermissionError('R035_LIGHTWEIGHT_AUTHORITY_DRIFT')
    previous.authority()
    return value


def validate():
    result = previous.validate()
    authority()
    return dict(result, exact_raw_storage=record(AMENDMENT))


def command(args):
    if not isinstance(args, (list, tuple)):
        return args
    result = list(args)
    entries = tuple(f'v44_recovery_r{n:03d}.operations' for n in range(29,35))
    if (len(result) >= 5 and result[1:3] == ['-u', '-m'] and
            result[3] in entries and result[4] in ('--worker', '--coordinator')):
        result[3] = ENTRY
        if '--algorithm' not in result:
            result += ['--algorithm', ALGORITHM]
    return result


@contextmanager
def install():
    from v44_recovery_r029 import current_ac_performance, handover
    with previous.install(), patch.object(current_ac_performance,'ExactAuditEncoding',SharedControlEncoding), queue_install(), content_install(RAW_ROOT):
        decorate, popen, activate = base.decorate, base.subprocess.Popen, handover.activate

        def decorate_case(case, permit):
            authority()
            case = decorate(case, permit)
            case['R035_exact_storage'] = record(AMENDMENT)
            case['sources'] = list({r['path']: r for r in
                case['sources']+sources()+[record(AMENDMENT)]}.values())
            case['source_sha'] = digest(case['sources'])
            return case

        def launch(args, *a, **kw):
            return popen(command(args), *a, **kw)

        def activated(lease):
            activate(lease)
            path = OPS/'CURRENT_HANDOFF.json'
            value = read(path)
            value.update(UTC=now(), active_revision='v44_recovery_r035',
                active_operational_entry=ENTRY, active_operational_permit=record(AMENDMENT),
                pending_revision=None, pending_permit=None, pending_validation=None,
                collector=str(OPS/'collect_watchdog_r035.py'),
                active_source_auditor=str(OPS/'audit_active_revision_r035.py'),
                windows_task='MobileESS_V44_Campaign004_Recovery_R032',
                entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
                latest_user_instruction='캠페인에서 저장하는 것도 효율화가 필요할 것 같아. 수정해. 기존 중복 정리는 5월 2일 B3 종료 후.',
                next='Reuse shared immutable control encoding and unchanged queue reads; store identical complete raw bytes once, preserving every receipt path. Existing duplicate cleanup only after May02 B3 exits.')
            atomic(path, value)

        base.decorate, base.subprocess.Popen, handover.activate = decorate_case, launch, activated
        try:
            yield
        finally:
            base.decorate, base.subprocess.Popen, handover.activate = decorate, popen, activate


def ready():
    return not base.workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'))


def states(root):
    with install():
        return base.states(root)


def authorize(request):
    previous.authorize(request)
    if request.get('R035_exact_storage') != record(AMENDMENT):
        raise PermissionError('R035_EXPLICIT_LIGHTWEIGHT_AUTHORIZATION_REQUIRED')


def cleanup_after_case():
    if not ready():raise PermissionError('R035_CLEANUP_LIVE_WORKER_FORBIDDEN')
    result_path=CLEANUP_CASE/'RESULT.json'
    result=read(result_path)
    if type(result.get('PASS')) is not bool:raise PermissionError('R035_MAY02_B3_TERMINAL_RESULT_REQUIRED')
    done=OPS/'R035_EXISTING_RAW_CLEANUP.json'
    if done.exists() and read(done).get('PASS'):return read(done)
    def progress(value):
        atomic(OPS/'R035_EXISTING_RAW_CLEANUP_PROGRESS.json',dict(UTC=now(),**value))
    value=cleanup_raw(RAW_ROOT,progress=progress)
    value.update(UTC=now(),after_case_result=record(result_path),case_root=str(CLEANUP_CASE),
        existing_receipt_paths_preserved=True,unique_raw_records_deleted=0)
    atomic(done,value)
    return value


def handover():
    """The running worker exits naturally; no process is killed or suspended."""
    from v42_may_campaign.common import LockBusy
    with exclusive_lock(OPS/'R035_HANDOVER.lock'):
        authority()
        while True:
            stop = OPS/'STOP_AUTONOMY.json'
            if not stop.exists():
                if not (OPS/'R035_HANDOVER_APPLIED.json').exists():
                    raise PermissionError('R035_OWN_DISPATCH_HOLD_REQUIRED')
                break
            value = read(stop)
            if value.get('reason') != HOLD_REASON or value.get('user_stop'):
                atomic(OPS/'R035_HANDOVER_BLOCKED.json', dict(UTC=now(), reason='OTHER_OR_USER_STOP_PRESERVED'))
                return
            if ready():
                try:
                    with exclusive_lock(OPS/'SUPERVISOR.lock'):
                        validate()
                        cleanup_after_case()
                        atomic(OPS/'R035_HANDOVER_APPLIED.json', dict(UTC=now(), PASS=True,
                            authorization=record(AMENDMENT), no_worker_terminated=True,
                            native_checkpoint_fast_path=False))
                        stop.rename(OPS/'R035_DISPATCH_HOLD_PRESERVED.json')
                    break
                except LockBusy:
                    pass
            atomic(OPS/'R035_HANDOVER_HEARTBEAT.json', dict(UTC=now(), **process_identity(),
                active_workers=[p['pid'] for p in base.workers()], active_worker_untouched=True))
            time.sleep(15.)
    with install():
        base.watchdog()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--coordinator', action='store_true')
    parser.add_argument('--watchdog', action='store_true')
    parser.add_argument('--handover', action='store_true')
    parser.add_argument('--algorithm', required=True, choices=[ALGORITHM])
    args = parser.parse_args()
    if sum((bool(args.worker), args.coordinator, args.watchdog, args.handover)) != 1:
        raise PermissionError('R035_ONE_OPERATION_REQUIRED')
    validate()
    if args.handover:
        return handover()
    with install():
        if args.worker:
            request = read(args.worker)
            authorize(request)
            base.worker(request)
        elif args.coordinator:
            base.run()
        else:
            base.watchdog()


if __name__ == '__main__':
    main()
