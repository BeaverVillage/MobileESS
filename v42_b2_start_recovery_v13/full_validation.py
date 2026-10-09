"""Separate source-only model construction; never a production Solver run."""
from pathlib import Path
import gc
import json
import sys
import threading
import time
import traceback
from dataclasses import asdict
from .common import atomic, read, sha, record, digest, now, process, environment, exclusive_lock, RUNTIME


def semantic_digest(value):
    """Hash every array entry; NumPy's truncated repr is never a proof."""
    import hashlib
    import numpy as np
    from dataclasses import is_dataclass
    from scipy import sparse
    from types import SimpleNamespace
    hasher = hashlib.sha256()
    def add(v):
        if is_dataclass(v):
            add(asdict(v))
        elif type(v) is SimpleNamespace:
            # Original Grid coefficients include every namespace field.
            hasher.update(b'SIMPLE_NAMESPACE')
            add(vars(v))
        elif sparse.issparse(v):
            a = v.tocsr()
            hasher.update(b'CSR')
            add(a.shape)
            for field in (a.indptr, a.indices, a.data):
                add(field)
        elif isinstance(v, np.ndarray):
            hasher.update(b'NDARRAY' + v.dtype.str.encode())
            add(v.shape)
            if v.dtype.hasobject:
                add(v.tolist())
            else:
                hasher.update(v.tobytes(order='C'))
        elif isinstance(v, dict):
            hasher.update(b'DICT')
            for k in sorted(v, key=lambda x: (type(x).__name__, repr(x))):
                add(k)
                add(v[k])
        elif isinstance(v, (list, tuple)):
            hasher.update(b'SEQ' + str(len(v)).encode())
            for item in v:
                add(item)
        elif isinstance(v, np.generic):
            add(np.asarray(v))
        elif v is None or type(v) in (str, bool, int, float):
            raw = json.dumps(v, ensure_ascii=False, allow_nan=True).encode()
            hasher.update(type(v).__name__.encode() + str(len(raw)).encode() + b':' + raw)
        else:
            raise TypeError('UNPROVEN_SCIENTIFIC_FINGERPRINT_TYPE:' + type(v).__name__)
    add(value)
    return hasher.hexdigest()


def fingerprint(case):
    from v42_may_campaign_native90.m_model import _domain_sha
    from v42_m1_hybrid.blocks import matrix_sha
    # Absolute output packet paths differ intentionally. Compare all scientific
    # content and exact transport state instead of hashing those provenance paths.
    return dict(original_matrix=matrix_sha(case.original_A), original_domain=_domain_sha(case.original_d),
        selected_matrix=matrix_sha(case.A), selected_domain=_domain_sha(case.d),
        compact_matrix=matrix_sha(case.compact.A), compact_domain=_domain_sha(case.compact.d),
        graph=semantic_digest(case.graph), grid_coefficients=semantic_digest(case.coefficients),
        anchor=semantic_digest(case.anchor), bundle=semantic_digest(case.bundle),
        transport=case.identity['transport'], transport_state=case.identity['transport_authority']['state_sha'])


def run(request_path):
    request = read(request_path)
    folder = Path(request['result']).parent
    environment(folder)
    from .policy import verify_request
    verify_request(request)
    from .worker import assert_no_other_native_worker
    assert_no_other_native_worker()
    stop = threading.Event()
    owner = process()
    phase = {'name': 'MODEL_VALIDATION_INPUTS'}
    def beat():
        while not stop.wait(2):
            atomic(folder / 'HEARTBEAT.json', dict(process=owner, UTC=now(), phase=phase['name'], Native_calls=0))
    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    started = time.perf_counter()
    receipt = dict(PASS=False, day=request['day'], mode=request['build_mode'], Native_calls=0, P2_calls=0,
                   implementation_SHA=request['implementation_SHA'], process=owner, UTC=now())
    try:
        from .execution import worker_scope, current
        from .preflight import native_zero
        from v42_may_campaign_native90.inputs import generate_b2
        from v42_may_campaign_native90 import m_model
        from v42_b2_build_authority_v13 import build_case as improved
        def progress(value):
            phase['name'] = value.get('phase', phase['name'])
            atomic(request['progress'], dict(value, timestamp_UTC=now(), process=owner, Native_calls=0))
        # All three slots are reserved only for this sequential Native=0
        # construction. No memory/CPU limits or model pacing are introduced.
        from contextlib import ExitStack
        with ExitStack() as locks:
            locks.enter_context(exclusive_lock(folder / 'VALIDATION.lock'))
            locks.enter_context(exclusive_lock(RUNTIME / 'NATIVE_WORKER.lock'))
            for slot in (1, 2, 3):
                locks.enter_context(exclusive_lock(RUNTIME / 'native_slots' / f'SLOT_{slot}.lock'))
            assert_no_other_native_worker()
            with worker_scope(request):
                current()['preflight_native_zero'] = True
                with native_zero() as attempts:
                    payload = generate_b2(request)
                    build = m_model.build_case if request['build_mode'] == 'BASELINE' else improved
                    case = build(payload, request, progress)
                    proof = m_model.verify_case(case)
                    if not proof.get('PASS') or attempts:
                        raise PermissionError('V7_ORIGINAL_MODEL_OR_NATIVE_ZERO_VALIDATION_FAILED')
                    receipt.update(PASS=True, fingerprint=fingerprint(case), original_transport_verification=proof,
                        input_SHA=sha(Path(request['input_folder']) / 'NATIVE_INPUT.json'),
                        total_preparation_seconds=time.perf_counter() - started, Native_calls=0,
                        optimized_receipt_files=[record(p) for p in Path(request['output']).glob('*BUILD*.json')])
                    del case
                    gc.collect()
    except BaseException as error:
        receipt.update(PASS=False, error=repr(error), traceback=traceback.format_exc())
    finally:
        stop.set()
        thread.join(timeout=3)
        receipt.update(finished_UTC=now())
        atomic(request['result'], receipt)
    return 0 if receipt['PASS'] else 1


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1]))
