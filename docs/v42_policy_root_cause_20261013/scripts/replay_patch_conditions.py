"""Same public controlled inputs under V5 snapshot or follow-up runtime code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('fixed_public_fixture', ROOT/'tests/test_v42_integration_sensitivity_policy.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
from v42_integration.sensitivity_policy import FrozenSensitivityPolicy
from v42_integration.policy import ReservationLedger

source = ROOT/'v42_integration/sensitivity_policy.py'
placement_path = Path('D:/v42_integration_validation_20261013/POLICY_V5_OFFLINE_FIXTURE/PLACEMENT_BENEFIT/OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json')
policy = FrozenSensitivityPolicy.load(placement_path)
cases = []
for batch in (True, None, False):
    meta = f.metadata()
    meta['batch_eligible'] = batch
    rec = f.receipt(0)
    selected = policy.select(meta, rec, 0, ReservationLedger({'A': 8, 'B': 8}), reserve=False)
    cases.append(dict(name='ZERO_DELAY_PREPLACE_BATCH_'+str(batch), public_input_sha=hashlib.sha256(
        json.dumps(dict(metadata=meta, receipt=rec), sort_keys=True).encode()).hexdigest(), selected=selected))
for permission in (False, True):
    meta = f.metadata()
    meta.update(source_site=None, can_prestart_place=permission)
    rec = f.receipt(0)
    cases.append(dict(name='SOURCE_NONE_PREPLACE_PERMISSION_'+str(permission), public_input_sha=hashlib.sha256(
        json.dumps(dict(metadata=meta, receipt=rec), sort_keys=True).encode()).hexdigest(), selected=policy.select(
            meta, rec, 0, ReservationLedger({'A': 8, 'B': 8}), reserve=False)))

values = f.fixture(profile='placement', q90_extra=3)
values[5]['time_slots'] = [2]
compiled = f.compile_fixture(values)
template = compiled.document['templates'][0]
input_payload = dict(envelope=values[1], q50=values[2].tolist(), q90=values[3].tolist(), kernel=values[4],
                     prototype=values[5], bindings=values[6], authority=values[7])
cases.append(dict(name='PAST_ONLY_Q90_CAPACITY_AT_EVENT_SLOT2', public_input_sha=hashlib.sha256(
    json.dumps(input_payload, sort_keys=True).encode()).hexdigest(), ordered_actions=len(template['ordered_actions']),
    numeric_candidates=len(template['scenario_comparisons']), source_policy_sha=compiled.sha,
    numeric_hard_pass=sum(c['hard_feasible'] for c in template['scenario_comparisons'])))
for stress_slot in (2, 3, 95):
    values = f.fixture(profile='placement', q90_extra=3)
    values[5]['time_slots'] = [2]
    stress = np.zeros((96, 2))
    stress[stress_slot, 1] = 12
    values[-1].update(stress_site_GPU=stress.tolist(), stress_allocation_source='A_STAGE_OPTIMIZED_RESERVE',
                      allocation_aidc_anchor=values[-2]['aidc_anchor'],
                      stress_profile_GPU=stress.sum(axis=1).tolist(), stress_carryout_GPUh=0.)
    controlled = f.compile_fixture(values)
    template = controlled.document['templates'][0]
    input_payload = dict(envelope=values[1], q50=values[2].tolist(), q90=values[3].tolist(), kernel=values[4],
                         prototype=values[5], bindings=values[6], authority=values[7])
    cases.append(dict(name='CURRENT_FUTURE_Q90_CAPACITY_SLOT_'+str(stress_slot), public_input_sha=hashlib.sha256(
        json.dumps(input_payload, sort_keys=True).encode()).hexdigest(), ordered_actions=len(template['ordered_actions']),
        numeric_candidates=len(template['scenario_comparisons']), source_policy_sha=controlled.sha,
        numeric_hard_pass=sum(c['hard_feasible'] for c in template['scenario_comparisons'])))
real = FrozenSensitivityPolicy.load('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json')
body = dict(schema='CONTROLLED_BEFORE_AFTER_REPLAY_SIDE_V1', source_root=str(ROOT),
            runtime_source_sha=hashlib.sha256(source.read_bytes()).hexdigest(), cases=cases,
            frozen_real_V5_policy_load_identical_sha=real.sha,
            frozen_real_V5_policy_status=real.document['status'],
            frozen_real_V5_ordered_actions=sum(len(t['ordered_actions']) for t in real.document['templates']),
            source_case_inputs_changed=False, forecast_model_or_values_changed=False,
            Native_Optimize_calls=0, production_Actual_runs=0, Fresh_AC_runs=0)
OUT.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'root':str(ROOT), 'source_sha':body['runtime_source_sha'],
                  'actions':[(c['name'],c.get('selected',{}).get('action'),c.get('ordered_actions')) for c in cases]}))
