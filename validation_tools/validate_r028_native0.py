"""Verify the real failed Planning and P1 evidence without native optimization."""
from pathlib import Path
from collections import defaultdict
from fractions import Fraction as F
from copy import deepcopy
import json
import numpy as np
import v44_recovery_r028
from v44.common import read,record,verify,atomic,now
from v44_recovery_r028.planning_reuse import load_state
from v44_recovery_r028.integer_repair import fixed_snapshot
from v44_recovery_r028.voltage_policy import authority
from v42_a_stage_practical.integer_model import restore_types
from v42_may_campaign_native90.budget import DateBudget
from v44_recovery_r026f1.operations import validate as validate_original

root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
out=Path('D:/MobileESS_V44/development/r028_native0_20261018_fix1');out.mkdir(exist_ok=False)
original=validate_original()
parent=root/'2025-05-06/B1/attempt001/A1'
request=dict(read(parent/'request.json'),planning_repair_parent=str(parent),output=str(out/'OUTPUT'))
Path(request['output']).mkdir()
budget=DateBudget(out/'NATIVE_RUNTIME_LEDGER.json',native_limit=5400.)
state,priced=load_state(request,budget)
typed,types=restore_types(state,state['global_types'])
identity=read(parent/'OUTPUT/P1/INTEGER_CONTROL/MODEL_IDENTITY.json')
assert typed.fingerprint()==identity['original_snapshot_sha256'] and types['PASS']
producer=read(parent/'OUTPUT/A_RESULT.json');ref=producer['incumbent']['point'];verify([ref])
with np.load(ref['path'],allow_pickle=False) as z:point=z['X']
fixed,integer,residual=fixed_snapshot(typed,point)
assert fixed.matrix is typed.matrix and fixed.rhs is typed.rhs
assert np.array_equal(fixed.lower[~integer],typed.lower[~integer])
assert np.array_equal(fixed.upper[~integer],typed.upper[~integer])
assert np.array_equal(fixed.lower[integer],fixed.upper[integer])
assert fixed.objectives is typed.objectives
gap=(F(producer['exact_UB'])-F(producer['exact_LB']))/abs(F(producer['exact_UB']))
assert 0<=gap<=F(5,1000)
v=authority();assert v['maximum_relaxation_pu']==.005
assert F('0.945')**2==F('0.893025') and F('1.055')**2==F('1.113025')
assert v['M2_lower_pu']==v['Actual_Fresh_lower_pu']==.95
assert v['M2_upper_pu']==v['Actual_Fresh_upper_pu']==1.05

a2=root/'2025-05-02/B3/attempt012/A2';ledger=read(a2/'NATIVE_RUNTIME_LEDGER.json')
groups=defaultdict(lambda:dict(calls=0,Native_seconds=0.))
for call in ledger['calls']:
 g=groups[call['component']];g['calls']+=1;g['Native_seconds']+=call['Native_Runtime'] or 0.
trace=read(a2/'OUTPUT/P1_TRACE.json')['trajectory']
last=read(a2/'OUTPUT/P1/S17/PRICE/FULL_PRICING_RESULT.json')
activation=read(a2/'OUTPUT/P1/S17/ACTIVATION.json')
proof=dict(UTC=now(),PASS=True,Native_optimization_calls=0,original_active_sources_verified=True,
 original_permit_source_sha=original['autonomous_recovery_policy_sha'],
 May06=dict(parent=record(parent/'OUTPUT/A_RESULT.json'),typed_snapshot_sha=typed.fingerprint(),
   fixed_snapshot_sha=fixed.fingerprint(),integer_residual=residual,original_integer_decisions_preserved=True,
   original_rows_objectives_continuous_bounds_unchanged=True,original_certified_gap=float(gap),
   inherited_Native_seconds=budget.used(),reuse_admission=record(Path(request['output'])/'R028_PLANNING_REUSE_ADMISSION.json'),
   repair_solve_and_full_physical_acceptance_still_required=True),
 voltage_policy=v,
 May02=dict(ledger=record(a2/'NATIVE_RUNTIME_LEDGER.json'),total_Native_seconds=ledger['measured_Native_Runtime'],
   components=dict(groups),Phase_I=read(a2/'OUTPUT/PHASE_I_NATIVE_BUDGET.json'),
   completed_P1_rounds=len(trace),first_LP_objective=trace[0]['objective'],last_LP_objective=trace[-1]['objective'],
   last_full_domain_LB=str(F(trace[-1]['valid_LB'])),last_negative_blocks=last['negative_blocks'],
   last_activated_blocks=len(activation['selected']),original_activation_cap=64,
   P1_slowdown_diagnosis=['INCLUSION_VERIFIED_PRIMAL_WAS_DISCARDED_AFTER_ACTIVATION',
       'NO_LOCAL_PRICING_SAME_MATRIX_BASIS_REUSE','FULLY_PRICED_NEGATIVE_SUPPORT_TRUNCATED_TO64'],
   new_P1_cold_vs_warm_speedup_measured=False,new_P1_PASS_claimed=False))
atomic(out/'VALIDATION.json',proof)
print(json.dumps(dict(PASS=True,May06_rows=typed.matrix.shape[0],May06_columns=typed.matrix.shape[1],
    inherited_Native_seconds=budget.used(),May02_components=dict(groups),
    last_negative_blocks=last['negative_blocks'],last_activated_blocks=len(activation['selected']),
    voltage_band=[v['lower_pu'],v['upper_pu']],proof=str(out/'VALIDATION.json'))))
