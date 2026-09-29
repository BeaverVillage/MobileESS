"""User-instruction compliance correction; original scientific thresholds stay frozen."""
from common16 import *
assert not (ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json').exists()
assert not list(LOCAL.glob('runtime_fold*'))
write('EXECUTION_ROUTING_CORRECTION.json',dict(time=now(),original_preregistration=rec(ROOT/'PREREGISTRATION.json'),
    user_instruction='USER_REQUEST sections30,43: STOP entire program only if ALL specified no-information conditions hold; Fail closed only at explicitly defined scientific stop conditions.',
    error='Assistant preregistration introduced an extra gray-zone no-bridge rule not required by the user. Original preregistration is retained byte-for-byte.',
    correction='If full primary STOP fires, no bridge. If it does not fire, freeze the native verdict and continue the already specified source-authority bridge and at most R16-A/B/C. Strict native success is still reported separately and is NOT relabelled as passed in a gray zone.',
    new_scientific_thresholds=False,Runtime_safety_gate_changes=False,native_success_threshold_changes=False,
    model_parameters_or_fold_changes=False,additional_challenger_arms=False,
    timing='After native fold1 and some fold2 results; before native pooled verdict or any bridge models. This is a disclosed instruction-compliance routing amendment, not an unseen pre-result registration.',
    observed_result_files=[rec(p) for p in sorted(LOCAL.glob('native_fold*/*.json')) if p.name in ['D0.json','D1.json','D2.json','D3.json','D4.json']]))
print('USER_ROUTING_CORRECTION_RECORDED',flush=True)
