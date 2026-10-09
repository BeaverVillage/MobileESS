from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
import numpy as np
import pytest
from v42_may_campaign_native90.a_routing import rebound
from v42_may_campaign_native90 import inputs
from v42_autonomous_b2.worker import CANONICAL

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
    with proof_scope(request,dict(execution_SHA='test_routing_only')) as routes:
        assert m_stage._strict_ub is algorithms._strict_ub is routes['final']['_strict_ub']
        assert m_stage._strict_ub.__code__ is before[0].__code__
        assert core.write is algorithms.write is routes['write']
        assert pricing.output_directory is dw.output_directory is routes['output_directory']
        assert (core.ROOT,algorithms.ROOT,final_verify.ROOT,operations.ROOT)==roots
        pricing.output_directory(routes['output']/'L1_PRICING')
        algorithms.write(routes['output']/'frontier/STATE.json',dict(PASS=True))
        assert operations.d_path(routes['output']/'OPERATIONS')==routes['output']/'OPERATIONS'
        with pytest.raises(ValueError,match='SCOPED_PROOF'):
            operations.d_path(folder/'OPERATIONS')
    assert (m_stage._strict_ub,algorithms._strict_ub,core.write,algorithms.write,
            pricing.output_directory,dw.output_directory,operations.d_path)==before
    receipt=core.read(Path(request['output'])/'SCOPED_PROOF_PATH_AUTHORITY.json')
    assert receipt['read_only_inputs_unchanged'] and receipt['original_validator_sources_unchanged']
    assert receipt['proof_read_write_roots']==[request['output']]


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
