from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
import numpy as np
import pytest
from v42_may_campaign_native90.a_routing import rebound
from v42_may_campaign_native90 import inputs
from v42_autonomous_b2.worker import CANONICAL


def test_module_cli_dispatches_canonical_run_once_with_original_request_and_exit(monkeypatch):
    import runpy,sys,warnings
    from v42_autonomous_b2 import worker
    seen=[];request='D:/native_denied_cli/request with spaces + receipt.json'
    monkeypatch.setattr(worker,'run',lambda path:seen.append(path) or 17)
    monkeypatch.setattr(sys,'argv',['v42_autonomous_b2.worker',request])
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message=".*found in sys.modules.*",category=RuntimeWarning)
        with pytest.raises(SystemExit) as result:
            runpy.run_module('v42_autonomous_b2.worker',run_name='__main__',alter_sys=True)
    assert result.value.code==17 and seen==[request]


def test_module_cli_actual_run_uses_exact_guarded_budget_and_restores_input_alias(monkeypatch):
    import runpy,sys,warnings,gurobipy as gp
    from v42_autonomous_b2 import worker,rmp_presolve
    from v42_b2_seed_recovery_v19 import worker as original
    seen=[];request='D:/native_denied_cli/unentered_request.json'
    before=inputs.generate_b2
    def probe(path):
        # DateBudget is supplied by the actual run() rebound namespace.
        assert DateBudget is worker.ReceiptDateBudget
        assert DateBudget is rmp_presolve.ReceiptDateBudget
        assert DateBudget.optimize is rmp_presolve._ORIGINAL_RECEIPT_OPTIMIZE
        assert DateBudget.native_optimize is rmp_presolve._ORIGINAL_NATIVE_OPTIMIZE
        budget=DateBudget.__new__(DateBudget)
        # The unchanged strict guard accepts the Budget identity and still
        # rejects a missing Native model before any constructor/delegate.
        with pytest.raises(PermissionError,match='RMP_PRESOLVE_EXACT_OWNED_MODEL_TYPES_REQUIRED'):
            rmp_presolve._delegates(None,budget)
        assert inputs.generate_b2 is not before and inputs.generate_b2.__code__ is before.__code__
        seen.append(path)
        return 0
    monkeypatch.setattr(original,'run',probe)
    monkeypatch.setattr(gp,'Model',lambda *a,**k:pytest.fail('REAL_NATIVE_MODEL_FORBIDDEN'))
    monkeypatch.setattr(sys,'argv',['v42_autonomous_b2.worker',request])
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message=".*found in sys.modules.*",category=RuntimeWarning)
        with pytest.raises(SystemExit) as result:
            runpy.run_module('v42_autonomous_b2.worker',run_name='__main__',alter_sys=True)
    assert result.value.code==0 and seen==[request] and inputs.generate_b2 is before


def test_fresh_interpreter_cli_keeps_canonical_budget_identity_without_native_or_ledger(tmp_path):
    import json,subprocess,sys
    from v42_autonomous_b2 import worker
    request=str(tmp_path/'unentered request + authority.json')
    code=r'''
import json,runpy,sys,warnings
from unittest.mock import patch
import gurobipy as gp
from v42_autonomous_b2 import worker,pricing_cache,rmp_presolve,f1_basis
from v42_b2_seed_recovery_v19 import worker as original
real_model=gp.Model;modelattempts=[];nativeattempts=[];seen=[]
def denied_model(*args,**kwargs):
    modelattempts.append(True);raise AssertionError('REAL_MODEL_FORBIDDEN')
def denied_native(*args,**kwargs):
    nativeattempts.append(True);raise AssertionError('REAL_NATIVE_FORBIDDEN')
def probe(path):
    assert DateBudget is worker.ReceiptDateBudget is rmp_presolve.ReceiptDateBudget
    assert DateBudget.optimize is rmp_presolve._ORIGINAL_RECEIPT_OPTIMIZE
    assert DateBudget.native_optimize is rmp_presolve._ORIGINAL_NATIVE_OPTIMIZE
    budget=DateBudget.__new__(DateBudget)
    try:rmp_presolve._delegates(None,budget)
    except PermissionError as error:
        assert str(error)=='RMP_PRESOLVE_EXACT_OWNED_MODEL_TYPES_REQUIRED'
    else:raise AssertionError('MISSING_MODEL_NOT_DENIED')
    seen.append(dict(path=path,Budget_module=DateBudget.__module__))
    return 0
request=sys.argv[1];before=original.run
with patch.object(original,'run',probe),patch.object(gp,'Model',side_effect=denied_model),patch.object(real_model,'__init__',side_effect=denied_model),patch.object(real_model,'optimize',side_effect=denied_native):
    sys.argv=['v42_autonomous_b2.worker',request]
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='.*found in sys.modules.*',category=RuntimeWarning)
        try:runpy.run_module('v42_autonomous_b2.worker',run_name='__main__',alter_sys=True)
        except SystemExit as result:assert result.code==0
        else:raise AssertionError('CLI_DID_NOT_EXIT')
assert original.run is before and not modelattempts and not nativeattempts
print(json.dumps(dict(PASS=True,seen=seen,modelattempts=modelattempts,nativeattempts=nativeattempts)))
'''
    result=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,request],
        cwd=worker.ROOT,capture_output=True,text=True,check=True)
    proof=json.loads(result.stdout)
    assert proof==dict(PASS=True,seen=[dict(path=request,Budget_module='v42_autonomous_b2.worker')],modelattempts=[],nativeattempts=[])
    assert not Path(request).exists()


def test_provenance_rebound_keeps_original_code_object_and_checks():
    generated=rebound(inputs.generate_b2,dict(inputs.generate_b2.__globals__,ROOT=CANONICAL))
    assert generated.__code__ is inputs.generate_b2.__code__
    assert generated.__globals__['ROOT']==CANONICAL
    assert generated.__globals__['fixed_aidc'] is inputs.fixed_aidc
    assert generated.__globals__['sha'] is inputs.sha
    assert generated.__globals__['read'] is inputs.read

def test_admission_scope_installs_accounting_context_before_native_peer_guard(monkeypatch):
    from v42_autonomous_b2 import worker
    from v42_may_campaign import execution as legacy
    request=dict(manifest_SHA='x',worker_slot=2)
    monkeypatch.setattr(worker,'verify_request',lambda r:dict(valid=True))
    monkeypatch.setattr(worker,'proof_scope',lambda *args:nullcontext())
    monkeypatch.setattr(worker,'assert_peers',lambda r:(_ for _ in ()).throw(AssertionError('Native only')))
    with worker.worker_scope(request):
        assert legacy._active.get()['worker_slot']==2
        assert legacy._active.get()['manifest']==dict(valid=True)
    assert legacy._active.get() is None


def proof_request(tmp_path,day='2025-05-03',attempt='proof_v22_01'):
    return dict(root=str(tmp_path),arm='B2',day=day,attempt_id=attempt,
        output=str(tmp_path/'dates/B2'/day/'attempts'/attempt/'output'))


def test_exact_own_output_paths_and_original_source_guards(tmp_path):
    from v42_autonomous_b2.worker import proof_routes
    from v42_m1_hybrid import final_verify
    request=proof_request(tmp_path);r=proof_routes(request)
    original_root=final_verify.ROOT
    point=r['output']/'adaptive/RAW.npz'
    assert r['final']['_under'](point,original_root,'EVIDENCE')==point
    for outside in (tmp_path/'other',Path(request['output']).parent/'other',
            tmp_path/'dates/B2/2025-05-02/attempts/proof_v22_01/output/RAW.npz',
            original_root/'runtime/historical/RAW.npz',tmp_path/'inputs/NATIVE_INPUT.json'):
        with pytest.raises(ValueError,match='SCOPED_PROOF'):
            r['final']['_under'](outside,original_root,'EVIDENCE')
    # Test storage lies inside the source checkout; compare the original guard
    # directly, and also exercise an external campaign path outside that root.
    assert r['final']['_under'](point,original_root,'PROTECTED_SOURCE')==final_verify._under(
        point,original_root,'PROTECTED_SOURCE')
    with pytest.raises(ValueError,match='HYBRID_FINAL_D_PATH_REQUIRED:PROTECTED_SOURCE'):
        r['final']['_under'](Path('D:/scoped_proof_external/RAW.npz'),original_root,'PROTECTED_SOURCE')
    assert r['final']['_under'](original_root/'v42_m1_hybrid/final_verify.py',
        original_root,'PROTECTED_SOURCE')==original_root/'v42_m1_hybrid/final_verify.py'
    assert final_verify.ROOT==original_root
    assert r['final']['ROOT']==original_root
    for name in ('_raw','_json','_packet','_strict_ub'):
        assert r['final'][name].__code__ is getattr(final_verify,name).__code__


def test_raw_packet_sha_and_recorded_path_contract_survives_routing(tmp_path):
    from v42_autonomous_b2.worker import proof_routes,record
    r=proof_routes(proof_request(tmp_path));r['output'].mkdir(parents=True)
    path=r['output']/'PACKET.json';path.write_text('{"PASS": true}',encoding='utf8')
    binding=record(path);evidence={}
    assert r['final']['_packet'](binding,path,evidence)==dict(PASS=True)
    assert evidence[str(path)]==binding['sha256']
    path.write_text('{"PASS": false}',encoding='utf8')
    with pytest.raises(ValueError,match='PACKET_SHA_DRIFT'):
        r['final']['_packet'](binding,path,{})
    with pytest.raises(ValueError,match='PACKET_PATH_BINDING_DRIFT'):
        r['final']['_packet'](dict(binding,path=str(r['output']/'OTHER.json')),path,{})


def test_routed_strict_validator_preserves_exact_full_integer_and_objective_gates(tmp_path):
    from v42_autonomous_b2.worker import proof_routes
    r=proof_routes(proof_request(tmp_path));r['output'].mkdir(parents=True)
    # Tiny axes isolate the unchanged literal FULL integer and objective gates;
    # actual 961362-row physical replay is separately run on saved May03 data.
    domain=dict(types=np.array(['B','C']),objective=np.array([0.,1.]),constant=0.)
    case=SimpleNamespace(A=np.zeros((1,2)),d=domain,original_d=dict(domain),
                         lift=lambda x:x.copy())
    r['final']['validate_candidate']=lambda *args:dict(PASS=True)
    packet=r['output']/'RAW.npz';np.savez_compressed(packet,point=np.array([1.,.5]))
    receipt=r['final']['_strict_ub'](case,packet,{})
    assert receipt['PASS'] and receipt['exact_Global_UB']=='1/2'
    assert receipt['Native_optimize_calls']==0
    case.lift=lambda x:np.array([1.-1e-12,x[1]])
    with pytest.raises(ValueError,match='LITERAL_INTEGER_GATE_FAILED:FULL'):
        r['final']['_strict_ub'](case,packet,{})
    case.lift=lambda x:x.copy();case.original_d=dict(domain,constant=.01)
    with pytest.raises(ValueError,match='EXACT_OBJECTIVE_TRANSPORT_DRIFT'):
        r['final']['_strict_ub'](case,packet,{})


def test_downstream_output_routing_rejects_siblings(tmp_path):
    from v42_autonomous_b2.worker import proof_routes
    from v42_m1_anytime import core
    r=proof_routes(proof_request(tmp_path))
    r['output_directory'](r['output']/'L1')
    r['write'](r['output']/'frontier/STATE.json',dict(PASS=True))
    assert core.read(r['output']/'frontier/STATE.json')==dict(PASS=True)
    assert r['write'].__code__ is core.write.__code__
    assert core.ROOT!=r['write'].__globals__['ROOT']
    with pytest.raises(ValueError,match='D_ONLY'):
        r['write'](r['output'].parent/'OTHER.json',{})
    with pytest.raises(ValueError,match='SCOPED_PROOF'):
        r['output_directory'](tmp_path/'dates/B2/2025-05-04')


def test_request_output_escape_and_invalid_axis_are_refused(tmp_path):
    from v42_autonomous_b2.worker import proof_routes
    request=proof_request(tmp_path)
    with pytest.raises(PermissionError,match='OWN_OUTPUT_REQUIRED'):
        proof_routes(dict(request,output=str(tmp_path)))
    for changed in (dict(day='../2025-05-03'),dict(attempt_id='../other'),dict(arm='B3')):
        with pytest.raises(PermissionError,match='IDENTITY_REQUIRED'):
            proof_routes(dict(request,**changed))


def test_production_scope_routes_imported_aliases_and_restores_sources(tmp_path):
    from v42_autonomous_b2.worker import proof_scope,record
    from v42_may_campaign_native90 import m_stage,operations
    from v42_m1_anytime import core,algorithms
    from v42_m1_hybrid import pricing,dw,final_verify
    from v42_b2_seed_recovery_v18 import certificate_box
    from v42_pr134_b1 import common
    from v42_autonomous_b2 import canonical_stream
    from v42_b2_seed_recovery_v19.common import atomic
    request=proof_request(tmp_path);folder=tmp_path/'inputs';folder.mkdir()
    for name in ('B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz','LINKED.json'):
        (folder/name).write_text('{}',encoding='utf8')
    linked=record(folder/'LINKED.json')
    atomic(folder/'NATIVE_INPUT.json',dict(route_table=linked,electrical_certificate=linked))
    manifest=tmp_path/'MANIFEST.json';manifest.write_text('{}',encoding='utf8')
    request.update(input_folder=str(folder),manifest=str(manifest),run_id='proof_only')
    before=(m_stage._strict_ub,algorithms._strict_ub,core.write,algorithms.write,
            pricing.output_directory,dw.output_directory,operations.d_path)
    roots=(core.ROOT,algorithms.ROOT,final_verify.ROOT,operations.ROOT)
    serialization=(certificate_box.digest,certificate_box.atomic,common.digest,common.atomic)
    dw_before=(dw.build_master,dw.write)
    pricing_before=pricing.run_pricing
    checker=certificate_box.check.__code__
    with proof_scope(request,dict(execution_SHA='test_routing_only')) as routes:
        assert m_stage._strict_ub is algorithms._strict_ub is routes['final']['_strict_ub']
        assert m_stage._strict_ub.__code__ is before[0].__code__
        assert core.write is algorithms.write is routes['write']
        assert pricing.output_directory is dw.output_directory is routes['output_directory']
        assert (core.ROOT,algorithms.ROOT,final_verify.ROOT,operations.ROOT)==roots
        assert certificate_box.digest is canonical_stream.digest
        assert certificate_box.check.__code__ is checker
        assert dw.build_master.original_builder.__code__ is dw_before[0].__code__
        assert dw.write is routes['write']
        assert pricing.run_pricing.original_pricing.__code__ is pricing_before.__code__
        assert (common.digest,common.atomic)==serialization[2:]
        packet=routes['output']/'CERTIFICATE_DOMAIN_PROOFS/P.json'
        certificate_box.atomic(packet,dict(PASS=True,exact='1/3'))
        assert core.read(packet)==dict(PASS=True,exact='1/3')
        with pytest.raises(ValueError,match='SCOPED_PROOF'):
            certificate_box.atomic(folder/'PROOF.json',dict(PASS=True))
        assert not (folder/'PROOF.json').exists()
        pricing.output_directory(routes['output']/'L1_PRICING')
        algorithms.write(routes['output']/'frontier/STATE.json',dict(PASS=True))
        assert operations.d_path(routes['output']/'OPERATIONS')==routes['output']/'OPERATIONS'
        with pytest.raises(ValueError,match='SCOPED_PROOF'):
            operations.d_path(folder/'OPERATIONS')
    assert (m_stage._strict_ub,algorithms._strict_ub,core.write,algorithms.write,
            pricing.output_directory,dw.output_directory,operations.d_path)==before
    assert (certificate_box.digest,certificate_box.atomic,common.digest,common.atomic)==serialization
    assert (dw.build_master,dw.write)==dw_before
    assert pricing.run_pricing is pricing_before
    receipt=core.read(Path(request['output'])/'SCOPED_PROOF_PATH_AUTHORITY.json')
    assert receipt['read_only_inputs_unchanged'] and receipt['original_validator_sources_unchanged']
    assert receipt['proof_read_write_roots']==[request['output']]
    assert receipt['certificate_proof_serialization']=='V42_B2_CANONICAL_STREAM_V24'
    assert receipt['restricted_master_native_rows']=='V42_B2_RMP_EXACT_POWER_OF_TWO_ROWS_V25'
    assert receipt['pricing_nonunit_box']=='V42_B2_PRICING_FULL_CASE_PROJECTION_BOX_V26'


@pytest.mark.parametrize('failure',('pricing','RMP'))
def test_production_computational_hooks_are_attempt_scoped_lazy_and_close_on_failure(tmp_path,monkeypatch,failure):
    from contextlib import contextmanager
    import gurobipy as gp
    from v42_autonomous_b2 import worker,pricing_cache,rmp_presolve
    from v42_m1_hybrid import pricing,dw
    request=proof_request(tmp_path);folder=tmp_path/'inputs';folder.mkdir()
    for name in ('B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz','LINKED.json'):
        (folder/name).write_text('{}',encoding='utf8')
    linked=worker.record(folder/'LINKED.json')
    from v42_b2_seed_recovery_v19.common import atomic
    atomic(folder/'NATIVE_INPUT.json',dict(route_table=linked,electrical_certificate=linked))
    manifest_path=tmp_path/'MANIFEST.json';manifest_path.write_text('{}',encoding='utf8')
    request.update(input_folder=str(folder),manifest=str(manifest_path),run_id='hook_only')
    manifest=dict(execution_SHA='test_lazy_only');events=[]
    saved_prices=pricing.run_pricing;saved_rmp=dw.run
    monkeypatch.setattr(gp,'Model',lambda *a,**k:pytest.fail('REAL_NATIVE_MODEL_FORBIDDEN'))
    class Cache:
        def scoped_pricing(self,original,output_directory):
            assert original is saved_prices
            def run(*args,**kwargs):
                events.append(('prices',args,kwargs))
                if kwargs.get('fail'):raise RuntimeError('pricing failure')
                return 'price receipt'
            return run
    @contextmanager
    def factory(actual_request,actual_manifest,code_root):
        assert actual_request is request and actual_manifest is manifest and code_root==worker.ROOT
        events.append(('cache_open',))
        try:yield Cache()
        finally:events.append(('cache_close',))
    def master_factory(original,output_directory,write):
        assert original is saved_rmp;events.append(('master_open',))
        def run(*args,**kwargs):
            events.append(('master',args,kwargs))
            if failure=='RMP':raise RuntimeError('RMP failure')
            return 'master receipt'
        return run
    monkeypatch.setattr(pricing_cache,'create_scope',factory)
    monkeypatch.setattr(rmp_presolve,'scoped_runner',master_factory)
    args=(object(),object(),object(),object(),Path(request['output'])/'round')
    with pytest.raises(RuntimeError,match=failure+' failure'):
        with worker.proof_scope(request,manifest):
            assert events==[]
            assert pricing.run_pricing(*args,seconds=30)=='price receipt'
            if failure=='pricing':pricing.run_pricing(*args,fail=True)
            else:dw.run(*args,seconds=30)
    assert sum(event[0]=='cache_open' for event in events)==1
    assert sum(event[0]=='cache_close' for event in events)==1
    prices=[event for event in events if event[0]=='prices']
    assert prices[0][1]==args and prices[0][2]==dict(seconds=30)
    if failure=='RMP':
        assert sum(event[0]=='master_open' for event in events)==1
        assert [event for event in events if event[0]=='master'][0][2]==dict(seconds=30)
    assert pricing.run_pricing is saved_prices and dw.run is saved_rmp


def test_production_scope_refuses_input_generation_and_detects_writes(tmp_path):
    from v42_autonomous_b2.worker import proof_scope,record
    from v42_b2_seed_recovery_v19.common import atomic
    request=proof_request(tmp_path);folder=tmp_path/'inputs';folder.mkdir()
    request.update(input_folder=str(folder),manifest=str(tmp_path/'MANIFEST.json'),run_id='proof_only')
    with pytest.raises(PermissionError,match='FROZEN_INPUT_REQUIRED'):
        with proof_scope(request,dict(execution_SHA='test_only')):pass
    for name in ('B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz','LINKED.json','MANIFEST.json'):
        (folder/name).write_text('{}',encoding='utf8')
    request['manifest']=str(folder/'MANIFEST.json')
    linked=record(folder/'LINKED.json')
    atomic(folder/'NATIVE_INPUT.json',dict(route_table=linked,electrical_certificate=linked))
    with pytest.raises(PermissionError,match='READ_ONLY_INPUT_CHANGED'):
        with proof_scope(request,dict(execution_SHA='test_only')):
            (folder/'B2_FIXED_AIDC.json').write_text('{"changed": true}',encoding='utf8')


def test_native_receipt_bridge_keeps_the_original_solve_and_exact_accounting(monkeypatch):
    from v42_autonomous_b2.worker import ReceiptDateBudget,OriginalDateBudget
    budget=ReceiptDateBudget.__new__(ReceiptDateBudget)
    budget.calls=[];budget.inflight=None;seen=[]
    receipt=dict(track='UB',label='000_U1_00',entered_native=True,
        runtime_unavailable=False,Native_Runtime=45.948999881744385,Native_Work=56.2185)
    def original_solve(self,model,callback=None,**kwargs):
        seen.append((model,callback,kwargs));self.calls.append(receipt)
        # Reproduce V19's implicit None return after real receipt persistence.
    monkeypatch.setattr(OriginalDateBudget,'native_optimize',original_solve)
    model=object();callback=object()
    returned=budget.optimize(model,track='UB',label='000_U1_00',requested_seconds=120.,callback=callback)
    assert returned==receipt and budget.calls==[receipt]
    assert seen==[(model,callback,dict(component='P1',track='UB',label='000_U1_00',requested_seconds=120.))]
    assert ReceiptDateBudget.native_optimize is OriginalDateBudget.native_optimize
    assert returned['Native_Runtime']==45.948999881744385


def test_native_receipt_bridge_never_reuses_stale_or_unknown_calls(monkeypatch):
    from v42_autonomous_b2.worker import ReceiptDateBudget,OriginalDateBudget
    budget=ReceiptDateBudget.__new__(ReceiptDateBudget);budget.calls=[];budget.inflight=None
    monkeypatch.setattr(OriginalDateBudget,'native_optimize',lambda *args,**kwargs:None)
    with pytest.raises(PermissionError,match='COMPLETED_NATIVE_RECEIPT_REQUIRED'):
        budget.optimize(None,track='UB',label='x',requested_seconds=120.)
    def bad(self,*args,**kwargs):
        self.calls.append(dict(track='UB',label='x',entered_native=True,
            runtime_unavailable=True,Native_Runtime=None))
    monkeypatch.setattr(OriginalDateBudget,'native_optimize',bad)
    with pytest.raises(PermissionError,match='NATIVE_RECEIPT_IDENTITY_DRIFT'):
        budget.optimize(None,track='UB',label='x',requested_seconds=120.)


def test_native_receipt_bridge_propagates_native_errors_without_retry(monkeypatch):
    from v42_autonomous_b2.worker import ReceiptDateBudget,OriginalDateBudget
    budget=ReceiptDateBudget.__new__(ReceiptDateBudget);budget.calls=[];budget.inflight=None
    calls=[]
    def fail(*args,**kwargs):calls.append(True);raise RuntimeError('original native failure')
    monkeypatch.setattr(OriginalDateBudget,'native_optimize',fail)
    with pytest.raises(RuntimeError,match='original native failure'):
        budget.optimize(None,track='UB',label='x',requested_seconds=120.)
    assert calls==[True] and budget.calls==[]


def test_request_seal_detects_serialization_source_tamper(tmp_path,monkeypatch):
    from v42_autonomous_b2 import worker
    from v42_b2_seed_recovery_v19.common import atomic,sha,digest
    source=tmp_path/'canonical_stream.py';source.write_text('verified source',encoding='utf8')
    monkeypatch.setattr(worker,'sources',lambda:{'canonical_stream.py':sha(source)})
    request=proof_request(tmp_path);manifest_path=tmp_path/'MANIFEST.json'
    manifest=dict(schema='V42_AUTONOMOUS_B2_V20',execution_sources=worker.sources(),
        execution_SHA=digest(worker.sources()),attempt_id=request['attempt_id'],run_id='test_only',
        input_folders={request['day']:str(tmp_path/'inputs')},initialization_native_limit_seconds=5400,
        builder_original_sources={},inherited_B1_results={},prior_attempts={})
    atomic(manifest_path,manifest)
    request.update(manifest=str(manifest_path),manifest_SHA=sha(manifest_path),
        implementation_SHA=manifest['execution_SHA'],run_id=manifest['run_id'],Threads=1,
        P2_calls=0,target_gap=.03,native_budget_seconds=5400,wall_budget_seconds=None,
        input_folder=manifest['input_folders'][request['day']])
    attempt=Path(request['output']).parent
    request.update(result=str(attempt/'RESULT.json'),progress=str(attempt/'progress.json'),error=str(attempt/'error.json'))
    assert worker.verify_request(request)==manifest
    source.write_text('changed source',encoding='utf8')
    with pytest.raises(PermissionError,match='DEPLOYMENT_OR_REQUEST_SEAL_DRIFT'):
        worker.verify_request(request)


def _hook35_frozen_proof_request(tmp_path, worker):
    from v42_b2_seed_recovery_v19.common import atomic
    request = proof_request(tmp_path)
    folder = tmp_path / 'inputs'
    folder.mkdir()
    for name in ('B2_FIXED_AIDC.json', 'PLANNING_PHYSICAL.npz', 'LINKED.json'):
        (folder / name).write_text('{}', encoding='utf8')
    linked = worker.record(folder / 'LINKED.json')
    atomic(folder / 'NATIVE_INPUT.json', dict(route_table=linked, electrical_certificate=linked))
    manifest_path = tmp_path / 'MANIFEST.json'
    manifest_path.write_text('{}', encoding='utf8')
    request.update(input_folder=str(folder), manifest=str(manifest_path), run_id='hook35_only')
    return request, dict(execution_SHA='test_lazy35_only')


@pytest.mark.parametrize('failure', (None, 'factory', 'delegate'))
def test_current_f1_price_hook_is_lazy_once_and_restores_all_aliases(tmp_path, monkeypatch, failure):
    import gurobipy as gp
    from v42_autonomous_b2 import worker, f1_price_seed, f1_basis, f1_state
    from v42_autonomous_b2 import pricing_cache, rmp_presolve, dw_native
    from v42_may_campaign_native90 import m_stage
    from v42_m1_anytime import algorithms
    from v42_m1_hybrid import pricing, dw
    from v42_b2_seed_recovery_v19 import initialization

    # All protected modules above must freeze originals before constructor and
    # Native descriptors are replaced. The outer selected-suite harness also
    # denies these entry points; retaining its denied class here remains safe.
    attempts = []
    retained_model = rmp_presolve._RAW_MODEL_TYPE
    class NativeModelDenied(AssertionError):
        pass
    def denied(*args, **kwargs):
        attempts.append((len(args), sorted(kwargs)))
        raise NativeModelDenied('REAL_NATIVE_MODEL_FORBIDDEN')
    monkeypatch.setattr(retained_model, '__init__', denied)
    monkeypatch.setattr(retained_model, 'optimize', denied)
    monkeypatch.setattr(gp, 'Model', denied)

    request, manifest = _hook35_frozen_proof_request(tmp_path, worker)
    inputs = {str(p): worker.record(p) for p in Path(request['input_folder']).rglob('*') if p.is_file()}
    before = (initialization.validated_start, m_stage._fresh_lp_dual,
              pricing.run_pricing, dw.run, algorithms.lp_round)
    events = []
    sentinels = (object(), object(), object())
    context = {'unchanged': object()}
    case, decomp, dual, budget, frontier = (object() for _ in range(5))

    class FakeCurrentF1Scope:
        def __init__(self, actual_request, code_root):
            assert actual_request is request and code_root == worker.ROOT
            events.append(('scope', self))
        def capture(self, original, actual_case, actual_budget, progress=None):
            assert original is before[0] and actual_case is case and actual_budget is budget
            events.append(('capture', progress))
            return 'captured'
        def full_lp_adapter(self, original, actual_case, actual_budget, progress=None):
            assert original is before[1] and actual_case is case and actual_budget is budget
            events.append(('full_lp', progress))
            return 'full_lp_receipt'

    def forbidden_cache_or_master(*args, **kwargs):
        pytest.fail('PRICE_HOOK_MUST_NOT_EAGERLY_CREATE_CACHE_OR_RMP')

    def factory(original, actual_request, code_root, getter, owned_output, writer):
        assert original is before[4] and actual_request is request and code_root == worker.ROOT
        # The price adapter must capture the installed routing aliases, not an
        # alias from before the worker's pricing and proof-write scopes.
        assert pricing.run_pricing is not before[2]
        assert pricing.run_pricing.original_pricing is before[2]
        assert algorithms.lp_round.original_lp_round is original
        assert writer is algorithms.write
        events.append(('factory', getter, owned_output, writer))
        if failure == 'factory':
            raise RuntimeError('hook35 factory failure')
        def routed(actual_case, actual_decomp, actual_dual, actual_budget,
                   actual_frontier, actual_path, method, kind, *, context=None):
            assert (actual_case is case and actual_decomp is decomp and actual_dual is dual
                    and actual_budget is budget and actual_frontier is frontier)
            scope = getter()
            assert scope is [event[1] for event in events if event[0] == 'scope'][0]
            events.append(('round', scope, actual_path, method, kind, context))
            if failure == 'delegate':
                raise RuntimeError('hook35 delegate failure')
            return sentinels
        return routed

    monkeypatch.setattr(f1_basis, 'Scope', FakeCurrentF1Scope)
    monkeypatch.setattr(f1_price_seed, 'scoped_lp_round', factory)
    monkeypatch.setattr(pricing_cache, 'create_scope', forbidden_cache_or_master)
    monkeypatch.setattr(rmp_presolve, 'scoped_runner', forbidden_cache_or_master)

    def body():
        with worker.proof_scope(request, manifest) as routes:
            assert events == []
            assert algorithms.lp_round.original_lp_round is before[4]
            path = routes['output'] / 'L1_PRICING'
            assert algorithms.lp_round(case, decomp, dual, budget, frontier, path,
                                       'L1', context=context) is sentinels
            assert len([e for e in events if e[0] == 'factory']) == 1
            assert len([e for e in events if e[0] == 'scope']) == 1
            # Initialization and FULL LP must address the same current slot
            # that the already-created lazy price wrapper consults.
            assert initialization.validated_start(case, budget, progress='same_slot') == 'captured'
            assert m_stage._fresh_lp_dual(case, budget, progress='same_slot') == 'full_lp_receipt'
            assert algorithms.lp_round(case, decomp, dual, budget, frontier,
                                       routes['output'] / 'L4_PRICING', 'L4',
                                       'MILP_AND_LP', context=context) is sentinels
    if failure is None:
        body()
        rounds = [e for e in events if e[0] == 'round']
        assert len(rounds) == 2 and all(e[5] is context for e in rounds)
        assert [(e[3], e[4]) for e in rounds] == [('L1', 'LP_ONLY'), ('L4', 'MILP_AND_LP')]
        assert len([e for e in events if e[0] == 'scope']) == 1
    else:
        with pytest.raises(RuntimeError, match='hook35 ' + failure + ' failure'):
            body()
    assert len([e for e in events if e[0] == 'factory']) == 1
    assert (initialization.validated_start, m_stage._fresh_lp_dual,
            pricing.run_pricing, dw.run, algorithms.lp_round) == before
    assert all(worker.record(path) == rec for path, rec in inputs.items())
    assert attempts == []


def test_current_f1_price_hook_no_scheduled_round_creates_no_factory_or_scope(tmp_path, monkeypatch):
    from v42_autonomous_b2 import worker, f1_price_seed, f1_basis, pricing_cache, rmp_presolve
    from v42_m1_anytime import algorithms
    from v42_m1_hybrid import pricing
    request, manifest = _hook35_frozen_proof_request(tmp_path, worker)
    before = (algorithms.lp_round, pricing.run_pricing)
    def forbidden(*args, **kwargs):
        pytest.fail('NO_SCHEDULED_ROUND_MUST_CREATE_NO_SCIENTIFIC_POLICY')
    monkeypatch.setattr(f1_price_seed, 'scoped_lp_round', forbidden)
    monkeypatch.setattr(f1_basis, 'Scope', forbidden)
    monkeypatch.setattr(pricing_cache, 'create_scope', forbidden)
    monkeypatch.setattr(rmp_presolve, 'scoped_runner', forbidden)
    with worker.proof_scope(request, manifest):
        assert algorithms.lp_round is not before[0]
        assert algorithms.lp_round.original_lp_round is before[0]
        assert pricing.run_pricing.original_pricing is before[1]
    assert (algorithms.lp_round, pricing.run_pricing) == before
