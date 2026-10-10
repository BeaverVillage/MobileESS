"""A sealed diagnostic permit alongside preserved, owned original canaries."""
from pathlib import Path
import os
import psutil
import shutil
import subprocess

from v42_common_campaign import VERSION
from v42_common_campaign.authority import ROOT, checked, source_files, verify_control_audit
from v42_pr134_b1.common import atomic, digest, now, read, record, sha
from . import POLICY, ATTEMPT, DAY, MANIFEST


def source_seal(manifest):
    code = Path(manifest['code_root']).resolve()
    if manifest.get('execution_SHA') != digest(manifest['execution_sources']):
        raise PermissionError('VMAX1048_SOURCE_IDENTITY_DRIFT')
    for name, expected in manifest['execution_sources'].items():
        path = (code / name).resolve()
        if not path.is_relative_to(code) or sha(path) != expected:
            raise PermissionError('VMAX1048_SOURCE_BYTES_DRIFT:'+name)


def prepare(root, regression, existing_canary_root, original_result):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / MANIFEST).exists():
        raise PermissionError('VMAX1048_SOURCE_EPOCH_NEVER_OVERWRITTEN')
    if shutil.disk_usage(root).free < 4*1024**3:
        raise PermissionError('VMAX1048_STORAGE_HEADROOM')
    gate = read(regression)
    sources = source_files()
    source_sha = digest(sources)
    if gate.get('PASS') is not True or gate.get('source_SHA') != source_sha:
        raise PermissionError('VMAX1048_REGRESSION_SOURCE_GATE_REQUIRED')
    existing_path = Path(existing_canary_root) / 'COMMON_U4_QUALIFICATION_MANIFEST.json'
    existing = read(existing_path)
    source_seal(existing)
    verify_control_audit(Path(existing_canary_root),existing)
    original = read(original_result)
    if (original.get('identity', {}).get('arm') != 'B2'
            or original.get('identity', {}).get('day') != DAY
            or original.get('status') != 'ACTUAL_AC_FAILED'):
        raise PermissionError('VMAX1048_PRESERVED_MAY01_BASELINE_REQUIRED')
    checked(original['native_ledger'])
    for receipt in original.get('files', []):
        checked(receipt)
    inputs = existing['input_receipts'][DAY]
    for receipt in inputs:
        checked(receipt)
    audit_status = read(Path(existing_canary_root) / 'COMMON_CONTROL_AUDIT_STATUS.json')
    audit = read(checked(audit_status['audit']))
    if (audit_status.get('status') != 'PASS'
            or audit.get('common_control_implementation_defect') is not False
            or audit.get('baseline_RESULT') != record(original_result)):
        raise PermissionError('VMAX1048_ORIGINAL_COMMON_CONTROL_AUDIT_REQUIRED')
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest = dict(schema='V42_VMAX1048_DIAGNOSTIC_MANIFEST_V1',run_id=root.name,
        code_root=str(ROOT),source_commit=commit,execution_sources=sources,execution_SHA=source_sha,
        builder_original_sources=sources,
        implementation=dict(version='B2_BUILD_SOURCE_AUTHORITY_V13_20261009',sources=sources),
        algorithm_version=VERSION,planning_policy=POLICY,
        planning_voltage_min_pu=.95,planning_voltage_max_pu=1.048,
        planning_voltage_max_squared_pu=1.098304,actual_voltage_min_pu=.95,
        actual_voltage_max_pu=1.05,native_M_limit_seconds=1800,Threads=1,P2_calls=0,
        input_folder=existing['input_folders'][DAY],input_receipts=inputs,
        original_May01_result=record(original_result),
        original_May01_output=str(Path(original_result).parent / 'output'),
        original_regcontrol_settings_SHA='3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf',
        original_May01_actual_phase_arrays=record(Path(original_result).parent / 'output/OPERATIONS/FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz'),
        original_control_audit_verdict=audit_status['audit'],
        permitted_existing_canary_manifest=record(existing_path),
        permitted_existing_canary_days=['2025-05-03'],
        source_qualification=record(regression),diagnostic_only=True,
        evaluation_classification='MAY01_POST_OBSERVATION_DIAGNOSTIC_NOT_HOLDOUT',
        all31_policy_conversion_approved=False,A1_A2_policy_changed=False,UTC=now())
    atomic(root / MANIFEST,manifest)
    verify_manifest(root / MANIFEST)
    attempt = root / 'dates/B2' / DAY / 'attempts' / ATTEMPT
    request = dict(root=str(root),campaign_root=str(root),code_root=str(ROOT),run_id=root.name,
        manifest=str(root / MANIFEST),campaign_manifest=str(root / MANIFEST),
        manifest_SHA=sha(root / MANIFEST),source_SHA=source_sha,implementation_SHA=source_sha,
        arm='B2',day=DAY,attempt_id=ATTEMPT,worker_slot=3,canary=True,
        algorithm_version=VERSION,planning_policy=POLICY,
        planning_voltage_max_pu=1.048,actual_voltage_max_pu=1.05,
        input_folder=manifest['input_folder'],result=str(attempt/'RESULT.json'),
        progress=str(attempt/'progress.json'),output=str(attempt/'output'),
        error=str(attempt/'error.json'),Threads=1,P2_calls=0,native_budget_seconds=1800,
        wall_budget_seconds=None,target_gap=.03,started_UTC=now())
    atomic(attempt / 'REQUEST.json',request)
    verify_request(request)
    return record(attempt / 'REQUEST.json')


def verify_manifest(path):
    manifest = read(path)
    if (manifest.get('schema') != 'V42_VMAX1048_DIAGNOSTIC_MANIFEST_V1'
            or Path(manifest['code_root']).resolve() != ROOT
            or manifest.get('planning_policy') != POLICY
            or manifest.get('algorithm_version') != VERSION
            or manifest.get('planning_voltage_min_pu') != .95
            or manifest.get('planning_voltage_max_pu') != 1.048
            or manifest.get('planning_voltage_max_squared_pu') != 1.098304
            or manifest.get('actual_voltage_min_pu') != .95
            or manifest.get('actual_voltage_max_pu') != 1.05
            or manifest.get('native_M_limit_seconds') != 1800
            or manifest.get('Threads') != 1 or manifest.get('P2_calls') != 0
            or manifest.get('diagnostic_only') is not True
            or manifest.get('all31_policy_conversion_approved') is not False
            or manifest.get('A1_A2_policy_changed') is not False):
        raise PermissionError('VMAX1048_DIAGNOSTIC_POLICY_DRIFT')
    source_seal(manifest)
    for receipt in manifest['input_receipts']:
        checked(receipt)
    for key in ('original_May01_result','original_control_audit_verdict',
                'permitted_existing_canary_manifest','source_qualification'):
        checked(manifest[key])
    peer_manifest=manifest['permitted_existing_canary_manifest']
    previous=read(peer_manifest['path'])
    verify_control_audit(Path(peer_manifest['path']).parent,previous)
    if manifest.get('original_May01_actual_phase_arrays'):
        checked(manifest['original_May01_actual_phase_arrays'])
    return manifest


def verify_request(request):
    root = Path(request['root']).resolve()
    path = root / MANIFEST
    manifest = verify_manifest(path)
    if (Path(request['manifest']).resolve() != path or request.get('manifest_SHA') != sha(path)
            or request.get('source_SHA') != manifest['execution_SHA']
            or request.get('run_id') != manifest['run_id'] or request.get('arm') != 'B2'
            or request.get('day') != DAY or request.get('attempt_id') != ATTEMPT
            or request.get('worker_slot') != 3 or request.get('canary') is not True
            or request.get('planning_policy') != POLICY
            or request.get('algorithm_version') != VERSION
            or request.get('planning_voltage_max_pu') != 1.048
            or request.get('actual_voltage_max_pu') != 1.05
            or request.get('native_budget_seconds') != 1800
            or request.get('wall_budget_seconds') is not None
            or request.get('Threads') != 1 or request.get('P2_calls') != 0
            or Path(request['input_folder']).resolve() != Path(manifest['input_folder']).resolve()):
        raise PermissionError('VMAX1048_REQUEST_POLICY_OR_SOURCE_DRIFT')
    attempt = root / 'dates/B2' / DAY / 'attempts' / ATTEMPT
    for key, name in (('result','RESULT.json'),('progress','progress.json'),('output','output')):
        if Path(request[key]).resolve() != attempt / name:
            raise PermissionError('VMAX1048_OWNED_ATTEMPT_PATH_REQUIRED')
    return manifest


def assert_peers(request):
    manifest = read(request['manifest'])
    permitted = manifest['permitted_existing_canary_manifest']
    original = read(checked(permitted))
    counts = {'B2':1,'B3':0}
    for proc in psutil.process_iter(['name']):
        if proc.pid == os.getpid() or (proc.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):
            continue
        try:
            args = proc.cmdline()
            module = args[args.index('-m')+1] if '-m' in args else ''
            if module == 'v42_vmax1048.worker':
                raise PermissionError('VMAX1048_DUPLICATE_DIAGNOSTIC_WORKER')
            if module == 'v42_common_campaign.worker':
                peer = read(args[-1])
                peer_path=Path(args[-1]).resolve()
                owner=read(peer_path.parent/'PROCESS.json')
                if (peer.get('canary') is not True
                        or Path(peer['manifest']).resolve() != Path(permitted['path']).resolve()
                        or peer.get('manifest_SHA') != permitted['sha256']
                        or peer.get('source_SHA') != original['execution_SHA']
                        or peer.get('day') not in manifest['permitted_existing_canary_days']
                        or peer.get('arm') not in counts or peer.get('worker_slot') == 3
                        or owner.get('PID') != proc.pid or owner.get('command') != args
                        or owner.get('created') != proc.create_time()
                        or peer_path != Path(permitted['path']).parent/'dates'/peer['arm']/peer['day']/'attempts'/peer['attempt_id']/'REQUEST.json'):
                    raise PermissionError('VMAX1048_ONLY_PRESERVED_AUTHORIZED_CANARY_PEER_ALLOWED')
                source_seal(original)
                counts[peer['arm']] += 1
            elif module.startswith('v42_') and module.endswith('.worker'):
                raise PermissionError('VMAX1048_UNREGISTERED_NATIVE_WORKER_PEER')
        except psutil.Error:
            continue
    if counts['B2'] > 3 or counts['B3'] > 1:
        raise PermissionError('VMAX1048_TOTAL_NATIVE_WORKER_LIMIT')
