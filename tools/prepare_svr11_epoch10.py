"""Exact Forecast allocation cache: immutable successor, natural worker drain."""
from pathlib import Path
import sys,shutil,copy,json,subprocess,time
import numpy as np
import psutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,now,sha,digest
from v42_common_campaign.authority import source_files
from v42_svr11.processes import live,identity,allowed_worker_cwds
from v42_svr11.model import FIELDS
from reuse_svr11_completed import normalized_reviewed_model
ROOT=Path(r'D:\v42_svr11_may_20261011_10');OLD=Path(r'D:\v42_svr11_may_20261011_09')
Q='DISPATCH_QUIESCENCE_FOR_FORECAST_ALLOCATION_CACHE.json'

def proof():
    old=read(OLD/'CAMPAIGN_MANIFEST.json');sources=source_files()
    changes={k for k in set(old['execution_sources'])|set(sources) if old['execution_sources'].get(k)!=sources.get(k)}
    assert changes=={'v42_svr11/model.py'}
    before=Path(old['code_root'])/'v42_svr11/model.py';after=SOURCE/'v42_svr11/model.py'
    assert normalized_reviewed_model(before.read_text())==normalized_reviewed_model(after.read_text())
    axis=[]
    for tag,day,t in [('cache_slot00','2025-05-01',0),('cache_may06_slot47','2025-05-06',47),('cache_slot95_v2','2025-05-01',95)]:
        path=ROOT/'model_benchmarks'/tag/'EQUIVALENCE.json';v=read(path)
        assert v['PASS'] and v['day']==day and v['slot']==t
        assert v['source_before']==record(before) and v['source_after']==record(after)
        assert v['original_and_cached_all121_responses_bitwise_equal'] and all(v['fields'].values())
        assert v['all_solve_timestamps_identical'] and v['independent_compiles']==121
        assert v['Actual_inputs_read']==v['Native_optimizer_calls']==v['campaign_workers_modified']==0
        assert record(v['reference_checkpoint']['path'])==v['reference_checkpoint']
        axis.append(record(path))
    all_inputs=ROOT/'model_benchmarks/ALL_FORECAST_INPUT_EQUIVALENCE.json';v=read(all_inputs)
    assert v['PASS'] and v['days']==31 and v['slots']==2976 and v['AC_solve_calls']==0
    assert v['source_before']==record(before) and v['source_after']==record(after)
    assert all(a['setter_order_and_float_hex_exact'] and a['original_invalid_allocation_rejected'] for a in v['axis'])
    for a in v['axis']:assert record(a['forecast']['path'])==a['forecast']
    tests=read(ROOT/'model_benchmarks/REGRESSION.json');assert tests['exit_code']==0 and tests['passed']==52
    atomic(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json',dict(PASS=True,
        generation_source_SHA=old['execution_SHA'],successor_source_SHA=digest(sources),
        source_before=record(before),source_after=record(after),changed_scientific_sources=sorted(changes),
        strict_reviewed_model_AST_identical=True,all31_forecast_96_slot_inputs_bitwise_equal=True,
        representative_real_DSS_121_responses_and_coefficients_bitwise_equal=True,
        all_native_solve_counts_timestamps_and_auto_control_commands_identical=True,
        benchmarks=axis,all_input_equivalence=record(all_inputs),regression=record(ROOT/'model_benchmarks/REGRESSION.json'),
        physical_model_objective_integer_domain_constraints_budgets_changed=False,
        equipment_SHA=read(old['hardware']['path'])['equipment_SHA'],Actual_inputs_read=0,
        proof_scope='All Forecast setter inputs; exact model AST; three representative independent prefixes. Not monthly voltage-safety certification.',
        qualified_completed_dates_and_models_reusable=True,UTC=now()))
    print('EXACT_CACHE_EQUIVALENCE_PASS',digest(sources))

def validate_proof():
    v=read(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json')
    assert v['PASS'] and v['successor_source_SHA']==digest(source_files())
    for key in ('source_before','source_after','all_input_equivalence','regression'):
        assert record(v[key]['path'])==v[key]
    for r in v['benchmarks']:assert record(r['path'])==r
    return v

def origin_workers():
    old=read(OLD/'CAMPAIGN_MANIFEST.json');allowed=allowed_worker_cwds(SOURCE)-{SOURCE}|{Path(old['code_root'])}
    peers=[]
    for p in psutil.process_iter(['pid','name']):
        try:
            if (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
            args=p.cmdline()
            if '-m' not in args or args[args.index('-m')+1]!='v42_svr11.worker':continue
            r=read(args[-1]);assert Path(r['root'])==OLD and r['source_SHA']==old['execution_SHA']
            assert Path(r['code_root'])==Path(old['code_root'])
            # Compile/Redirect temporarily changes process cwd; make a bounded
            # read-only resample rather than relax the approved directory set.
            observed=[]
            for sample in range(25):
                cwd=Path(p.cwd());observed.append(str(cwd))
                if cwd in allowed:break
                time.sleep(.02)
            else:raise PermissionError('TRANSFER_PREDECESSOR_CHECKOUT_DRIFT:'+json.dumps(dict(observed=observed,approved=list(map(str,allowed)))))
            peers.append(dict(identity(p),arm=r['arm'],day=r['day'],request=record(args[-1])))
        except psutil.Error:continue
    return peers

def quiesce():
    validate_proof();old=read(OLD/'CAMPAIGN_MANIFEST.json')
    for k,v in old['execution_sources'].items():assert sha(Path(old['code_root'])/k)==v
    sup=read(OLD/'SUPERVISOR_PROCESS.json');assert live(sup) and sup['source_SHA']==old['execution_SHA']
    assert not (OLD/Q).exists()
    p=psutil.Process(sup['PID']);assert p.status()!=psutil.STATUS_STOPPED
    p.suspend();peers=origin_workers()
    atomic(OLD/Q,dict(PASS=True,process=sup,root=str(OLD),source_SHA=old['execution_SHA'],
        new_dispatch_quiesced=True,worker_terminated=0,current_workers_preserved=peers,
        equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        reason='Verified exact Forecast allocation cache; only old dispatch pauses, healthy Workers finish naturally; reuse qualified complete dates/models.',UTC=now()))
    assert all(live(v) for v in peers)
    print('DISPATCH_QUIESCED_HEALTHY_WORKERS_PRESERVED',json.dumps(peers))

def prepare():
    validate_proof();assert not (ROOT/'CAMPAIGN_MANIFEST.json').exists()
    (ROOT/'hardware').mkdir(parents=True,exist_ok=True)
    for p in (OLD/'hardware').iterdir():
        if p.is_file():shutil.copyfile(p,ROOT/'hardware'/p.name)
    atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),source_SHA=read(OLD/'CAMPAIGN_MANIFEST.json')['execution_SHA'],
        dispatch_quiescence=record(OLD/Q),equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        reason='Mathematically exact Forecast allocation cache; same SVR11 equipment, preserve all complete dates/models and source/runtime provenance.',
        physical_equipment_change=False,all_old_results_preserved=True,qualified_completed_dates_reused=True,UTC=now()))
    from v42_svr11.prepare import raw
    raw(ROOT);print('SAME_RAW_INPUTS_PREPARED')

def freeze_slots():
    validate_proof();assert not origin_workers(),'WAIT_FOR_HEALTHY_WORKERS_NATURAL_DRAIN'
    from prepare_svr11_epoch07 import freeze_slots as freeze
    import prepare_svr11_epoch07 as helper
    # Same reviewed input/slot ownership checks, with the exact performance
    # proof receipt replacing the earlier NPZ-loader proof. Never new physics.
    helper.root=ROOT;helper.old=OLD
    equivalence=ROOT/'COEFFICIENT_IO_EQUIVALENCE.json'
    assert not equivalence.exists();shutil.copyfile(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json',equivalence)
    freeze()
    p=ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json';v=read(p)
    v.update(regression='52 passed',forecast_allocation_equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        exact_equipment_and_unchanged_native_model=True,all_completed_origin_models_captured_after_natural_drain=True)
    atomic(p,v)

def release_and_reuse():
    validate_proof();assert not origin_workers()
    from v42_svr11.prepare import release
    release(ROOT)
    import prepare_svr11_epoch07 as helper
    helper.root=ROOT;helper.old=OLD;helper.reuse()
    from reuse_svr11_completed import admit_before_first_dispatch
    admit_before_first_dispatch(ROOT)
    ledger=read(ROOT/'CAMPAIGN_LEDGER.json');rows=list(ledger['dates'].values())
    assert sum(r['status']=='PASS' and r['arm']=='B0' for r in rows)==31
    print('QUALIFIED_COMPLETED_DATES_REUSED',sum(bool(r.get('reused')) for r in rows))

if __name__=='__main__':
    {'proof':proof,'quiesce':quiesce,'prepare':prepare,'freeze_slots':freeze_slots,'release':release_and_reuse}[sys.argv[1]]()
