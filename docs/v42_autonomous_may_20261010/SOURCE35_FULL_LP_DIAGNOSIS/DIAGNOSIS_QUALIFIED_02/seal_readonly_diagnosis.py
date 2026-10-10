"""Copy and compare current full-LP receipts; no science import or Native call."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json

OUT = Path(__file__).resolve().parent
ROOT = Path(r'D:\v42_may_restart_20261010_02')
FROZEN = Path(r'D:\v42run35')
DRAFT = Path(r'D:\v42_source36_pdhg_diagnostics_draft_20261010_01')


def record(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(path):
    return json.loads(Path(path).read_bytes())


def copy(source, relative):
    source = Path(source)
    target = OUT / relative
    assert not target.exists(), 'DIAGNOSIS_ARTIFACT_ALREADY_EXISTS'
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = source.read_bytes()
    target.write_bytes(raw)
    return record(target), json.loads(raw) if source.suffix == '.json' else None


def write(path, value):
    assert not path.exists()
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def main():
    freeze = read(ROOT / 'autonomous/V35_SPARSE_IMMUTABLE_FREEZE.json')
    expected = {item['path']: item['sha256'] for item in freeze['source_files']}
    before = {name: record(name)['sha256'] for name in expected}
    source_names = ['v42_autonomous_b2/f1_basis.py','v42_autonomous_b2/f1_state.py',
                    'v42_b2_seed_recovery_v19/budget.py','v42_b2_seed_recovery_v19/native_diagnostics.py',
                    'v42_may_campaign_native90/m_stage.py']
    sources = {}
    for name in source_names:
        copied, _ = copy(FROZEN / name, Path('frozen_source_readonly') / name)
        sources[name] = dict(origin=record(FROZEN / name), copied=copied)
    basis = (FROZEN / source_names[0]).read_text()
    budget = (FROZEN / source_names[2]).read_text()
    diagnostics = (FROZEN / source_names[3]).read_text()
    native_tree = ast.parse(diagnostics)
    callback_guard = dict(PDHG_branch_absent='PDHG' not in diagnostics,
                         PDHGIterCount_absent='PDHGIterCount' not in diagnostics,
                         Runtime_original_cap_termination="if self.latest['Runtime'] >= limit:" in budget
                         and 'm.terminate()' in budget,
                         downstream_observer_invoked_after_original_budget_callback=
                         'if callback is not None:\n                callback(m, where)' in budget,
                         full_LP_exact_call_guard_preserved="kwargs.get('track') != 'M_LB'" in basis
                         and 'requested <= 300.' in basis and 'callback is not None' in basis)
    observations = []
    for day, attempt in [('01','repair_b2_v35_01_s3'),('02','repair_b2_v35_01_s1'),('03','repair_b2_v35_01_s2')]:
        original = ROOT / f'dates/B2/2025-05-{day}/attempts/{attempt}'
        files = {}
        documents = {}
        names = ['request.json','NATIVE_RUNTIME_LEDGER.json','0001_M_LB_P1_NATIVE.log',
                 'output/F1_FULL_LP_COMPUTATIONAL_ENTRY.json','output/F1_FULL_LP_WARMSTART.json',
                 'output/F1_STATE_ADMISSION.json','output/F1_FULL_DOMAIN_LB_SELECTION.json',
                 'output/INITIAL_EXACT_LB_CERTIFICATE.json','output/STATIONARY_DISPATCH_REPLAY.json',
                 'output/SAME_DAY_LP_MODEL_IDENTITY.json']
        for name in names:
            copied, document = copy(original / name, Path('actual') / day / name)
            files[name] = dict(origin=str(original / name), snapshot=copied)
            if document is not None:
                documents[name] = document
        request = documents['request.json']
        ledger = documents['NATIVE_RUNTIME_LEDGER.json']
        entry = documents['output/F1_FULL_LP_COMPUTATIONAL_ENTRY.json']
        selection = documents['output/F1_FULL_DOMAIN_LB_SELECTION.json']
        calls = [call for call in ledger['calls'] if call.get('track') == 'M_LB']
        assert len(calls) == 1 and entry['completed_original_Native_call'] == calls[0]
        call = calls[0]
        assert request['implementation_SHA'] == 'a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
        assert ledger['P2_calls'] == 0 and ledger['Native_ceiling_seconds'] == 5400
        candidates = {item['kind']: item['certificate'] for item in selection['candidates']}
        full = candidates['ORIGINAL_FULL_LP']
        f1 = candidates['CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI']
        assert {k:v for k,v in full.items() if k != 'check_wall_seconds'} == {k:v for k,v in f1.items() if k != 'check_wall_seconds'} and full['nonzero_dual_rows'] > 0
        parameters = entry['actual_parameters']
        assert parameters['Method'] == 6 and parameters['LPWarmStart'] == 2
        assert parameters['TimeLimit'] == 300 and parameters['Threads'] == 1
        assert parameters['PDHG_parameters'] == dict(PDHGAbsTol=1e-9,PDHGRelTol=0.,PDHGConvTol=1e-9,PDHGGPU=0)
        assert call['Native_status'] == 11 and call['SolCount'] == 0 and call['error'] is None
        observations.append(dict(day=request['day'], attempt=attempt, source=request['implementation_SHA'],
            files=files, actual_original_full_LP_call=call, actual_parameters=parameters,
            strict_current_F1_point_replay_PASS=documents['output/STATIONARY_DISPATCH_REPLAY.json']['PASS'],
            complete_current_state_axes=list(documents['output/F1_STATE_ADMISSION.json']['binding']['arrays']),
            full_LP_missing_Pi_receipt_present=(original / 'output/LP_DUAL_UNAVAILABLE.json').exists(),
            full_LP_and_F1_exact_scientific_certificate_fields_identical=True,
            diagnostic_checker_wall_seconds_may_differ=True,
            full_LP_and_F1_certified_LB=full['independently_certified_LB'],
            full_LP_and_F1_nonzero_dual_rows=full['nonzero_dual_rows'],
            full_LP_and_F1_dual_SHA=full['dual_SHA256'], selected_initial_bound=selection['selected'],
            initial_exact_bound=selection['maximum_exact_bound']))
    draft_files = {}
    for name in ['DESIGN.md','pdhg_observer.py','NATIVE_DENIED_TEST_PROPOSAL.md','READONLY_FINDINGS_AND_PROPOSAL.json']:
        copied, _ = copy(DRAFT / name, Path('historical_external_proposal') / name)
        draft_files[name] = dict(origin=record(DRAFT / name), copied=copied)
    after = {name: record(name)['sha256'] for name in expected}
    checks = dict(frozen_1111_before_end_matches_declared=before == after == expected,
                  all_three_completed_original_full_LP_entries=True,
                  all_three_current_basis_and_F1_FULL_replay_present=True,
                  all_three_full_LP_exact_bound_matches_F1=True,
                  diagnostic_gap_and_original_budget_guards=all(callback_guard.values()))
    references = [dict(url='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-LPWarmStart',
        checked_UTC=datetime.now(timezone.utc).isoformat(), claims=[
            'PDHG uses primal and dual start vectors, deriving them from a supplied basis.',
            'LPWarmStart2 crushes starts when presolve is enabled.',
            'Method2 with complete warm vectors or a basis uses crossover without barrier iterations.',
            'Primal simplex uses PStart; warm2 can derive a crushed primal start from the current basis.']),
        dict(url='https://docs.gurobi.com/projects/optimizer/en/current/reference/releasenotes/fixedbugs.html',
             claim='Gurobi13.0.2 fixes the PDHG dual-start sign bug.'),
        dict(url='https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html',
             claim='PDHG callback exposes iteration, primal/dual objective, primal/dual infeasibility and complementarity scalars.'),
        dict(url='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#attr-PDHGIterCount',
             claim='PDHGIterCount reports PDHG iterations from the most recent optimization.')]
    receipt = dict(PASS=all(checks.values()), UTC=datetime.now(timezone.utc).isoformat(),
        schema='V42_SOURCE35_FULL_LP_INDEPENDENT_READONLY_DIAGNOSIS', checks=checks,
        sources=sources, immutable_frozen_1111_before=before, immutable_frozen_1111_after=after,
        actual_three_observations=observations, callback_guard=callback_guard,
        official_primary_sources=references, historical_external_proposal=draft_files,
        established=['PDHG warm starts are supported; the current basis is not ignored by documented semantics.',
            'All three full LP calls consumed their original300cap and did not improve the independently certified initial LB.',
            'Pi availability cannot be inferred from SolCount0; all three have nonzero exact full-LP certificates identical to F1.',
            'Current diagnostic code cannot identify actual PDHG iteration or residual progress.'],
        inference_only=['Starting basic Pi may remain the returned Pi while a PDHG/crossover iterate is unfinished.',
            'Method2 crossover-only may reach a usable basis/Pi sooner; no measured benefit or300second guarantee exists.'],
        recommendation='Keep qualified Source36 RMP policy. Add an owned diagnostic-only callback observer at the single original full-LP call in a future source, retaining original Runtime/UNKNOWN accounting and source/model/call guards before delegation; collect PDHG/other phases and scalar iteration/residuals before changing algorithms.',
        model_constructions=0, Native_optimize_calls=0, scientific_module_imports=0,
        production_source_queue_or_process_mutations=0, producer=record(__file__),
        limitations=['Receipt comparison is not a fresh scientific matrix or rational-checker replay.',
            'No Native probe, callback occurrence, algorithm improvement, final3%gap or datePASS is claimed.',
            'Method0/warm2 previously hit300cap in Source32; different attempts are not controlled performance comparisons.'])
    path = OUT / 'SOURCE35_FULL_LP_INDEPENDENT_READONLY_DIAGNOSIS.json'
    write(path, receipt)
    print(json.dumps(dict(PASS=receipt['PASS'], receipt=record(path), Native_optimize_calls=0,
        observations=[dict(day=item['day'], Native=item['actual_original_full_LP_call']['Native_Runtime'],
            certified_LB=item['full_LP_and_F1_certified_LB']) for item in observations])))


if __name__ == '__main__':
    main()
