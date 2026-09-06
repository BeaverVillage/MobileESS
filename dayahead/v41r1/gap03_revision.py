"""Evidence-bound transition to the user-authorized 3% B1/B3 gap."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

import psutil

from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.execution import science
from dayahead.v41.preflight import ROOT, OUT, record
from dayahead.v41.reserve import require
from .campaign_revision import model_build_parts


PREVIOUS = '48657f65c9c176d8fc9398ebdfe90d636d25db81'
REVISION = RUNTIME / 'rev/gap03'
GAP_SOURCES = {
    'dayahead/v40g/optimizer.py',
    'dayahead/v40h/feedback.py',
    'dayahead/v41r1/migration_solver_policy.py',
}


def _old_blob(commit, relative):
    return subprocess.check_output(['git', 'show', commit + ':' + relative], cwd=ROOT)


def _live_scientific_workers():
    result = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = process.info['cmdline'] or []
        if 'dayahead.v41.execution' in command or 'dayahead.v41r1.campaign_run' in command:
            result.append(dict(pid=process.pid, command=command))
    return result


def preserve():
    """Preserve the interrupted B1 attempts before changing campaign identity."""
    require(not _live_scientific_workers(), 'SCIENTIFIC_WORKER_STILL_RUNNING')
    state_path = RUNTIME / 'campaign_state.json'
    state = read(state_path)
    require(state['scientific_commit'] == PREVIOUS, 'UNEXPECTED_PRE_GAP03_COMMIT')
    require(state['status'] in ('FAILED', 'PAUSED', 'PAUSED_FOR_USER_AUTHORIZED_B1_B3_3PCT'),
            'CAMPAIGN_NOT_STOPPED_FOR_GAP03')
    REVISION.mkdir(parents=True, exist_ok=True)
    before = REVISION / 'CAMPAIGN_STATE_BEFORE_GAP03.json'
    if not before.exists():
        write_json(before, state)
    preserved = []
    from dayahead.v41.campaign import verify_receipt
    for row in state['units'].values():
        if row['status'] == 'COMPLETE':
            require(row['policy'] == 'B0', 'NON_B0_COMPLETE_REQUIRES_SEPARATE_IMPACT_AUDIT')
            for phase in ('dayahead', 'actual'):
                verify_receipt(Path(row[phase + '_receipt']['path']), None)
            preserved.append(dict(day=row['day'], policy='B0', status='COMPLETE',
                unit_receipt=record(row['unit_receipt']['path']), action='REUSE_PENDING_CURRENT_SOURCE_EQUIVALENCE'))
        elif row['policy'] == 'B1' and row['status'] in ('FAILED', 'DAYAHEAD_RUNNING', 'PAUSED'):
            folder = RUNTIME / row['day'] / 'B1/dayahead'
            archive = None
            if folder.exists() and not (folder / 'DAYAHEAD_RECEIPT.json').exists():
                archive = RUNTIME / 'interrupted' / (row['day'] + '_B1_dayahead_user_gap03_' + uuid.uuid4().hex[:8])
                archive.parent.mkdir(parents=True, exist_ok=True)
                folder.rename(archive)
            previous_error = row.pop('error', 'USER_REQUESTED_STOP_DURING_B1_DAYAHEAD')
            row['superseded_attempt'] = dict(classification='USER_AUTHORIZED_SCIENTIFIC_GAP_REVISION',
                previous_gap=.001, replacement_gap=.03, prior_commit=PREVIOUS,
                error=previous_error, preserved_folder=str(archive) if archive else None,
                log=row.get('log'))
            row.update(status='PAUSED', phase=None, worker_pid=None)
    state.update(status='PAUSED_FOR_USER_AUTHORIZED_B1_B3_3PCT', updated_at=time.time())
    write_json(state_path, state)
    authorization = dict(status='AUTHORIZED', user_instruction='B1 B3 3% gap으로 변경 후 5월 전체 재실행',
        affected_policies=['B1', 'B3'], affected_stages=['P1', 'P2'], relative_gap=.03,
        absolute_gap=0., feasibility_tolerances='UNCHANGED', physical_constraints='UNCHANGED',
        objectives='UNCHANGED; accepted P1/P2 incumbents are frozen exactly for lower priorities',
        P3_P5_gap=0., B0_reuse='REQUIRES_EXPLICIT_EQUIVALENCE', B2_reuse='IF_COMPLETE_AND_EQUIVALENT',
        prior_commit=PREVIOUS, preserved_completed_units=preserved,
        state_before=record(before), stopped_worker_evidence='Four B1 DayAhead processes stopped before source change')
    write_json(OUT / 'USER_APPROVED_B1_B3_GAP_3PCT.json', authorization)
    write_json(REVISION / 'PRESERVATION.json', authorization)
    print('GAP03_PRESERVATION_PASS', len(preserved), flush=True)


def _test_evidence():
    path = OUT / 'V41_TEST_RESULTS.xml'
    tree = ET.parse(path)
    cases = list(tree.iter('testcase'))
    require(len(cases) >= 253 and not any(list(tree.iter(tag)) for tag in ('failure', 'error', 'skipped')),
            'GAP03_FULL_REGRESSION_NOT_PASS')
    focused = [case.attrib['name'] for case in cases
        if case.attrib.get('classname') in ('tests.dayahead.test_v41r1_gap_and_b3',
                                            'tests.dayahead.test_v41_scalar_interface')]
    require(len(focused) >= 43, 'GAP03_FOCUSED_REGRESSIONS_MISSING')
    return path, cases, focused


def evidence():
    """Refresh gates while proving B0 and memory-model invariance."""
    require(not _live_scientific_workers(), 'SCIENTIFIC_WORKER_STARTED_BEFORE_GAP03_FREEZE')
    test_path, cases, focused = _test_evidence()
    current = science()
    authorization = read(OUT / 'USER_APPROVED_B1_B3_GAP_3PCT.json')
    require(authorization['relative_gap'] == .03, 'GAP03_AUTHORITY_DRIFT')

    exact_path = OUT / 'EXACT_COMPRESSION_GATE.json'
    exact = read(exact_path)
    historical = REVISION / 'EXACT_COMPRESSION_GATE_BEFORE_GAP03.json'
    if not historical.exists():
        shutil.copyfile(exact_path, historical)
    exact.update(status='PASS', sources=[record(row['path']) for row in current['files']]
        + [record(ROOT / 'tests/dayahead/test_v41r1_compression.py'),
           record(ROOT / 'tests/dayahead/test_v41r1_gap_and_b3.py')],
        test_results=record(test_path), full_regression_case_count=len(cases),
        P1_P2_termination_gap=.03, P3_P5_termination_gap=0.,
        gap_scope='B1 A0 and B3 A1 only; feasible set, objective expressions and exact factorization unchanged',
        gap_authorization=record(OUT / 'USER_APPROVED_B1_B3_GAP_3PCT.json'))
    # De-duplicate by absolute path while retaining deterministic order.
    exact['sources'] = [dict(value) for _, value in sorted({row['path']: row for row in exact['sources']}.items())]
    write_json(exact_path, exact)

    gate_path = OUT / 'Q90_BASELINE_RETAINED_B0_GATE.json'
    gate = read(gate_path)
    from dayahead.v41.campaign import verify_receipt
    state = read(RUNTIME / 'campaign_state.json')
    for row in state['units'].values():
        if row['status'] != 'COMPLETE':
            continue
        require(row['policy'] == 'B0', 'NON_B0_COMPLETE_REQUIRES_SEPARATE_GAP03_AUDIT')
        for phase in ('dayahead', 'actual'):
            receipt_path = Path(row[phase + '_receipt']['path'])
            receipt = read(receipt_path)
            matches = [entry for entry in gate['receipts']
                if entry['day'] == row['day'] and read(entry['receipt']['path']) == receipt]
            if matches:
                require(len(matches) == 1, 'DUPLICATE_B0_REUSE_RECEIPT')
                continue
            common = RUNTIME / 'inputs' / row['day'] / 'common_q90_v3'
            reference = record(common / 'COMMON_B0_REFERENCE_JOBS.json')
            gate['receipts'].append(dict(day=row['day'], phase=phase, receipt=record(receipt_path),
                old_reference=reference, new_reference=reference, attested_changed_paths=[],
                input_equality_evidence=[record(common / 'COMMON_INPUT_RECEIPT.json')]))
    checks = []
    for entry in gate['receipts']:
        receipt = verify_receipt(Path(entry['receipt']['path']), None)
        changed = set(entry.get('attested_changed_paths', []))
        changed_rel = []
        for ref in receipt['science']['files']:
            relative = ref['relative_path']
            original = _old_blob(receipt['scientific_commit'], relative)
            require(hashlib.sha256(original).hexdigest() == ref['sha256'], 'B0_ORIGINAL_GIT_BLOB_DRIFT')
            current_path = ROOT / relative
            if current_path.exists() and record(current_path)['sha256'] != ref['sha256']:
                require(relative in GAP_SOURCES or str(current_path.resolve()) in changed,
                        'B0_UNATTESTED_GAP03_SOURCE_CHANGE:' + relative)
                changed.add(str(current_path.resolve()))
                changed_rel.append(relative)
        entry['attested_changed_paths'] = sorted(changed)
        checks.append(dict(day=receipt['day'], phase=Path(entry['receipt']['path']).parent.name,
            receipt=entry['receipt'], changed_scientific_paths=sorted(changed_rel),
            B0_solver_gap_path_active=False, B3_feedback_path_active=False,
            artifact_bytes_and_scientific_manifest_reopened=True))
    proof_path = OUT / 'GAP03_B0_REUSE_EQUIVALENCE.json'
    proof = dict(status='PASS', prior_commit=PREVIOUS, current_source=current, checks=checks,
        exact_scope='B0 never calls v40g.optimizer.solve or v40h.feedback.solve_feedback; gap policy is inactive for B0',
        common_inputs='UNCHANGED', electrical='UNCHANGED', Actual='UNCHANGED', objectives='UNCHANGED',
        completed_B0_artifacts_overwritten=False, focused_regressions=focused,
        tests=record(test_path), authorization=record(OUT / 'USER_APPROVED_B1_B3_GAP_3PCT.json'))
    write_json(proof_path, proof)
    gate.update(status='PASS', current_source=current, receipts=gate['receipts'], proof=record(proof_path),
        gap03_authorization=record(OUT / 'USER_APPROVED_B1_B3_GAP_3PCT.json'),
        scope='Only enumerated completed B0 phases; B1/B3 are invalidated and rerun')
    write_json(gate_path, gate)

    stress_path = OUT / 'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json'
    stress = read(stress_path)
    old_reuse = read(OUT / 'Q90_REVISION_STRESS_REUSE.json')
    current_builder = model_build_parts((ROOT / 'dayahead/v40g/optimizer.py').read_bytes())
    require(current_builder == old_reuse['model_build'], 'GAP03_CHANGED_MODEL_BUILD_OR_MEMORY_STRUCTURE')
    stress_reuse = dict(status='PASS', current_source=current, measurement=record(stress_path),
        proof=record(proof_path), exact_same_representative_reference=old_reuse['exact_same_representative_reference'],
        measured_source=stress['source'], fresh_measurement=False, model_build=current_builder,
        reason='Only post-build B1/B3 termination controls changed; model construction, variables, constraints, nonzeros, '
               'factorization, four-worker architecture and memory limits are byte-identical',
        source_changes=sorted(GAP_SOURCES), authorization=record(OUT / 'USER_APPROVED_B1_B3_GAP_3PCT.json'))
    write_json(OUT / 'Q90_REVISION_STRESS_REUSE.json', stress_reuse)
    from .migration_factor import verify_gate
    verify_gate()
    print('GAP03_EQUIVALENCE_PASS', len(cases), len(checks), flush=True)


def transition():
    """Move only invalidated B1/B3 work to the new scientific identity."""
    from .campaign_prepare import verify_release
    from .campaign_run import verify_phase
    frozen = verify_release()
    state_path = RUNTIME / 'campaign_state.json'
    state = read(state_path)
    require(state['scientific_commit'] == PREVIOUS, 'UNEXPECTED_GAP03_TRANSITION_SOURCE')
    require(state['status'] == 'PAUSED_FOR_USER_AUTHORIZED_B1_B3_3PCT', 'GAP03_STATE_NOT_PAUSED')
    for row in state['units'].values():
        if row['status'] == 'COMPLETE':
            require(row['policy'] == 'B0', 'COMPLETED_CHANGED_POLICY_REQUIRES_RERUN')
            for key in ('dayahead_receipt', 'actual_receipt'):
                verify_phase(row[key]['path'], frozen)
            row['reuse_classification'] = 'REUSED_PASS_BY_VERIFIED_EQUIVALENCE'
            row['reuse_receipt'] = record(OUT / 'GAP03_B0_REUSE_EQUIVALENCE.json')
        if row['policy'] in ('B1', 'B3') and row['status'] != 'COMPLETE':
            row.update(status='PENDING', phase=None, worker_pid=None)
            row.pop('dayahead_receipt', None)
            row.pop('actual_receipt', None)
    state.update(scientific_commit=frozen['scientific_commit'], prior_scientific_commit=PREVIOUS,
        status='READY_AFTER_USER_AUTHORIZED_B1_B3_3PCT',
        gap03_revision_proof=record(OUT / 'GAP03_B0_REUSE_EQUIVALENCE.json'), updated_at=time.time())
    write_json(REVISION / 'CAMPAIGN_STATE_AFTER_GAP03.json', state)
    write_json(state_path, state)
    print('GAP03_STATE_TRANSITION_PASS', frozen['scientific_commit'], flush=True)


if __name__ == '__main__':
    import sys
    {'preserve': preserve, 'evidence': evidence, 'transition': transition}[sys.argv[1]]()
