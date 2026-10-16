"""Small binary/proof, lease and issue-only fixtures; no solver or DSS calls."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import pytest
import numpy as np

from v44.common import atomic,read,record,digest,DOC
from v44.config import DAYS


@pytest.fixture
def stage_request(tmp_path,monkeypatch):
    import v44.svr11_hardware as hardware
    h=tmp_path/'hardware';atomic(h/'HARDWARE.json',dict(fixture=True))
    monkeypatch.setattr(hardware,'HARDWARE',h)
    source=tmp_path/'source.py';source.write_text('immutable_fixture=True\n')
    return dict(day=DAYS[0],arm='B2',stage='M1',case_root=str(tmp_path/'attempt001'),
        source_sha=digest('fixture'),sources=[record(source)])


def test_completed_binary_receipt_restores_without_calls_and_rejects_corruption(tmp_path,stage_request):
    from v44.checkpoints import seal_stage,load_completed
    root=tmp_path/'M1';root.mkdir()
    binary=root/'point.npz';np.savez_compressed(binary,point=np.array([0.,1.]))
    result=dict(PASS=True,day=DAYS[0],arm='B2',point=record(binary))
    seal_stage(root,stage_request,result)
    assert load_completed(root,stage_request)==result
    binary.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='SOURCE_SHA_DRIFT'):load_completed(root,stage_request)


@pytest.mark.parametrize('field,value',[('day',DAYS[1]),('arm','B3'),('stage','M2'),('source_sha','0'*64),('case_root','other_attempt')])
def test_completed_rejects_cross_day_arm_stage_source_attempt(tmp_path,stage_request,field,value):
    from v44.checkpoints import seal_stage,load_completed
    root=tmp_path/'M1';seal_stage(root,stage_request,dict(PASS=True))
    with pytest.raises(ValueError,match='DRIFT|CASE_STAGE_AXIS'):load_completed(root,dict(stage_request,**{field:value}))


def test_duplicate_worker_creation_identity_and_hardware_drift(tmp_path,stage_request,monkeypatch):
    import v44.checkpoints as cp
    root=tmp_path/'M1';cp.seal_stage(root,stage_request,dict(PASS=True))
    atomic(root/'START.json',dict(pid=123,process_created=42.))
    monkeypatch.setattr(cp,'alive',lambda who:True)
    with pytest.raises(cp.NotReady,match='STILL_LIVE'):cp.load_completed(root,stage_request)
    monkeypatch.setattr(cp,'alive',lambda who:False)
    import v44.svr11_hardware as hardware
    atomic(hardware.HARDWARE/'HARDWARE.json',dict(changed=True))
    with pytest.raises(ValueError,match='HARDWARE_DRIFT'):cp.load_completed(root,stage_request)


def test_reconciled_300_900_budgets_and_exhaustion_never_reset(tmp_path):
    from v44.checkpoints import ledger_state
    for cap,used in ((300.,127.),(900.,901.)):
        path=tmp_path/f'{cap}.json';value=dict(inflight=None,Native_ceiling_seconds=cap,
            measured_Native_Runtime=used,calls=[dict(status='FINISHED',Native_Runtime=used)])
        atomic(path,value);state=ledger_state(path,ceiling=cap)
        assert state['measured']==used and state['remaining']==max(0,cap-used)
        atomic(path,dict(value,inflight={'Runtime':2.}))
        with pytest.raises(Exception,match='INFLIGHT'):ledger_state(path,ceiling=cap)
        atomic(path,dict(value,measured_Native_Runtime=used-1))
        with pytest.raises(ValueError,match='TOTAL_UNRECONCILED'):ledger_state(path,ceiling=cap)


def test_nonpersisted_actual_native_queue_is_explicit_not_supported(tmp_path,stage_request):
    from v44.checkpoints import crash_admission
    result=crash_admission(tmp_path,dict(stage_request,stage='ACTUAL'))
    assert result['status']=='NOT_SUPPORTED' and result['Native_clock_reset'] is False


@pytest.mark.parametrize('day',DAYS)
def test_real_issue_only_initial_state_audit_has_no_source_promotion(day):
    audit=read(DOC/'V44_MAY02_07_INITIAL_RUNNING_AUDIT.json')
    row=next(r for r in audit['days'] if r['day']==day)
    assert row['unresolved']==0 and row['Actual_outcomes_read']==row['Native_calls']==0
    assert all(r['label']=='INITIAL_RUNNING_SITE_MODEL_ASSUMED' for r in row['assumed_UIDs'])
    mess=read(row['MESS']['path'])
    assert mess['policy']=='INDEPENDENT_DAILY_MESS_INITIAL_STATE_ASSUMPTION'
    assert mess['SOC']==760. and not mess['observed_geolocation_or_SOC']
    assert sum(r['assumed'] for r in audit['days'][1:])==213


def test_deterministic_initializer_preserves_fixed_gpu_and_compatibility(tmp_path):
    from v43_actual.vendor.initialization import InitialRunningJob,initialize_running
    source=tmp_path/'issue.json';atomic(source,{'only':'issue_observations'})
    receipt=record(source)
    jobs=[InitialRunningJob(uid,uid,0.,1.,1,('A','B'),receipt['sha256'],receipt['sha256']) for uid in ('1','2','3')]
    result=initialize_running(jobs,{'A':1,'B':2},{'A':[1],'B':[1]},dict({'1':'A'}),
        issue_seconds=2.,source_receipts=[receipt],budget=None)
    assert result['policy']['PASS'] and result['policy']['mapping']=={'1':'A','2':'B','3':'B'}
    assert result['decision']['synthetic_assigned_jobs']==2
    assert not result['policy']['exact_feasibility']['executed']


def test_forecast_cohort_lease_wait_and_supervisor_failure(tmp_path,monkeypatch):
    import v44.svr11_forecast_parallel as cohort
    supervisor=dict(pid=1,process_created=1);owner=dict(pid=2,process_created=2)
    monkeypatch.setattr(cohort,'alive',lambda identity:identity in (supervisor,owner))
    atomic(tmp_path/'LEASE_STATE.json',dict(mode='WAITING_EXTERNAL_LOCK_HANDOVER'))
    ticks=[]
    def handover(seconds):
        ticks.append(seconds)
        atomic(tmp_path/'LEASE_STATE.json',dict(mode='OWNED_FORECAST_COHORT',owner=owner,supervisor=supervisor))
    monkeypatch.setattr(cohort.time,'sleep',handover)
    assert cohort.wait_for_lease(tmp_path,supervisor)['owner']==owner and ticks
    monkeypatch.setattr(cohort,'alive',lambda identity:False)
    with pytest.raises(Exception,match='SUPERVISOR_GONE'):cohort.wait_for_lease(tmp_path,supervisor)


def test_saved_original_k48_packet_is_reloaded_and_reverified(tmp_path):
    from test_v44_ports import original_fixture
    from v44.frozen.v43_mess.library import load
    from v44.m_restore import packet
    case=original_fixture();case.identity.update(schema='V44_DATED_FIXED_AIDC_MESS_CASE_V1',day=DAYS[2])
    case.bundle['day']=DAYS[2];case.case_sha=digest(case.identity)
    module=load()['table_v_k48'];original,proof=module.prepare_k16(case,None,tmp_path/'K16')
    restored,checked=packet(tmp_path/'K16',case,module)
    assert checked==proof and restored['source']==original['source']
    assert (restored['A']!=original['A']).nnz==0
    assert np.array_equal(restored['d']['objective'],original['d']['objective'])
    assert restored['start'] is None


def test_real_binary_matrix_inverse_and_transport_restore_without_native(tmp_path,stage_request,monkeypatch):
    """One-site 96-slot flow fixture, with the actual lossless proof/replay."""
    from scipy import sparse
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_may_campaign_native90.m_model import verify_transport,_freeze_transport,_domain_sha
    from v42_m1_hybrid.blocks import matrix_sha
    from v44.checkpoints import save_binary
    from v44.m_restore import restore
    from v44.frozen.v43_mess.library import load
    from types import ModuleType
    import sys
    parent=tmp_path/'M1';parent.mkdir();output=tmp_path/'RESTORED';output.mkdir()
    rr=[];cc=[];vv=[]
    for t in range(96):
        rr.append(t);cc.append(t);vv.append(1.)
        if t:rr.append(t);cc.append(t-1);vv.append(-1.)
    rr.append(96);cc.append(95);vv.append(1.)
    rr.extend((97,97));cc.extend((96,97));vv.extend((1.,1.))
    A=sparse.coo_matrix((vv,(rr,cc)),shape=(98,98)).tocsr()
    data=dict(names=np.array([f'arc[MESS01,{t}]' for t in range(96)]+['rho_max','fixture_aux']),
        types=np.array(['B']*96+['C','C']),lower=np.zeros(98),upper=np.ones(98),objective=np.r_[np.zeros(96),1.,0.],
        constant=np.array(0.),rhs=np.r_[1.,np.zeros(95),1.,.2],sense=np.array(['=']*97+['>']),
        row_names=np.array([f'flow[MESS01,IDC00,{t}]' for t in range(96)]+['terminal_location[MESS01]','fixture_coupling']))
    sites=['IDC00'];initial=dict(MESS01='IDC00');arcs=[('IDC00',t,'IDC00',t+1,None) for t in range(96)]
    battery=SimpleNamespace(initial=760.);graph=(sites,initial,arcs,battery,{})
    compact=Compact(A,data,arcs,initial,96);presolve=Presolve(compact.A,compact.d);B,selected=presolve.run()
    proof=verify_transport(compact,presolve);authority=_freeze_transport(compact,presolve,graph,proof,parent)
    coeff_path=tmp_path/'COEFFICIENTS.npz'
    np.savez_compressed(coeff_path,node_names=np.array(['fixture.1']),branch_names=np.array(['line.fixture::a']),transformer_ratings=np.array([np.nan]))
    cert=tmp_path/'ELECTRICAL.json';atomic(cert,dict(output=record(coeff_path)))
    bundle=dict(day=DAYS[0],electrical_certificate=record(cert));anchor=dict(fixture='96-slot flow')
    aidc=dict(day=DAYS[0],aidc_anchor=digest('aidc'));payload=dict(bundle=bundle,identity=aidc,planning={})
    identity=dict(schema='V44_DATED_FIXED_AIDC_MESS_CASE_V1',day=DAYS[0],arm='B2',stage='M1',
        source_sha=stage_request['source_sha'],parent_case_sha=digest('parent'),aidc_anchor=aidc['aidc_anchor'],
        original_matrix_sha=matrix_sha(A),original_domain_sha=_domain_sha(data),selected_matrix_sha=matrix_sha(B),
        selected_domain_sha=_domain_sha(selected),bundle_sha=digest(bundle),anchor_sha=digest(anchor),
        transport=proof,transport_authority=authority)
    case=SimpleNamespace(output=parent,original_A=A,original_d=data,A=B,d=selected,compact=compact,presolve=presolve,
        graph=graph,case_sha=digest(identity),identity=identity)
    sparse.save_npz(parent/'FULL_A.npz',A);np.savez_compressed(parent/'FULL_DATA.npz',**data)
    sparse.save_npz(parent/'C3A_A.npz',B);np.savez_compressed(parent/'C3A_DATA.npz',**selected)
    np.savez_compressed(parent/'CURRENT_C2_AXES.npz',rows=presolve.row_ids,columns=presolve.col_ids)
    atomic(parent/'CURRENT_C2_ALIASES.json',presolve.steps);atomic(parent/'CURRENT_C2_ROW_PROOFS.json',presolve.rows)
    atomic(parent/'SCIENTIFIC_CASE_IDENTITY.json',dict(identity,case_sha=case.case_sha));atomic(parent/'FIXED_AIDC_ANCHOR.json',anchor)
    save_binary(case,stage_request)
    import v42_bootstrap.m1 as native
    monkeypatch.setattr(native,'native_inputs',lambda ignored:(sites,initial,[],battery,{}))
    model=ModuleType('v42_svr11.model');model.load_coefficients=lambda ignored,day:[]
    monkeypatch.setitem(sys.modules,'v42_svr11.model',model)
    restored=restore(parent,output,stage_request,payload,load())
    assert restored.case_sha==case.case_sha and (restored.original_A!=A).nnz==0
    x=np.r_[np.ones(96),.7,.1];compact_x=compact.forward(x);selected_x=compact_x[presolve.col_ids]
    assert np.array_equal(restored.lift(selected_x),x)
    assert read(output/'BINARY_RESTORE_RECEIPT.json')['transport_and_FULL_matrix_SHA_replayed']
    assert not read(output/'BINARY_RESTORE_RECEIPT.json')['Native_clock_reset']


def test_campaign_completed_stage_reuse_has_zero_dispatch(tmp_path,stage_request,monkeypatch):
    import v44.campaign as campaign
    from v44.checkpoints import seal_stage
    parent=Path(stage_request['case_root']);old=parent/'M1'
    result=dict(PASS=True,allow_downstream=True,day=DAYS[0],arm='B2')
    seal_stage(old,stage_request,result)
    case=dict(stage_request,case_root=str(tmp_path/'attempt002'),scientific_case_root=str(parent),resume_of=str(parent))
    monkeypatch.setattr(campaign,'stage_request',lambda case,stage:dict(case,stage=stage))
    def forbidden(request):pytest.fail('completed stage must not execute')
    assert campaign.stage_result(case,'M1',forbidden)==result
    pointer=read(Path(case['case_root'])/'RESTORED_COMPLETED_STAGES.json')
    assert pointer['M1']['new_Native_calls']==0 and campaign.stage_file(case,'M1')==old/'RESULT.json'


def test_svr11_candidate_cache_binds_hardware_and_fresh_never_uses_it():
    from v44.svr11_ac import SVR11CurrentAC,evaluate_body
    from v43_actual.current_ac import OriginalCurrentAC
    oracle=object.__new__(SVR11CurrentAC)
    model=SimpleNamespace(authority_sha='power',recompute=lambda *args:dict(PCC_P_kw=np.array([[2.]]),PCC_Q_kvar=np.array([[.2]])))
    observations=SimpleNamespace(at=lambda *a,**kw:dict(weather=dict(values={})))
    OriginalCurrentAC.__init__(oracle,issue_seconds=0.,sites=('IDC01',),power_model=model,observations=observations)
    oracle.hardware_record={'sha256':'first_hardware'};oracle.scenario={'scenario_SHA':'scenario'}
    oracle.mess_sha='plan';oracle.hardware={'equipment_SHA':'equipment'}
    oracle._candidate_evaluator=evaluate_body();oracle._independent_fresh=False
    calls=[]
    def probe(rows):calls.append(oracle._independent_fresh);return dict(PASS=True)
    oracle._probe=probe;oracle.observe(0.,[])
    assert not oracle.evaluate(0.,[1.],uid='A')['cache_hit']
    assert oracle.evaluate(0.,[1.],uid='B')['cache_hit']
    oracle.hardware_record={'sha256':'other_hardware'}
    assert not oracle.evaluate(0.,[1.],uid='C')['cache_hit']
    oracle.full_fresh_probe([])
    assert calls==[False,False,True] and not oracle._independent_fresh


def test_windows_atomic_replacement_retries_transient_reader_lock(tmp_path,monkeypatch):
    import v44.common as common
    original=common._original_replace;attempts=[];pauses=[]
    def blocked_then_replaced(source,target):
        attempts.append((source,target))
        if len(attempts)<=3:raise PermissionError(13,'transient Windows reader handle')
        return original(source,target)
    monkeypatch.setattr(common,'_original_replace',blocked_then_replaced)
    monkeypatch.setattr(common.time,'sleep',lambda value:pauses.append(value))
    target=tmp_path/'status.json';common.atomic(target,dict(PASS=True))
    assert common.read(target)==dict(PASS=True) and len(attempts)==4 and len(pauses)==3
    assert not list(tmp_path.glob('*.tmp'))


def test_binary_extended_bound_metadata_uses_original_storage_digest(tmp_path,stage_request):
    from v44.checkpoints import save_binary
    from v42_pr134_b1.common import digest as original_digest
    names=('FULL_A.npz','FULL_DATA.npz','C3A_A.npz','C3A_DATA.npz','CURRENT_C2_AXES.npz',
        'CURRENT_C2_ALIASES.json','CURRENT_C2_ROW_PROOFS.json','SCIENTIFIC_CASE_IDENTITY.json',
        'FIXED_AIDC_ANCHOR.json','ORIGINAL_DOMAIN_EQUIVALENCE.json')
    for name in names:(tmp_path/name).write_bytes(b'NAMED_SERIALIZATION_FIXTURE_ONLY')
    bound=[dict(column=1,old_lower=-float('inf'),old_upper=float('inf'),new_lower=0.,new_upper=0.)]
    case=SimpleNamespace(output=tmp_path,presolve=SimpleNamespace(bound=bound),
        case_sha=digest('fixture'),identity=dict(aidc_anchor=digest('fixture_anchor')))
    save_binary(case,stage_request)
    assert original_digest(read(tmp_path/'CURRENT_C2_BOUND_PROOFS.json'))==original_digest(bound)


@pytest.mark.parametrize('change',[
    {'day':'2025-05-02'}, {'arm':'B3'}, {'stage':'A1'}, {'stage':'M2'},
    {'case_root':'different_attempt'}, {'source_sha':'different_source'},
    {'scientific_source_sha':'different_science'},
])
def test_single_b2_pilot_cannot_dispatch_other_case_or_optimization(change):
    from v44.pilot import MODE,STAGES,POLICY,check_scope
    permit=dict(mode=MODE,explicit_user_approved=True,day=DAYS[0],arm='B2',
        stages=STAGES,policy=POLICY,case_root='attempt001',case_source_sha='source',scientific_source_sha='science')
    request=dict(day=DAYS[0],arm='B2',stage='M1',case_root='attempt001',source_sha='source',scientific_source_sha='science')
    assert check_scope(permit,request) is permit
    with pytest.raises(PermissionError):check_scope(permit,dict(request,**change))


def test_single_b2_pilot_rejects_budget_or_automatic_advance_drift():
    from v44.pilot import MODE,STAGES,POLICY,check_scope
    permit=dict(mode=MODE,explicit_user_approved=True,day=DAYS[0],arm='B2',
        stages=STAGES,policy=POLICY,case_root='attempt001',case_source_sha='source',scientific_source_sha='science')
    request=dict(day=DAYS[0],arm='B2',case_root='attempt001',source_sha='source',scientific_source_sha='science')
    for policy in (dict(POLICY,Joint_seconds=1800.),dict(POLICY,automatic_advance=True)):
        with pytest.raises(PermissionError):check_scope(dict(permit,policy=policy),request)
