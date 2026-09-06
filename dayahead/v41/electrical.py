"""V41 provenance wrapper around the unchanged V40I electrical generator."""
from copy import deepcopy
from pathlib import Path
from types import FunctionType
from datetime import datetime, timezone
import shutil

from dayahead.paper_analysis.storage import read, write_json
from dayahead.v40h.identity import manifest, bind, verify_bound_files, file_record
from dayahead.v40i.electrical import generate_outputs, validate_windows_output_path
from .data import SOURCE_REPO, RUNTIME
from .preflight import ROOT, record
from .reserve import require


def copy_input(relative):
    source, target = SOURCE_REPO / relative, ROOT / relative
    require(source.is_file(), 'FROZEN_DEPENDENCY_MISSING:' + str(source))
    source_sha = record(source)['sha256']
    if target.exists():
        require(record(target)['sha256'] == source_sha, 'LOCAL_DEPENDENCY_DIFFERS:' + relative)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return dict(source=record(source), local=record(target))


def dependencies(day):
    paths = [
        'dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json',
        'dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_CAPACITY_FREEZE_CERTIFICATE.json',
        'dayahead/artifacts/v39d_independent_daily_temporal_first_migration/V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json',
        'dayahead/artifacts/v39d_independent_daily_temporal_first_migration/V39D_RACK_FREEZE_CERTIFICATE.json',
        'dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json',
        'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json',
        f'dayahead/cache/v37_may_locked_final/electrical/{day}/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz',
    ]
    return [copy_input(p) for p in paths]


def identity(day):
    inventory_path = SOURCE_REPO / 'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json'
    values = deepcopy(read(inventory_path)['daily_electrical_identities'][day]['identity']['inputs'])
    folders = ('v40e', 'v40i')
    # Bind numerical generation and its local path/validation dependencies.
    # Adding an unrelated replay/report module cannot change these equations.
    paths = [p for folder in folders for p in (ROOT / 'dayahead' / folder).glob('*.py')]
    paths += [ROOT / 'dayahead/v40h' / name for name in ('numerical_context.py', 'identity.py')]
    paths += [ROOT / 'dayahead/v41' / name for name in ('electrical.py', 'data.py', 'preflight.py', 'reserve.py', 'mapper_audit.py', 'persistence.py')]
    source = manifest(paths, ROOT)
    values['V41_generation_source'] = source
    values['V41_generation_entrypoint'] = 'dayahead.v40i.electrical:generate_outputs'
    values['V41_authority'] = 'V41_USER_AUTHORIZED_NEW_GENERATION_NO_OLD_OUTPUT_ADOPTION'
    verify_bound_files(values)
    return bind('V41_ELECTRICAL_GENERATION_V1', values, tuple(values))


def kernel(run):
    from dayahead.v40e import electrical as frozen
    namespace = dict(vars(frozen)); namespace['REL'] = run.relative_to(ROOT) / 'kernel'
    for name in ('upstream', 'electrical_context', 'planning_context'):
        fn = getattr(frozen, name); fn = getattr(fn, '__wrapped__', fn)
        namespace[name] = FunctionType(fn.__code__, namespace, name, fn.__defaults__, fn.__closure__)
    return namespace


def generate(day):
    run = RUNTIME / 'e' / day.replace('-', '')
    certificate = run / 'V41_ELECTRICAL_CERTIFICATE.json'
    validate_windows_output_path(run)
    if certificate.exists():
        return load(day)
    require(not run.exists(), 'PRESERVE_UNATTESTED_ELECTRICAL_ATTEMPT')
    deps = dependencies(day)
    before = identity(day)
    write_json(run / 'PRE_GENERATION_IDENTITY.json', before)
    captured_at=datetime.now(timezone.utc).isoformat()
    started_at=datetime.now(timezone.utc).isoformat()
    write_json(run/'RUN_STARTED.json',dict(input_identity=record(run/'PRE_GENERATION_IDENTITY.json'),
        pre_generation_identity_completed_at=captured_at,generation_started_at=started_at))
    from .mapper_audit import observe
    with observe(run/'mapper_audit',day,'Planning_GENERATION'):
        outputs, proof = generate_outputs(ROOT, day, run, before)
    finished_at=datetime.now(timezone.utc).isoformat()
    after = identity(day)
    require(before == after, 'ELECTRICAL_SOURCE_CHANGED_DURING_GENERATION')
    verified_at=datetime.now(timezone.utc).isoformat()
    value = dict(schema='V41_ELECTRICAL_CERTIFICATE_V1', input_identity=before,
        outputs={k: record(p) for k, p in outputs.items()}, proof=proof,
        mapper_audit=record(run/'mapper_audit/MAPPER_AUDIT.json'),
        pre_generation_identity_completed_at=captured_at,generation_started_at=started_at,
        generation_finished_at=finished_at,post_generation_verification_completed_at=verified_at,
        generation_start_receipt=record(run/'RUN_STARTED.json'),
        dependency_copies=deps, generation_attestation='CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER')
    write_json(certificate, value)
    return load(day)


def load(day):
    run = RUNTIME / 'e' / day.replace('-', '')
    certificate = run / 'V41_ELECTRICAL_CERTIFICATE.json'
    value = read(certificate)
    verify_generation_proof(value)
    require(value['mapper_audit']==record(run/'mapper_audit/MAPPER_AUDIT.json'),'ELECTRICAL_MAPPER_AUDIT_DRIFT')
    require(read(value['mapper_audit']['path'])['status']=='PASS','ELECTRICAL_MAPPER_AUDIT_FAILED')
    require(value['input_identity'] == identity(day), 'STALE_ELECTRICAL_GENERATION_SOURCE')
    for entry in value['outputs'].values():
        require(entry == record(entry['path']), 'ELECTRICAL_OUTPUT_FILE_DRIFT')
    context = kernel(run)['planning_context'](ROOT, day)
    import numpy as np
    from dayahead.v40h.numerical_context import FIELDS
    with np.load(value['outputs']['planning_coefficients']['path'],allow_pickle=False) as stored:
        for key in FIELDS:
            require(np.array_equal(stored[key],np.asarray([getattr(c,key) for c in context.coefficients])),
                    'ELECTRICAL_REOPEN_NUMERICAL_DRIFT:'+key)
    from dayahead.v38.authority import load_wan_authority
    context.wan = load_wan_authority(ROOT)
    import pandas as pd
    from .data import issue_time
    path = SOURCE_REPO / 'dayahead/artifacts/v37_r4a_per_day_aidc/days' / day / 'V37_R4A_D1_SNAPSHOT.parquet'
    frame = pd.read_parquet(path, columns=['id', 'state_at_issue', 'known_running_start', 'submit_time'])
    require(frame.submit_time.le(issue_time(day)).all(), 'ELAPSED_FUTURE_SUBMISSION')
    context.elapsed = {str(r.id): (issue_time(day) - pd.Timestamp(r.known_running_start)).total_seconds()
                       for r in frame[frame.state_at_issue == 'RUNNING'].itertuples()}
    context.v41_electrical_certificate = record(certificate)
    context.v41_electrical_identity = value['input_identity']['identity_SHA']
    return context


def verify_generation_proof(value):
    require(value.get('schema')=='V41_ELECTRICAL_CERTIFICATE_V1','LEGACY_ELECTRICAL_CERTIFICATE_FORBIDDEN')
    require(value.get('generation_attestation')=='CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER','POSTHOC_ELECTRICAL_ATTESTATION_FORBIDDEN')
    require(value['pre_generation_identity_completed_at']<=value['generation_started_at']<=value['generation_finished_at']<=
            value['post_generation_verification_completed_at'],'ELECTRICAL_PRE_POST_TIME_ORDER')
    proof=value['proof']
    require(proof['fresh_output_paths_were_absent'] and proof['old_result_cache_reuse_count']==0,
            'OLD_ELECTRICAL_OUTPUT_ADOPTION_FORBIDDEN')
    require(proof['fresh_generation_total_SolveSnap_calls']==23234 and proof['measured_nonconverged_calls']==0 and
            proof['measured_solve_calls']=={'voltage':11617,'current':11617},'ELECTRICAL_REAL_GENERATION_PROOF_FAILED')


if __name__ == '__main__':
    import sys
    ctx = generate(sys.argv[1])
    print('ELECTRICAL_READY', ctx.day, ctx.v41_electrical_identity, flush=True)
    ctx.electrical.voltage.close(); ctx.electrical.current.close()
