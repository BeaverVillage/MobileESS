"""One independent Native=0 cache validation after Golden002 has finished."""
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
import argparse
import os
import pickle
import traceback

import psutil

from v43.common import DOC, ROOT, RUNS, atomic, git, now, read, record, verify_records
from .physical_cache import seal_completed_case, load_current_date_physical_cache, _completed, _terminated


def run(destination, *, domain_only=False):
    golden_request = DOC / 'GOLDEN_REQUEST_ATTEMPT002.json'
    original = read(golden_request)
    golden = Path(original['root'])
    (_terminated if domain_only else _completed)(*(read(golden / n) for n in ('START.json', 'RESULT.json', 'RECONCILIATION.json')))
    from v43.golden import no_heavy_peer
    from v42_may_campaign_native90.common import exclusive_lock
    no_heavy_peer()
    destination = Path(destination).resolve()
    if not destination.is_relative_to(RUNS) or destination.exists():
        raise PermissionError('NEW_INDEPENDENT_V43_VALIDATION_FOLDER_REQUIRED')
    code = [record(ROOT / 'v43_followup' / n) for n in
            ('__init__.py', 'physical_cache.py', 'cache_validation.py')]
    code += [record(ROOT / 'v43' / n) for n in ('common.py', 'golden.py')]
    began = perf_counter()
    with ExitStack() as stack:
        locks = [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'), RUNS / 'V43_HEAVY_WORKER.lock',
                 Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1, 2, 3)]
        for path in locks:
            stack.enter_context(exclusive_lock(path))
        destination.mkdir()
        atomic(destination / 'START.json', dict(UTC=now(), pid=os.getpid(),
            process_created=psutil.Process().create_time(), source=code,
            source_commit=git('rev-parse', 'HEAD').decode().strip(), Worker=1, Threads=1,
            scope='COMPLETED_GOLDEN002_STATIC_DOMAIN_REUSE_VALIDATION', Golden003=False))
        ledger = dict(Native_calls=0, Native_seconds=0., inflight=None, blocked_entrypoint_attempts=[])
        atomic(destination / 'NATIVE_RUNTIME_LEDGER.json', ledger)
        result = dict(PASS=False, Native_calls=0, Native_seconds=0.)
        try:
            proof_path = destination / 'COMPLETED_GOLDEN002_STATIC_CASE_PROOF.json'
            seal_completed_case(golden_request, proof_path, domain_only=domain_only)
            request = dict(original, root=str(destination), run_id=destination.name,
                output=str(destination / 'dates/B1/2025-05-01/output'))
            Path(request['output']).mkdir(parents=True)
            atomic(destination / 'request.json', request)
            data_path = Path(original['output']) / 'STATIC/DATA/DATA.pkl'
            data_receipt = record(data_path)
            domain_receipt = read(Path(original['output']) / 'STATIC/DOMAIN/2025-05-01/PHYSICAL_DOMAIN_CACHE.json')
            if data_receipt != domain_receipt['frozen_DATA']:
                raise ValueError('GOLDEN002_FRESH_DATA_IDENTITY_DRIFT')
            import gurobipy as gp
            def blocked(*args, **kwargs):
                ledger['blocked_entrypoint_attempts'].append('FORBIDDEN_NATIVE_ENTRYPOINT')
                raise PermissionError('CACHE_VALIDATION_NATIVE_FORBIDDEN')
            for name in ('optimize', 'presolve', 'computeIIS'):
                stack.enter_context(patch.object(gp.Model, name, blocked))
            atomic(destination / 'progress.json', dict(UTC=now(), phase='LOAD_COMPLETED_GOLDEN002_FRESH_DATA', Native_calls=0))
            with data_path.open('rb') as stream:
                data = pickle.load(stream)
            def progress(value):
                atomic(destination / 'progress.json', dict(value, UTC=now(), pid=os.getpid()))
            domains = load_current_date_physical_cache(request, data, case_proof=proof_path, progress=progress)
            if ledger['blocked_entrypoint_attempts']:
                raise PermissionError('CACHE_VALIDATION_NATIVE_ATTEMPT')
            verify_records(code + [data_receipt])
            result.update(PASS=True, jobs=len(domains), classes=len(data[7]['classes']),
                cache_reuse=record(Path(request['output']) / 'PATH_INDEPENDENT_PHYSICAL_CACHE_REUSE.json'),
                scope='STATIC_PHYSICAL_CACHE_ONLY_NOT_A_NEW_OPTIMIZATION', Golden003=False,
                prior_UB_LB_used=False, prior_Native_runtime_used=False, solved_point_used=False)
        except BaseException as error:
            result.update(error=repr(error), traceback=traceback.format_exc())
        finally:
            result.update(finished_UTC=now(), validation_wall_seconds=perf_counter() - began)
            atomic(destination / 'NATIVE_RUNTIME_LEDGER.json', ledger)
            atomic(destination / 'RESULT.json', result)
    return result


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--domain-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output, domain_only=args.domain_only), ensure_ascii=False))
