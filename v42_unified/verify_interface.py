"""Independent edge check directly against original freeze/certificates/arrays."""
from fractions import Fraction
from v42_native.contracts import digest


def verify(handoff, freeze, identity, certificates, replay, source_sha256, control_names):
    a = handoff['anchor']
    if handoff['schema'] != 'V42_A1_P1_ONLY_TO_M1_V1' or handoff['anchor_sha256'] != digest(a):
        raise ValueError('INTERFACE_HASH_OR_SCHEMA_DRIFT')
    if handoff['P2_certificate'] is not None or a['P2_certificate'] is not None or a['P2_objectives_optimized'] is not False:
        raise ValueError('P2_NOT_CERTIFIED')
    if a['A1_ACCEPTED'] is not False or handoff['A1_ACCEPTED'] is not False or a['A1_P1_ONLY_ACCEPTED'] is not True:
        raise ValueError('ACCEPTANCE_SCOPE_CHANGED')
    if freeze['state'] != 'A1_P1_ONLY_ACCEPTED' or not all(certificates[k]['PASS'] is True for k in certificates):
        raise ValueError('ORIGINAL_PROOFS_NOT_PASS')
    c = certificates['closure']
    if c['classes'] != 130 or c['complete_STAY_and_migration_coverage'] is not True:
        raise ValueError('FULL_DOMAIN_NOT_CERTIFIED')
    L, U = Fraction(certificates['bound']['exact_LB']), Fraction(certificates['integer']['exact_UB'])
    if U < L or U < 0 or not (U == L == 0 or U > 0 and (U-L)/U <= Fraction(1,200)):
        raise ValueError('ORIGINAL_GLOBAL_GAP_FAILED')
    if Fraction(a['exact_P1']['exact_LB']) != L or Fraction(a['exact_P1']['exact_UB']) != U:
        raise ValueError('INTERFACE_GLOBAL_BOUND_DRIFT')
    expected_hashes = {r['axis']:r['expected']['sha256'] for r in identity['files']}
    checks = dict(
        original_day=a['day'] == freeze['day'] == identity['day'],
        original_input_hashes=a['input_authority_hashes'] == expected_hashes,
        grid_arrays=a['grid_array_identities'] == identity['original_grid_array_identities'],
        workload_axes=a['workload_axis_identities'] == identity['original_workload_axis_identities'],
        selected_jobs=a['selected_jobs'] == freeze['selected_jobs'],
        selected_job_hash=a['selected_jobs_sha256'] == digest(freeze['selected_jobs']),
        controls=a['controls'] == freeze['controls'],
        control_names=a['control_names'] == list(control_names),
        AIDC_constants=a['fixed_AIDC_control_columns'] == [i for i,n in enumerate(control_names) if n.startswith('aidc_load_kw[')],
        source_identity=a['source_freeze_sha256'] == source_sha256,
        zero_AIDC_decision_variables=a['M1_AIDC_decision_variables'] == 0,
        no_AIDC_Q_variable=a['AIDC_Q_decision'] is False,
        original_integer_and_physical=replay['PASS'] is True and replay['exact_UB'] == str(U),
        no_downstream_acceptance=handoff['downstream_accepted'] is False and handoff['allowed_next_stage'] == 'M1',
    )
    if not all(checks.values()):
        raise ValueError('INDEPENDENT_INTERFACE_FAILED:'+','.join(k for k,v in checks.items() if not v))
    return dict(PASS=True, checks=checks, source_sha256=source_sha256, exact_LB=str(L), exact_UB=str(U),
                exact_gap=str((U-L)/U if U else Fraction(0)), original_classes=130,
                original_jobs=len(freeze['selected_jobs']), native_optimize_calls=0,
                production_handoff_builder_called=False, P2_certified=False)
