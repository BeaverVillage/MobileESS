"""Reproducible four-date reporting from receipts; never build or solve a model.

Missing observations remain null. In particular, native active-domain proofs
and LP pricing do not substitute for an integer-domain closure certificate.
``finalize`` is called only after the isolated runner has stopped.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from .execution import REQUIRED_STRESS_GATES, REQUIRED_RUN_SOURCE_NAMES
from .status import validate_domain_status

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/v42_a_stage_v2_stress4_20261007'
AUTHORITY_DOCS = ROOT/'docs/v42_a_stage_domain_authority_v2_20261007'
BASE = '1e2d819406081af5b4bbee6fab3c4b5c3e102b2b'
PRODUCTION = Path('C:/v42_pr134_sc_execution_20261007')
EXTERNAL_STATIC = Path('C:/v42_a_stage_v2_stress4_20261007/static')
DAYS = ('2025-05-17', '2025-05-19', '2025-05-12', '2025-05-10')
LEX = ('rho', 'migration_count', 'shift_magnitude', 'prestart_relocation')
HISTORICAL = ('docs/v42_b1_may17_may19_repair_20261007',
              'docs/v42_b1_adaptive_prescreening_rescue_20261007',
              'docs/v42_b1_may19_prescreening_rescue_20261007')
REQUIRED_JSON = ('INPUT_IDENTITY.json', 'DOMAIN_CENSUS.json', 'SOLVER_PARAMETERS.json',
                 'A1_RESULT.json', 'DOMAIN_CLOSURE_RESULT.json')
REQUIRED_CSV = {
    'MODEL_CENSUS_BY_LEX_STAGE.csv': ('stage', 'build_seconds', 'rows', 'cols', 'binaries', 'integer_counts', 'continuous', 'nnz'),
    'A1_PROGRESS.csv': ('day', 'objective', 'native_seconds', 'Work', 'incumbent', 'active_domain_global_bound', 'gap', 'node_count', 'event', 'RSS_bytes'),
    'RESOURCE_TELEMETRY.csv': ('day', 'objective', 'wall_seconds', 'RSS_bytes', 'available_RAM_bytes', 'peak_RSS_bytes', 'observational_only'),
}
PIPELINE = ('PLANNING_FREEZE.json', 'ACTUAL_RESULT.json', 'FRESH_OPENDSS_RESULT.json', 'PHYSICAL_VALIDATION.json')


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8', newline='\n')


def rows(path):
    path = Path(path)
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig', newline='') as stream: return list(csv.DictReader(stream))


def table(path, values, fields=None):
    values = list(values)
    fields = list(fields or dict.fromkeys(k for value in values for k in value))
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader(); writer.writerows(values)


def record(path, root=ROOT):
    path = Path(path)
    with path.open('rb') as stream: sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    try: label = path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError: label = str(path.resolve())
    return dict(path=label, sha256=sha, bytes=path.stat().st_size)


def finite(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        try: number = float(value)
        except ValueError: return None
        return number if math.isfinite(number) else None
    return None


def subtract(after, before):
    after, before = finite(after), finite(before)
    return after-before if after is not None and before is not None else None


def unavailable(day, reason, name):
    return dict(day=day, availability='UNAVAILABLE', artifact=name, reason=reason,
                PASS=None, observed=False, missing_values_inferred=False)


def historical_changes(root=ROOT):
    """Tracked, staged, unstaged and nonignored untracked historical changes."""
    root = Path(root)
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', *HISTORICAL], cwd=root, text=True).splitlines()
    changed += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--', *HISTORICAL], cwd=root, text=True).splitlines()
    return sorted(set(changed))


def _passes(result, folder):
    value = {p['component']:p for p in result.get('passes', []) if p.get('component') in LEX}
    for name in LEX:
        receipt = read(folder/name/'PASS_RESULT.json')
        if receipt is not None:
            value[name] = receipt
    return value


def _telemetry(folder, name):
    return read(folder/name/'NATIVE_TELEMETRY.json', {})


def _root_observation(telemetry):
    root = telemetry.get('root_relaxation') or {}
    events = telemetry.get('events') or {}
    return dict(root_relaxation_seconds=root.get('seconds'), root_iterations=root.get('iterations'),
                root_objective=root.get('objective'),
                root_completion_native_seconds=events.get('root_completion_observed_native_seconds'),
                root_Work=events.get('root_completion_observed_Work'),
                root_completed=bool(root or events.get('root_completion_observed_native_seconds') is not None),
                barrier_seconds=(telemetry.get('barrier') or {}).get('seconds'),
                barrier_iterations=(telemetry.get('barrier') or {}).get('iterations'),
                crossover_seconds=(telemetry.get('crossover') or {}).get('seconds'))


def _replay_PASS(folder, name, stage):
    replay = read(folder/name/'INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json', {})
    return stage.get('independently_verified') is True and replay.get('PASS') is True


def summarize_date(day, result, folder, census, forecast=None):
    """Return evidence-only summary and diagnostic discrepancies.

    Full acceptance needs the runner's explicit acceptance, all four current
    verified lex proofs and its explicit integer closure. Missing prerequisites
    reject a claimed acceptance rather than silently promoting other flags.
    """
    passes = _passes(result, folder); closure = read(folder/'DOMAIN_CLOSURE_RESULT.json', {})
    domain = result.get('domain_status') or {}
    discrepancies = []
    independent = {name:_replay_PASS(folder, name, stage) for name,stage in passes.items()}
    feasible = any(independent.values())
    complete = all(name in passes and passes[name].get('active_domain_objective_proven') is True
                   and independent.get(name) is True for name in LEX)
    integer_closed = closure.get('INTEGER_DOMAIN_CLOSURE_PROVEN') is True
    if integer_closed or closure.get('PRODUCTION_DOMAIN_ACCEPTED') is True:
        try: validate_domain_status(closure)
        except PermissionError as error:
            discrepancies.append('INVALID_INTEGER_DOMAIN_CLOSURE_CERTIFICATE:'+str(error))
            integer_closed = False
    migration_closed = closure.get('MIGRATION_PRICING_CLOSED') is True
    full = (result.get('A1_full_domain_accepted') is True and
            closure.get('PRODUCTION_DOMAIN_ACCEPTED') is True and integer_closed and complete and feasible)
    if result.get('day', day) != day: discrepancies.append('RESULT_DATE_AUTHORITY_MISMATCH')
    for name,stage in passes.items():
        if stage.get('component') != name: discrepancies.append('OBJECTIVE_COMPONENT_RECEIPT_MISMATCH:'+name)
    for stage in result.get('passes', []):
        if stage.get('component') in passes and stage != passes[stage['component']]:
            discrepancies.append('A1_RESULT_AND_COMPONENT_RECEIPT_DISAGREE:'+stage['component'])
    if result.get('A1_active_domain_feasible') is True and not feasible:
        discrepancies.append('ACTIVE_FEASIBILITY_WITHOUT_INDEPENDENT_CURRENT_REPLAY')
    if result.get('A1_full_domain_accepted') is True and not full:
        discrepancies.append('FULL_ACCEPTANCE_WITHOUT_COMPLETE_CURRENT_LEX_AND_INTEGER_CLOSURE')
    if result.get('integer_domain_closure_proven') is True and not integer_closed:
        discrepancies.append('INTEGER_CLOSURE_RESULT_CONTRADICTION')
    if result.get('migration_pricing_closed') is True and not migration_closed:
        discrepancies.append('MIGRATION_PRICING_RESULT_CONTRADICTION')
    pipeline = {name:read(folder/name, {}) for name in PIPELINE}
    planning = full and result.get('Planning_freeze') is True and pipeline['PLANNING_FREEZE.json'].get('PASS') is True
    actual = planning and result.get('Actual') is True and pipeline['ACTUAL_RESULT.json'].get('PASS') is True
    fresh = actual and result.get('Fresh_OpenDSS') is True and pipeline['FRESH_OPENDSS_RESULT.json'].get('PASS') is True
    physical = fresh and result.get('physical_PASS') is True and pipeline['PHYSICAL_VALIDATION.json'].get('PASS') is True
    if result.get('physical_PASS') is True and not physical:
        discrepancies.append('FULL_PHYSICAL_PASS_WITHOUT_COMPLETE_PIPELINE_RECEIPTS')
    declared = result.get('classification', 'UNRESOLVED')
    if discrepancies or result.get('global_scientific_stop') or declared == 'SCIENTIFIC_IDENTITY_FAIL':
        classification = 'SCIENTIFIC_IDENTITY_FAIL'
    elif declared == 'PHYSICAL_VALIDATION_FAIL': classification = declared
    elif physical: classification = 'STRESS_DATE_FULL_PASS'
    elif full: classification = 'A1_FULL_DOMAIN_ACCEPTED_FRESH_PENDING'
    elif declared.startswith('NOT_ATTEMPTED'): classification = declared
    elif complete: classification = 'A1_ACTIVE_DOMAIN_SOLVED_DOMAIN_CLOSURE_UNRESOLVED'
    elif declared in ('ROOT_LP_TIMEOUT', 'LEX_P2_TIMEOUT'): classification = declared
    else: classification = 'UNRESOLVED'
    old_status = {'17':'OLD_ARTIFICIAL_DOMAIN_INFEASIBILITY; 35_OPTION_DIAGNOSTIC_RESCUE',
                  '19':'OLD_DOMAIN_VOLTAGE_CC4_DIAGNOSTIC_UNRESOLVED',
                  '12':'OLD_P1_ROOT_TIMEOUT; DUAL_SIMPLEX_ROOT_3562.46_SECONDS',
                  '10':'OLD_LEX_P2_SHIFT_TIMEOUT; FEASIBLE_INCUMBENT_12_BOUND_0'}[day[-2:]]
    forecast = forecast or {}
    stay = census.get('hard_valid_STAY_starts', forecast.get('physical_STAY_options'))
    migration = census.get('new_hard_physical', {}).get('migration_path_multiplicity')
    migration = census.get('physical_migration_paths', migration)
    if migration is None: migration = forecast.get('physical_migration_paths')
    new_size = census.get('total_physical_path_multiplicity', census.get('hard_valid_total_candidates'))
    if new_size is None and finite(stay) is not None and finite(migration) is not None:
        new_size = int(float(stay))+int(float(migration))
    old_active = census.get('old_S0', {}).get('migration_path_multiplicity', forecast.get('old_active_migration_paths'))
    lazy = subtract(migration, old_active)
    summary = dict(date=day, old_historical_status=old_status, new_domain_size=new_size,
                   new_domain_size_scope='SCIENTIFIC_CLASS_OPTION_SUPPORT; NO_JOB_PERMUTATIONS',
                   physical_STAY_support=stay,
                   restored_STAY_support=census.get('new_candidates_restored_relative_to_old_S0'),
                   active_STAY_support=census.get('qualification_active_STAY_options'),
                   active_migration_support=census.get('old_active_migration_paths', old_active),
                   active_support_scope=('NATIVE_BUILD_QUALIFICATION_RECEIPT' if census.get('qualification_complete_STAY_active') is True
                                         else 'PREREGISTERED_SUPPORT_ONLY; NATIVE_ACTIVATION_UNAVAILABLE'),
                   remaining_lazy_migration_support=lazy if lazy is not None else forecast.get('inactive_migration_paths'),
                   A1_active_domain_feasible=feasible, ACTIVE_DOMAIN_SOLVED=complete,
                   STAY_DOMAIN_COMPLETE=closure.get('STAY_DOMAIN_COMPLETE', domain.get('STAY_DOMAIN_COMPLETE')),
                   migration_pricing_closed=migration_closed, integer_domain_closure_proven=integer_closed,
                   A1_full_domain_accepted=full, Planning_freeze=planning, Actual=actual,
                   Fresh_OpenDSS=fresh, physical_PASS=physical,
                   cumulative_native_seconds=result.get('native_seconds'),
                   cumulative_native_budget_seconds=result.get('native_budget_seconds'),
                   computational_resource_failure=result.get('computational_resource_failure', False),
                   error=result.get('error', result.get('native_solver_error')),
                   final_classification=classification)
    for name in LEX:
        stage = passes.get(name, {})
        summary.update({name+'_status':stage.get('status'), name+'_value':stage.get('objective'),
                        name+'_bound':stage.get('active_domain_global_bound'), name+'_gap':stage.get('gap'),
                        name+'_time_seconds':stage.get('native_seconds'),
                        name+'_active_optimum_proven':bool(stage.get('active_domain_objective_proven') is True and independent.get(name))})
    return summary, discrepancies


def overall_classification(summaries, verification_PASS=True):
    if not verification_PASS or any(s['final_classification'] in ('SCIENTIFIC_IDENTITY_FAIL', 'PHYSICAL_VALIDATION_FAIL') for s in summaries):
        return 'A_STAGE_V2_REJECTED'
    if all(s['final_classification'] == 'STRESS_DATE_FULL_PASS' for s in summaries): return 'A_STAGE_V2_STRESS4_PASS'
    if any(s['A1_full_domain_accepted'] for s in summaries): return 'A_STAGE_V2_STRESS4_PARTIAL_PASS'
    return 'A_STAGE_V2_STRESS4_UNRESOLVED'


def _historical_native_stages(production):
    """Read exact native log geometry; do not confuse it with original replay rows."""
    folder = Path(production)/'stages/2025-05-10/A1/1/output'
    result = read(folder/'A1_SOLVE_RESULT.json', {})
    path = folder/'A1_SOLVE.log'; text = path.read_text(encoding='utf8') if path.exists() else ''
    chunks = re.split(r'(?=Optimize a model with \d+ rows,)', text)[1:]
    stages = {}
    for stage,chunk in zip(result.get('passes', []), chunks):
        geometry = re.search(r'Optimize a model with (\d+) rows, (\d+) columns and (\d+) nonzeros', chunk)
        types = re.search(r'Variable types: (\d+) continuous, (\d+) integer \((\d+) binary\)', chunk)
        root = re.search(r'Root relaxation: objective ([^,]+), (\d+) iterations, ([\d.]+) seconds', chunk)
        values = dict(stage, geometry_source='HISTORICAL_NATIVE_SOLVER_LOG_EXACT_STAGE',
                      root_relaxation_seconds=float(root[3]) if root else None)
        if geometry: values.update(rows=int(geometry[1]), cols=int(geometry[2]), nnz=int(geometry[3]))
        if types: values.update(continuous=int(types[1]), integer_counts=int(types[2])-int(types[3]), binaries=int(types[3]))
        stages[stage['component']] = values
    return stages, folder


def may10_before_after(output, result, production=PRODUCTION):
    historical, source = _historical_native_stages(production)
    passes = _passes(result, output); before = historical.get('shift_magnitude', {})
    after = passes.get('shift_magnitude', {}); geometry = after.get('model_census') or {}
    telemetry = _telemetry(output, 'shift_magnitude'); root = _root_observation(telemetry)
    metrics = {
        'rows':(before.get('rows'), geometry.get('rows')),
        'columns':(before.get('cols'), geometry.get('cols')),
        'integer_count_variables':(before.get('integer_counts'), geometry.get('integer_counts')),
        'binary_variables':(before.get('binaries'), geometry.get('binaries')),
        'nnz':(before.get('nnz'), geometry.get('nnz')),
        'root_relaxation_seconds':(before.get('root_relaxation_seconds'), root['root_relaxation_seconds']),
        'best_valid_active_bound':(before.get('valid_LB'), after.get('active_domain_global_bound')),
        'incumbent':(before.get('valid_UB'), after.get('objective')),
        'native_stage_seconds':(before.get('native_runtime'), after.get('native_seconds')),
        'exact_proof_seconds':(None, after.get('native_seconds') if after.get('active_domain_objective_proven') is True else None),
    }
    values = [dict(metric=metric, historical_value=a, new_actual_value=b, new_minus_historical=subtract(b,a),
                   historical_scope='READ_ONLY_OLD_S0_NATIVE_SHIFT_STAGE',
                   new_scope='CURRENT_V2_NATIVE_ACTIVE_SHIFT_STAGE',
                   availability='OBSERVED_BOTH' if a is not None and b is not None else 'UNAVAILABLE_ONE_OR_BOTH',
                   objective_domain_changed=True, historical_locks_reused=False, missing_values_inferred=False)
              for metric,(a,b) in metrics.items()]
    table(output/'SHIFT_STAGE_BEFORE_AFTER.csv', values)
    old_forensic = read(output/'SHIFT_STAGE_FORENSIC.json', {})
    migration = passes.get('migration_count', {})
    projection = read(output/'shift_magnitude/ACTUAL_ZERO_PROJECTION_PROOF.json')
    projection_summary = {key:value for key,value in projection.items() if key != 'proof'} if projection else None
    old_forensic.update(day='2025-05-10', actual_new_migration_optimum=migration.get('objective'),
                        actual_new_migration_optimum_proven=migration.get('active_domain_objective_proven') is True,
                        migration_zero_projection_used=projection is not None and projection.get('PASS') is True,
                        actual_zero_projection=projection_summary,
                        actual_zero_projection_evidence=record(output/'shift_magnitude/ACTUAL_ZERO_PROJECTION_PROOF.json') if projection else None,
                        historical_locks_reused=False,
                        historical_native_source=[record(p) for p in (source/'A1_SOLVE_RESULT.json', source/'A1_SOLVE.log') if p.exists()],
                        exact_proof_time_definition='Native stage runtime only when current active objective certificate PASS; not full-domain proof.',
                        historical_optimal_proof_time=None,
                        new_shift_stage_observed=bool(after), comparison_records=values, missing_values_inferred=False)
    write(output/'SHIFT_STAGE_FORENSIC.json', old_forensic)


def _complete_required(day, result, output, expected_input, static_census):
    reason = result.get('error', result.get('native_solver_error', result.get('classification', 'NO_RECEIPT')))
    created = []
    for name in REQUIRED_JSON:
        path = output/name
        if path.exists(): continue
        value = unavailable(day, reason, name)
        if name == 'INPUT_IDENTITY.json': value['preregistered_expected_inputs'] = expected_input
        if name == 'DOMAIN_CENSUS.json':
            value['static_scientific_census'] = {key:static_census.get(key) for key in
                ('PASS','day','jobs','classes','class_exact_cardinality','old_S0','new_hard_physical',
                 'counts_unit','hard_valid_STAY_starts','new_candidates_restored_relative_to_old_S0',
                 'migration_lazy_blocks','total_physical_path_multiplicity','domain_sha256')}
            value['static_scientific_census_receipt'] = (expected_input or {}).get('authority_static_census')
            value['native_activation_observed'] = False
        if name == 'A1_RESULT.json': value = result
        if name == 'DOMAIN_CLOSURE_RESULT.json':
            value.update(INTEGER_DOMAIN_CLOSURE_PROVEN=False, PRODUCTION_DOMAIN_ACCEPTED=False,
                         MIGRATION_PRICING_CLOSED=False, root_LP_pricing_is_not_integer_domain_closure=True)
        write(path, value); created.append(name)
    for name,fields in REQUIRED_CSV.items():
        path = output/name
        # An interrupted build may leave an empty file/header: one explicit
        # unavailable row is preferable to silently implying zero observations.
        if path.exists() and rows(path): continue
        table(path, [dict(day=day, stage='UNAVAILABLE', event='UNAVAILABLE', availability='UNAVAILABLE', reason=reason,
                          observational_only=True, missing_values_inferred=False)],
              fields=(*fields, 'availability', 'reason', 'missing_values_inferred'))
        created.append(name)
    if day == '2025-05-12':
        for name in ('ROOT_PHASE_TIMELINE.json', 'ROOT_NUMERICAL_AUDIT.json'):
            if not (output/name).exists():
                write(output/name, dict(unavailable(day, reason, name), passes=[], numerical=[],
                                        historical_root_seconds=3562.46, parameter_sweep=False))
                created.append(name)
    return created


def scheduling_freedom_audit(schedule, census):
    """Describe measured selected choices, without causal/counterfactual claims."""
    anchors = {row['class_id']:row for row in census.get('no_flex_anchor_inclusion', {}).get('records', [])}
    references = {}
    for scientific_class in census.get('candidate_counts_by_class', []):
        anchor = anchors.get(scientific_class['class_id'])
        if anchor:
            for uid in scientific_class.get('members', []):
                references[str(uid)] = (anchor['reference_start'], anchor['reference_site'])
    selected = schedule.get('selected_jobs') or {}
    counts = {}; missing = []; earlier = total_displacement = 0
    for uid,option in selected.items():
        if str(uid) not in references:
            missing.append(str(uid)); continue
        reference_start,reference_site = references[str(uid)]
        shift = option['start'] != reference_start
        relocation = option['initial_site'] != reference_site
        migration = option.get('checkpoint', -1) >= 0
        labels = [label for yes,label in ((shift,'TIMESHIFT'),(relocation,'PRESTART_RELOCATION'),(migration,'MIGRATION')) if yes]
        label = '+'.join(labels) if labels else 'UNCHANGED_REFERENCE'
        counts[label] = counts.get(label, 0)+1
        earlier += int(option['start'] < reference_start)
        total_displacement += abs(option['start']-reference_start)
    return dict(PASS=bool(selected) and not missing, selected_jobs=len(selected),
                choices_by_freedom_combination=counts, earlier_than_reference_jobs=earlier,
                total_shift_slots=total_displacement, missing_reference_job_ids=missing,
                historical_objective_locks_used=False, counterfactual_causality_proven=False,
                scope='Measured choices of independently replayed current active-domain feasible schedule only.')


def _record_objects(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str): yield value
        for child in value.values(): yield from _record_objects(child)
    elif isinstance(value, list):
        for child in value: yield from _record_objects(child)


def verify_external_artifacts(out, root=ROOT, external_static=EXTERNAL_STATIC):
    """Verify expected input/model byte hashes where an execution receipt exists."""
    root, out = Path(root), Path(out); expected = {}; conflicts = []
    # Historical producer/module hashes document the earlier executed source,
    # not a claim that the final source stayed byte-identical. Only frozen input
    # and external scientific matrices/interfaces belong in this check.
    for path in sorted(out.rglob('*.json')):
        if path.name in ('SHA256_MANIFEST.json', 'VERIFICATION.json', 'EXTERNAL_ARTIFACT_VERIFICATION.json'): continue
        for item in _record_objects(read(path, {})):
            target = Path(item['path'])
            if not target.is_absolute(): continue
            if target.suffix.lower() not in ('.npz', '.pkl', '.gz') and target.name != 'NATIVE_INPUT.json': continue
            if root.resolve() in target.resolve().parents: continue
            key = str(target.resolve())
            if key in expected and expected[key]['sha256'] != item['sha256']:
                conflicts.append(dict(path=key, first=expected[key], conflicting=item))
            expected[key] = dict(item, expected_receipt=str(path.relative_to(root)) if path.is_relative_to(root) else str(path))
    observed = []
    targets = set(expected)
    for day in DAYS:
        for name in ('V2_ACTIVE_ORIGINAL_MATRIX.npz', 'V2_ACTIVE_ORIGINAL_ATTRIBUTES.npz', 'SCIENTIFIC_INTERFACES.pkl.gz'):
            path = Path(external_static)/day/name
            if path.exists(): targets.add(str(path.resolve()))
    for target in sorted(targets):
        path = Path(target); wanted = expected.get(target)
        actual = record(path, root) if path.exists() else None
        status = ('UNAVAILABLE' if actual is None else 'HASH_RECORDED_ONLY_UNATTESTED' if wanted is None
                  else 'PASS' if actual['sha256'] == wanted['sha256'] and actual['bytes'] == wanted.get('bytes', actual['bytes'])
                  else 'HASH_MISMATCH')
        observed.append(dict(path=target, status=status, expected=wanted, actual=actual,
                             execution_identity_verified=status == 'PASS'))
    return dict(PASS=not conflicts and all(r['status'] not in ('UNAVAILABLE', 'HASH_MISMATCH') for r in observed),
                all_present_external_artifacts_attested=all(r['status'] == 'PASS' for r in observed),
                no_matrix_or_pickle_loaded=True, files=observed, conflicting_expected_hashes=conflicts)


def verify_execution_freeze(out, root=ROOT):
    """Recheck real permit sources/gates without invoking execution APIs."""
    out, root = Path(out), Path(root)
    permits = []
    for path in sorted(out.glob('*.json')):
        document = read(path, {})
        if isinstance(document, dict) and document.get('schema') == 'A_STAGE_V2_STRESS4_VERIFIED_PERMIT_V1':
            permits.append((path, document))
    sources = {}; gate_checks = []; failures = []
    for permit_path,document in permits:
        if document.get('run_order') != list(DAYS) or document.get('other_27_dates_authorized') is not False:
            failures.append('PERMIT_FOUR_DATE_AUTHORITY_MISMATCH:'+permit_path.name)
        if document.get('actual_reoptimization_authorized') is not False:
            failures.append('PERMIT_ACTUAL_REOPTIMIZATION_AUTHORITY_MISMATCH:'+permit_path.name)
        if set(document.get('gate_receipts', {})) != REQUIRED_STRESS_GATES:
            failures.append('PERMIT_TWELVE_DISTINCT_GATES_REQUIRED:'+permit_path.name)
        if len({item.get('path') for item in document.get('gate_receipts', {}).values()}) != 12:
            failures.append('PERMIT_TWELVE_DISTINCT_GATE_PATHS_REQUIRED:'+permit_path.name)
        required_sources = {str((root/'v42_a_stage_domain_v2'/name).resolve()) for name in REQUIRED_RUN_SOURCE_NAMES}
        if not required_sources <= {str(Path(label).resolve()) for label in document.get('execution_sources', {})}:
            failures.append('PERMIT_EXECUTION_GUARD_SOURCES_REQUIRED:'+permit_path.name)
        for key,expected in document.get('gate_receipts', {}).items():
            path = Path(expected['path']); path = path if path.is_absolute() else root/path
            actual = record(path, root) if path.exists() else None
            receipt = read(path, {}) if actual else {}
            passed = actual is not None and actual['sha256'] == expected['sha256'] and receipt.get('PASS') is True
            gate_checks.append(dict(gate=key, permit=record(permit_path, root), expected=expected,
                                   actual=actual, current_PASS=passed))
            if not passed: failures.append('FROZEN_GATE_DRIFT_OR_NOT_PASS:'+key)
        for label,sha in document.get('execution_sources', {}).items():
            path = Path(label); path = path if path.is_absolute() else root/path
            actual = record(path, root) if path.exists() else None
            passed = actual is not None and actual['sha256'] == sha
            key = str(path.resolve())
            if key in sources and sources[key]['expected_sha256'] != sha:
                failures.append('CONFLICTING_EXECUTION_SOURCE_FREEZE:'+label)
            sources[key] = dict(expected_sha256=sha, actual=actual, current_PASS=passed)
            if not passed: failures.append('FROZEN_EXECUTION_SOURCE_DRIFT:'+label)
    attempted = any((out/('MAY'+day[-2:])/'A1_STARTED.json').exists() for day in DAYS)
    if attempted and not permits: failures.append('ATTEMPTED_RUN_WITHOUT_PERSISTED_PERMIT_RECEIPT')
    return dict(PASS=not failures, availability='OBSERVED' if permits else 'UNAVAILABLE',
                permits=[record(path, root) for path,_ in permits], attempted_run_observed=attempted,
                source_checks=sources, gate_checks=gate_checks, failures=failures,
                optimize_or_execution_api_called=False)


QUESTIONS = (
    '최종 구현의 정확한 base는?', '최종 A-stage Domain Authority V2는?',
    '기존 reference-lower prescreen을 과학적 컷에서 제거했는가?', 'complete STAY 지원은 정확하고 활성화됐는가?',
    '공통 권한에서 no-flex가 flex에 포함되는가?', '후보·변수·행은 얼마나 줄거나 늘었는가?',
    'exact migration equivalence aggregation을 채택했는가?', '남은 lazy migration universe 크기는?',
    'Solver Policy V2의 정확한 설정은?', 'parameter sweep을 했는가?', 'May17은 feasible인가?',
    'May17이 기존 35-option rescue를 재현하거나 넘었는가?', 'May19는 feasible인가?',
    'May19가 feasible이면 어떤 스케줄 자유도가 해결했는가?', 'CC4를 변경했는가?',
    'May12 root가 완료됐는가?', 'May12 root 시간은 기존 3562.46초 대비 어떤가?', 'May12 P1 결과는?',
    'May10 rho 결과는?', 'May10 migration-count 결과는?', 'May10 migration_count*=0인가?',
    '그렇다면 exact no-migration projection이 shift stage를 얼마나 줄였는가?',
    'May10 shift incumbent는?', 'May10 shift의 유효 bound는?', 'May10 shift exact optimum이 증명됐는가?',
    'May10 prestart 결과는?', '어느 날짜에서 integer-domain closure를 얻었는가?',
    '어느 날짜가 A1_FULL_DOMAIN_ACCEPTED인가?', '어느 날짜가 Planning/Actual/Fresh를 완료했는가?',
    '물리적 위반은?', 'future information을 사용했는가?', 'Actual reoptimization을 했는가?',
    'PQ repair를 했는가?', '다른 27개 May 날짜를 다시 실행했는가?', '원래 네 문제 중 무엇을 해결했는가?',
    '무엇이 미해결이고 이유는?', '최종 commit SHA는?', 'Draft PR URL은?',
)


def _display(value):
    if value is None: return '관측 불가'
    if isinstance(value, bool): return '예' if value else '아니오'
    return str(value)


def _stage_sentence(summary, name):
    return (f"status={_display(summary.get(name+'_status'))}, value={_display(summary.get(name+'_value'))}, "
            f"active bound={_display(summary.get(name+'_bound'))}, gap={_display(summary.get(name+'_gap'))}, "
            f"native time={_display(summary.get(name+'_time_seconds'))}초, "
            f"활성 도메인 목적 증명={_display(summary.get(name+'_active_optimum_proven'))}. 전체 도메인 최적성은 별도 closure 판단입니다.")


def review_ko(summaries, results, out, source_commit, pr_url, observed_head, overall, authority_docs=AUTHORITY_DOCS):
    byday = {s['date']:s for s in summaries}; short = {s['date'][-2:]:s for s in summaries}
    complete = read(out/'COMPLETE_STAY_VERIFICATION.json', {})
    source_identity = read(out/'STATIC_SOURCE_DATA_IDENTITY.json', {})
    authority = read(out/'A_STAGE_DOMAIN_AUTHORITY_V2_REFERENCE.json', {})
    policy = read(out/'A_STAGE_SOLVER_POLICY_V2.json', {})
    nesting = read(Path(authority_docs)/'DOMAIN_NESTING_VERIFICATION.json', {})
    membership = read(Path(authority_docs)/'MAY17_RESCUE_OPTION_MEMBERSHIP.json', {})
    migration_audit = read(out/'MIGRATION_EQUIVALENCE_AUDIT.json', {})
    verified = [s['date'] for s in summaries if s['integer_domain_closure_proven']]
    accepted = [s['date'] for s in summaries if s['A1_full_domain_accepted']]
    pipeline = [s['date'] for s in summaries if s['Planning_freeze'] and s['Actual'] and s['Fresh_OpenDSS']]
    telemetry12 = _telemetry(out/'MAY12', 'rho'); root12 = _root_observation(telemetry12)
    beforeafter = rows(out/'MAY10/SHIFT_STAGE_BEFORE_AFTER.csv')
    forensic = read(out/'MAY10/SHIFT_STAGE_FORENSIC.json', {})
    actual_migration_zero = short['10']['migration_count_active_optimum_proven'] and short['10']['migration_count_value'] == 0
    signatures = source_identity.get('dates', {})
    unchanged = source_identity.get('PASS') is True and all(v.get('hard_limits_service_Runtime_CC4_GPU_grid_unchanged') is True for v in signatures.values())
    future_zero = source_identity.get('PASS') is True and bool(signatures) and all(v.get('future_information_reads') == 0 for v in signatures.values())
    counts = '; '.join(f"May{s['date'][-2:]} STAY 복원 {_display(s['restored_STAY_support'])}, 활성 migration {_display(s['active_migration_support'])}" for s in summaries)
    lazy = '; '.join(f"May{s['date'][-2:]} {_display(s['remaining_lazy_migration_support'])}" for s in summaries)
    # A feasible schedule is diagnostic evidence, not a counterfactual causal
    # attribution. Describe only measured changes in the selected new schedule.
    schedule19 = read(out/'MAY19/ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json', {})
    freedom = read(out/'MAY19/SCHEDULING_FREEDOM_AUDIT.json', schedule19.get('scheduling_freedom_audit'))
    answers = [
        f"구현 base PR166 {BASE}. 과학적 원형 PR134 52ef855a59144a7c561df44b81dc2ad265babdbd. 실행 소스 고정은 PRE_RUN_TESTS/permit receipt로 구분합니다.",
        f"AIDC_A_STAGE_DOMAIN_AUTHORITY_V2. 참조 영수증 존재={bool(authority)}; complete STAY와 원래 migration 물리를 유지하고 정수 closure 전에는 production 승인을 막습니다.",
        '예. R0/reference는 P2 이동 기준과 no-action anchor이며 독립적 causal release를 대체하는 시작 하한이 아닙니다.',
        f"독립 complete STAY 검증 PASS={_display(complete.get('PASS'))}, 모든 scope 물리 지원={_display(complete.get('all_scopes_complete_physical_stay_support'))}. 검증된 기존 class histogram을 유지하고 singleton mixed는 원래 event-flow를 보존합니다. native 활성화는 날짜별 STAY_DOMAIN_COMPLETE와 실제 build receipt를 보십시오.",
        f"공통 권한 nesting 정적 검증 PASS={_display(nesting.get('PASS'))}. no-flex 자체의 전역 feasibility는 이 주장에 포함되지 않습니다.",
        counts+'. PRE_RUN_MODEL_CENSUS는 구조적 변수 수/추정 행·nnz, MODEL_CENSUS_BY_LEX_STAGE는 실제 생성 수입니다. May10 변화는 SHIFT_STAGE_BEFORE_AFTER.csv에 null과 함께 구분했습니다.',
        f"다른 과학 열을 가격만으로 합치지 않았습니다. canonical 후보 제거={_display(migration_audit.get('canonical_pool_semantic_candidate_removals'))}; 전체 scientific signature의 단사성 감사 PASS={_display(migration_audit.get('PASS'))}.",
        lazy+'. full path multiplicity를 lossless lazy pool에 유지합니다. 정적 lazy 크기를 pricing/정수 closure로 해석하지 않습니다.',
        '고정 정책: '+json.dumps(policy.get('parameters', policy), ensure_ascii=False, sort_keys=True)+'. 실제 SOLVER_PARAMETERS와 pass telemetry를 함께 기록했습니다.',
        '아니오. 한 정책만 preregister하며 날짜별 튜닝과 재시도 tournament를 허용하지 않습니다.',
        f"May17 독립 새 해 replay에 따른 활성 도메인 feasible={_display(short['17']['A1_active_domain_feasible'])}, 전체 승인={_display(short['17']['A1_full_domain_accepted'])}.",
        f"기존 35개 Option의 원래 과학 속성 포함 membership={_display(membership.get('MAY17_35_RESCUE_OPTIONS_INCLUDED'))}. 새 solve 활성 feasibility={_display(short['17']['A1_active_domain_feasible'])}; 정적 포함만으로 rescue 재현/초과 성능을 주장하지 않습니다.",
        f"May19 독립 새 해 replay에 따른 활성 도메인 feasible={_display(short['19']['A1_active_domain_feasible'])}, 전체 승인={_display(short['19']['A1_full_domain_accepted'])}.",
        ('관측된 선택 자유도: '+json.dumps(freedom, ensure_ascii=False) if freedom else '새 feasible point가 없어 어떤 자유도가 해결했다고 주장하지 않습니다.')+' 선택 조합은 관측이며 counterfactual 원인 귀속은 미증명입니다. CC4/전압 원인도 closure 없이 단정하지 않습니다.',
        f"아니오. 정적 frozen identity에서 CC4/Runtime/service/GPU/grid hard limit 불변 검증={_display(unchanged)}. 실행 identity 미관측은 별도로 표기합니다.",
        f"May12 실제 root 완료 관측={_display(root12['root_completed']) if telemetry12 else '관측 불가'}. "+('MAY12_ROOT_STILL_UNRESOLVED.' if short['12']['final_classification']=='ROOT_LP_TIMEOUT' else short['12']['final_classification']+'.'),
        f"기존 root dual simplex 3562.46초. 새 root relaxation 시간={_display(root12['root_relaxation_seconds'])}초, root 완료 관측 native 시간={_display(root12['root_completion_native_seconds'])}초. 관측 지표와 root phase duration을 혼동하지 않습니다.",
        _stage_sentence(short['12'], 'rho'), _stage_sentence(short['10'], 'rho'),
        _stage_sentence(short['10'], 'migration_count'),
        f"{_display(actual_migration_zero)}. 새 migration value={_display(short['10']['migration_count_value'])}, 활성 목적 증명={_display(short['10']['migration_count_active_optimum_proven'])}. 미관측/미증명은 zero로 가정하지 않습니다.",
        ('새 migration zero가 증명되어 projection 영수증: '+json.dumps(forensic.get('actual_zero_projection'), ensure_ascii=False)
         if actual_migration_zero else '새 zero optimum이 증명되지 않아 no-migration projection 축소를 가정할 수 없습니다.')+' 실제 stage 전후 수치는 SHIFT_STAGE_BEFORE_AFTER.csv에 있습니다.',
        f"{_display(short['10']['shift_magnitude_value'])}. 새 독립 replay 및 원래 rows 검증 없이는 유효한 incumbent로 승인하지 않습니다.",
        f"현재 native 활성 domain bound={_display(short['10']['shift_magnitude_bound'])}. 누락 migration 전체-domain bound로 전환하지 않습니다.",
        f"활성 도메인 shift exact proof={_display(short['10']['shift_magnitude_active_optimum_proven'])}; 전체-domain closure={_display(short['10']['integer_domain_closure_proven'])}.",
        _stage_sentence(short['10'], 'prestart_relocation'),
        ', '.join(verified) or '없음. root LP 가격 closure만으로 integer-domain closure를 인정하지 않습니다.',
        ', '.join(accepted) or '없음. 활성-domain feasibility/lex proof와 전체-domain 승인을 구분했습니다.',
        ', '.join(pipeline) or '없음. A1 전체 승인 후에만 Planning freeze, 고정 Actual, Fresh OpenDSS를 진행할 수 있습니다.',
        '새 independent replay의 물리 검증과 Fresh 이후 최종 물리 검증은 별도입니다. Fresh 최종 PASS 날짜: '+(', '.join(s['date'] for s in summaries if s['physical_PASS']) or '없음')+'. 미관측을 무위반 PASS로 해석하지 않습니다.',
        f"아니오. frozen issue-time 인과 입력 감사={_display(future_zero)}. after-issue 실제 outcome을 도메인 생성에 사용하지 않습니다.",
        '아니오. '+('; '.join(f"May{day[-2:]} 기록={_display(results[day].get('Actual_reoptimization'))}" for day in DAYS))+'. 실행되지 않은 Actual은 승인되지 않습니다.',
        '아니오. '+('; '.join(f"May{day[-2:]} 기록={_display(results[day].get('PQ_repair'))}" for day in DAYS))+'. 숨은 repair를 승인하지 않습니다.',
        '아니오. '+('; '.join(f"May{day[-2:]} 다른 날짜 실행 기록={_display(results[day].get('other_27_dates_run'))}" for day in DAYS))+'. 실행 permit은 네 날짜로 한정됩니다.',
        '실제 전체 생산 PASS로 해결된 날짜: '+(', '.join(s['date'] for s in summaries if s['physical_PASS']) or '없음')+'. 후보벽 제거/정적 membership PASS는 계산 timeout 또는 전체 생산 성공의 증거를 대신하지 않습니다.',
        '; '.join(f"May{s['date'][-2:]} {s['final_classification']}, 원인={s.get('error') or results[s['date']].get('domain_status', {}).get('closure_limitation', '해당 objective/closure/pipeline 미증명; 실제 receipt 참조')}" for s in summaries if not s['physical_PASS']),
        f"보고서 생성의 구현 commit={source_commit or '미지정'}, 당시 관측 HEAD={observed_head or '관측 불가'}. 이 보고서를 포함하는 최종 evidence commit은 자기 참조가 불가능하므로 게시 후 git rev-parse HEAD/PR head와 외부 publication receipt로 확인합니다.",
        pr_url or '미게시. Draft PR 생성/갱신 후 외부 publication receipt와 사용자 최종 응답에 URL을 기록합니다.',
    ]
    assert len(answers) == len(QUESTIONS) == 38
    lines = ['# A-stage V2 네 날짜 최종 stress 검토', '', f'전체 분류: **{overall}**.', '',
             '표의 null/빈칸은 관측 불가입니다. TIME_LIMIT은 infeasible이 아니며 활성 도메인 최적성은 전체 정수 도메인 최적성이 아닙니다.', '']
    for number,(question,answer) in enumerate(zip(QUESTIONS, answers), 1):
        lines.extend([f'{number}. **{question}** {answer}', ''])
    lines.extend(['| 날짜 | 활성 feasible | 활성 4목적 증명 | 정수 closure | 전체 A1 승인 | Fresh 물리 PASS | 최종 분류 |',
                  '|---|---|---|---|---|---|---|'])
    for s in summaries:
        lines.append('| '+s['date']+' | '+' | '.join(_display(s[k]) for k in
                     ('A1_active_domain_feasible','ACTIVE_DOMAIN_SOLVED','integer_domain_closure_proven','A1_full_domain_accepted','physical_PASS','final_classification'))+' |')
    (out/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines)+'\n', encoding='utf8', newline='\n')


def finalize(source_commit=None, pr_url=None, *, out=OUT, root=ROOT,
             authority_docs=AUTHORITY_DOCS, production=PRODUCTION, external_static=EXTERNAL_STATIC,
             check_git=True):
    """Aggregate finished receipts. No optimizer, subprocess worker or native import.

    Optional directory arguments support independent temporary-fixture tests.
    The normal CLI always verifies historical evidence against the exact base.
    """
    root, out, authority_docs = Path(root), Path(out), Path(authority_docs)
    out.mkdir(parents=True, exist_ok=True)
    runner_results = read(out/'STRESS4_RESULTS.json', [])
    root_results = {r['day']:r for r in runner_results}
    forecasts = {r['day']:r for r in rows(out/'PRE_RUN_MODEL_CENSUS.csv')}
    expected_inputs = read(out/'STATIC_SOURCE_DATA_IDENTITY.json', {}).get('dates', {})
    results = {}; summaries = []; discrepancies = {}; placeholders = {}; stopped_by = None
    for day in DAYS:
        output = out/('MAY'+day[-2:]); output.mkdir(exist_ok=True)
        result = read(output/'A1_RESULT.json', root_results.get(day))
        if result is None:
            classification = 'NOT_ATTEMPTED_GLOBAL_SCIENTIFIC_STOP' if stopped_by else 'NOT_ATTEMPTED_NO_RUN_RECEIPT'
            result = dict(unavailable(day, classification, 'A1_RESULT.json'), classification=classification,
                          passes=[], global_scientific_stop=False, stopped_by=stopped_by,
                          A1_full_domain_accepted=False, integer_domain_closure_proven=False)
        results[day] = result
        census = read(output/'DOMAIN_CENSUS.json', {})
        static_census = read(authority_docs/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json'), {})
        if not census or census.get('availability') == 'UNAVAILABLE': census = static_census
        placeholders[day] = _complete_required(day, result, output, expected_inputs.get(day), static_census)
        summary, errors = summarize_date(day, result, output, census, forecasts.get(day))
        summaries.append(summary); discrepancies[day] = errors
        if summary['A1_active_domain_feasible']:
            schedule = read(output/'ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json')
            if schedule:
                audit = scheduling_freedom_audit(schedule, static_census)
                audit.update(day=day, schedule_receipt=record(output/'ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json', root))
                write(output/'SCHEDULING_FREEDOM_AUDIT.json', audit)
        if result.get('global_scientific_stop') or errors: stopped_by = day
    may10_before_after(out/'MAY10', results['2025-05-10'], production)
    # Accepted dates need all downstream files, even if the pipeline has not
    # reached them. Placeholders are unavailable, not fabricated successful runs.
    for s in summaries:
        if s['A1_full_domain_accepted']:
            folder = out/('MAY'+s['date'][-2:])
            for name in PIPELINE:
                if not (folder/name).exists(): write(folder/name, unavailable(s['date'], 'A1_ACCEPTED_DOWNSTREAM_NOT_COMPLETED', name))
    changed = historical_changes(root) if check_git else []
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() if check_git else None
    external = verify_external_artifacts(out, root, external_static)
    write(out/'EXTERNAL_ARTIFACT_VERIFICATION.json', external)
    freeze = verify_execution_freeze(out, root)
    write(out/'EXECUTION_FREEZE_VERIFICATION.json', freeze)
    prohibited = {day:{name:result.get(name) for name in ('Actual_reoptimization','PQ_repair','other_27_dates_run')
                       if result.get(name) is True or (finite(result.get(name)) is not None and finite(result[name]) != 0)}
                  for day,result in results.items()}
    prohibited = {day:value for day,value in prohibited.items() if value}
    required_present = all((out/('MAY'+day[-2:])/name).exists() for day in DAYS for name in (*REQUIRED_JSON, *REQUIRED_CSV))
    verification_PASS = (not changed and not any(discrepancies.values()) and not prohibited
                         and external['PASS'] and freeze['PASS'] and required_present)
    overall = overall_classification(summaries, verification_PASS)
    table(out/'STRESS4_SUMMARY.csv', summaries)
    verification = dict(PASS=verification_PASS, scope='RECEIPT_AND_REPOSITORY_INTEGRITY; NOT_PRODUCTION_SUCCESS',
                        overall_classification=overall, date_classifications={s['date']:s['final_classification'] for s in summaries},
                        missing_values_inferred=False, aggregation_native_builds=0, aggregation_optimize_calls=0,
                        exact_base=BASE, historical_directories=list(HISTORICAL), historical_changes=changed,
                        historical_check_executed=check_git, receipt_discrepancies=discrepancies,
                        unavailable_artifacts_created=placeholders, all_date_required_artifacts_present=required_present,
                        external_byte_verification_PASS=external['PASS'],
                        all_present_external_artifacts_attested=external['all_present_external_artifacts_attested'],
                        frozen_execution_sources_and_gates_PASS=freeze['PASS'],
                        frozen_permit_receipt_availability=freeze['availability'], prohibited_activity_findings=prohibited,
                        full_domain_acceptance_requires_explicit_integer_closure=True,
                        root_LP_pricing_is_integer_closure=False, source_commit=source_commit,
                        observed_git_HEAD_at_report_generation=head, Draft_PR=pr_url,
                        final_evidence_commit='Recorded externally after committing these bytes; self-referential tracked commit SHA impossible.')
    write(out/'VERIFICATION.json', verification)
    review_ko(summaries, results, out, source_commit, pr_url, head, overall, authority_docs)
    files = [record(path, root) for path in sorted(out.rglob('*')) if path.is_file() and path.name != 'SHA256_MANIFEST.json']
    files += [record(path, root) for path in sorted((root/'v42_a_stage_domain_v2').glob('*.py'))]
    files += [record(path, root) for path in sorted((root/'tests').glob('test_v42_a_stage*.py'))]
    files += [value['actual'] for value in freeze['source_checks'].values() if value['actual'] is not None]
    if check_git:
        changed_source = subprocess.check_output(['git','diff','--name-only',BASE,'--','*.py'],cwd=root,text=True).splitlines()
        changed_source += subprocess.check_output(['git','ls-files','--others','--exclude-standard','--','*.py'],cwd=root,text=True).splitlines()
        files += [record(root/path,root) for path in sorted(set(changed_source)) if (root/path).is_file()]
    files = list({item['path']:item for item in files}.values())
    write(out/'SHA256_MANIFEST.json', dict(algorithm='SHA256', self_excluded=True, files=files,
                                         external_files=[value['actual'] for value in external['files'] if value['actual'] is not None],
                                         source_commit=source_commit, observed_git_HEAD_at_report_generation=head,
                                         post_publication_HEAD='External publication receipt and git/PR head; not a self-reference.'))
    # Check every hashed byte again after all writes. The manifest is excluded
    # from itself; this verification is returned so no circular hash is created.
    byte_PASS = all(record(root/item['path'] if not Path(item['path']).is_absolute() else item['path'], root)['sha256'] == item['sha256'] for item in files)
    if not byte_PASS: raise ValueError('STRESS_REPORT_MANIFEST_BYTES_CHANGED_DURING_FINALIZATION')
    return dict(verification, manifest_byte_verification_PASS=byte_PASS, manifest_files=len(files))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--source-commit'); parser.add_argument('--pr-url')
    arguments = parser.parse_args()
    print(json.dumps(finalize(arguments.source_commit, arguments.pr_url), ensure_ascii=False, indent=2))
