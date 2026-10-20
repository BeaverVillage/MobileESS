"""Retain every original completed M1 replay; admit the new tight M1 only."""
from pathlib import Path
import inspect, textwrap
from v44.common import read, verify, record, atomic
from v44_recovery_r029 import parent_admission as original
from v44_recovery_r030.m1_voltage import POLICY, LOWER, UPPER

PARENT = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt014')


def compile_validate():
    source = textwrap.dedent(inspect.getsource(original.validate))
    old = "('2025-05-02','B3','M1','attempt001')"
    if source.count(old) != 1:
        raise ValueError('R032_COMPLETED_M1_PARENT_ADMISSION_BOUNDARY_DRIFT')
    source = source.replace(old, "('2025-05-02','B3','M1','attempt014')")
    namespace = dict(original.validate.__globals__)
    exec(compile(source, __file__+'.generated', 'exec'), namespace)
    return namespace['validate']


def validate(parent, output, current_request=None):
    parent = Path(parent)
    if parent.resolve() != PARENT.resolve():
        raise PermissionError('R032_EXACT_TIGHT_M1_COMPLETED_PARENT_REQUIRED')
    result = read(parent/'M1/RESULT.json')
    policy = result['B3_M1_voltage_policy']
    verify([policy['rows'], policy['plan_validation'], policy['amendment']])
    proof = read(policy['plan_validation']['path'])
    if (policy['policy'] != POLICY or (policy['lower_pu'],policy['upper_pu']) != (LOWER,UPPER)
            or not proof['PASS'] or not read(policy['rows']['path'])['PASS']):
        raise PermissionError('R032_R030_TIGHT_M1_PROOF_REQUIRED')
    answer = compile_validate()(parent, output, current_request)
    answer.update(r032_same_completed_tight_M1=True, tight_M1_band=[LOWER,UPPER],
        tight_voltage_proof=policy['plan_validation'], exact_parent=record(parent/'M1/RESULT.json'))
    atomic(Path(output)/'R032_COMPLETED_M1_COMPATIBILITY.json', answer)
    return answer
