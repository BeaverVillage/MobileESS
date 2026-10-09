"""Read completed Git evidence without importing historical experiment code.

This audit validates source bytes and records historical claims. It deliberately
does not turn a stored PASS receipt into a new independent mathematical proof.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/v42_m1_joint_gap_research'
M188 = '4b19e85089171729a3225529a40cb00bf31f43d5'
M190 = 'c10e2deb0970b52b308ff71d7b7642b9156cfafe'
C3A = '1d922c91eb27056a5ccc79c92ef18146707099ab'


def git_blob(head: str, path: str) -> bytes:
    """Read immutable completed objects from the independent D-drive clone."""
    if ROOT.resolve().drive.upper() != 'D:':
        raise ValueError('D_DRIVE_REQUIRED')
    if len(head) != 40 or any(c not in '0123456789abcdef' for c in head):
        raise ValueError('EXACT_COMMIT_REQUIRED')
    if path.startswith(('/', '\\')) or '..' in Path(path).parts:
        raise ValueError('REPOSITORY_RELATIVE_PATH_REQUIRED')
    return subprocess.check_output(['git', 'show', f'{head}:{path}'], cwd=ROOT)


def source_receipt(head: str, path: str) -> dict:
    raw = git_blob(head, path)
    blob = subprocess.check_output(
        ['git', 'rev-parse', f'{head}:{path}'], cwd=ROOT, text=True).strip()
    return dict(head=head, path=path, git_blob=blob,
                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def read_source(head: str, path: str):
    return json.loads(git_blob(head, path).decode('utf-8-sig'))


SOURCES = {
    'PR167_one_slot_hulls': (M188, 'docs/v42_m1_root_gap_attribution_20261007/ROOT_GAP_CONCLUSION.json'),
    'PR169_four_slot_hulls': (M188, 'docs/v42_m1_gap_rootcause_20261007/LB_VALIDATION.json'),
    'PR169_exact_homogeneous_bound': (M188, 'docs/v42_m1_gap_rootcause_20261007/MULTIWINDOW_STRENGTHENED_LP_HOMOGENEOUS_VALID_LB_CERTIFICATE.json'),
    'PR170_UB': (M188, 'docs/v42_m1_hamming48_20261007/GAP_UPDATE.json'),
    'PR171_UB': (M188, 'docs/v42_m1_hamming48_600s_20261007/GAP_UPDATE.json'),
    'PR173_cutoff': (M188, 'docs/v42_m1_target_rho_t1_20261007/RESULT.json'),
    'PR175_cutoff': (M188, 'docs/v42_m1_target_rho_t1_1800s_20261007/RESULT.json'),
    'PR177_original_objective': (M188, 'docs/v42_m1_p1_objective_t1_1800s_20261008/RESULT.json'),
    'PR179_external_tree': (M188, 'docs/v42_m_practical_exact_solver_overnight_20261008/RESULT.json'),
    'PR182_joint_formulation': (M188, 'docs/v42_m1_joint_formulation_20261008/RESULT.json'),
    'PR182_original_exact_bound': (M188, 'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/EXACT_LB_CERTIFICATE.json'),
    'PR183_integer_first': (M188, 'docs/v42_m1_route_mode_benders_20261008/FINAL_RESULT.json'),
    'PR183_UB_change': (M188, 'docs/v42_m1_route_mode_benders_20261008/VALID_UB_CHANGE.json'),
    'PR183_best_full_replay': (M188, 'docs/v42_m1_route_mode_benders_20261008/BEST_FULL_REPLAY.json'),
    'PR183_independent_final': (M188, 'docs/v42_m1_route_mode_benders_20261008/FINAL_VALIDATION.json'),
    'PR183_integer_projection': (M188, 'docs/v42_m1_route_mode_benders_20261008/GENERAL_EXACTNESS_GATE.json'),
    'PR185_physics_scope': (M188, 'docs/v42_m1_physics_strengthened_20261008/FINAL_DECISION.json'),
    'PR187_B2_validity': (M188, 'docs/v42_m1_b2_root_validation_20261008/INDEPENDENT_VALID_INEQUALITY_AUDIT.json'),
    'PR187_B2_bound': (M188, 'docs/v42_m1_b2_root_validation_20261008/B2_ROOT_LB_CERTIFICATE.json'),
    'PR187_B2_decision': (M188, 'docs/v42_m1_b2_root_validation_20261008/B2_ROOT_FINAL_DECISION.json'),
    'PR188_branching': (M188, 'docs/v42_m1_group_branching_20261008/FINAL_DECISION.json'),
    'PR188_dual_repair': (M188, 'docs/v42_m1_group_branching_20261008/DUAL_CERTIFICATION_REPAIR_AUDIT.json'),
    'PR190_scalar_failure': (M190, 'docs/v42_m1_global_physical_proof_20261008/GLOBAL_INFEASIBILITY_PROOF.json'),
    'PR190_failure_analysis': (M190, 'docs/v42_m1_global_physical_proof_20261008/GAP_ROOT_CAUSE_AUDIT.json'),
    'PR190_cutoff': (M190, 'docs/v42_m1_global_physical_proof_20261008/ORIGINAL_CUTOFF_RESULT.json'),
    'PR190_independent_UB': (M190, 'docs/v42_m1_global_physical_proof_20261008/BASELINE_UB_INDEPENDENT_REPLAY.json'),
}


def run(pr_metadata_path: str | Path | None = None) -> dict:
    sources = {key: source_receipt(*spec) for key, spec in SOURCES.items()}
    values = {key: read_source(*spec) for key, spec in SOURCES.items()}
    point_path = 'docs/v42_m1_route_mode_benders_20261008/artifacts/BEST_VALID_POINT.npz'
    point = source_receipt(M188, point_path)
    root = values['PR167_one_slot_hulls']
    homogeneous = values['PR169_exact_homogeneous_bound']
    old = values['PR188_branching']
    b2 = values['PR187_B2_bound']
    gap_audit = values['PR190_failure_analysis']
    ub = values['PR183_UB_change']
    joint = values['PR182_joint_formulation']
    benders = values['PR183_integer_first']
    validity = values['PR187_B2_validity']
    if not (validity['PASS'] and validity['delivered_rows'] == 651
            and ub['new_UB'] == old['new_UB'] == 0.6284141956452488
            and homogeneous['valid_for_every_original_integer_schedule']
            and values['PR190_independent_UB']['PASS']):
        raise ValueError('HISTORICAL_EVIDENCE_SCOPE_OR_VALUE_DRIFT')
    if pr_metadata_path is not None:
        prs = json.loads(Path(pr_metadata_path).read_text(encoding='utf-8-sig'))
    elif (REPORT / 'HISTORICAL_EVIDENCE_AUDIT.json').exists():
        # Preserve the explicit remote inventory captured at research start.
        prs = json.loads((REPORT / 'HISTORICAL_EVIDENCE_AUDIT.json').read_text(
            encoding='utf-8'))['source_pr_inventory']
    else:
        prs = json.loads((ROOT / 'tmp/history_pr_metadata.json').read_text(encoding='utf-8-sig'))
    if sorted(p['number'] for p in prs) != list(range(167, 191)):
        raise ValueError('PR167_190_INVENTORY_INCOMPLETE')
    for p in prs:
        if p['number'] in (188, 190) and p['headRefOid'] != {188: M188, 190: M190}[p['number']]:
            raise ValueError('COMPLETED_HEAD_DRIFT')
        p['scientific_scope'] = ('M1_SAME_MAY01_CASE' if p['number'] in
            (167,169,170,171,173,175,177,179,182,183,185,187,188,190)
            else 'INTEGRATION_ONLY' if p['number'] == 189 else 'A_STAGE_DIFFERENT_CASE_NOT_M1_AUTHORITY')
    heads = {p['number']: p['headRefOid'] for p in prs}
    for label, receipt in sources.items():
        original_pr = int(label.split('_', 1)[0][2:])
        original = source_receipt(heads[original_pr], receipt['path'])
        receipt['original_PR_HEAD_source'] = original
        receipt['unchanged_since_original_PR_HEAD'] = receipt['sha256'] == original['sha256']
    result = dict(
        schema='V42_M1_COMPLETED_HISTORY_AUDIT_V1', PASS=True,
        validation_scope='Committed source byte identity and historical claim/scope consistency; no new certificate replay or optimize.',
        source_pr_inventory=sorted(prs, key=lambda p: p['number']),
        source_receipts=sources, best_incumbent_source=point,
        C3A_authority=C3A, completed_M_authority=M188, completed_reference_only=M190,
        PR190_scalar_implementation_imported=False, unfinished_M_sources_read=False,
        native_optimize_calls=0, old_records_modified=False,
        historical_native_global_LB=dict(value=old['new_valid_global_LB'],
            origin='PR162 native MILP ObjBound authority, preserved by completed M stages',
            independently_exact_ROOT_dual_certificate=False,
            authority_scope=gap_audit['numerical_certification']['original_ROOT']['authority_scope']),
        archived_exact_global_LB=dict(value=homogeneous['lower_bound'],
            exact_rational=homogeneous['exact_rational'],
            valid_for_every_original_integer_schedule=homogeneous['valid_for_every_original_integer_schedule'],
            source=sources['PR169_exact_homogeneous_bound'],
            newly_independently_replayed=False,
            lifting_required='Two conservative four-slot perspective hulls, each232837 disjuncts; stored homogeneous residual certificate'),
        plain_C3A_archived_exact_LB=values['PR182_original_exact_bound']['lower_bound'],
        B2=dict(stored_independent_validity_PASS=validity['PASS'], additional_rows=651,
            additional_columns=0, additional_nnz=1302,
            row_source=(M188, 'docs/v42_m1_b2_root_validation_20261008/artifacts/TEMPORAL_VALID_ROWS.npz'),
            data_source=(M188, 'docs/v42_m1_b2_root_validation_20261008/artifacts/TEMPORAL_VALID_ROW_DATA.npz'),
            raw_multiplier_rejected=True, exact_certified_LB=b2['exact_certified_LB'],
            certified_global_improvement=0.0,
            new_independent_validity_replay_required_before_use=True),
        UB=dict(value=ub['new_UB'], source_best_assignment=ub['source_best_assignment'],
            point=point, old_UB=ub['old_UB'], historical_improvement=ub['absolute_improvement'],
            changed_integer_bits=ub['changed_binary_names'],
            route_changed_in_this_PR183_improvement=False,
            dispatch_changes=ub['maximum_dispatch_change_by_family'],
            stored_original_full_replay_PASS=values['PR183_best_full_replay']['PASS'],
            stored_independent_PR190_replay_PASS=values['PR190_independent_UB']['PASS'],
            new_replay_required_before_MIP_start=True,
            C3A_VALID_START_is_best_UB=False, C3A_VALID_START_objective=0.6694159238756877),
        structural_ROOT=dict(original_fractional_charge_modes=384,
            original_fractional_node_activity=7070, original_fractional_continuous_route_flows=140502,
            B2_fractional_binary_count=gap_audit['structural_LP_diagnostics']['B2_ROOT']['fractional_binary_count'],
            known_bound_gap_is_not_proven_true_integrality_gap=True),
        failed_methods=dict(one_slot_hulls=root['classification'], one_slot_delivered_rows=root['added_rows'],
            one_slot_certified_Delta_LB=root['absolute_global_LB_improvement'],
            four_slot_hull_archived_exact_LB=homogeneous['lower_bound'],
            branch=old['classification'], branch_certified_Delta_LB=old['Delta_LB'],
            joint_formulation=joint['classification'],
            joint_ROOT_candidates=[{k:r.get(k) for k in ('label','status_name','rows','columns','nnz','Runtime','valid_LB','root_completed')} for r in joint['root_comparison']],
            integer_first=benders['classification'],
            known_feasible_recourse_median_Runtime=benders['recourse_median_Runtime'],
            new_canary_separation_unresolved=benders['canary_separation_unresolved'],
            scalar_direction_contradiction_NOT_PROVEN=True,
            selected_scalar_exact_private_lower_witnesses_exceed_grid_demand=True,
            cutoff_result='TIME_LIMIT_NO_INTEGER_INCUMBENT_INCONCLUSIVE'),
        historical_global_gap_percent=old['new_global_gap_percent'], M1_ACCEPTED=False,
        next_bottleneck='Joint multiple line/time requirements across all four complete96-slot trajectories, SOC, mode and PQ; avoid the failed scalar sum.')
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'HISTORICAL_EVIDENCE_AUDIT.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    audit = run()
    print('COMPLETED_HISTORY_AUDIT', audit['PASS'], len(audit['source_receipts']))
