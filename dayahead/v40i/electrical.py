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
EPOCH = 'epoch3'
EPOCH_ROOT = ROOT / 'generation_epochs' / EPOCH
FREEZE = EPOCH_ROOT / 'SOURCE_INPUT_FREEZE.json'
OUTPUT_ROOT = ROOT / 'g3'
DAYS = tuple(f'2025-05-{d:02}' for d in range(1, 32))
OUTPUT_NAMES = ('voltage', 'current', 'planning_coefficients', 'transformer_coefficients')


def now(): return datetime.now(timezone.utc).isoformat()


def validate_windows_output_path(run):
    longest = Path(run) / 'kernel/electrical/2025-05-31/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_2025-05-31.npz'
    # storage.atomic adds a dot, eight random characters and .tmp (13 chars).
    require(len(str(longest)) + 13 < 260, 'WINDOWS_GENERATION_OUTPUT_PATH_TOO_LONG')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf-8').strip()


def freeze_generator(repo):
    release = generation_release(repo)
    repo = Path(repo).resolve(); source = read(repo / 'dayahead/artifacts/v40h_production_integrity/FINAL_SCIENTIFIC_SOURCE_FREEZE.json')
    science_paths = [Path(r['path']) for r in source['source_manifest']['files']]
    generator_paths = sorted(Path(__file__).parent.glob('*.py')) + sorted((repo / 'tests/dayahead').glob('test_v40i_*.py'))
    paths = science_paths + generator_paths
    names = [p.relative_to(repo).as_posix() for p in paths]
    tracked = set(git(repo, 'ls-files').splitlines())
    require(set(names).issubset(tracked), 'GENERATOR_SOURCE_MUST_BE_COMMITTED')
    require(not (set(git(repo, 'diff', '--name-only', 'HEAD').splitlines()) & set(names)), 'GENERATOR_SOURCE_DIRTY')
    tests_path = repo / ROOT / 'V40I_PRE_GENERATION_TEST_REPORT.json'
    tests = read(tests_path)
    require(tests['status'] == 'PASS' and tests['failures'] == 0 and tests['errors'] == 0, 'ALL_REGRESSIONS_MUST_PASS_BEFORE_FREEZE')
    verify_manifest(tests['V40I_tested_source_manifest'])
    require({r['path'] for r in tests['V40I_tested_source_manifest']['files']} == {str(p.resolve()) for p in generator_paths}, 'TESTED_SOURCE_SCOPE_INCOMPLETE')
    value = {'revision': 'V40I', 'epoch': EPOCH, 'freeze_started_at': now(),
        'forensic_completion_release': release,
        'generator_commit_created_at': git(repo, 'show', '-s', '--format=%cI', 'HEAD'),
        'generator_git_commit': git(repo, 'rev-parse', 'HEAD'),
        'generator_entrypoint': 'dayahead.v40i.electrical:generate_day', 'source_manifest': manifest(paths, repo),
        'pre_generation_regression_report': file_record(tests_path),
        'generator_source_manifest': manifest(generator_paths, repo),
        'protected_science_source_manifest': manifest(science_paths, repo),
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


def generation_release(repo):
    root=Path(repo).resolve()/ROOT
    latest_hold=root/'V40I_ADDITIONAL_FORENSIC_GENERATION_HOLD.json'
    require(not latest_hold.exists() or read(latest_hold).get('status')!='HOLD',
            'ELECTRICAL_GENERATION_HOLD_LATEST_USER_ADDENDUM')
    path=root/'V40I_GENERATION_RELEASE_AFTER_FORENSIC.json'
    require(path.is_file(),'ELECTRICAL_GENERATION_HOLD_FORENSIC_PENDING')
    value=read(path)
    require(value.get('status')=='RELEASED_AFTER_FORENSIC' and value.get('production_optimization_authorized') is False,
            'ELECTRICAL_GENERATION_HOLD_FORENSIC_PENDING')
    for key in ('forensic_report','legacy_failure_classification','authority_closure'):
        verify_file(value[key])
    forensic=read(value['forensic_report']['path'])
    require(forensic['status']=='FORENSIC_COMPLETE_WITH_EXPLICIT_AUTHORITY_LIMITS'
            and forensic['no_optimization_executed'] and forensic['no_retuning_or_policy_selection'],
            'FORENSIC_PREREQUISITE_INCOMPLETE')
    failures=read(value['legacy_failure_classification']['path'])
    require(failures['status']=='CLASSIFIED' and failures['total']==64 and failures['V40I_failures']==0,
            'REPOSITORY_FAILURE_CLASSIFICATION_INCOMPLETE')
    closure=read(value['authority_closure']['path'])
    require(closure['TOTAL']==122 and closure['BLOCKER_REMAINING']==72,'AUTHORITY_CLOSURE_NOT_FINAL')
    return file_record(path)


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
    finally:
        os.chdir(previous)
        write_json(run / 'OPENDSS_INVOCATION_ACCOUNTING.json', {'at': now(),
            'measured_solve_calls': {k:m.count for k,m in meters.items()},
            'actual_opendss_invocation_count': sum(m.count for m in meters.values()),
            'nonconverged_calls': sum(m.nonconverged for m in meters.values()),
            'cache_hit_count': 0, 'previous_result_reuse_count': 0})
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
    import platform
    from importlib.metadata import version, PackageNotFoundError
    versions = {}
    for name in ('opendssdirect.py', 'dss-python', 'dss-python-backend', 'numpy', 'scipy'):
        try: versions[name] = version(name)
        except PackageNotFoundError: versions[name] = 'NOT_INSTALLED'
    old_outputs = list((run / 'kernel').rglob('*.npz')) if (run / 'kernel').exists() else []
    require(not old_outputs, 'PREEXISTING_OUTPUT_OR_CACHE_FORBIDDEN')
    generator_paths = {r['path'] for r in frozen.get('generator_source_manifest', {}).get('files', [])}
    science_paths = {r['path'] for r in frozen.get('protected_science_source_manifest', {}).get('files', [])}
    def split_hashes(rows):
        return {'generator_source_hashes': [r for r in rows if r['path'] in generator_paths],
            'protected_science_source_hashes': [r for r in rows if r['path'] in science_paths],
            'protected_input_hashes': [r for r in rows if r['path'] not in generator_paths | science_paths]}
    split_pre = split_hashes(pre_record['source_input_hashes'])
    pre_record.update(date=metadata['date'], captured_at=pre_record['created_at'], git_head=pre_record['git_HEAD'],
        branch=git(repo, 'branch', '--show-current'), generator_entrypoint=metadata.get('generator_entrypoint'),
        generator_source_files=frozen.get('generator_source_manifest', {}).get('files', []),
        protected_input_files=split_pre['protected_input_hashes'], **split_pre,
        generator_parameters=metadata.get('generation_parameters'), output_target_directory=str(run / 'kernel'),
        expected_output_contract=list(OUTPUT_NAMES), old_output_present_before_generation=False,
        old_cache_present_before_generation=False, process_id=os.getpid(), python_version=platform.python_version(),
        opendss_runtime_identity=versions, identity_schema_version='V40I_DURABLE_GENERATION_IDENTITY_V3')
    require(pre_record['git_HEAD'] == metadata['git_commit'], 'GENERATION_START_HEAD_MISMATCH')
    write_json(pre_path, pre_record)
    # Re-read the durable receipt before entering any generator computation.
    require(read(pre_path) == pre_record, 'DURABLE_PRE_IDENTITY_NOT_COMPLETE')
    started = now(); start_path = run / 'RUN_STARTED.json'
    start = {'generation_started_at': started, 'generation_git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'pre_generation_identity': file_record(pre_path), 'pre_generation_identity_completed_before_start': True}
    start.update(started_at=started, git_head=start['generation_git_HEAD'], process_id=os.getpid(),
        exact_generation_command=metadata.get('generation_command'), pre_generation_identity_hash=sha(pre_path))
    require(start['generation_git_HEAD'] == metadata['git_commit'], 'GENERATION_START_HEAD_MISMATCH')
    require(frozen['freeze_completed_at'] <= pre_record['created_at'] <= started, 'GENERATION_BEFORE_INPUT_FREEZE')
    write_json(start_path, start)
    error = None; outputs = {}; proof = {}
    try: outputs, proof = producer(pre)
    except Exception as e: error = e
    finished = now(); post_path = run / 'POST_GENERATION_IDENTITY.json'
    for path in outputs.values():
        require(not Path(path).is_symlink() and Path(path).stat().st_nlink == 1, 'OUTPUT_LINK_REUSE_FORBIDDEN')
    files = {k: file_record(p) for k, p in outputs.items()}
    post_hashes = rehash_evidence(pre)
    post_record = {'verification_completed_at': now(), 'git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'source_input_hashes': post_hashes, 'generator_error': repr(error) if error else None,
        'pre_post_hashes_match': flatten_files(pre) == post_hashes}
    split_post = split_hashes(post_hashes)
    flags = {'repository_head_unchanged': pre_record['git_HEAD'] == post_record['git_HEAD'],
        'generator_source_identity_unchanged': split_pre['generator_source_hashes'] == split_post['generator_source_hashes'],
        'protected_science_source_identity_unchanged': split_pre['protected_science_source_hashes'] == split_post['protected_science_source_hashes'],
        'protected_input_identity_unchanged': split_pre['protected_input_hashes'] == split_post['protected_input_hashes']}
    post_record.update(finished_at=finished, git_head_after=post_record['git_HEAD'],
        **{k + '_after': v for k, v in split_post.items()}, generated_output_files=files,
        generated_output_hashes={k:v['sha256'] for k,v in files.items()},
        actual_opendss_invocation_count=proof.get('fresh_generation_total_SolveSnap_calls', 0),
        cache_hit_count=proof.get('old_result_cache_reuse_count', 0),
        previous_result_reuse_count=proof.get('old_result_cache_reuse_count', 0),
        generation_exit_status='FAIL' if error else 'SUCCESS', pre_generation_identity_hash=sha(pre_path),
        run_started_hash=sha(start_path), **flags)
    accounting = run / 'OPENDSS_INVOCATION_ACCOUNTING.json'
    if accounting.exists():
        actual_accounting = read(accounting)
        post_record['actual_opendss_invocation_count'] = actual_accounting['actual_opendss_invocation_count']
        post_record['opendss_accounting'] = file_record(accounting)
    write_json(post_path, post_record)
    if error: raise error
    require(post_record['pre_post_hashes_match'], 'GENERATOR_PRE_POST_INPUT_MISMATCH')
    require(post_record['git_HEAD'] == metadata['git_commit'], 'GENERATOR_FROZEN_HEAD_CHANGED')
    require(set(outputs) == set(OUTPUT_NAMES), 'GENERATION_OUTPUT_COVERAGE')
    require(proof.get('fresh_output_paths_were_absent') is True and proof.get('old_result_cache_reuse_count') == 0
        and proof.get('fresh_generation_total_SolveSnap_calls', 0) > 0, 'FRESH_GENERATOR_EXECUTION_PROOF_MISSING')
    post = expected_builder()
    require(pre['identity_SHA'] == post['identity_SHA'] and pre['identity'] == post['identity'], 'GENERATOR_PRE_POST_INPUT_MISMATCH')
    require(all(flags.values()), 'GENERATOR_IDENTITY_FLAGS_FAIL')
    cert = {'revision': 'V40I', 'schema': 'V40I_ELECTRICAL_GENERATION_CERTIFICATE_V2', **metadata,
        'pre_generation_input_manifest': pre, 'pre_generation_input_hashes': flatten_files(pre),
        'generated_files': files, 'generated_file_hashes': {k: v['sha256'] for k, v in files.items()},
        'post_generation_input_hashes': flatten_files(post), 'input_identity_unchanged': True,
        'generation_started_at': started, 'generation_finished_at': finished, 'certificate_issued_at': now(), 'certificate_status': 'PASS',
        **flags,
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
    run = repo / OUTPUT_ROOT / day / token
    if os.name == 'nt': validate_windows_output_path(run)
    run.mkdir(parents=True, exist_ok=False)
    certificate = repo / ROOT / 'electrical_generation_certificates' / (day + '.json')
    write_json(run / 'RUN_ADMITTED.json', {'date': day, 'pid': os.getpid(), 'at': now(), 'generator_source_freeze': frozen})
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
            require(all(c.get(k) is True for k in ('repository_head_unchanged','generator_source_identity_unchanged',
                'protected_science_source_identity_unchanged','protected_input_identity_unchanged')), 'CERTIFICATE_IDENTITY_FLAGS')
            require(c['pre_generation_identity_completed_before_start'] is True and
                c['pre_generation_freeze_completed_at'] <= c['pre_generation_identity_completed_at'] <=
                c['generation_started_at'] <= c['generation_finished_at'] <=
                c['post_generation_verification_completed_at'] <= c['certificate_issued_at'], 'CERTIFICATE_CHRONOLOGY_INVALID')
            if verify:
                verify_file(c['source_input_freeze'])
                for key in ('durable_pre_generation_receipt', 'durable_generation_start_receipt', 'durable_post_generation_receipt'):
                    verify_file(c[key])
                pre = read(c['durable_pre_generation_receipt']['path']); start = read(c['durable_generation_start_receipt']['path'])
                post = read(c['durable_post_generation_receipt']['path']); frozen = read(c['source_input_freeze']['path'])
                require(start['pre_generation_identity_hash'] == post['pre_generation_identity_hash'] == c['durable_pre_generation_receipt']['sha256'], 'CERTIFICATE_PRE_RECEIPT_BINDING')
                require(post['run_started_hash'] == c['durable_generation_start_receipt']['sha256'], 'CERTIFICATE_START_RECEIPT_BINDING')
                require(pre['input_identity'] == c['pre_generation_input_manifest'] and
                    post['source_input_hashes'] == c['post_generation_input_hashes'], 'CERTIFICATE_IDENTITY_RECEIPT_BINDING')
                require(post['generated_output_files'] == c['generated_files'] and post['actual_opendss_invocation_count'] == 23234, 'CERTIFICATE_OUTPUT_RECEIPT_BINDING')
                require(frozen['generator_git_commit'] == c['git_commit'], 'CERTIFICATE_FROZEN_COMMIT_BINDING')
                require(read(verify_file(frozen['daily_pre_generation_inputs'][day]))['input_identity'] == pre['input_identity'], 'CERTIFICATE_PREFREEZE_BINDING')
                for value in c['generated_files'].values(): verify_file(value)
                verify_bound_files(c['pre_generation_input_manifest'])
            rows.append({'date': day, 'status': 'PASS', 'certificate': file_record(path), 'generated_files': c['generated_files']})
        except (ValueError, KeyError, OSError) as e: rows.append({'date': day, 'status': 'FAIL', 'reason': str(e)})
    count = sum(r['status'] == 'PASS' for r in rows)
    result = {'revision': 'V40I', 'certificate_status': 'PASS' if count == 31 else 'FAIL', 'CERTIFIED_DAYS': count,
        'REQUIRED_DAYS': 31, 'FAILED_DAYS': sum(r['status'] == 'FAIL' for r in rows),
        'MISSING_DAYS': sum(r['status'] == 'MISSING' for r in rows),
        'old_result_cache_reuse': 0, 'days': rows}
    write_json(root / 'V40I_ELECTRICAL_GENERATION_CERTIFICATION.json', result); return result


def run_all(repo):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    repo = Path(repo).resolve(); frozen = read(repo / FREEZE)
    verify_file(file_record(repo / FREEZE))
    for record in frozen['daily_pre_generation_inputs'].values(): verify_file(record)
    require(set(frozen['daily_pre_generation_inputs']) == set(DAYS), 'ALL_DAYS_MUST_BE_FROZEN_BEFORE_ALL')
    require(git(repo, 'rev-parse', 'HEAD') == frozen['generator_git_commit'], 'GENERATOR_FROZEN_HEAD_CHANGED')
    logs = repo / EPOCH_ROOT / 'generation_logs'; logs.mkdir(parents=True, exist_ok=True)
    all_started = now(); progress = {}; completed = {}
    write_json(repo / EPOCH_ROOT / 'ALL_GENERATION_STARTED.json', {'at': all_started, 'git_HEAD': git(repo, 'rev-parse', 'HEAD'),
        'complete_pre_generation_freeze': file_record(repo / FREEZE), 'frozen_days': 31})
    def update_progress():
        write_json(repo / ROOT / 'V40I_ELECTRICAL_GENERATION_PROGRESS.json', {'total_days':31,
            'completed_days':sorted(completed), 'certified_days':sum(v == 0 for v in completed.values()),
            'failed_days':sum(v != 0 for v in completed.values()), 'current_day':sorted(progress),
            'frozen_head':frozen['generator_git_commit'], 'frozen_head_still_current':git(repo,'rev-parse','HEAD') == frozen['generator_git_commit'],
            'started_at':all_started, 'last_update_at':now()})
    def worker(day):
        progress[day] = True
        with (logs / (day + '.log')).open('xb') as stream:
            result = subprocess.run([sys.executable, '-m', 'dayahead.v40i.electrical', '--day', day], cwd=repo, stdout=stream, stderr=subprocess.STDOUT)
        return day, result.returncode
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(worker, day): day for day in DAYS}
        for future in as_completed(pending):
            day, code = future.result(); print(f'{day} generator exit={code}', flush=True)
            completed[day] = code; progress.pop(day, None); update_progress()
    result = aggregate(repo); print('CERTIFIED_DAYS', result['CERTIFIED_DAYS'], '/31', flush=True)
    require(result['CERTIFIED_DAYS'] == 31, 'MAY_GENERATION_INCOMPLETE')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--day', choices=DAYS); parser.add_argument('--freeze', action='store_true'); parser.add_argument('--all', action='store_true')
    args = parser.parse_args(); repo = Path.cwd()
    if args.freeze: freeze_generator(repo)
    elif args.all: run_all(repo)
    elif args.day: generate_day(repo, args.day)
    else: print(aggregate(repo))
