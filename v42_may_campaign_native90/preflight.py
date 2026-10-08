"""Real Native=0 input/model preflight, kept separate from OS installation."""
from contextlib import contextmanager
from pathlib import Path
import argparse
import sys
import traceback
import time
from .common import ROOT, AXIS, DAYS, d_path, environment, atomic, read, record, now, process


@contextmanager
def native_zero():
    import gurobipy as gp
    methods = {name: getattr(gp.Model, name) for name in ('optimize', 'presolve')}
    attempts = []
    def denied(*args, **kwargs):
        attempts.append(dict(UTC=now(), error='NATIVE_ZERO_PREFLIGHT_OPTIMIZE_DENIED'))
        raise PermissionError('NATIVE_ZERO_PREFLIGHT_OPTIMIZE_DENIED')
    for name in methods:
        setattr(gp.Model, name, denied)
    try:
        yield attempts
    finally:
        for name, function in methods.items():
            setattr(gp.Model, name, function)


def generate_inputs(root):
    from .inputs import produce_b1, produce_b2_raw
    root = d_path(root); environment(root)
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with native_zero() as attempts:
        produce_b1(root)
        produce_b2_raw(root)
    folders = {a + '/' + d: str(root / 'inputs' / a / d) for a, d in AXIS}
    rows = []
    for arm, day in AXIS:
        folder = Path(folders[arm + '/' + day])
        identity = read(folder / 'INPUT_IDENTITY.json')
        if not identity['PASS'] or identity['day'] != day or identity['arm'] != arm:
            raise ValueError('INDEPENDENT_DATE_ARM_INPUT_IDENTITY')
        files = [record(p) for p in sorted(folder.rglob('*')) if p.is_file()]
        rows.append(dict(arm=arm, day=day, PASS=True, files=files))
    result = dict(PASS=not attempts, Native_calls=0, denied_native_attempts=attempts,
        generated_arm_dates=62, input_folders=folders, dates=rows,
        B0_B1_results_used_for_B2=False, input_generation_seconds=time.perf_counter() - started, UTC=now())
    atomic(root / 'MAY31_INDEPENDENT_INPUT_VERIFICATION.json', result)
    b2 = [read(root / 'inputs/B2' / day / 'B2_FIXED_AIDC.json')['identity'] for day in DAYS]
    atomic(root / 'B2_INDEPENDENT_AIDC_GENERATION.json', dict(PASS=all(r['PASS'] for r in b2),
        generated_days=31, dates=b2, AIDC_optimization_calls=0, Native_calls=0,
        B0_B1_schedule_result_reads=0, independently_generated=True))
    return result


def case_preflight(root, arm, day, own_domain_cache=None):
    root = d_path(root); environment(root)
    output = root / 'preflight_cases' / arm / day
    if output.exists() and any(output.iterdir()):
        original = output
        attempt = 2
        while output.exists():
            output = original.with_name(day + '_attempt' + str(attempt))
            attempt += 1
    progress_path = root / 'preflight_progress' / arm / (day + '.json')
    def progress(value):
        atomic(progress_path, dict(value, timestamp_UTC=now(), process=process()))
        print('MODEL_PREFLIGHT', arm, day, value.get('phase'), flush=True)
    request = dict(root=str(root), input_folder=str(root / 'inputs' / arm / day),
                   day=day, arm=arm, output=str(output))
    if own_domain_cache is not None:
        request['_current_date_physical_cache'] = str(d_path(own_domain_cache))
    started = time.perf_counter()
    with native_zero() as attempts:
        if arm == 'B1':
            from .a_stage import prepare, verify_case
        elif arm == 'B2':
            from .m_stage import prepare, verify_case
        else:
            raise ValueError('UNKNOWN_ARM')
        state = prepare(request, progress)
        verification = verify_case(state)
    if not verification.get('PASS') or attempts:
        raise ValueError('ORIGINAL_DATE_MODEL_PREFLIGHT_NOT_PASS')
    result = dict(PASS=True, day=day, arm=arm, Native_calls=0,
        case_verification=verification, construction_seconds=time.perf_counter() - started,
        input_SHA=record(Path(request['input_folder']) / 'NATIVE_INPUT.json'),
        output=str(output), UTC=now(), denied_native_attempts=attempts)
    atomic(root / 'preflight_receipts' / arm / (day + '.json'), result)
    print('CASE_PREFLIGHT_PASS', arm, day, result['construction_seconds'], flush=True)
    return result


def validate_b2_inputs(root):
    from .inputs import generate_b2
    from .input_checks import verify_b2
    root = d_path(root); rows = []
    with native_zero() as attempts:
        for day in DAYS:
            folder = root / 'inputs/B2' / day
            payload = generate_b2(dict(input_folder=str(folder), day=day, arm='B2'))
            result = verify_b2(payload, folder)
            rows.append(result)
            print('B2_INDEPENDENT_PHYSICAL', day, result['PASS'], flush=True)
    receipt = dict(PASS=all(r['PASS'] for r in rows) and not attempts,
        dates=rows, Native_calls=0, denied_native_attempts=attempts, UTC=now(),
        verifier=record(ROOT / 'v42_may_campaign/input_checks.py'))
    atomic(root / 'B2_INDEPENDENT_ORIGINAL_PHYSICAL_VERIFICATION.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--generate-inputs', action='store_true')
    parser.add_argument('--case', action='store_true')
    parser.add_argument('--validate-b2-inputs', action='store_true')
    parser.add_argument('--arm', choices=('B1', 'B2'))
    parser.add_argument('--day')
    parser.add_argument('--own-domain-cache')
    args = parser.parse_args()
    root = d_path(args.root)
    try:
        if args.generate_inputs:
            generate_inputs(root)
        elif args.validate_b2_inputs:
            validate_b2_inputs(root)
        elif args.case:
            case_preflight(root, args.arm, args.day, args.own_domain_cache)
        else:
            raise ValueError('SELECT_REAL_PREFLIGHT_ACTION')
    except BaseException as error:
        error_path = root / ('PREFLIGHT_ERROR_' + (args.arm or 'INPUT') + '_' + (args.day or 'ALL') + '.json')
        if error_path.exists():
            from uuid import uuid4
            atomic(root / 'preflight_error_history' / (error_path.stem + '_' + uuid4().hex + '.json'), read(error_path))
        atomic(error_path,
            dict(PASS=False, error=str(error), traceback=traceback.format_exc(), UTC=now(), Native_calls=0))
        traceback.print_exc()
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
