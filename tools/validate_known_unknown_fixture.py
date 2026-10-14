"""Compare exact PR226 controller with repair on one named synthetic replay.

No May optimization/Canary/AC. Both paths share public requests, private service,
initial state, power model, original response equations and fixed commands.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import types
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from v42_capacity.actual import Environment
from v42_integration.actual import FrozenPowerModel
from v42_integration.experimental_actual import run_experimental_actual
from v42_integration.action_metrics import unknown_actual_metrics
from test_v42_integration_actual import request
from test_v42_experimental_control import research_provider,policy
from test_v42_known_unknown_contract import frozen

BASE='1100995086a8d202cb6b8a7308ccc6d60799bbc5'


def historical_module(relative,name,*,old_actual=False):
    raw=subprocess.check_output(['git','show',BASE+':'+relative],cwd=ROOT).decode('utf8')
    sha=hashlib.sha256(raw.encode()).hexdigest()
    if old_actual:raw=raw.replace('from .actual import','from ._pr226_actual_fixture import')
    module=types.ModuleType(name);module.__file__=str(ROOT/relative);module.__package__='v42_integration'
    sys.modules[name]=module;exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module,sha


def common(provider,selector):
    from v42_integration.experimental_qos import participation_for
    unknown_uid=next('SYNTHETIC_UNKNOWN_'+str(i) for i in range(100)
        if participation_for('SYNTHETIC_UNKNOWN_'+str(i))['membership']['FLEX40'])
    known=request('SYNTHETIC_UID_2',qos='UNCONFIRMED',protected=None,batch_eligible=None,partition='',
        requested_walltime_seconds=None,origin_unknown=False,representation_starts_seconds=tuple(range(0,86400,900)))
    unknown=request(unknown_uid,submit=900,qos='UNCONFIRMED',protected=None,batch_eligible=None,
        partition='',requested_walltime_seconds=None,representation_starts_seconds=tuple(range(0,86400,900)))
    bg=request('BG',submit=-1000,q50=900,source_site='B',compatible=('B',),origin_unknown=False,
        qos='high',protected=True,batch_eligible=False,elapsed_compute_seconds=1000,
        representation_starts_seconds=tuple(range(0,86400,900)))
    return dict(capacities={'A':8,'B':8},requests=[known,unknown],environment=Environment({known.uid:900,unknown.uid:900,'BG':10000},{'BG':9000}),
        arm='B3',qos_window_provider=provider,frozen_policy=selector,known_schedule={known.uid:dict(start_seconds=0,site='A')},
        running=[(bg,'B',-1000)],begin=0,end=1800,
        power_model=FrozenPowerModel(0.,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'NAMED_TOY_LINEAR_C1'),weather=[{}]*2)


def main(output):
    output.mkdir(parents=True,exist_ok=True)
    _,actual_sha=historical_module('v42_integration/actual.py','v42_integration._pr226_actual_fixture')
    old,adapter_sha=historical_module('v42_integration/experimental_actual.py','v42_integration._pr226_experimental_fixture',old_actual=True)
    provider=research_provider();selector=policy(provider)
    before=old.run_experimental_actual(**common(provider,selector))
    provider=research_provider();selector_c1=policy(provider)
    c1=run_experimental_actual(**common(provider,selector_c1),legacy_diagnostic=True)
    provider,selector=frozen();after=run_experimental_actual(**common(provider,selector))
    provider,selector_c3=frozen(service_reallocation=True)
    c3=run_experimental_actual(**common(provider,selector_c3))
    before_k=next(r for r in before['queue_ledger'] if r['job_uid']=='SYNTHETIC_UID_2')
    after_k=next(r for r in after['queue_ledger'] if r['job_uid']=='SYNTHETIC_UID_2')
    assert before_k['site']=='B' and after_k['site']=='A'
    assert any(r['uid']=='SYNTHETIC_UID_2' for r in before['rule_consumption_receipt'])
    assert all(r['uid']!='SYNTHETIC_UID_2' for r in after['rule_consumption_receipt'])
    assert after['receipt']['capacity_violations']==0 and after['receipt']['future_duration_controller_reads']==0
    selector.save(output/'FIXTURE_FROZEN_UNKNOWN_POLICY.json')
    selector.save(output/'UNKNOWN_FROZEN_POLICY_TABLE.json')
    selector_c3.save(output/'FIXTURE_C3_FROZEN_UNKNOWN_POLICY.json')
    np.savez_compressed(output/'FIXTURE_BEFORE_AFTER_PCC.npz',before_GPU=before['occupancy_GPU'],after_GPU=after['occupancy_GPU'],
        before_P=before['physical']['PCC_P_kw'],after_P=after['physical']['PCC_P_kw'],
        before_Q=before['physical']['PCC_Q_kvar'],after_Q=after['physical']['PCC_Q_kvar'])
    receipt=dict(PASS=True,evidence_kind='NAMED_SYNTHETIC_TWO_SLOT_SAVED_PROGRAM_REPLAY_NOT_MAY01',
        before_source_commit=BASE,before_actual_sha=actual_sha,before_adapter_sha=adapter_sha,
        before_receipt=before['receipt'],after_receipt=after['receipt'],before_Known=before_k,after_Known=after_k,
        before_QoS=before['qos_ledger'],after_QoS=after['qos_ledger'],
        before_Known_in_Unknown_policy_UIDs=len({r['uid'] for r in before['rule_consumption_receipt'] if r['uid']=='SYNTHETIC_UID_2'}),
        after_Known_in_Unknown_policy_UIDs=0,Unknown_Actual=unknown_actual_metrics(after),
        actual_PCC_delta_scope='TOTAL_TOY_REPLAY_ONLY_NOT_ISOLATED_UNKNOWN_EFFECT',
        actual_PCC_P_delta_kw=(after['physical']['PCC_P_kw']-before['physical']['PCC_P_kw']).tolist(),
        actual_PCC_Q_delta_kvar=(after['physical']['PCC_Q_kvar']-before['physical']['PCC_Q_kvar']).tolist(),
        Native_Optimize_calls=0,Fresh_AC_calls=0,new_May01_B1_Canary=False,
        new_B1_B3_Full96=False,integrated_science_performance_PASS=False)
    receipt['C0_C1_C2_C3']={label:dict(completed=result['receipt']['completed_jobs'],carryover=result['receipt']['carryout_jobs'],
        Known_entered_Unknown_UIDs=len({r['uid'] for r in result['rule_consumption_receipt'] if r['uid']=='SYNTHETIC_UID_2'}),
        Unknown=unknown_actual_metrics(result),QoS_budget_excess_UIDs=sum(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-9 for r in result['qos_ledger']),
        physical_capacity_violations=result['receipt']['capacity_violations'],policy_sha=pol.sha,
        role='NAMED_SYNTHETIC_TWO_SLOT_DIAGNOSTIC_NOT_MAY01') for label,result,pol in (
            ('C0',before,selector_c1),('C1',c1,selector_c1),('C2',after,selector),('C3',c3,selector_c3))}
    (output/'FIXTURE_BEFORE_AFTER_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(PASS=True,before_Known_site=before_k['site'],after_Known_site=after_k['site'],
        before_completed=before['receipt']['completed_jobs'],after_completed=after['receipt']['completed_jobs'],
        before_carryover=before['receipt']['carryout_jobs'],after_carryover=after['receipt']['carryout_jobs'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();main(args.output)
