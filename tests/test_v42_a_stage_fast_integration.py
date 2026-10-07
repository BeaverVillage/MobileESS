"""Tiny algebra/adapter/report integration; no production models or optimizers."""
from contextlib import nullcontext
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.stress_backend import row_replay
from v42_a_stage_domain_v2.fast_backend import Backend,lp_replay,frozen_grid_priority
from v42_a_stage_domain_v2.fast_execution import canonical_hash
from v42_a_stage_domain_v2.fast_report import speed_gate,metric
from v42_a_stage_domain_v2.fast_runner import _receipt_value,_pricing_trace
from v42_pr134_b1.common import digest,record
from v42_job_capability import Option


def snapshot():
    return LinearSnapshot(sp.csr_matrix([[1.]]),np.array([0.]),np.array([1.]),
        np.array(['<']),np.array([1.]),np.array(['I']),
        tuple(Objective(name,((0,Fraction(1,2)),)) for name in
            ('rho','migration_count','shift_magnitude','prestart_relocation'))).require()


def test_current_lp_replay_relaxes_only_integrality_and_preserves_raw_point():
    original=snapshot();point=np.array([.5]);before=point.copy()
    assert not row_replay(original,point)['PASS']
    assert lp_replay(original,point)['PASS'] is True
    assert original.vtypes.tolist()==['I'] and np.array_equal(point,before)
    assert lp_replay(original,np.array([1.1]))['PASS'] is False
    with pytest.raises(ValueError,match='FINITE_ORIGINAL_COLUMN_AXIS_POINT_REQUIRED'):
        lp_replay(original,np.array([np.nan]))


@pytest.mark.parametrize('point,expected',[(.5,True),(1.1,False)])
def test_backend_lp_verification_returns_python_bool_identity(point,expected):
    backend=Backend();backend.current=replace(snapshot(),vtypes=np.array(['C']))
    receipt=backend.verify_lp(None,np.array([point]))
    assert receipt['PASS'] is expected
    assert type(receipt['PASS']) is bool
    assert receipt['lp_snapshot_sha256']==backend.current.fingerprint()
    assert receipt['physical_integer_schedule_claimed'] is False


def test_source_manifest_json_hash_matches_common_digest_including_unicode():
    value={'C:/repo/과학.py':'a'*64,'C:/repo/fast_runner.py':'b'*64}
    assert canonical_hash(value)==digest(value)


def speed_fixture():
    permit=dict(execution_sources={'C:/fixture/실행.py':'a'*64},solver_policy=dict(sha256='b'*64),
        activation_policy=dict(sha256='c'*64))
    canary=dict(root_completed=True,first_root_native_seconds=10.,native_seconds=20.,global_scientific_stop=False,
        execution_sources_sha256=canonical_hash(permit['execution_sources']),solver_policy_sha256='b'*64,
        activation_policy_sha256='c'*64,domain_status=dict(LP_PRICING_CLOSED=False))
    baseline=dict(raw_model=dict(cols=1000),factor_nonzeros=1000,factor_memory_GB=4.,
        ordering_seconds=100.,interrupted_root_attempt_seconds=3500.)
    initial=dict(cols=100);fill=dict(factor_nnz=100,factor_memory_GB=.1,ordering_seconds=1.)
    return baseline,canary,initial,fill,permit


def test_engineering_speed_success_does_not_claim_lp_or_integer_closure():
    gate=speed_gate(*speed_fixture())
    assert gate['PASS'] and gate['classification']=='SPEED_GATE_PASS'
    assert gate['engineering_only'] and not gate['scientific_feasibility_or_integer_closure_implied']
    assert gate['full_A1_speedup'] is None


@pytest.mark.parametrize('field',['execution_sources_sha256','solver_policy_sha256','activation_policy_sha256'])
def test_speed_gate_rejects_source_policy_or_activation_identity_drift(field):
    values=list(speed_fixture());values[1][field]='d'*64
    gate=speed_gate(*values)
    assert not gate['PASS'] and not gate['canary_source_bound']


def test_speed_gate_missing_baseline_or_canary_ordering_is_unavailable_failure():
    values=list(speed_fixture());values[0]['ordering_seconds']=None
    assert not speed_gate(*values)['PASS']
    values=list(speed_fixture());values[3]['ordering_seconds']=None
    assert not speed_gate(*values)['PASS']
    values=list(speed_fixture());values[3]['factor_nnz']=None
    assert not speed_gate(*values)['PASS']


def test_signed_grid_ranking_retains_original_native_coefficients():
    coeff=SimpleNamespace(current_constant=np.array([0.,0.]),current_matrix=np.array([[2.,-1.],[-1.,3.]]),
        anchor=np.array([1.,2.]),control_names=['aidc_load_kw[A]','aidc_load_kw[B]'])
    before=coeff.current_matrix.copy()
    scores,receipt=frozen_grid_priority([coeff],SimpleNamespace(capacities={'A':1,'B':1}))
    assert scores['A',0]>.0 and scores['B',0]<.0
    assert receipt['ranking_only'] and receipt['low_rank_remains_in_pool']
    assert not receipt['physical_coefficients_changed'] and np.array_equal(before,coeff.current_matrix)


def test_pricing_evidence_option_and_fraction_serialization_preserves_executable_identity():
    option=Option(1,'A',(('A',1,3),))
    receipt=dict(selections={'class':(option,)},selected_scores=[dict(option=option,price=Fraction(-1,3))])
    encoded=_receipt_value(receipt)
    json.dumps(encoded,allow_nan=False)
    assert encoded['selected_scores'][0]['price']=='-1/3'
    assert encoded['selected_scores'][0]['option']['start']==1
    assert receipt['selections']['class'][0] is option


def test_adapter_nested_pricing_trace_is_present_in_runner_artifact():
    build=SimpleNamespace(metadata=dict(active_counts=dict(stay=2,inactive_stay=3,migration=0)))
    pricing=dict(mode='OPTIMALITY',candidates_activated=1,trace=dict(candidates_scanned=4,
        improving_candidates=2,minimum_reduced_cost='-1/3',median_activated_reduced_cost='-1/4'))
    row=_pricing_trace('2025-05-19','rho',0,build,pricing,dict(status=2,native_seconds=.5,bound=1.),
        dict(presolved_matrix=dict(rows=10,columns=20,nnz=30)))
    assert row['candidates_scanned']==4 and row['improving_candidates']==2
    assert row['minimum_reduced_cost']=='-1/3' and row['presolved_cols']==20


def test_factor_memory_units_are_normalized_without_exact_memory_claim():
    result=metric('Factor NZ : 1.2e+06 (roughly 250 MB of memory)\n')
    assert result['factor_memory_GB']==.25 and result['factor_memory_printed']==250
    assert result['barrier_seconds'] is None and result['root_completed'] is None


def test_successive_lp_build_reuses_initial_bound_namespace_without_rebinding(tmp_path,monkeypatch):
    backend=Backend();native=object();identity=dict(PASS=True);seen=[]
    first=tmp_path/'rho/LP_0000';first.mkdir(parents=True)
    def prepare(day,folder):
        backend.data=(dict(day=day),);backend.frozen_data=backend.data
        backend.native=native
        (folder/'INPUT_IDENTITY.json').write_text(json.dumps(identity))
        return native,tmp_path/'external',identity
    monkeypatch.setattr(backend,'_prepare',prepare)
    monkeypatch.setattr(backend,'_native',lambda day,folder,module,static,proof:seen.append((module,proof)) or object())
    import v42_pr134_b1.native as historical
    def reject(*args):raise AssertionError('DATE_NAMESPACE_MUST_NOT_BE_REBOUND_FOR_ACTIVATION')
    monkeypatch.setattr(historical,'bind',reject)
    backend.build_lp('2025-05-19',first,'rho',[],None)
    backend.build_lp('2025-05-19',tmp_path/'rho/LP_0001','rho',[],dict(active=True))
    assert seen==[(native,identity),(native,identity)]


def test_each_lp_iteration_retains_immutable_external_snapshot_bytes(tmp_path,monkeypatch):
    import v42_a_stage_domain_v2.fast_backend as module
    import v42_pr134_sc.snapshot as descriptor
    import v42_two.contract as objectives
    import v42_integrated.contract as integrated
    import v42_a_stage_domain_v2.fast_execution as execution
    backend=Backend();backend.data=(None,)*7+(dict(physical_domain_hash='a'*64),)
    backend.ledger=dict(receipt=dict(PASS=True,active_STAY=1,inactive_STAY=1,active_migration=0,
        active_subset_physical=True,active_union_pool_equals_physical=True))
    class Model:
        NumVars=1;NumConstrs=1;NumNZs=1
        def getAttr(self,name):return ['x']
        def setAttr(self,name,values):assert name=='VType' and values==['C']
        def update(self):pass
    native=SimpleNamespace(build=lambda *args:(Model(),[],None,[],{}))
    monkeypatch.setattr(module,'snapshot_of',lambda *args:snapshot())
    monkeypatch.setattr(backend,'_coupling_rows',lambda *args:{})
    monkeypatch.setattr(objectives,'aidc_groups',lambda *args:None)
    monkeypatch.setattr(objectives,'passes',lambda *args:[('P1','rho',0)])
    monkeypatch.setattr(integrated,'physical_authority',lambda:nullcontext())
    monkeypatch.setattr(integrated,'all_transformer_rows',lambda old:old)
    current={'identity':'1'*64}
    monkeypatch.setattr(execution,'current_fast_permit',lambda:SimpleNamespace(identity=current['identity']))
    def capture(*args):
        Path(args[-1]).write_bytes(b'TINY_IMMUTABLE_DESCRIPTOR');return dict(units=[])
    monkeypatch.setattr(descriptor,'capture',capture)
    root=tmp_path/'external';one=tmp_path/'rho/LP_0000';two=tmp_path/'rho/LP_0001'
    one.mkdir(parents=True);two.mkdir(parents=True)
    first=backend._native('2025-05-19',one,native,root,dict(PASS=True))
    receipts=first.metadata['static_artifacts']
    second=backend._native('2025-05-19',two,native,root,dict(PASS=True))
    assert {v['path'] for v in receipts}.isdisjoint({v['path'] for v in second.metadata['static_artifacts']})
    assert all(record(v['path'])==v for v in receipts)
    assert first.metadata['lp_snapshot_sha256']!=first.metadata['original_integer_snapshot_sha256']
    assert len(first.metadata['objective_sha256'])==64
    current['identity']='2'*64
    repaired=backend._native('2025-05-19',one,native,root,dict(PASS=True))
    assert {v['path'] for v in receipts}.isdisjoint({v['path'] for v in repaired.metadata['static_artifacts']})
    assert all('EXECUTION_'+('1'*16) in v['path'] for v in receipts)
    assert all('EXECUTION_'+('2'*16) in v['path'] for v in repaired.metadata['static_artifacts'])
    assert all(record(v['path'])==v for v in receipts)


def test_requalification_subtracts_actual_prior_runtime_without_budget_extension(tmp_path,monkeypatch):
    import v42_a_stage_domain_v2.fast_qualify as module
    root=tmp_path/'source';out=tmp_path/'new';old=tmp_path/'old';static=tmp_path/'external'
    for path in (root,out,old,static):path.mkdir()
    monkeypatch.setattr(module,'ROOT',root);monkeypatch.setattr(module,'OUT',out)
    monkeypatch.setattr(module,'OLD',old);monkeypatch.setattr(module,'STATIC',static)
    (root/'fixture.py').write_text('value = 1\n')
    for name in ('FAST_FULL_TESTS.xml','FAST_FINAL_TARGETED.xml'):
        (static/name).write_text('<testsuite><testcase classname="fixture" name="pure_control" /></testsuite>')
    for day in ('2025-05-17','2025-05-19'):
        folder=static/day;folder.mkdir();(folder/'PHYSICAL_DOMAIN_CACHE.json').write_text('{}')
    (old/'STRESS_RUN_PERMIT.json').write_text(json.dumps(dict(gate_receipts={})))
    spent=1.3819999694824219
    previous=out/'REJECTED_FAST_CANARY_ATTEMPT_01/MAY17_CANARY';previous.mkdir(parents=True)
    (previous/'FAST_RESULT.json').write_text(json.dumps(dict(native_seconds=spent)))
    def command(args,**kwargs):
        if args[0]=='rg':return 'fixture.py\n' if kwargs['cwd']==root else ''
        if '--name-only' in args:return 'fixture.py\n'
        if 'rev-parse' in args:return 'a'*40+'\n'
        return ''
    monkeypatch.setattr(module.subprocess,'check_output',command)
    monkeypatch.setattr(module,'solver_policy',lambda native:dict(PASS=True,scope='SYNTHETIC_NO_NATIVE_METADATA'))
    captured={}
    def create(*args,**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(identity='b'*64,document=dict(run_order=['2025-05-17','2025-05-19']))
    monkeypatch.setattr(module,'create_fast_run_permit',create)
    module.qualify()
    freeze=json.loads((out/'CANARY_SOURCE_FREEZE.json').read_text())
    assert captured['native_budget_seconds']==300.-spent==298.6180000305176
    assert spent+captured['native_budget_seconds']==300.
    assert freeze['previous_rejected_native_seconds']==spent
    assert freeze['native_budget_per_canary']==captured['native_budget_seconds']
    assert freeze['cumulative_May17_budget_across_attempts']==300.


def test_heavy_worker_inventory_detects_parallel_fast_worker_and_excludes_serial_parent(monkeypatch):
    import v42_a_stage_domain_v2.fast_runner as runner
    monkeypatch.setattr(runner,'_historical_heavy_optimizers',lambda:[dict(pid=300,command='historical native worker')])
    monkeypatch.setattr(runner.os,'getpid',lambda:101)
    monkeypatch.setattr(runner.psutil,'Process',lambda:SimpleNamespace(parents=lambda:[SimpleNamespace(pid=100)]))
    processes=[SimpleNamespace(pid=pid,info=dict(cmdline=['python','-m','v42_a_stage_domain_v2.fast_runner']))
        for pid in (100,101,200)]
    monkeypatch.setattr(runner.psutil,'process_iter',lambda fields:processes)
    assert [row['pid'] for row in runner.other_heavy_optimizers()]==[200,300]
