"""Read-only authority audit. An empty eligible population never means epsilon=0.

This revision stops at the user's Section 3 boundary. It does not call an
optimizer, import Actual execution, or change any V41 scientific implementation.
"""
from datetime import date, datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import subprocess

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT.parent / 'MobileESS_v41_final_ml_interface_may_campaign'
UPSTREAM = ROOT.parent / 'MobileESS_v40a_bounded_iterative_coopt'
OUT = ROOT / 'dayahead/artifacts/v41r1_premay_voltage_security_margin'
DISCOVERY = ROOT / 'frozen_artifacts/v41r1_premay_voltage_security_margin/discovery'
BASE = '110035d6c1999adf590e36c6ff16dc80cc46369b'
STOP = 'V41R1_PREMAY_VOLTAGE_MARGIN_AUTHORITY_INSUFFICIENT'
CUTOFF = date(2025, 5, 1)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ref(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    path.write_text(text, encoding='utf-8')
    assert read(path) == value
    return ref(path)


def require_premay(day):
    parsed = date.fromisoformat(day)
    if not parsed < CUTOFF:
        raise ValueError('MAY_OR_LATER_SOURCE_FORBIDDEN')
    return parsed


def dated_path(path):
    days = re.findall(r'2025[-_]?(\d{2})[-_]?(\d{2})', str(path))
    if not days:
        raise ValueError('UNDATED_NUMERICAL_SOURCE_FORBIDDEN')
    for month, day in days:
        require_premay(f'2025-{month}-{day}')


def cannot_freeze(eligible):
    if not eligible:
        raise ValueError(STOP)
    raise ValueError('NONEMPTY_POPULATION_REQUIRES_SEPARATE_VERIFIED_PAIRING_REVIEW')


def old_files():
    files = set()
    for relative in ('frozen_artifacts/v41_may_campaign/pilot/2025-05-01',
                     'frozen_artifacts/v41_may_campaign/2025-05-01'):
        directory = OLD / relative
        if not directory.is_dir():
            raise ValueError('MISSING_OLD_MAY01_DIRECTORY:' + relative)
        files.update(p for p in directory.rglob('*') if p.is_file())
    for p in (OLD / 'dayahead/artifacts/v41_final_ml_interface_may_campaign').rglob('*'):
        if p.is_file() and re.search(r'MAY01|MAY_01|2025-05-01', str(p), re.I):
            files.add(p)
    return {str(p): ref(p) for p in sorted(files)}


def prepare():
    preserved = OUT / 'V41_EXPOSED_PRE_MARGIN_PILOT_PRESERVATION.json'
    if not preserved.exists():
        write(preserved.name, dict(classification='V41_EXPOSED_PRE_MARGIN_PILOT',
            additive_classification_only=True, old_artifacts_modified=False,
            files=old_files(), captured_at=datetime.now(timezone.utc).isoformat()))
    sources = ('dayahead/v40a/grid.py', 'dayahead/grid_lp.py', 'dayahead/v40e/electrical.py',
        'dayahead/v40e/mapping.py', 'dayahead/v40g/optimizer.py', 'dayahead/v40h/feedback.py',
        'dayahead/v40h/recourse.py', 'dayahead/v40h/mobility.py', 'dayahead/v40h/beam_driver.py',
        'dayahead/v35r3/algorithm.py', 'dayahead/v34/integrated_mess.py', 'dayahead/v34/correction.py',
        'dayahead/v28r2/electrical_subproblem.py', 'dayahead/v41/grid_archive.py',
        'dayahead/v41/execution.py', 'dayahead/v41/electrical.py', 'dayahead/v41/actual_dispatch.py',
        'dayahead/v41/objectives.py', 'dayahead/v41/scalars.py', 'dayahead/v41/snapshot.py')
    write('V41R1_PLANNING_VOLTAGE_AUTHORITY_AUDIT.json', dict(
        identified_before_any_margin_computation=True, margin_computations=0,
        PLANNING_VOLTAGE_QUANTITY='sqrt(voltage_constant + voltage_matrix.T @ frozen_controls)',
        PLANNING_VOLTAGE_SOURCE='V41 corrected V40E/V40I affine voltage-squared coefficients; grid_archive.planning PLANNING_BUS_PHASES.parquet',
        ACTUAL_VOLTAGE_SOURCE='Authoritative realized three-phase OpenDSS voltage_pu array; V41 grid_archive.persist BUS_PHASE_VOLTAGES.parquet, stage=Actual',
        CUT_IMPLEMENTATION_PATH='v40a.grid.add_grid: v_squared variable upper bound; M1 v35r3.algorithm and v34.integrated_mess use v34.correction.bind_squared_voltage_bounds for the same affine quantity',
        UNIT='pu', Fresh_is_not_the_planning_authority=True,
        existing_upper_squared=1.05**2, existing_lower_squared=.95**2,
        legitimate_future_tightening='Existing squared upper bound would be (1.05 - EPSILON_V_UP)**2 after eligible pre-May authority and freeze; not implemented at this stop boundary',
        stage_ownership=dict(B0='Fixed reference, grid.evaluate_grid feasibility gate',
            A0_B1='v40g.optimizer -> v40a.grid.add_grid',
            A1_B3='v40h.feedback.solve_feedback -> v40a.grid.add_grid',
            MF_B3='v40h.recourse.solve_fixed_route -> v40a.grid.add_grid',
            M1_B2_B3='v40h.mobility -> beam_driver -> v35r3.algorithm restricted/full voltage constraints / v34.integrated_mess',
            Fresh_Actual='Measured verification, physical limits unchanged; no new optimization authority'),
        source_files=[ref(ROOT / p) for p in sources], base_implementation_commit=BASE))


def run():
    prepare()
    inventories = [read(p) for p in sorted(DISCOVERY.glob('*_complete_inventory.json'))]
    assert len(inventories) == 3
    assert all(x['returncode'] == 0 and not x['errors'] and x['includes_gitignored'] for x in inventories)
    # Discovery lists names only, including ignored result directories. No May
    # result body is opened while finding explicitly dated pre-May candidates.
    candidates = []
    for inventory in inventories:
        for raw in inventory['all_paths']:
            normalized = raw.replace('\\', '/')
            if 'v41r1_premay_voltage_security_margin' in normalized:
                continue
            if '/actual/' not in normalized.lower() or not normalized.endswith('OPENDSS_PHASE_ARRAYS.npz'):
                continue
            try:
                dated_path(normalized)
            except ValueError:
                continue
            candidates.append(Path(normalized))
    if not candidates:
        raise ValueError('DISCOVERY_INCOMPLETE_EXPECTED_HISTORICAL_ACTUAL_FILES')
    rows = []
    old_mapper = 'dayahead/v28r2/opendss_mapping.py'
    corrected_sha = sha(ROOT / 'dayahead/v40e/mapping.py')
    for path in sorted(set(candidates)):
        manifest_path = path.with_name('OPENDSS_OUTPUT_MANIFEST.json')
        manifest = read(manifest_path)
        require_premay(manifest['day'])
        assert manifest['namespace'] == 'ACTUAL'
        assert manifest['day'] in path.as_posix()
        assert sha(path) == manifest['files'][path.name]['sha256']
        repo = Path(path.as_posix().split('/frozen_artifacts/')[0])
        family = path.as_posix().split('/frozen_artifacts/')[1].split('/')[0]
        code_path = path.parents[3] / 'run_authority/CODE_TREE_MANIFEST.json'
        old_source = ref(repo / old_mapper)
        code = read(code_path) if code_path.exists() else None
        producer_hash = code['files'].get(old_mapper) if code else None
        if producer_hash is not None:
            assert producer_hash == old_source['sha256']
        # A legacy file hash is never promoted to a corrected production proof.
        rows.append(dict(source_revision=family, day=manifest['day'], policy=manifest['case'],
            bus=None, phase=None, slot=None, planning_voltage=None, Actual_voltage=None,
            numerical_pairing_performed=False, actual_source=ref(path), manifest=ref(manifest_path),
            source_SHA256=sha(path), historical_mapper=old_source,
            producer_recorded_mapper_SHA256=producer_hash,
            producer_code_manifest=ref(code_path) if code else None,
            corrected_mapper_SHA256=corrected_sha,
            compatibility_status='REJECTED',
            reasons=['KNOWN_LEGACY_DUPLICATED_MAPPER' if producer_hash else 'NO_CORRECTED_MAPPER_GENERATION_ATTESTATION',
                     'NOT_CURRENT_CORRECTED_PLANNING_AUTHORITY'],
            topology_ratings_exact_pair_status='NOT_ADMITTED_MAPPER_PRECONDITION_FAILED',
            source_values_not_extracted_after_rejection=True))
    write('V41R1_HISTORICAL_ACTUAL_CANDIDATE_ROWS.json', dict(rows=rows))
    april = UPSTREAM / 'dayahead/artifacts/v40e_background_mapping_fix/april_joint_authority'
    authority_path = april / 'V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json'
    authority = read(authority_path)
    assert authority['mapper_SHA'] == corrected_sha
    states_path = april / 'FROZEN_CALIBRATION_STATES.parquet'
    sensitivity_path = april / 'V40E_CORRECTED_APRIL_FULL_BUS_PHASE_SENSITIVITY.parquet'
    states = pd.read_parquet(states_path)
    # Only identifying columns/schema are read. Fresh/Planning voltage values
    # must not be substituted for realized Actual.
    import pyarrow.parquet as pq
    fields = pq.read_schema(sensitivity_path).names
    days = sorted(states.day.unique().tolist())
    assert days == authority['calibration_days']
    for day in days:
        require_premay(day)
    assert not any('actual' in column.lower() for column in fields)
    april_rejection = dict(source_revision='V40E_CORRECTED_APRIL_JOINT_AUTHORITY',
        days=days, policy_labels=sorted(states['case'].unique().tolist()), state_rows=len(states),
        sensitivity_rows=pq.read_metadata(sensitivity_path).num_rows, sensitivity_schema=fields,
        corrected_mapper_match=True, compatibility_status='REJECTED_NO_REALIZED_ACTUAL',
        reason='Frozen April Fresh calibration/probe states and derivatives, not paired 96-slot realized Actual policy-days. saved_Planning fields are not promoted to current corrected authority.',
        sources=[ref(authority_path), ref(states_path), ref(sensitivity_path)])
    identity_path = ROOT / 'dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt/days/2025-04-01/ACTUAL_FIXED_REPLAY.json'
    identity = read(identity_path)
    assert identity['replay_scope'] == 'EXISTING_FIXED_DECISION_REPLAY_IDENTITY_GATE'
    eligible = []
    try:
        cannot_freeze(eligible)
    except ValueError as error:
        assert str(error) == STOP
    else:
        raise AssertionError('EMPTY_POPULATION_MUST_STOP')
    tables = {}
    schemas = {
        'V41R1_PREMAY_VOLTAGE_ELEMENT_RESIDUALS.parquet': dict(source_revision='string', day='string', policy='string', bus='string', phase='string', slot='int64', planning_voltage_pu='float64', Actual_voltage_pu='float64', residual_pu='float64', planning_source_SHA256='string', Actual_source_SHA256='string'),
        'V41R1_PREMAY_VOLTAGE_DAILY_MAX.parquet': dict(source_revision='string', day='string', policy='string', element_rows='int64', daily_max_residual_pu='float64')}
    for name, schema in schemas.items():
        frame = pd.DataFrame({k: pd.Series(dtype=v) for k, v in schema.items()})
        frame.to_parquet(OUT / name, index=False)
        pd.testing.assert_frame_equal(frame, pd.read_parquet(OUT / name), check_exact=True)
        tables[name] = dict(**ref(OUT / name), rows=0, status='EMPTY_NO_ELIGIBLE_AUTHORITY')
    discovery = [ref(p) for p in sorted(DISCOVERY.glob('*_complete_inventory.json'))]
    write('V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json', dict(status=STOP,
        eligible_policy_days=[], N_preMay_policy_days=0, eligible_element_rows=0,
        historical_Actual_candidate_count=len(rows), candidate_rows=ref(OUT / 'V41R1_HISTORICAL_ACTUAL_CANDIDATE_ROWS.json'),
        corrected_April=april_rejection,
        v40a_Apr01_identity_only=dict(source=ref(identity_path), reason=identity['replay_scope'], actual_voltage_rows=0),
        earlier_stage7_H0=dict(reason='Single controller-transition Fresh summaries, no current corrected 96-slot frozen-policy Planning-Actual pairs',
            sources=[ref(ROOT / f'stage7/r13_zero_burnin/RESTART/evidence/{case}/FRESH_EXACT_OPENDSS.json')
                     for case in ('W02_2025-01-13', 'W10_2025-03-10')]),
        search_scope=[dict(root=x['root'], file_count=len(x['all_paths']), errors=x['errors'], includes_gitignored=True) for x in inventories],
        search_inventories=discovery, element_fields_null_reason='Compatibility rejected before numerical pairing; no voltage residual inferred',
        tables=tables, missing_authority='At least one pre-May complete policy-day pair of current constrained Planning voltage and frozen-policy realized three-phase Actual with matching bus/phase/96 slots, topology, corrected mapper, ratings and source-generation provenance'))
    write('V41R1_VOLTAGE_MARGIN_DATA_FIREWALL.json', dict(status='PASS_AT_AUTHORITY_STOP',
        method='PREMAY_DAILY_MAX_ONE_SIDED_Q99', registered_quantile=.99,
        interpolation=False, alternative_quantile_selection=False,
        numerical_calibration_source_days=[], numerical_calibration_rows=0, May_calibration_rows=0,
        candidate_source_days=sorted({r['day'] for r in rows} | set(days)),
        May01_access='Existing exposed files hashed only for preservation, never supplied as margin input',
        May02_31_Actual_scientific_outcomes_opened=False,
        directory_name_inventory_is_not_outcome_access=True,
        preMay_evidence_only_for_authority_screening=True,
        margin_computed=False, May_based_floor=False, May_based_retuning=False,
        old_campaign_control_state=read(OLD / 'frozen_artifacts/v41_may_campaign/campaign_progress.json'),
        old_campaign_stop_request=ref(OLD / 'frozen_artifacts/v41_may_campaign/STOP_REQUESTED.json')))
    write('V41R1_VOLTAGE_SECURITY_MARGIN_FREEZE.json', dict(status='NOT_FROZEN', reason=STOP,
        method='PREMAY_DAILY_MAX_ONE_SIDED_Q99', N_preMay_policy_days=0,
        k_order_statistic=None, EPSILON_V_UP=None, V_MAX_PHYSICAL=1.05, V_MIN_PHYSICAL=.95,
        V_MAX_PLANNING=None, source_day_list=[], daily_residual_distribution=[],
        diagnostics=dict(min=None, median=None, P90=None, P95=None, P99=None, max=None),
        pairing_table=ref(OUT / 'V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json'),
        daily_max_table=tables['V41R1_PREMAY_VOLTAGE_DAILY_MAX.parquet'],
        mapper_SHA256=corrected_sha, electrical_topology_SHA256=None,
        scientific_commit=None, base_implementation_commit=BASE,
        created_before_May_rerun=True, new_May_reruns=0,
        artifact_is_stop_record_not_an_authorized_freeze=True))
    write('V41R1_MAY_VOLTAGE_MARGIN_PROPAGATION_AUDIT.json', dict(status='BLOCKED', reason=STOP,
        expected_units=124, evaluated_units=0, passed_units=0, launched_units=0,
        EPSILON_V_UP=None, V_MAX_PLANNING=None, common_margin_verified=False,
        full_May_launch_gate='FAIL'))
    old = read(OUT / 'V41_EXPOSED_PRE_MARGIN_PILOT_PRESERVATION.json')['files']
    current = old_files()
    assert old == current, 'OLD_MAY01_FILE_SET_OR_BYTES_CHANGED'
    write('V41R1_OLD_MAY01_READBACK_AUDIT.json', dict(status='PASS', files=len(current),
        added=0, removed=0, changed=0, preservation_manifest=ref(OUT / 'V41_EXPOSED_PRE_MARGIN_PILOT_PRESERVATION.json')))
    inherited = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE, 'dayahead'], cwd=ROOT, text=True).splitlines()
    source_rows = []
    for relative in inherited:
        if relative.endswith('.py'):
            assert sha(ROOT / relative) == sha(OLD / relative), relative
            source_rows.append(dict(path=relative, sha256=sha(ROOT / relative)))
    write('V41R1_UNCHANGED_SCIENTIFIC_IMPLEMENTATION.json', dict(status='PASS',
        base_commit=BASE, inherited_python_files=len(source_rows), files=source_rows,
        objective_ML_Actual_dispatch_mapper_voltage_constraints_unchanged=True,
        no_Actual_based_cut=True, new_optimizer_calls=0, new_Actual_calls=0))
    print(json.dumps(dict(status=STOP, eligible_policy_days=0, legacy_candidates=len(rows), preserved_files=len(current))))


if __name__ == '__main__':
    run()
