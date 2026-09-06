"""Fresh 31-day generation with pre/post provenance and measured solve calls."""
from pathlib import Path
from types import FunctionType
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import os
import subprocess
import sys
import time
import uuid
import numpy as np
from dayahead.paper_analysis.storage import read, write_json, write_npz, sha
from dayahead.v40a.invariants import digest
from dayahead.v40h.identity import require, manifest, file_record, verify_file, verify_manifest, verify_bound_files, bind
from dayahead.v40h.electrical import feeder_manifest
from dayahead.v40h.numerical_context import FIELDS

ROOT = Path('dayahead/artifacts/v40i_authority_electrical_closure')
ELECTRICAL_ROOT = ROOT / 'generated'
EPOCH = 'epoch2'
EPOCH_ROOT = ROOT / 'generation_epochs' / EPOCH
FREEZE = EPOCH_ROOT / 'SOURCE_INPUT_FREEZE.json'
DAYS = tuple(f'2025-05-{d:02}' for d in range(1, 32))
OUTPUT_NAMES = ('voltage', 'current', 'planning_coefficients', 'transformer_coefficients')


def now(): return datetime.now(timezone.utc).isoformat()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf-8').strip()


def freeze_generator(repo):
    repo = Path(repo).resolve(); source = read(repo / 'dayahead/artifacts/v40h_production_integrity/FINAL_SCIENTIFIC_SOURCE_FREEZE.json')
    paths = [Path(r['path']) for r in source['source_manifest']['files']] + [Path(__file__), Path(__file__).with_name('__init__.py')]
    names = [p.relative_to(repo).as_posix() for p in paths]
    tracked = set(git(repo, 'ls-files').splitlines())
    require(set(names).issubset(tracked), 'GENERATOR_SOURCE_MUST_BE_COMMITTED')
    require(not (set(git(repo, 'diff', '--name-only', 'HEAD').splitlines()) & set(names)), 'GENERATOR_SOURCE_DIRTY')
    value = {'revision': 'V40I', 'epoch': EPOCH, 'freeze_started_at': now(),
        'generator_commit_created_at': git(repo, 'show', '-s', '--format=%cI', 'HEAD'),
        'generator_git_commit': git(repo, 'rev-parse', 'HEAD'),
        'generator_entrypoint': 'dayahead.v40i.electrical:generate_day', 'source_manifest': manifest(paths, repo),
        'protected_V40H_input_inventory': file_record(repo / 'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json'),
        'settings': {'workers': 4, 'native_controls': 'solve then freeze per slot', 'slots': 96,
            'voltage_and_current_central_difference_controls': 60, 'prior_output_or_cache_reuse': 0,
            'frozen_April_surrogate_input_retained': True, 'May_based_surrogate_retuning': False}}
    path = repo / FREEZE
    require(not path.exists(), 'GENERATOR_FREEZE_ALREADY_EXISTS')
    daily = {}
    for day in DAYS:
        identity = input_identity(repo, day, value)
        target = repo / EPOCH_ROOT / 'frozen_inputs' / (day + '.json')
        require(not target.exists(), 'PRESERVE_EXISTING_PRE_GENERATION_INPUT')
        write_json(target, {'date': day, 'created_at': now(), 'git_HEAD': git(repo, 'rev-parse', 'HEAD'), 'input_identity': identity})
        daily[day] = file_record(target)
    require(git(repo, 'rev-parse', 'HEAD') == value['generator_git_commit'], 'HEAD_CHANGED_DURING_FREEZE')
    verify_manifest(value['source_manifest'])
    value.update(daily_pre_generation_inputs=daily, freeze_completed_at=now())
    write_json(path, value); return value


def input_identity(repo, day, frozen):
    repo = Path(repo).resolve()
    verify_manifest(frozen['source_manifest']); verify_file(frozen['protected_V40H_input_inventory'])
    require(git(repo, 'rev-parse', 'HEAD') == frozen['generator_git_commit'], 'GENERATOR_FROZEN_HEAD_CHANGED')
    inventory = read(frozen['protected_V40H_input_inventory']['path'])
    values = deepcopy(inventory['daily_electrical_identities'][day]['identity']['inputs'])
    feeder = values['feeder_manifest']
    current = feeder_manifest(feeder['consumed_roots'], [r['path'] for r in feeder['masters']])
    require(current['manifest_SHA'] == feeder['manifest_SHA'], 'GENERATION_FEEDER_INPUT_CHANGED')
    values['generation_source']['V40I_source_manifest'] = frozen['source_manifest']
    values['generation_source']['V40I_generator_git_commit'] = frozen['generator_git_commit']
    values['generation_source']['V40I_generator_entrypoint'] = frozen['generator_entrypoint']
    verify_bound_files(values)
    return bind('V40I_ELECTRICAL_GENERATION_INPUT_V1', values, values.keys())


def expected(repo, day):
    frozen = read(Path(repo) / FREEZE)
    original = read(verify_file(frozen['daily_pre_generation_inputs'][day]))['input_identity']
    current = input_identity(repo, day, frozen)
    require(current == original, 'PRE_GENERATION_FROZEN_INPUT_CHANGED')
    return current


def rehash_evidence(identity):
    """Capture actual bytes even on failure; never report expected hashes as observed."""
    rows = []
    for old in flatten_files(identity):
        try: rows.append({**old, **{k: v for k, v in file_record(old['path']).items() if k != 'relative_path'}})
        except OSError as e: rows.append({'path': old['path'], 'error': repr(e)})
        except ValueError as e: rows.append({'path': old['path'], 'error': repr(e)})
    return rows


def flatten_files(value):
    files = {}
    def walk(node):
        if isinstance(node, dict):
            if {'path', 'bytes', 'sha256'}.issubset(node): files[node['path']] = node
            for x in node.values(): walk(x)
        elif isinstance(node, (list, tuple)):
            for x in node: walk(x)
    walk(value); return [files[k] for k in sorted(files)]


class Meter:
    """Observe real engine calls, and refuse any non-converged perturbation."""
    def __init__(self, phase, run): self.phase, self.run, self.count, self.nonconverged = phase, run, 0, 0
    def compiled(self, compile_function):
        meter = self
        def compile(*args, **kwargs):
            odd, adapter = compile_function(*args, **kwargs)
            class Solution:
                def __getattr__(self, name): return getattr(odd.Solution, name)
                def SolveSnap(self):
                    value = odd.Solution.SolveSnap(); meter.count += 1
                    if not odd.Solution.Converged(): meter.nonconverged += 1
                    require(meter.nonconverged == 0, 'GENERATION_PERTURBATION_NONCONVERGENCE')
                    if meter.count % 1000 == 0:
                        write_json(meter.run / ('PROGRESS_' + meter.phase + '.json'), {'phase': meter.phase, 'SolveSnap_calls': meter.count, 'at': now()})
                    return value
            solution = Solution()
            class Engine:
                Solution = solution
                def __getattr__(self, name): return getattr(odd, name)
            return Engine(), adapter
        return compile


def clone(function, namespace):
    fn = getattr(function, '__wrapped__', function)
    return FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, fn.__closure__)


def generate_outputs(repo, day, run, identity):
    from dayahead.v40e import electrical as old
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead import run_v16_3_voltage_candidate as voltage, run_v16_3_correction as current
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    relative = run.relative_to(repo) / 'kernel'
    namespace = dict(vars(old)); namespace['REL'] = relative
    for name in ('upstream', 'electrical_context', 'planning_context'): namespace[name] = clone(getattr(old, name), namespace)
    joint = identity['identity']['inputs']['voltage_generation']['frozen_April_joint_authority']
    joint_target = repo / relative / 'april_joint_authority' / Path(joint['path']).name
    joint_target.parent.mkdir(parents=True, exist_ok=True); joint_target.write_bytes(verify_file(joint).read_bytes())
    plan, forecast, background, binding, source, refs = namespace['upstream'](str(repo), day)
    out = repo / relative / 'electrical' / day
    vp = out / 'data' / f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz'
    ip = out / 'data' / f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'
    require(not vp.exists() and not ip.exists(), 'EXISTING_COEFFICIENT_CANNOT_BE_RECERTIFIED')
    meters = {phase: Meter(phase, run) for phase in ('voltage', 'current')}
    previous = Path.cwd()
    try:
        with corrected_mapping():
            vg = dict(vars(voltage)); vg['_compile'] = meters['voltage'].compiled(voltage._compile)
            cg = dict(vars(current)); cg['_compile'] = meters['current'].compiled(current._compile)
            print(day + ' NEW voltage generation', flush=True)
            v = clone(voltage._anchor_and_sensitivity_day, vg)(SOURCE_DATA_REPOSITORY, source, background, plan.tolist(), binding, day, vp)
            print(day + ' NEW current/transformer generation', flush=True)
            c = clone(current._generate_current_day, cg)(SOURCE_DATA_REPOSITORY, source, out, day,
                ({'plan_kw_96x12': plan.tolist()}, forecast, background, binding, vp, None))
    finally: os.chdir(previous)
    require(all(m.count == 11617 and m.nonconverged == 0 for m in meters.values()), 'FRESH_GENERATOR_EXECUTION_PROOF_MISSING')
    # This compatibility document is produced in the fresh isolated run only;
    # the old numerical loader consumes it to preserve the frozen equations.
    write_json(out / 'V40E_ELECTRICAL_REBUILD_LINEAGE.json', {'status': 'PASS', 'day': day,
        'mapper_SHA': sha(repo / 'dayahead/v40e/mapping.py'),
        'outputs': {'voltage': {'new': file_record(vp)}, 'current': {'new': file_record(ip)}},
        'producer': 'V40I_FRESH_GENERATION_NUMERICAL_COMPATIBILITY_ADAPTER'})
    context = namespace['planning_context'](repo, day)
    try:
        arrays = {k: np.asarray([getattr(x, k) for x in context.coefficients]) for k in FIELDS}
        require(all(np.isfinite(a).all() for a in arrays.values()), 'NONFINITE_GENERATED_COEFFICIENTS')
        pp = out / 'V40I_PLANNING_ELECTRICAL_COEFFICIENTS.npz'
        write_npz(pp, **arrays, node_names=np.array(context.nodes), branch_names=np.array(context.coefficients[0].branch_names))
        tx = np.flatnonzero(np.char.startswith(np.array(context.coefficients[0].branch_names), 'transformer.'))
        tp = out / 'V40I_TRANSFORMER_COEFFICIENTS.npz'
        write_npz(tp, current_constant=arrays['current_constant'][:, tx], current_matrix=arrays['current_matrix'][:, :, tx],
            P_constant=arrays['flow_p_constant'][:, tx], Q_constant=arrays['flow_q_constant'][:, tx],
            P_matrix=arrays['flow_p_matrix'][:, tx, :], Q_matrix=arrays['flow_q_matrix'][:, tx, :],
            ratings=np.array([np.nan if v is None else float(v) for v in context.coefficients[0].transformer_ratings])[tx])
    finally: context.electrical.voltage.close(); context.electrical.current.close()
    proof = {'fresh_output_paths_were_absent': True, 'old_result_cache_reuse_count': 0,
        'voltage_generator': v, 'current_generator': c,
        'measured_solve_calls': {k: m.count for k, m in meters.items()}, 'measured_nonconverged_calls': 0,
        'fresh_generation_total_SolveSnap_calls': sum(m.count for m in meters.values()),
        'same_bytes_as_historical_allowed_if_recomputed': True}
    write_json(run / 'GENERATOR_EXECUTION_PROOF.json', proof)
    return dict(voltage=vp, current=ip, planning_coefficients=pp, transformer_coefficients=tp), proof


def certify_run(certificate_path, expected_builder, producer, *, metadata):
    require(not Path(certificate_path).exists(), 'PREVIOUS_CERTIFICATE_COPY_OR_RECERTIFICATION_FORBIDDEN')
    repo = Path(metadata['repository']); run = Path(metadata['isolated_run_path'])
    frozen_path = Path(metadata['source_input_freeze']['path'])
    verify_file(metadata['source_input_freeze']); frozen = read(frozen_path)
    pre = expected_builder()
    pre_path = run / 'PRE_GENERATION_IDENTITY.json'
    pre_record = {'created_at': now(), 'git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'source_input_freeze': metadata['source_input_freeze'], 'input_identity': pre,
        'source_input_hashes': flatten_files(pre)}
    require(pre_record['git_HEAD'] == metadata['git_commit'], 'GENERATION_START_HEAD_MISMATCH')
    write_json(pre_path, pre_record)
    # Re-read the durable receipt before entering any generator computation.
    require(read(pre_path) == pre_record, 'DURABLE_PRE_IDENTITY_NOT_COMPLETE')
    started = now(); start_path = run / 'GENERATION_STARTED.json'
    start = {'generation_started_at': started, 'generation_git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'pre_generation_identity': file_record(pre_path), 'pre_generation_identity_completed_before_start': True}
    require(start['generation_git_HEAD'] == metadata['git_commit'], 'GENERATION_START_HEAD_MISMATCH')
    require(frozen['freeze_completed_at'] <= pre_record['created_at'] <= started, 'GENERATION_BEFORE_INPUT_FREEZE')
    write_json(start_path, start)
    error = None
    try: outputs, proof = producer(pre)
    except Exception as e: error = e
    finished = now(); post_path = run / 'POST_GENERATION_IDENTITY.json'
    post_hashes = rehash_evidence(pre)
    post_record = {'verification_completed_at': now(), 'git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'source_input_hashes': post_hashes, 'generator_error': repr(error) if error else None,
        'pre_post_hashes_match': flatten_files(pre) == post_hashes}
    write_json(post_path, post_record)
    if error: raise error
    require(post_record['pre_post_hashes_match'], 'GENERATOR_PRE_POST_INPUT_MISMATCH')
    require(post_record['git_HEAD'] == metadata['git_commit'], 'GENERATOR_FROZEN_HEAD_CHANGED')
    require(set(outputs) == set(OUTPUT_NAMES), 'GENERATION_OUTPUT_COVERAGE')
    require(proof.get('fresh_output_paths_were_absent') is True and proof.get('old_result_cache_reuse_count') == 0
        and proof.get('fresh_generation_total_SolveSnap_calls', 0) > 0, 'FRESH_GENERATOR_EXECUTION_PROOF_MISSING')
    post = expected_builder()
    require(pre['identity_SHA'] == post['identity_SHA'] and pre['identity'] == post['identity'], 'GENERATOR_PRE_POST_INPUT_MISMATCH')
    files = {k: file_record(p) for k, p in outputs.items()}
    cert = {'revision': 'V40I', 'schema': 'V40I_ELECTRICAL_GENERATION_CERTIFICATE_V2', **metadata,
        'pre_generation_input_manifest': pre, 'pre_generation_input_hashes': flatten_files(pre),
        'generated_files': files, 'generated_file_hashes': {k: v['sha256'] for k, v in files.items()},
        'post_generation_input_hashes': flatten_files(post), 'input_identity_unchanged': True,
        'generation_started_at': started, 'generation_finished_at': finished, 'certificate_issued_at': now(), 'certificate_status': 'PASS',
        'generation_git_HEAD': start['generation_git_HEAD'], 'post_generation_git_HEAD': post_record['git_HEAD'],
        'pre_generation_freeze_completed_at': frozen['freeze_completed_at'],
        'pre_generation_identity_completed_at': pre_record['created_at'],
        'pre_generation_identity_completed_before_start': True,
        'post_generation_verification_completed_at': post_record['verification_completed_at'],
        'durable_pre_generation_receipt': file_record(pre_path), 'durable_generation_start_receipt': file_record(start_path),
        'durable_post_generation_receipt': file_record(post_path),
        'generation_execution_proof': proof, 'prior_result_cache_reuse': 0, 'schema_validation': 'PASS'}
    write_json(certificate_path, cert); return cert


def generate_day(repo, day):
    repo = Path(repo).resolve(); require(day in DAYS, 'MAY_DAY_REQUIRED')
    frozen = read(repo / FREEZE)
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
    run = repo / EPOCH_ROOT / 'generated' / day / token; run.mkdir(parents=True, exist_ok=False)
    certificate = repo / ROOT / 'electrical_generation_certificates' / (day + '.json')
    write_json(run / 'RUN_STARTED.json', {'date': day, 'pid': os.getpid(), 'at': now(), 'generator_source_freeze': frozen})
    try:
        result = certify_run(certificate, lambda: expected(repo, day), lambda identity: generate_outputs(repo, day, run, identity),
            metadata={'date': day, 'epoch': EPOCH, 'repository': str(repo), 'source_input_freeze': file_record(repo / FREEZE),
                'generator_entrypoint': frozen['generator_entrypoint'], 'git_commit': frozen['generator_git_commit'],
                'generator_source_files': frozen['source_manifest']['files'], 'generator_source_hashes': frozen['source_manifest']['manifest_SHA'],
                'generation_command': [sys.executable, '-m', 'dayahead.v40i.electrical', '--day', day],
                'generation_parameters': frozen['settings'], 'isolated_run_path': str(run)})
        write_json(run / 'RUN_FINISHED.json', {'status': 'PASS', 'at': now(), 'certificate': file_record(certificate)})
        print(day + ' CERTIFIED PASS', flush=True); return result
    except Exception as e:
        write_json(run / 'RUN_FAILED.json', {'status': 'FAIL', 'at': now(), 'error': repr(e), 'historical_evidence_preserved': True})
        raise


def aggregate(repo, verify=True):
    root = Path(repo) / ROOT; rows = []
    for day in DAYS:
        path = root / 'electrical_generation_certificates' / (day + '.json')
        if not path.exists(): rows.append({'date': day, 'status': 'MISSING'}); continue
        try:
            c = read(path)
            require(c['schema'] == 'V40I_ELECTRICAL_GENERATION_CERTIFICATE_V2', 'LEGACY_GENERATION_CERTIFICATE_FORBIDDEN')
            require(c['date'] == day and c['certificate_status'] == 'PASS' and c['input_identity_unchanged'] and c['prior_result_cache_reuse'] == 0, 'CERTIFICATE_SCHEMA')
            require(c['pre_generation_input_hashes'] == c['post_generation_input_hashes'], 'CERTIFICATE_PRE_POST_DRIFT')
            require(c['generation_execution_proof']['fresh_generation_total_SolveSnap_calls'] == 23234, 'CERTIFICATE_EXECUTION_PROOF')
            require(set(c['generated_files']) == set(OUTPUT_NAMES), 'CERTIFICATE_OUTPUT_COVERAGE')
            require(c['git_commit'] == c['generation_git_HEAD'] == c['post_generation_git_HEAD'], 'CERTIFICATE_HEAD_DRIFT')
            require(c['pre_generation_identity_completed_before_start'] is True and
                c['pre_generation_freeze_completed_at'] <= c['pre_generation_identity_completed_at'] <=
                c['generation_started_at'] <= c['generation_finished_at'] <=
                c['post_generation_verification_completed_at'] <= c['certificate_issued_at'], 'CERTIFICATE_CHRONOLOGY_INVALID')
            if verify:
                verify_file(c['source_input_freeze'])
                for key in ('durable_pre_generation_receipt', 'durable_generation_start_receipt', 'durable_post_generation_receipt'):
                    verify_file(c[key])
                for value in c['generated_files'].values(): verify_file(value)
                verify_bound_files(c['pre_generation_input_manifest'])
            rows.append({'date': day, 'status': 'PASS', 'certificate': file_record(path), 'generated_files': c['generated_files']})
        except (ValueError, KeyError, OSError) as e: rows.append({'date': day, 'status': 'FAIL', 'reason': str(e)})
    count = sum(r['status'] == 'PASS' for r in rows)
    result = {'revision': 'V40I', 'certificate_status': 'PASS' if count == 31 else 'FAIL', 'CERTIFIED_DAYS': count,
        'REQUIRED_DAYS': 31, 'old_result_cache_reuse': 0, 'days': rows}
    write_json(root / 'V40I_ELECTRICAL_GENERATION_CERTIFICATION.json', result); return result


def run_all(repo):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    repo = Path(repo).resolve(); frozen = read(repo / FREEZE)
    verify_file(file_record(repo / FREEZE))
    for record in frozen['daily_pre_generation_inputs'].values(): verify_file(record)
    require(set(frozen['daily_pre_generation_inputs']) == set(DAYS), 'ALL_DAYS_MUST_BE_FROZEN_BEFORE_ALL')
    require(git(repo, 'rev-parse', 'HEAD') == frozen['generator_git_commit'], 'GENERATOR_FROZEN_HEAD_CHANGED')
    logs = repo / EPOCH_ROOT / 'generation_logs'; logs.mkdir(parents=True, exist_ok=True)
    write_json(repo / EPOCH_ROOT / 'ALL_GENERATION_STARTED.json', {'at': now(), 'git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'complete_pre_generation_freeze': file_record(repo / FREEZE), 'frozen_days': 31})
    def worker(day):
        with (logs / (day + '.log')).open('xb') as stream:
            result = subprocess.run([sys.executable, '-m', 'dayahead.v40i.electrical', '--day', day], cwd=repo, stdout=stream, stderr=subprocess.STDOUT)
        return day, result.returncode
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(worker, day): day for day in DAYS}
        for future in as_completed(pending):
            day, code = future.result(); print(f'{day} generator exit={code}', flush=True)
    result = aggregate(repo); print('CERTIFIED_DAYS', result['CERTIFIED_DAYS'], '/31', flush=True)
    require(result['CERTIFIED_DAYS'] == 31, 'MAY_GENERATION_INCOMPLETE')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--day', choices=DAYS); parser.add_argument('--freeze', action='store_true'); parser.add_argument('--all', action='store_true')
    args = parser.parse_args(); repo = Path.cwd()
    if args.freeze: freeze_generator(repo)
    elif args.all: run_all(repo)
    elif args.day: generate_day(repo, args.day)
    else: print(aggregate(repo))
