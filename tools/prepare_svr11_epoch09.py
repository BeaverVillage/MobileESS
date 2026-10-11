"""One justified physical placement change; no old numerical result promotion."""
from pathlib import Path
import sys,copy,json,psutil,subprocess
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now,digest,sha
from v42_svr11.processes import live,workers
root=Path(r'D:\v42_svr11_may_20261011_09');old=Path(r'D:\v42_svr11_may_20261011_08')

def stage():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists() and not (root/'EQUIPMENT_CHANGE_CONTRACT.json').exists()
    m=read(old/'CAMPAIGN_MANIFEST.json');ledger=read(old/'CAMPAIGN_LEDGER.json');evidence=[];failures=[]
    for day in ('2025-05-04','2025-05-05'):
        path=Path(ledger['dates']['B2/'+day]['result']);r=read(path)
        assert r['source_SHA']==m['execution_SHA'] and r['status']=='FAIL' and r['reason']=='ACTUAL:VOLTAGE_VIOLATION'
        assert r['FULL_feasible_certified'] and r['Actual_PQ_repair']==r['Actual_reoptimization']==0
        ar=next(x for x in r['metrics']['evidence'] if 'ACTUAL' in x['path']);a=read(ar['path'])
        assert record(ar['path'])==ar and record(a['slots_receipt']['path'])==a['slots_receipt']
        slots=read(a['slots_receipt']['path']);assert [x['slot'] for x in slots]==list(range(96))
        bad=[(s,n) for s in slots for n in s['physical']['nodes'] if not .95<=n['voltage_pu']<=1.05]
        assert len(bad)==1 and bad[0][1]['node_phase']=='svr_bus82_series_input.1'
        s,n=bad[0];v={x['node_phase']:x['voltage_pu'] for x in s['physical']['nodes']}
        bank=next(x for x in s['svr']['devices'] if x['id']=='BUS82');phase=bank['phases'][0]
        env=r['metrics']['environments']['ACTUAL']
        assert .95<=v['81.1']<=1.05 and .95<=v['82.1']<=1.05 and v[n['node_phase']]>v['81.1']
        assert env['line_current_violations']==env['transformer_current_violations']==env['transformer_kVA_violations']==0
        assert env['AC_converged'] and env['control_complete'] and env['SVR11_finite_rating_and_taps']
        failures.append(dict(day=day,slot=s['slot'],node=n['node_phase'],voltage=n['voltage_pu'],
            upstream_Bus81A=v['81.1'],controlled_Bus82A=v['82.1'],tap=phase['tap'],
            W1_Q_into_kvar=phase['terminals'][0]['Q_into_kvar'],result=record(path)))
        evidence.extend([record(path),ar,a['slots_receipt']])
    evidence.extend([record(old/'LINE82_PRIMARY_VOLTAGE_CAUSE_AUDIT.json'),m['hardware'],m['scenario'],m['thermal'],record(old/'CAMPAIGN_MANIFEST.json')])
    contract=dict(schema='SVR11_REPEATED_PRIMARY_PLACEMENT_CORRECTION_V1',confirmed_repeated_physical_failure=True,
        failed_dates=failures,protected_evidence=evidence,origin_source_SHA=m['execution_SHA'],
        origin_equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],SVR_count=11,
        change=dict(bank='BUS82',element='Line.l82',old_terminal=2,new_terminal=1,
            old_path='Bus81 -> original line82 -> unregulated bank input -> SVR8 -> controlled Bus82',
            new_path='Bus81 -> same SVR8 -> controlled line82 input -> original line82 -> remote sensed Bus82',
            sensed_nodes=['82.1','82.2','82.3'],rating_or_control_settings_changed=False,additional_SVRs=0),
        justification='Two current-epoch actual dates fail on the same unregulated line82 receiving-side primary; Bus81 and controlled Bus82 pass. Historical same-branch failures and all96 positive rises are preserved. Move the existing bank before the preserved line so the receiving-side primary is no longer an unregulated intermediate node. No separated attribution or monthly success is claimed.',
        Native_policy_or_budget_change=False,voltage_limits=[.95,1.05],Actual_repair_or_reoptimization=0,
        old_results_or_models_promoted=0,raw_inputs_and_domain_descriptors_reused=True,
        affected_results='Network-coupled physics changes; all124 official policy/date Planning/Actual/Fresh must be recalculated under the new common equipment. Preserve every prior result and checkpoint separately.',
        retrospective_design=True,independent_holdout_claim=False,precampaign_monthly_canary=False,UTC=now())
    atomic(root/'EQUIPMENT_CHANGE_CONTRACT.json',contract)
    from v42_svr11.prepare import raw
    raw(root)
    print(json.dumps(dict(status='STAGED_NOT_RELEASED',failed_dates=failures,old_workers_terminated=0),ensure_ascii=False))

def freeze():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()
    from v42_svr11.freeze import prepare
    h=prepare(root/'hardware')
    origin=read(old/'hardware/SCENARIO.json')['svr']['units'];units=read(root/'hardware/SCENARIO.json')['svr']['units']
    fields={'cut_terminal','original_bus_spec','series_orientation','upstream_new_bus','engineering_assumptions'}
    assert len(units)==11 and [x['id'] for x in units]==[x['id'] for x in origin]
    for a,b in zip(origin,units):
        if a['id']=='BUS82':assert {k:v for k,v in a.items() if k not in fields}=={k:v for k,v in b.items() if k not in fields}
        else:assert a==b
    assert h['equipment_SHA']!=read(old/'hardware/HARDWARE.json')['equipment_SHA']
    assert h['monthly_zero_violation_certification'] is False
    print(json.dumps(dict(status='MINIMUM_COMPILE_AND_ONE_TIMESTAMP_SMOKE_PASS',equipment_SHA=h['equipment_SHA'],monthly_safety_certified=False)))

def handoff():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()
    h=read(root/'hardware/HARDWARE.json');assert h['PASS'] and h['SVR_count']==11
    assert record(h['equipment_change_contract']['path'])==h['equipment_change_contract']
    m=read(old/'CAMPAIGN_MANIFEST.json');sup=read(old/'SUPERVISOR_PROCESS.json')
    assert live(sup) and sup['source_SHA']==m['execution_SHA']
    p=psutil.Process(sup['PID']);assert p.status()!=psutil.STATUS_STOPPED
    # Each process inventory validates its own checkout's frozen authority.
    # Never execute predecessor inventory through the successor's ROOT.
    for name,expected in m['execution_sources'].items():assert sha(Path(m['code_root'])/name)==expected
    code="from pathlib import Path;import json;from v42_svr11.processes import workers;from v42_pr134_b1.common import read;root=Path(r'D:\\v42_svr11_may_20261011_08');m=read(root/'CAMPAIGN_MANIFEST.json');print(json.dumps(workers(root,m['execution_SHA'])))"
    peers=json.loads(subprocess.check_output([sys.executable,'-B','-X','utf8','-c',code],cwd=m['code_root'],encoding='utf8'))
    p.suspend()
    q=old/'DISPATCH_QUIESCENCE_FOR_LINE82_PLACEMENT.json'
    assert not q.exists()
    atomic(q,dict(PASS=True,root=str(old),source_SHA=m['execution_SHA'],process=sup,new_dispatch_quiesced=True,
        worker_terminated=0,current_workers_preserved=peers,equipment_change_contract=record(root/'EQUIPMENT_CHANGE_CONTRACT.json'),
        reason='Validated minimum placement implementation; healthy workers finish under unchanged Epoch08 before common physical Epoch09 begins',UTC=now()))
    # A Worker may finish naturally between inventory and this receipt.
    assert all(not live(w) or psutil.Process(w['PID']).status()!=psutil.STATUS_STOPPED for w in peers)
    atomic(root/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(old/'CAMPAIGN_MANIFEST.json'),source_SHA=m['execution_SHA'],dispatch_quiescence=record(q),
        physical_equipment_change=True,qualified_completed_dates_reused=False,all_old_results_preserved=True,
        reason='Repeated genuine primary voltage failures justify one existing-bank placement correction; all affected scientific physics/results need a separate common epoch',UTC=now()))
    from v42_svr11.prepare import release
    from v42_svr11.controller import initial
    new=release(root);atomic(root/'CAMPAIGN_LEDGER.json',initial())
    assert new['fresh_all_124_physical_results_required'] and 'model_checkpoint_reuse_contract' not in new
    print(json.dumps(dict(status='FROZEN_WAIT_HEALTHY_PREDECESSOR_DRAIN',source_SHA=new['execution_SHA'],root=str(root),
        workers_preserved=[w['PID'] for w in peers],old_numerical_results_promoted=0),ensure_ascii=False))

if __name__=='__main__':{'stage':stage,'freeze':freeze,'handoff':handoff}[sys.argv[1]]()
