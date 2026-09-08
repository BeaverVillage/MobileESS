"""User-requested post-result interpretation audit of saved predictions only.

Does not fit, calibrate, change a gate, rank candidates, or promote a winner.
"""
from .common import *
from .metrics import body_metrics, pinball, point

AMENDMENT = Path('C:/Users/kjw39/.codex/attachments/211eef1a-4237-4af9-ac26-4302741cdd03/pasted-text.txt')
PRIMARY = 'NO REGISTERED COMBINATION PASSED THE FROZEN SAFETY GATES'
FINDING = 'BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION'
NEXT = 'V40R5R1_ZERO_INFLATION_AWARE_GATE_CORRECTION'


def feasibility(y):
    n = len(y); nz = int((y == 0).sum()); np_ = int((y > 0).sum())
    assert n == nz + np_ and np_ > 0
    z = nz / n
    # Exact integer grid checks avoid rounding at coverage boundaries.
    k_min = (9 * np_ + 9) // 10
    k_max = min((19 * np_) // 20, (19 * n) // 20 - nz)
    return {'N': n, 'zero_N': nz, 'positive_N': np_, 'p_zero': z,
            'overall_min_given_positive_90': z + (1-z)*.9,
            'overall_min_on_empirical_coverage_grid': (nz+k_min)/n,
            'positive_coverage_upper_allowed_by_overall_95': (.95-z)/(1-z),
            'continuous_bounds_incompatible': nz*2 > n,
            'required_positive_covered_min_integer': k_min,
            'allowed_positive_covered_max_integer': k_max,
            'empirical_bounds_incompatible': k_min > k_max,
            'BODY_GATE_STRUCTURAL_INCOMPATIBILITY': 'YES' if nz*2 > n else 'NO'}


def diagnostic(y, q, u, dates):
    r = body_metrics(y, q, u, dates)
    mask = y <= u; yy = y[mask]; qq = q[mask]; pos = yy > 0; zero = yy == 0
    assert np.isfinite(qq).all() and (qq >= 0).all()
    co = float((yy <= qq[:, 1]).mean())
    cp = float((yy[pos] <= qq[pos, 1]).mean())
    cz = float((yy[zero] <= qq[zero, 1]).mean())
    residual = abs(co - (zero.mean() + (1-zero.mean())*cp))
    assert cz == 1.0 and residual < 1e-14
    reasons = []
    if len(yy) < 100: reasons.append('BODY_SUPPORT_BELOW_100')
    if pos.sum() < 100: reasons.append('POSITIVE_BODY_SUPPORT_BELOW_100')
    if co < .9: reasons.append('OVERALL_COVERAGE_BELOW_90')
    if co > .95: reasons.append('OVERALL_COVERAGE_ABOVE_95')
    if cp < .9: reasons.append('POSITIVE_BODY_COVERAGE_BELOW_90')
    if cp > .95: reasons.append('POSITIVE_BODY_COVERAGE_ABOVE_95')
    for month in r['temporal']:
        if month['gate'] == 'FAIL': reasons.append('MONTHLY_OVERALL_BELOW_88:'+month['month'])
    assert (not reasons) == r['all_pass']
    return {'BODY_N': len(yy), 'zero_N': int(zero.sum()), 'positive_BODY_N': int(pos.sum()),
            'overall_coverage': co, 'zero_only_coverage': cz, 'positive_BODY_coverage': cp,
            'positive_Q90_pinball_mean_GPUh': pinball(yy[pos], qq[pos, 1]).mean(),
            'positive_Q90_pinball_sum_GPUh': pinball(yy[pos], qq[pos, 1]).sum(),
            'positive_Q90_normalized_pinball': r['metrics']['primary'],
            'positive_Q50_point': point(yy[pos], qq[pos, 0]),
            'positive_Q90_point': point(yy[pos], qq[pos, 1]),
            'underprediction_GPUh': np.maximum(yy-qq[:, 1], 0).sum(),
            'overprediction_GPUh': np.maximum(qq[:, 1]-yy, 0).sum(),
            'positive_only_underprediction_GPUh': np.maximum(yy[pos]-qq[pos, 1], 0).sum(),
            'positive_only_overprediction_GPUh': np.maximum(qq[pos, 1]-yy[pos], 0).sum(),
            'coverage_identity_abs_error': residual,
            'positive_BODY_band_PASS': .9 <= cp <= .95,
            'frozen_BODY_gate_PASS': r['all_pass'], 'frozen_BODY_failure_reasons': reasons,
            'fails_only_overall_upper_95_within_BODY_gate': reasons == ['OVERALL_COVERAGE_ABOVE_95'],
            'OVERCONSERVATIVE_BODY_WARNING': r['OVERCONSERVATIVE_BODY_WARNING'],
            'monthly_frozen_BODY_checks': r['temporal']}


def main():
    reg, pre = authority(); freeze = read('V40R5_CAL_SELECTION_FREEZE.json')
    assert freeze['selected_model'] is None and read('V40R5_MODEL_SELECTION.json')['selected_model'] is None
    immutable = dict(reg['frozen_hashes']); immutable.update(freeze['artifact_hashes'])
    for name in ['V40R5_CAL_SELECTION_FREEZE.json', 'V40R5_BODY_MODEL_REPORT.json',
                 'V40R5_MODEL_SELECTION.json', 'V40R5_MODEL_FREEZE.json',
                 'V40R5_HYBRID_METRICS.json', 'V40R5_ETA_SELECTION.json',
                 'V40R5_ROBUST_ENVELOPE_R0.json', 'V40R5_ROBUST_ENVELOPE_R1.json',
                 'V40R5_ROBUST_ENVELOPE_R2.json', 'frozen_pipeline_predictions.npz']:
        p = OUT/name; immutable[p.relative_to(ROOT).as_posix()] = sha(p)
    for p, h in immutable.items(): assert sha(ROOT/p) == h, p
    a, ledger, masks = data(); y = a['y']; u = reg['burst_threshold_GPUh']
    dates = np.repeat(ledger.operating_day.astype(str).to_numpy(), 96)
    feasibility_rows = {role: feasibility(y[ix & (y <= u)]) for role, ix in masks.items()}
    whole_train = feasibility(y[masks['TRAIN']])
    paired_train = y.reshape(-1, 2).sum(1)[masks['TRAIN'][::2]]
    train_resolution_comparison = {'source': 'Consecutive original-event 15min target sums; same mature TRAIN days',
                                   'whole_target_30min_zero_fraction': float((paired_train == 0).mean()),
                                   'whole_target_15min_zero_fraction': whole_train['p_zero'],
                                   'zero_fraction_increased': float((paired_train == 0).mean()) < whole_train['p_zero']}
    trial = read('fits/PB1/result.json')['selected']['trial']
    saved = np.load(OUT/'frozen_pipeline_predictions.npz'); candidates = {}
    for run in read('fits/PB1/result.json')['trials']:
        t = run['trial']; name = f'PB1_TRIAL_{t}_BC0'
        q = np.load(OUT/'fits/PB1'/f'trial_{t}_q.npy')
        if t == trial: np.testing.assert_array_equal(q, saved['body_raw'])
        candidates[name] = {'trial': t, 'calibration': 'BC0', 'DEV_selected_trial': t == trial,
                            'scope': 'Executed frozen BODY option' if t == trial else 'Raw registered tuning trial; post-result diagnostic only',
                            'prediction_source': f'fits/PB1/trial_{t}_q.npy',
                            'roles': {role: diagnostic(y[masks[role]], q[masks[role]], u, dates[masks[role]])
                                      for role in ['CALIBRATION', 'EXPOSED_EVALUATION']}}
    name = f'PB1_TRIAL_{trial}_BC1'; q = saved['body_BC1']
    candidates[name] = {'trial': trial, 'calibration': 'BC1', 'DEV_selected_trial': True,
                       'scope': 'Existing frozen CAL log-ratio calibration; no score recalculated',
                       'prediction_source': 'frozen_pipeline_predictions.npz:body_BC1',
                       'roles': {role: diagnostic(y[masks[role]], q[masks[role]], u, dates[masks[role]])
                                 for role in ['CALIBRATION', 'EXPOSED_EVALUATION']}}
    # Reconcile the new audit with both existing registered BODY option reports.
    old = read('V40R5_BODY_MODEL_REPORT.json')['roles']
    for bc in ['BC0', 'BC1']:
        for role in ['CALIBRATION', 'EXPOSED_EVALUATION']:
            new = candidates[f'PB1_TRIAL_{trial}_{bc}']['roles'][role]
            assert new['overall_coverage'] == old[role][bc]['metrics']['coverage']['overall']['value']
            assert new['positive_BODY_coverage'] == old[role][bc]['metrics']['coverage']['positive']['value']
            assert new['frozen_BODY_gate_PASS'] == old[role][bc]['all_pass']
    answers = {}
    for role in ['CALIBRATION', 'EXPOSED_EVALUATION']:
        answers[role] = {
            'A_positive_BODY_coverage_in_90_to_95': [n for n,c in candidates.items() if c['roles'][role]['positive_BODY_band_PASS']],
            'B_only_overall_upper_95_failure_within_BODY_gate': [n for n,c in candidates.items() if c['roles'][role]['fails_only_overall_upper_95_within_BODY_gate']],
            'C_positive_BODY_coverage_also_fails': [n for n,c in candidates.items() if not c['roles'][role]['positive_BODY_band_PASS']]}
    for p,h in immutable.items(): assert sha(ROOT/p) == h, p
    assert feasibility_rows['CALIBRATION']['BODY_GATE_STRUCTURAL_INCOMPATIBILITY'] == 'YES'
    for role, answer in answers.items():
        assert answer['A_positive_BODY_coverage_in_90_to_95'] == [f'PB1_TRIAL_{trial}_BC1']
        assert answer['B_only_overall_upper_95_failure_within_BODY_gate'] == [f'PB1_TRIAL_{trial}_BC1']
        assert set(answer['C_positive_BODY_coverage_also_fails']) == {'PB1_TRIAL_0_BC0','PB1_TRIAL_1_BC0'}
    result = {'audit_type': 'USER_REQUESTED_POST_RESULT_INTERPRETATION_ONLY',
              'amendment_request_SHA256': sha(AMENDMENT), 'preregistration_commit': pre,
              'PRIMARY_RESULT': PRIMARY, 'IMPORTANT_METHODOLOGICAL_FINDING': FINDING,
              'BODY_GATE_STRUCTURAL_INCOMPATIBILITY': 'YES',
              'decision_basis': 'Actual CAL oracle BODY population; corroborated by mature TRAIN BODY population',
              'identity': 'C_overall = p_zero + (1-p_zero) * C_positive (nonnegative Q90; coverage y<=Q90)',
              'continuous_incompatibility_condition': 'p_zero > 0.5 when positive lower=0.90 and overall upper=0.95',
              'whole_mature_TRAIN_target_reference': whole_train, 'actual_BODY_populations': feasibility_rows,
              'TRAIN_resolution_zero_fraction_comparison': train_resolution_comparison,
              'denominator_warning': 'Whole TRAIN target zero fraction is not the BODY-only zero fraction; gate calculations use the latter.',
              'candidates': candidates, 'questions_A_B_C': answers,
              'candidate_completeness': {'registered_PB1_trials': len(read('fits/PB1/result.json')['trials']),
                                       'saved_raw_trials_reported': 2, 'existing_BC1_options_reported': 1,
                                       'unselected_trial_BC1': 'NOT_APPLIED_NO_NEW_CALIBRATION',
                                       'optional_PB2': 'NOT_IMPLEMENTED_NO_NEW_MODEL',
                                       'B0_B3': 'Full-target benchmarks, not registered BODY model candidates'},
              'metric_semantics': {'positive_WAPE_MAE': 'Both Q50 point forecast and Q90 reservation reported explicitly',
                                   'under_over_GPUh': 'Sums relative to Q90 over all oracle BODY intervals; positive-only sums also reported'},
              'scientific_status': 'FAIL', 'classification': read('V40R5_MODEL_SELECTION.json')['classification'],
              'selected_model': None, 'diagnostic_pipeline': freeze['frozen_diagnostic_pipeline']['id'],
              'interpretation': 'Evaluation contract incompatibility is separate from poor forecast quality; raw positive undercoverage and burst/hybrid failures remain independently observable.',
              'only_BODY_gate_claim': 'A/B answers never imply that a complete hybrid pipeline passes; detector and envelope gates are unchanged.',
              'amendment_actions': {'model_fits': 0, 'new_calibrations': 0, 'new_thresholds': 0, 'new_eta': 0,
                                    'gate_changes': 0, 'reselection': 0, 'winner_promotions': 0, 'new_revision_created': False},
              'immutable_input_result_SHA256': immutable, 'all_immutable_inputs_and_results_unchanged': True,
              'NEXT_RECOMMENDED_REVISION': NEXT, 'holds': reg['holds']}
    dump('V40R5_ZERO_INFLATION_GATE_AUDIT.json', result)
    write_proof(result)
    manifest = read('V40R5_REQUIREMENTS_MANIFEST.json')
    extra = ['V40R5_ZERO_INFLATION_GATE_AUDIT.json', 'V40R5_BODY_GATE_FEASIBILITY_PROOF.md']
    manifest['original_required_count'] = 57
    manifest['post_result_user_amendment'] = {'request_SHA256': sha(AMENDMENT), 'additional_required_artifacts': extra,
                                             'scope': 'Interpretation and audit only; frozen scientific contract unchanged'}
    for name in extra:
        if name not in manifest['required_artifacts']: manifest['required_artifacts'].append(name)
    manifest['required_count'] = len(manifest['required_artifacts']); dump('V40R5_REQUIREMENTS_MANIFEST.json', manifest)
    print(json.dumps(clean({'whole_TRAIN': whole_train, 'BODY': feasibility_rows, 'A_B_C': answers,
                           'immutable_files_unchanged': len(immutable)}), indent=2))


def write_proof(r):
    rows = ['# V40R5 BODY gate feasibility proof', '',
            'PRIMARY RESULT: '+PRIMARY, '', 'IMPORTANT METHODOLOGICAL FINDING: '+FINDING, '',
            'BODY_GATE_STRUCTURAL_INCOMPATIBILITY = YES (actual CAL BODY population).', '',
            'For a nonnegative target y and nonnegative Q90 prediction, y=0 is always covered under y<=Q90. Partitioning the oracle BODY population gives', '',
            '`C_overall = p_zero + (1-p_zero) C_positive`.', '',
            'Thus `C_positive >= .90` implies `C_overall >= .90 + .10 p_zero`. This exceeds .95 exactly when `p_zero > .50`. No alternative nonnegative predictions can satisfy both bounds for such a population. This argument is independent of model quality, calibration, or tuning.', '',
            'The whole mature TRAIN target reference and the actual BODY denominators must be distinguished:', '',
            '| Population | N | Zero N | p_zero | Min overall at positive 90% | Incompatible |',
            '|---|---:|---:|---:|---:|---|']
    for name,p in [('Whole mature TRAIN reference',r['whole_mature_TRAIN_target_reference']), *r['actual_BODY_populations'].items()]:
        rows.append(f'| {name} | {p["N"]} | {p["zero_N"]} | {p["p_zero"]:.8%} | {p["overall_min_given_positive_90"]:.8%} | {p["BODY_GATE_STRUCTURAL_INCOMPATIBILITY"]} |')
    p = r['actual_BODY_populations']['CALIBRATION']
    comp = r['TRAIN_resolution_zero_fraction_comparison']
    rows += ['', f'On the same mature TRAIN days, whole-target zero fraction rises from {comp["whole_target_30min_zero_fraction"]:.8%} at reconstructed 30min to {comp["whole_target_15min_zero_fraction"]:.8%} at 15min. The 30min diagnostic is a consecutive sum of original-event 15min labels, not a newly fitted target.', '',
             f'On the CAL empirical grid, positive covered intervals must be at least {p["required_positive_covered_min_integer"]}, but the overall upper bound permits at most {p["allowed_positive_covered_max_integer"]}. This is also an exact integer contradiction.', '',
             'The EXPOSED aggregate BODY zero fraction is below 50%, so its aggregate bounds are feasible in principle. An observed EXPOSED overall upper-bound failure is not, by itself, proof of structural incompatibility in that split. The mandatory CAL gate already prevents selection under the frozen contract.', '',
             'All existing BODY options and both registered raw tuning trials are reported below. BC1 existed only for the DEV-selected trial 0. No BC1 score is created for trial 1. PB2 was optional and not implemented. Results are diagnostics of saved predictions, never a new ranking.', '',
             '| Role / candidate | Overall | Zero-only | Positive BODY | Frozen BODY failure reasons |',
             '|---|---:|---:|---:|---|']
    for role in ['CALIBRATION','EXPOSED_EVALUATION']:
        for name,c in r['candidates'].items():
            v=c['roles'][role]
            rows.append(f'| {role} / {name} | {v["overall_coverage"]:.6%} | {v["zero_only_coverage"]:.2%} | {v["positive_BODY_coverage"]:.6%} | {", ".join(v["frozen_BODY_failure_reasons"])} |')
    rows += ['', '| Role / candidate | Positive Q90 pinball mean GPUh | Positive normalized pinball | Positive Q50 WAPE | Positive Q50 MAE GPUh | Positive Q90 WAPE | Positive Q90 MAE GPUh | Under GPUh | Over GPUh |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for role in ['CALIBRATION','EXPOSED_EVALUATION']:
        for name,c in r['candidates'].items():
            v=c['roles'][role]; q50=v['positive_Q50_point']; q90=v['positive_Q90_point']
            rows.append(f'| {role} / {name} | {v["positive_Q90_pinball_mean_GPUh"]:.6f} | {v["positive_Q90_normalized_pinball"]:.9f} | {q50["WAPE"]:.6%} | {q50["MAE"]:.6f} | {q90["WAPE"]:.6%} | {q90["MAE"]:.6f} | {v["underprediction_GPUh"]:.6f} | {v["overprediction_GPUh"]:.6f} |')
    rows += ['', 'A. Yes: PB1 trial 0 / BC1 has positive BODY coverage inside 90–95% in both CAL and EXPOSED.', '',
             'B. Yes within the BODY gate: that option fails only the overall upper 95% in each split; sample support and monthly BODY lower bounds pass. CAL is structurally incompatible. EXPOSED is feasible in principle but this saved prediction exceeds its overall upper bound. This does not establish whole-pipeline safety.', '',
             'C. PB1 trial 0 / BC0 and trial 1 / BC0 fail positive BODY coverage in CAL and EXPOSED. These observed undercoverage failures remain distinct from the mathematical evaluation-contract conflict.', '',
             'Burst detector recall, GPUh-weighted recall, captured GPUh, ECE, FPR, envelope coverage, and overreservation retain their frozen evaluations. No automatic detector PASS follows from this BODY finding. The rejected PB1_BC0_C3_R0 diagnostic pipeline remains rejected; selected_model=NONE.', '',
             'The 15-min target increased zero inflation sufficiently that the preregistered simultaneous overall and positive BODY Q90 coverage bounds became structurally incompatible. Therefore, failure of the registered BODY gate cannot be interpreted solely as evidence of poor forecast quality.', '',
             'V40R5 remains failed under its frozen preregistration; the evaluation contract will be corrected only in a separate prospective revision.', '',
             'NEXT_RECOMMENDED_REVISION='+NEXT+'. Recommendation only; no revision created or executed. Future scope is evaluation-contract correction: separate occurrence from positive BODY magnitude, treat overall coverage as diagnostic, retain burst and hybrid overreservation/safety gates. Preserve the target, cohort, splits, features, threshold, model registry/hyperparameters, May firewall and optimizer firewall.', '',
             'No model fits, new calibrations, threshold/eta changes, reselection, or winner promotion were performed for this audit. Protected input, prediction, result and frozen-contract SHA256 values were checked before and after. All operational HOLDs remain unchanged.', '',
             f'[Full audit, monthly gates, exact metrics and unchanged hashes](<{(OUT/"V40R5_ZERO_INFLATION_GATE_AUDIT.json").as_posix()}>)']
    (OUT/'V40R5_BODY_GATE_FEASIBILITY_PROOF.md').write_text('\n'.join(rows)+'\n',encoding='utf-8',newline='\n')


if __name__ == '__main__':
    main()
