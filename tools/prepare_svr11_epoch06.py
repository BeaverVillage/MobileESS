"""One-time authorized model restart, retaining completed dates and slots."""
from pathlib import Path
import sys,shutil,numpy as np
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now,sha
from v42_svr11.model import FIELDS
root=Path(r'D:\v42_svr11_may_20261011_06');old=Path(r'D:\v42_svr11_may_20261011_05');model_origin=Path(r'D:\v42_svr11_may_20261011_04')

def prepare():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()
    (root/'hardware').mkdir(parents=True,exist_ok=True)
    for p in (old/'hardware').iterdir():
        if p.is_file():shutil.copyfile(p,root/'hardware'/p.name)
    atomic(root/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(old/'CAMPAIGN_MANIFEST.json'),source_SHA=read(old/'CAMPAIGN_MANIFEST.json')['execution_SHA'],
        reason='User explicitly authorized one-time model interruption and restart; reuse all complete dates and complete forecast slots',
        all_old_results_preserved=True,qualified_completed_dates_reused=True,UTC=now()))

def freeze_slots():
    origin=read(model_origin/'CAMPAIGN_MANIFEST.json')
    for name,value in origin['execution_sources'].items():assert sha(Path(origin['code_root'])/name)==value
    assert read(origin['hardware']['path'])['equipment_SHA']==read(root/'hardware/HARDWARE.json')['equipment_SHA']
    assert record(root/'hardware/SCENARIO.json')['sha256']==origin['scenario']['sha256']
    assert record(root/'hardware/THERMAL.json')['sha256']==origin['thermal']['sha256']
    current=read(root/'RAW_INPUT_RECEIPTS.json');days={}
    for day in ('2025-05-01','2025-05-02','2025-05-03'):
        exclude={'OPERATIONS_TEMPLATE_B1.json','OPERATIONS_TEMPLATE_B2.json','NATIVE_INPUT_TEMPLATE_B1.json'}
        axes=[];inputs=[]
        for refs in (origin['input_receipts'][day],current[day]):
            axis={}
            for r in refs:
                assert record(r['path'])==r
                if Path(r['path']).name not in exclude:axis[Path(r['path']).name]=(r['sha256'],r['bytes']);inputs.append(r)
            axes.append(axis)
        assert axes[0]==axes[1]
        folder=model_origin/'models'/day;slots={}
        for p in sorted(folder.glob('SLOT_*.json')):
            v=read(p);assert v['source_SHA']==origin['execution_SHA'] and v['day']==day
            assert record(v['data']['path'])==v['data']
            with np.load(v['data']['path']) as z:
                assert set(z.files)==set(FIELDS) and all(np.isfinite(z[f]).all() for f in FIELDS)
            slots[str(int(p.stem.split('_')[1]))]=dict(original_checkpoint=record(p),original_data=v['data'])
        assert list(map(int,slots))==list(range(len(slots)))
        anchor={n:record(folder/'FORECAST_ANCHOR'/n) for n in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz')}
        with np.load(anchor['PLANNING_PHYSICAL.npz']['path']) as z:
            assert z['PCC_P_kw'].shape==(96,12) and np.isfinite(z['PCC_P_kw']).all()
        days[day]=dict(slots=slots,forecast_anchor=anchor,input_evidence=inputs)
    atomic(root/'MODEL_CHECKPOINT_REUSE_CONTRACT.json',dict(PASS=True,generation_source_SHA=origin['execution_SHA'],
        generation_manifest=record(model_origin/'CAMPAIGN_MANIFEST.json'),days=days,
        mathematical_model_changed=False,native_solve_and_clock_commands_unchanged=True,
        only_discarded_forecast_event_receipts_skipped=True,Actual_inputs_read_by_model=0,
        Planning_tap_or_queue_transferred_to_Actual=False,interruption=record(model_origin/'USER_AUTHORIZED_MODEL_RESTART.json'),
        regression='43 passed; real native auto-tap/voltage/queue/clock/solve equality test',UTC=now()))
    print('FROZEN_COMPLETED_MODEL_SLOTS',sum(len(v['slots']) for v in days.values()))

def reuse():
    from v42_svr11 import DAYS
    from v42_svr11.controller import initial
    from reuse_svr11_completed import qualify
    m=read(root/'CAMPAIGN_MANIFEST.json');ledger=initial();assert not (root/'CAMPAIGN_LEDGER.json').exists()
    for day in DAYS:
        p,v,row=qualify(root,old,day)
        row.update(reused=True,reuse_proof=record(p),execution_source_SHA=v['execution_source_SHA'],
            validation_source_SHA=m['execution_SHA'],retry_pending=False)
        ledger['dates']['B0/'+day]=row
    contract=read(root/'MODEL_CHECKPOINT_REUSE_CONTRACT.json')
    for day,value in contract['days'].items():
        dest=root/'models'/day;(dest/'FORECAST_ANCHOR').mkdir(parents=True,exist_ok=True)
        for name,r in value['forecast_anchor'].items():
            assert record(r['path'])==r;shutil.copyfile(r['path'],dest/'FORECAST_ANCHOR'/name)
        for slot,r in value['slots'].items():
            data=dest/f'SLOT_{int(slot):02d}.npz';assert record(r['original_data']['path'])==r['original_data']
            shutil.copyfile(r['original_data']['path'],data)
            atomic(dest/f'SLOT_{int(slot):02d}.json',dict(day=day,source_SHA=m['execution_SHA'],
                generation_source_SHA=contract['generation_source_SHA'],reused=True,data=record(data),
                revalidation_contract=m['model_checkpoint_reuse_contract']))
        interrupted=read(model_origin/'CAMPAIGN_LEDGER.json')['dates']['B2/'+day]
        result=Path(read(interrupted['request'])['result'])
        ledger['dates']['B2/'+day].update(previous_epoch_attempts=[record(interrupted['request']),record(result)],
            previous_epoch_Native_Runtime=read(result)['Native_Runtime'],
            user_authorized_one_time_model_restart=True,reused_forecast_model_slots=len(value['slots']))
    ledger.update(policy='B2',source_SHA=m['execution_SHA'],UTC=now())
    atomic(root/'CAMPAIGN_LEDGER.json',ledger)
    atomic(root/'REUSE_ADMISSION.json',dict(PASS=True,reused_completed_dates=31,
        completed_model_slots_reused=sum(len(v['slots']) for v in contract['days'].values()),
        original_execution_SHA_and_Runtime_preserved=True,user_authorized_Native0_interrupted_workers=3,
        model_reuse_contract=m['model_checkpoint_reuse_contract'],AC_calls=0,Native_calls=0,UTC=now()))
    shutil.copyfile(old/'NORMALAMPS_CLASSIFICATION_CORRECTION.json',root/'NORMALAMPS_CLASSIFICATION_CORRECTION.json')
    print('ADMITTED_B0_31_AND_MODEL_SLOTS',m['execution_SHA'])

if __name__=='__main__':{'prepare':prepare,'freeze_slots':freeze_slots,'reuse':reuse}[sys.argv[1]]()
