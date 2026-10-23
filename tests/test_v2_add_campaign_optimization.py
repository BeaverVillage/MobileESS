import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import numpy as np

def test_source_A_preparation_has_empty_directory_next_to_existing_ledger(tmp_path):
    from contextlib import contextmanager
    from v2_add_preflight import stage_a_casefactory as factory
    ledger=tmp_path/'NATIVE_RUNTIME_LEDGER.json';ledger.write_text('{}')
    request=dict(stage='A1',output=str(tmp_path));budget=object();seen=[]
    def source(actual,account,progress):
        output=Path(actual['output']);assert output==tmp_path/'SOURCE'
        assert not output.exists() and ledger.exists() and account is budget
        seen.append(actual);return dict(original_source_boundary_reached=True)
    @contextmanager
    def route(req,m1):
        assert req is request;yield source
    with patch.object(factory,'current_stage',route):
        assert factory.run(request,budget)['original_source_boundary_reached']
    assert request['output']==str(tmp_path) and len(seen)==1

def test_source_JSON_original_atomic_writer_handles_long_windows_temp_name(tmp_path):
    import os,json
    from v43.common import atomic
    from v2_add_preflight.stage_m_case import source_json_writer
    folder=tmp_path
    while len(str(folder.resolve()))<190:
        folder=folder/'directory';folder.mkdir()
    target=folder/'CURRENT_SOURCE_PROJECTION_CERTIFICATE.json'
    if os.name=='nt':assert len(str(target.resolve()))+46>=260
    payload=dict(PASS=True,current_rows=[1,2,3],original_serializer_unchanged=True)
    source_json_writer(atomic)(target,payload)
    assert json.loads(target.read_text(encoding='utf8'))==payload
    assert not list(folder.glob('*.tmp'))

@pytest.mark.parametrize('bound',[float('-inf'),float('inf'),float('nan'),-12.5])
def test_unavailable_bound_keeps_measured_call_and_resume_account(tmp_path,bound):
    import json,math
    from v2_add_preflight.stage_budget import scope,a_budget
    from v42_may_campaign_native90 import budget as native
    from v44.budget import StageBudget,resume
    original=native.DateBudget.persist
    case=SimpleNamespace(identity=dict(arm='B2',stage='M1',source_sha='a'*64),case_sha='b'*64)
    with patch.object(native,'d_path',lambda p:Path(p)),scope():
        accounts=[a_budget(tmp_path/'A.json'),native.DateBudget(tmp_path/'diagnostic.json',native_limit=30.),
                  StageBudget(tmp_path/'M.json',case=case,kind='PLANNING_NATIVE')]
        for account in accounts:
            row=dict(status='FINISHED',Native_Runtime=2.75,Native_status=11,SolCount=0,Native_BestBd=bound)
            account.calls.append(row);account.charge(2.75)
            saved=json.loads(account.path.read_text(encoding='utf8'))
            assert saved['measured_Native_Runtime']==account.used()==2.75
            assert saved['inflight'] is None and len(saved['calls'])==1
            if math.isfinite(bound):assert saved['calls'][0]['Native_BestBd']==bound
            else:
                assert saved['calls'][0]['Native_BestBd'] is None
                assert saved['calls'][0]['Native_BestBd_unavailable']==str(bound)
            with pytest.raises(ValueError,match='NONFINITE_NATIVE_RUNTIME'):account.charge(float('inf'))
        continued=resume(accounts[-1].path,case=case,kind='PLANNING_NATIVE',destination=tmp_path/'resumed.json')
        assert continued.used()==2.75 and continued.remaining()==3597.25
    assert native.DateBudget.persist is original

def test_replay_provenance_never_accepts_unproved_source_drift(tmp_path):
    from v2_add_preflight.stage_optimization_gate import replay_source_compatibility
    a=[dict(path='source',sha256='a')];b=[dict(path='source',sha256='b')]
    assert replay_source_compatibility(dict(validation_source_files=a,validation_source_snapshot_unchanged=True),a,tmp_path)
    assert not replay_source_compatibility(dict(validation_source_files=a,validation_source_snapshot_unchanged=True),b,tmp_path)
    assert not replay_source_compatibility(dict(validation_source_files=a,validation_source_snapshot_unchanged=False),a,tmp_path)

def test_B3_reuses_only_the_same_accepted_B1_A1_without_new_Native(tmp_path):
    import json
    from copy import deepcopy
    from v2_add_preflight import stage_handlers as h
    from v2_add_preflight.stage_common import record
    sources=[dict(path='same-source',sha256='a'*64,bytes=12)]
    files=dict(native=dict(sha256='b'*64),windows=dict(sha256='c'*64))
    identity=dict(day='2025-05-01',arm='B1',stage='A1',reused_exact_A1=True,
        source_sha='d'*64,source=sources,input=files['native'],windows=files['windows'],
        FULL_feasible=True,independent_Global_LB_validated=True,certified_gap=.004)
    path=tmp_path/'AIDC_REFERENCE.json'
    request=dict(day='2025-05-01',arm='B3',stage='A1_REUSE',source_sha='d'*64,sources=sources)
    def saved(i):
        path.write_text(json.dumps(dict(identity=i)),encoding='utf8')
        return dict(PASS=True,AIDC_reference=record(path),Native_seconds=19.5,acceptance_sha='accepted-B1')
    with patch.object(h,'current',lambda:{}),patch.object(h,'day_inputs',lambda:dict(files=files)):
        original=saved(identity);value=h.reuse(request,{},original)
        assert value['reused_exact_A1'] and value['Native_seconds']==0.
        assert value['AIDC_reference']==original['AIDC_reference'] and value['acceptance_sha']=='accepted-B1'
        for key,bad in [('day','2025-05-02'),('source_sha','e'*64),('FULL_feasible',False),('certified_gap',.01)]:
            changed=deepcopy(identity);changed[key]=bad
            with pytest.raises(ValueError,match='A1_REUSE_SAME_CASE_FULL_ACCEPTANCE_REQUIRED'):
                h.reuse(request,{},saved(changed))

def test_scoped_budget_constructor_and_reconciled_resume(tmp_path):
    from v2_add_preflight.stage_budget import scope
    import v44.budget as m
    from v42_may_campaign_native90 import budget as native
    original=m.StageBudget.__init__;case=SimpleNamespace(identity=dict(arm='B3',stage='M2',source_sha='a'*64),case_sha='b'*64)
    with patch.object(native,'d_path',lambda p:Path(p)),scope():
        from v2_add_preflight.stage_budget import a_budget
        a=a_budget(tmp_path/'A.json');assert a.native_limit==7200. and a.remaining()==7200.
        for kind,ceiling in [('PLANNING_NATIVE',3600.),('K48_SEPARATE',300.)]:
            old=m.StageBudget(tmp_path/(kind+'.json'),case=case,kind=kind)
            assert old.native_limit==ceiling
            old.calls=[dict(status='FINISHED',Native_Runtime=19.25,fixture=True)];old.native_used=19.25;old.persist()
            new=m.resume(old.path,case=case,kind=kind,destination=tmp_path/(kind+'_resume.json'))
            assert new.used()==19.25 and new.remaining()==ceiling-19.25
            new._call_cap=300.;assert new.remaining()==min(300.,ceiling-19.25)
        assert m.JOINT_CALL_CAP==300.
    assert m.StageBudget.__init__ is original and m.JOINT_SECONDS==900.

def test_immutable_record_cache_denies_write_and_then_releases(tmp_path):
    from v2_add_preflight.stage_immutable_io import ImmutableRecords
    path=tmp_path/'input.bin';path.write_bytes(b'original');calls=[]
    def record(p):
        calls.append(p);return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
    cache=ImmutableRecords([path]);wrapped=cache.wrap(record)
    try:
        a=wrapped(path);b=wrapped(path);assert a==b and len(calls)==1
        b['sha256']='changed';assert wrapped(path)==a
        with pytest.raises(PermissionError):path.write_bytes(b'replacement')
        assert cache.report()['avoided_rehashed_bytes']==16
    finally:cache.close()
    path.write_bytes(b'new');assert wrapped(path)['sha256']!=a['sha256'];cache.close()

def test_strict_replay_lifts_only_once_without_modifying_raw(tmp_path):
    from v2_add_preflight import stage_m_validation as v
    p=np.array([1.]);path=tmp_path/'p.npz';np.savez_compressed(path,point=p);calls=[]
    case=SimpleNamespace(d=dict(types=np.array(['C'])),original_d=dict(types=np.array(['C'])),lift=lambda x:(calls.append(x.copy()) or x.copy()))
    def replay(c,x,full):
        assert np.array_equal(x,p) and np.array_equal(full,p)
        return dict(PASS=True,exact_objective='1')
    with patch.object(v,'_validate',replay):assert v.strict(case,path)['PASS']
    assert len(calls)==1

def test_physical_domain_keeps_source_releases_and_protected_timing():
    from v42_job_capability import Job
    from v42_native.service import boundary
    from v2_add_preflight.stage_source_windows import starts
    from v42_a_stage_domain_v2.domain import physical_starts
    j=Job('x','PENDING',0,0,4,'A',3,1,initial_sites=('A',),duration_authority='test')
    bound=boundary(j,(4,),'a'*64,'b'*64,H=10)
    assert starts(j,bound,10)==physical_starts(j,bound,10)==tuple(range(11))
    assert min(starts(j,bound,10,hard_release=2))==2
    from dataclasses import replace
    assert starts(replace(j,protected=True),bound,10)==(4,)

def test_same_case_preparation_reuse_rejects_domain_mutation_and_new_anchor(tmp_path):
    import scipy.sparse as sp
    from v2_add_preflight.stage_case_cache import Cache
    from v2_add_preflight.stage_common import record
    from v42_native.contracts import digest
    path=tmp_path/'authority.bin';path.write_bytes(b'fixed')
    identity=dict(day='2025-05-01',stage='M1',arm='B3',anchor='current')
    d=dict(lower=np.array([0.]),upper=np.array([1.]),types=np.array(['C']),objective=np.array([1.]),
        rhs=np.array([1.]),sense=np.array(['<']),constant=np.asarray(0.),names=np.array(['x']),row_names=np.array(['row']))
    case=SimpleNamespace(A=sp.eye(1,format='csr'),d=d,identity=identity,case_sha=digest(identity))
    manifest=dict(files=[record(path)],proof_files=[],identity=identity)
    cache=Cache()
    try:
        cache.remember(case,manifest);assert cache.take(manifest,tmp_path/'out') is case
        case.d['rhs'][0]=2.
        with pytest.raises(ValueError,match='MUTATED'):cache.take(manifest,tmp_path/'bad')
        case.d['rhs'][0]=1.
        assert cache.take(dict(manifest,identity=dict(identity,anchor='changed')),tmp_path/'new') is None
        assert cache.entry is None
    finally:cache.clear()

def test_batched_actual_native_rows_match_independent_getA_and_reject_changed_coefficient():
    import scipy.sparse as sp
    import gurobipy as gp
    import time
    from v2_add_preflight.stage_native_batch import blocks,exact
    from v2_add_preflight.prestart_native import native_zero
    A=sp.csr_matrix(np.array([[0.,3.,-2.,0.,1.],[-4.,0.,0.,5.,0.],[0.,0.,0.,0.,0.],[1.,0.,0.,0.,-1.]]))
    m=gp.Model();m.Params.OutputFlag=0
    try:
        with native_zero() as denied:
            x=m.addMVar(5,lb=-7,ub=9);handle=m.addMConstr(A,x,np.array(['<','=','>','<']),np.array([4.,2.,0.,3.]));m.update()
            observed=sp.vstack([b for _,b in blocks(m,0,4,chunk_rows=2)],format='csr')
            independent=m.getA().tocsr();assert (observed!=independent).nnz==0
            from v2_add_preflight.stage_native_batch import difference
            assert difference(m,A).nnz==0
            exact(m,handle,A,np.array([4.,2.,0.,3.]),np.array(['<','=','>','<']),time.perf_counter())
            changed=A.copy();changed.data[0]+=1
            assert difference(m,changed).nnz==1
            with pytest.raises(ValueError,match='COEFFICIENT'):exact(m,handle,changed,np.array([4.,2.,0.,3.]),np.array(['<','=','>','<']),time.perf_counter())
            assert not denied and m.SolCount==0
    finally:m.dispose()

def test_array_serialization_has_identical_original_wire_bytes():
    import v42_pr134_b1.common as common
    from v2_add_preflight.stage_a_performance import scope
    values=[np.random.default_rng(14).normal(size=(6,9)),np.array([0.,-0.,np.nan,np.inf,-np.inf]),
        np.arange(24).reshape(4,6),np.array(['가','b']),{'x':np.array([True,False]),'path':Path('D:/example')}]
    expected=[common.digest(x) for x in values]
    with scope():assert [common.digest(x) for x in values]==expected
    import v42_a_stage_domain_v2.domain as domain
    cases=[{'a':[(1,2.,'한글'),(-0.,None,True)],'b':np.int64(4)},[(str(i),tuple(range(50))) for i in range(1000)]]
    expected=[domain.digest(v) for v in cases]
    with scope():
        assert [domain.digest(v) for v in cases]==expected
        with pytest.raises(ValueError):domain.digest({'bad':float('nan')})

def test_domain_constructor_and_immutable_boundary_memo_preserve_full_original_domain():
    from v42_job_capability import Job,Resources
    from v42_native.service import boundary
    from v42_a_stage_domain_v2.domain import physical_domain as original
    from v2_add_preflight.stage_source_windows import physical_domain
    from v2_add_preflight.stage_a_performance import scope
    from dataclasses import replace
    r=Resources({'A':2,'B':2},{'A':(2,),'B':(2,)},{('link',t):1e9 for t in range(12)},
        {('A','B'):('link',),('B','A'):('link',)},12,100,{},{},{})
    j=Job('x','PENDING',0,0,2,'A',5,1,initial_sites=('A','B'),checkpoint_authorized=True,duration_authority='test')
    b=boundary(j,(2,),'a'*64,'b'*64,H=12);expected=original(j,b,r)
    with scope() as stats:
        observed=physical_domain(j,b,r)
        assert type(observed) is type(expected)
        assert observed.stays==expected.stays and observed.blocks==expected.blocks and observed.sha==expected.sha
        for _ in range(5):b.require()
        with pytest.raises(ValueError):replace(b,finalized=False).require()
        assert stats['boundary_validation_reuses']>0 and stats['discarded_domain_hashes_avoided']==1
        assert stats['tau_sequences_reused']>0 and stats['tau_tuple_elements_avoided']>0
        empty=physical_domain(j,b,r,hard_release=20);old_empty=original(j,b,r,hard_release=20)
        assert empty.stays==old_empty.stays==() and empty.blocks==old_empty.blocks==()
        assert empty.sha==old_empty.sha

def test_actual_A_native_constructor_records_7200_without_solver(tmp_path):
    from v42_may_campaign_native90 import a_stage
    from v2_add_preflight.stage_a_native import constructor
    from v2_add_preflight.stage_common import read
    request=dict(day='2025-05-01',arm='B1',input_folder=str(tmp_path),output=str(tmp_path))
    fn=constructor(a_stage._native)
    with patch.dict(a_stage._native.__globals__,_paths=lambda r:('2025-05-01',tmp_path,tmp_path)):
        # constructor cloned globals on entry; construct after the test path route.
        fn=constructor(a_stage._native)
        account=SimpleNamespace(native_limit=7200.,started=1.,remaining=lambda:7200.)
        native=fn(request,{'_campaign':{'input_receipts':{}}},account,None)
    assert native.budget.record['limit_seconds']==7200.
    assert read(tmp_path/'CONTINUATION_BUDGET.json')['native_limit']==7200.
    assert native.remaining()==7200.

def test_original_A_native_solve_performs_actual_full_readback_before_any_solver(tmp_path):
    import gurobipy as gp
    import scipy.sparse as sp
    from types import FunctionType
    from v2_add_preflight.stage_a_native import solve_io
    from v2_add_preflight.stage_common import read
    from v2_add_preflight.prestart_native import native_zero
    A=sp.csr_matrix([[1.,-2.],[0.,1.]])
    m=gp.Model();m.Params.OutputFlag=0;x=m.addMVar(2,lb=0.,ub=4.)
    m.addMConstr(A,x,np.array(['<','<']),np.array([3.,2.]));m.update()
    objective=SimpleNamespace(coefficients=lambda:{0:1.},constant=0.)
    snapshot=SimpleNamespace(matrix=A,lower=np.zeros(2),upper=np.full(2,4.),vtypes=np.array(['C','C']),
        senses=np.array(['<','<']),rhs=np.array([3.,2.]),objectives=[objective],fingerprint=lambda:hashlib.sha256(A.data.tobytes()).hexdigest())
    class BoundaryReached(Exception):pass
    def before_policy(*args):raise BoundaryReached('AFTER_ACTUAL_READBACK_BEFORE_OPTIMIZATION')
    original=solve_io();namespace=dict(original.__globals__,materialize=lambda *a:(m,[('rho',x[0])]),apply_policy=before_policy)
    fn=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    receiver=SimpleNamespace(verify=lambda:True,remaining=lambda:7200.,policy={})
    try:
        with native_zero() as denied:
            with pytest.raises(BoundaryReached):fn(receiver,snapshot,tmp_path,'ORIGINAL_P1')
            assert read(tmp_path/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')['PASS']
            assert not denied and m.SolCount==0
    finally:m.dispose()

def test_matrix_files_are_lossless_and_copy_on_write(tmp_path):
    import scipy.sparse as sp
    from v2_add_preflight.stage_matrix_storage import MatrixFiles
    cache=MatrixFiles(tmp_path);save=cache.wrap(sp.save_npz);A=sp.csr_matrix([[1.,0.],[2.,3.]])
    a=tmp_path/'a/MATRIX.npz';b=tmp_path/'b/MATRIX.npz';a.parent.mkdir();b.parent.mkdir()
    save(a,A);save(b,A);assert a.read_bytes()==b.read_bytes() and b.stat().st_nlink==2
    changed=A.copy();changed.data[0]=4.;save(b,changed)
    assert (sp.load_npz(a)!=A).nnz==0 and (sp.load_npz(b)!=changed).nnz==0
    assert cache.report()['linked_matrices']==1

def test_exact_view_cache_commits_and_rejects_changed_RHS_without_overwrite(tmp_path):
    import scipy.sparse as sp
    from v2_add_preflight.stage_view_cache import load_or_build
    from v2_add_preflight.stage_common import record
    calls=[];A=sp.csr_matrix([[1.]])
    def build():calls.append(1);return A,{'rhs':np.array([1.])},{'roundtrip':True}
    authority={'RHS':'current'};context={'day':'2025-05-01','stage':'M2','anchor':'same'}
    first,proof,hit=load_or_build(tmp_path,authority,context,build)
    assert not hit and len(calls)==1
    second,again,hit=load_or_build(tmp_path,authority,context,build)
    assert hit and len(calls)==1 and proof==again and (first!=second).nnz==0
    previous=record(tmp_path/'D.npz')
    def changed():return A,{'rhs':np.array([2.])},{'roundtrip':True}
    with pytest.raises(ValueError,match='NEW_CASE_OUTPUT_ROOT'):
        load_or_build(tmp_path,{'RHS':'changed'},context,changed)
    assert record(tmp_path/'D.npz')==previous


def test_short_canary_uses_a_new_separate_measured_account(tmp_path):
    from v2_add_preflight.stage_numerical_canary import account
    from v2_add_preflight.stage_budget import scope,policy
    from v2_add_preflight.stage_common import read
    from v42_may_campaign_native90 import budget as native
    case=SimpleNamespace(identity=dict(arm='B2',stage='M1',source_sha='a'*64),case_sha='b'*64)
    with patch.object(native,'d_path',lambda p:Path(p)),scope():
        short=account(tmp_path/'CANARY.json',case,'PLANNING_NATIVE')
        from v44.budget import StageBudget
        assert type(short) is StageBudget and short.remaining()==30. and short.calls==[]
        ordinary=StageBudget(tmp_path/'FORMAL_POLICY_FIXTURE.json',case=case,kind='PLANNING_NATIVE')
        assert ordinary.remaining()==3600. and policy()['A_seconds']==7200.
        receipt=read(short.path)
        assert receipt['authorization']['official_campaign_result'] is False
        assert receipt['authorization']['role']=='ISOLATED_NUMERICAL_CANARY'


def test_pause_admission_rejects_frozen_ledger_mutation(tmp_path):
    from v2_add_preflight.prestart_execution import atomic
    from v2_add_preflight.stage_common import record
    from v2_add_preflight.stage_pause import verify
    for name in ('ledger','exit','hold'):atomic(tmp_path/(name+'.json'),{'explicit_fixture':True})
    frozen=dict(Native_inflight=None,Native_budget_reset=False,ledger=record(tmp_path/'ledger.json'),
        worker=dict(pid=2**30,process_created=0.),supervisor=dict(pid=2**30+1,process_created=0.))
    atomic(tmp_path/'frozen.json',frozen)
    atomic(tmp_path/'pause.json',dict(PASS=True,all_OS_locks_verified_released=True,
        no_next_stage_dispatched=True,scheduled_task_disabled=True,worker_killed=False,Supervisor_terminated=False,
        stage_frozen=record(tmp_path/'frozen.json'),coordinator_normal_finally_exit=record(tmp_path/'exit.json'),
        persistent_hold=record(tmp_path/'hold.json')))
    receipt=record(tmp_path/'pause.json');assert verify(receipt)['PASS']
    atomic(tmp_path/'ledger.json',dict(explicit_fixture=True,changed=True))
    with pytest.raises(PermissionError,match='FROZEN_LEDGER_DRIFT'):verify(receipt)


def test_real_M_case_entrypoint_accepts_3600_and_preserves_parent_refusal(tmp_path):
    import v2_add_preflight.stage_casefactory as factory
    from v2_add_preflight.stage_common import day_inputs
    from v44.runtime import build as original
    row=day_inputs();code=original.__code__
    identity=dict(day='2025-05-01',arm='B0',stage='REFERENCE',input=row['files']['native'],windows=row['files']['windows'])
    p=np.ones((96,12));q=np.tan(np.arccos(.95))*p
    payload=dict(identity=identity,bundle=dict(day='2025-05-01'),planning=dict(PCC_P_kw=p,PCC_Q_kvar=q))
    req=dict(day='2025-05-01',arm='B2',stage='M1')
    case=SimpleNamespace(mess_stage_budget_seconds=3600.)
    with patch.object(factory,'_construct',lambda *a:case):
        assert factory.prepare_current(payload,req,tmp_path) is case
        wrong=dict(payload,identity=dict(identity,arm='B1'))
        with pytest.raises(ValueError,match='B2_SAME_DAY_B0_R0_Q50_ONLY'):
            factory.prepare_current(wrong,req,tmp_path)
    assert original.__code__ is code


def test_stage_timing_separates_paid_history_native_and_non_native_costs(tmp_path):
    from v2_add_preflight.stage_timing import stage
    from v2_add_preflight.prestart_execution import atomic
    parent=tmp_path/'old';out=tmp_path/'new'
    old_call=dict(Native_Runtime=12.5,optimize_wall_seconds=14.,fixture_synthetic_Runtime=True)
    old_cost=dict(kind='model_preparation',wall_seconds=40.)
    atomic(parent/'JOINT_NATIVE_LEDGER.json',dict(calls=[old_call],costs=[old_cost]))
    req=dict(output=str(out),resume_parent=str(parent))
    with patch('v2_add_preflight.stage_timing.time.perf_counter',side_effect=[10.,30.]):
        with stage(req) as costs:
            atomic(out/'JOINT_NATIVE_LEDGER.json',dict(calls=[old_call,
                dict(Native_Runtime=2.5,optimize_wall_seconds=3.,fixture_synthetic_Runtime=True)],
                costs=[old_cost,dict(kind='model_preparation',wall_seconds=8.,exclusive_non_native_wall_seconds=5.),dict(kind='OTHER_SOLVER',wall_seconds=2.)],
                measured_Native_Runtime=15.,inflight=None,Native_ceiling_seconds=3600.))
    assert costs['this_attempt_measured_Native_seconds']==2.5
    assert costs['stage_wall_seconds']==20. and costs['external_score_solver_wall_seconds']==2.
    assert costs['non_Native_preparation_validation_IO_and_score_wall_seconds']==17.
    assert costs['A_model_preparation_wall_seconds']==5.
    assert costs['ledgers'][0]['cumulative_measured_Native_seconds']==15.


def test_actual_migration_pool_receipt_avoids_giant_json_join_and_keeps_original_hash():
    from v42_a_stage_domain_v2.active import MigrationPool
    import v42_a_stage_domain_v2.domain as domain
    from v2_add_preflight.stage_a_performance import scope
    keys=frozenset((i,'A',i+1,float(i*900),'B',i+2) for i in range(5000))
    pool=MigrationPool('class',SimpleNamespace(count=5002,stays=(('A',0),),blocks=((),)),keys)
    before=pool.receipt()
    with scope(),patch.object(domain.json,'dumps',side_effect=AssertionError('GIANT_JSON_JOIN_CALLED')):
        assert pool.receipt()==before


def test_A_physical_reader_accepts_only_original_derived_authority_marker():
    from v2_add_preflight.stage_a_canary import require_frozen_bundle
    from v42_a_stage_domain_v2 import AUTHORITY
    frozen=dict(day='2025-05-01',capacities={'IDC01':65},beta_BG=2.)
    assert require_frozen_bundle(frozen,frozen)
    assert require_frozen_bundle(dict(frozen,aidc_domain_authority=AUTHORITY),frozen) is False
    with pytest.raises(ValueError,match='INPUT_BUNDLE_DRIFT'):
        require_frozen_bundle(dict(frozen,aidc_domain_authority='other'),frozen)
    with pytest.raises(ValueError,match='INPUT_BUNDLE_DRIFT'):
        require_frozen_bundle(dict(frozen,aidc_domain_authority=AUTHORITY,beta_BG=1.),frozen)
