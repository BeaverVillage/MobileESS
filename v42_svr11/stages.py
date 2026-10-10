"""Existing approved A and common U4 M source bridges, scoped to new hardware."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import shutil,json
from v42_pr134_b1.common import read,record,atomic,digest
from v42_common_campaign.authority import ROOT
from .authority import active

def inputs(request,progress):
    m=active();day=request['day'];arm=request['arm'];raw=Path(m['root'])/'raw'/day;folder=Path(request['input_folder'])
    if (folder/'SVR11_INPUT_READY.json').exists():
        ready=read(folder/'SVR11_INPUT_READY.json')
        if ready['source_SHA']!=m['execution_SHA'] or any(record(r['path'])!=r for r in ready['files']):raise PermissionError('SVR11_INPUT_READY_DRIFT')
        return
    folder.mkdir(parents=True,exist_ok=True)
    for path in raw.iterdir():
        if path.name.endswith('_TEMPLATE_B1.json') or path.name.endswith('_TEMPLATE_B2.json'):continue
        if path.is_file() and not (folder/path.name).exists():shutil.copyfile(path,folder/path.name)
    kind='B1' if arm in ('B1','B3') else 'B2'
    bundle=read(raw/f'NATIVE_INPUT_TEMPLATE_{kind}.json');ops=read(raw/f'OPERATIONS_TEMPLATE_{kind}.json')
    ops['current_day_folder']=str(folder);atomic(folder/'OPERATIONS.json',ops)
    atomic(folder/'NATIVE_INPUT.json',bundle)
    if arm!='B0':
        # Shared identical forecast anchor, regenerated on SVR11; every policy
        # optimizes afresh. A completed model can be reused across policies.
        from .model import generate
        cert=generate(day,folder,Path(m['root'])/'models'/day,progress)
        bundle.update(electrical_certificate=cert,grid_outputs=read(cert['path'])['outputs'])
    atomic(folder/'NATIVE_INPUT.json',bundle)
    atomic(folder/'SVR11_INPUT_READY.json',dict(source_SHA=m['execution_SHA'],day=day,arm=arm,
        files=[record(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name!='SVR11_INPUT_READY.json']))

@contextmanager
def b1_scope(request,manifest):
    from v42_may_campaign import execution as old
    from v42_may_campaign_native90 import execution, budget
    from .authority import verify_request
    from .processes import assert_peers
    original=execution.guard
    def guard(model):
        verify_request(request);assert_peers(request);return original(model)
    token=old._active.set(dict(request=request,manifest=manifest,manifest_sha=request['manifest_SHA'],worker_slot=request['worker_slot']))
    with patch.object(old,'guard',guard),patch.object(budget,'guard',guard):
        try:yield
        finally:old._active.reset(token)

def b1(request,manifest,progress):
    from v42_may_campaign_native90 import a_stage,operations
    from v42_may_campaign_native90.budget import DateBudget
    from v42_may_campaign_native90.preflight import native_zero
    from .operations import scope
    with b1_scope(request,manifest),scope():
        budget=DateBudget(Path(request['result']).parent/'NATIVE_RUNTIME_LEDGER.json',native_limit=5400,progress=progress)
        scientific=a_stage.run(request,budget,progress)
        out=dict(scientific=scientific,PASS=False,status=scientific.get('classification','OPTIMIZATION_FAIL'),Native_Runtime=budget.used())
        if scientific.get('PASS') is not True:return out
        with native_zero() as calls:evaluation=operations.run(request,scientific,progress)
        if calls:raise PermissionError('SVR11_ACTUAL_NATIVE_OPTIMIZATION_FORBIDDEN')
        out.update(evaluation=evaluation,PASS=bool(evaluation['PASS']),status='PASS' if evaluation['PASS'] else 'ACTUAL_AC_FAILED',
            FULL_feasible_certified=True,global_gap_certified=True)
        return out

def b3_setup(request,seal,pipeline):
    from v42_autonomous_b3.worker import original_domain_sha
    from v42_b3_joint.contracts import Authority,StageRequest,canonical
    from v42_b3_joint.source_runtime import source_input_identity,SourceRegistry,RealStageContext
    from v42_b3_joint.grid_binding import InjectionAuthority
    from .model import load_coefficients,verify_coefficients
    m=active();folder=Path(request['input_folder']);i=source_input_identity(folder);bundle=i['bundle'];ops=read(folder/'OPERATIONS.json')
    cert=read(bundle['electrical_certificate']['path']);coeff=load_coefficients(cert,request['day']);verify_coefficients(cert,request['day'],coeff)
    authority=Authority(day=request['day'],input_sha=i['input_sha'],grid_sha=m['hardware']['sha256'],
        pcc_mapping_sha=digest(list(bundle['capacities'])),physical_domain_sha=original_domain_sha(Path(m['origins'][request['day']]['domain_source']),request['day']),
        forecast_sha=digest(ops['forecast_inputs']),runtime_sha=digest({k:bundle.get(k) for k in
            ('runtime_provider','runtime_provider_ready','RUNTIME_PROVIDER_READY','C0_Q50','C0_Q90','CC4_reserve_GPU','runtime_reserve_gamma','runtime_survival_kernel','C0_binding')}),
        source_sha=seal['source_sha'],planning_cutoff=ops['forecast_inputs']['AEMO']['cutoff_fixed_aest'],
        forecast_available_at=ops['forecast_inputs']['AEMO']['demand_issue'],pcc_ids=tuple(bundle['capacities']),mess_ids=tuple(bundle['initial_MESS_sites']))
    registry=SourceRegistry(ROOT,seal['files']);names=list(coeff[0].control_names)
    validity=dict(grid_sha=authority.grid_sha,pcc_mapping_sha=authority.pcc_mapping_sha,producer_source_sha=authority.source_sha,units='kW_kvar',
        sign_convention='ORIGINAL_NATIVE_CONTROL_SIGN',sensitivity_scope='ORIGINAL_FULL_CONTROL_DOMAIN',
        phase_mapping_sha=digest(dict(control_names=names,coefficients=[c.coefficient_sha256 for c in coeff])),
        verifier_source_sha=seal['files']['v42_may_campaign_native90/bindings.py'],coefficient_sha256_by_slot=[c.coefficient_sha256 for c in coeff],
        control_names=names,transformer_phase_rows_per_slot=153)
    grid=InjectionAuthority(registry,authority,validity_json=canonical(validity),expected_transformer_rows=153)
    def factory(stage_request,packets,output):
        return RealStageContext(stage_request,folder,output,canonical(bundle),registry,grid,packets,seal['source_sha'],request['run_id'])
    return authority,factory

def b3(request,manifest,progress):
    from v42_autonomous_b3.admission import execution_permit
    from v42_b3_joint.a_source import ASourceBridge
    from v42_b3_joint.m_source import MSourceBridge
    from v42_b3_joint.source_coordinator import SourceCoordinator
    from v42_b3_joint.operations_bridge import SourceOperationsBridge
    from v42_b3_joint.native_ledger import SourceStageLedger
    from v42_autonomous_b3.worker import realized_inputs
    seal=read(Path(request['root'])/'B3_SOURCE_SEAL.json');pipeline=Path(request['output'])/'PIPELINE'
    with execution_permit(request,seal):
        authority,factory=b3_setup(request,seal,pipeline)
        coordinator=SourceCoordinator(pipeline,factory,ASourceBridge(),MSourceBridge(),
            ledger_factory=lambda context:SourceStageLedger(context,progress=lambda v:progress(dict(v,stage=context.request.stage))))
        outcome=coordinator.run(authority,operations_factory=SourceOperationsBridge,realized_inputs=realized_inputs,progress=progress)
        stages={}
        for stage,out in coordinator.outputs.items():
            ledger=json.loads(out.ledger_receipt)
            stages[stage]=dict(native_seconds=ledger['measured_native_runtime'],native_calls=ledger['native_call_count'],
                FULL_feasible_certified=out.physical_evidence.get('PASS'),bounds=out.global_evidence,output_SHA=out.sha)
        return dict(PASS=outcome['status']=='COMPLETE' and outcome['validation']['PASS'],status=outcome['status'],
            stages=stages,Native_Runtime=sum(s['native_seconds'] for s in stages.values()),outcome=outcome)
