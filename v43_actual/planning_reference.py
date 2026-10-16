"""Reuse the new Golden003 point and original coefficients without solving."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from v43.common import DOC, ROOT, read, record, atomic, verify_records
from .case import accepted, BUNDLE
from .vendor.policy import digest
from .vendor.trajectory_tracking import TrackingReference
from .vendor.sensitivity_policy import OriginalGridPacket
from .vendor.aidc_sensitivity_runtime import anonymous_cohort_residual


def build(args, case, output):
    """Caller holds Native0 and the shared heavy-worker locks."""
    from v42_pr134_b1.native import bind
    from v42_integrated.contract import physical_authority
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    certificate,freeze,native,windows,arrays=accepted()
    folder=Path(freeze['scientific_input']['NATIVE_INPUT.json']['path']).parent
    with physical_authority():
        _,_,coeff,power,idle,swing=bind(native,folder,output/'ORIGINAL_LOAD_ONLY')
    sites=tuple(map(str,arrays['sites']))
    known=np.zeros((96,len(sites)))
    gpu={r['job_uid']:r['GPU_gang'] for r in native['known_population']}
    for uid,option in freeze['selected_jobs'].items():
        for site,left,right in option['segments']:
            known[max(0,left-24):min(96,max(0,right-24)),sites.index(site)]+=gpu[uid]
    anonymous=arrays['GPU']-known
    numerical_floor=float(anonymous.min())
    if numerical_floor < -1e-7:
        raise ValueError('GOLDEN_SELECTED_KNOWN_GPU_PROJECTION_DRIFT')
    anonymous=np.maximum(anonymous,0.)
    service={};carry={}
    for key,value in freeze['globals'].items():
        if key.startswith('CC4_x['):
            service[str(tuple(map(int,key[6:-1].split(','))))]=value
        elif key.startswith('CC4_carryout['):
            carry[key[13:-1]]=value
    cc4_binding_path=BUNDLE.parents[2]/'MAY_CC4_BINDING.json'
    cc4_binding=read(cc4_binding_path)
    kernel=ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv'
    timing=ROOT/'docs/v42_ts_cc4_temporal_refinement/CC4_SERVICE_TIMING_ENVELOPE.csv'
    if record(kernel)['sha256'] != cc4_binding['kernel']['sha256']:
        raise ValueError('ORIGINAL_CC4_KERNEL_CHANGED')
    verify_records([cc4_binding['interface']['prediction']])
    envelope=pd.read_csv(timing)
    bindings=dict(science_sha=digest(dict(Golden_Source=certificate['source_freeze'],
        port_manifest=record(DOC/'GATE_B_SELECTIVE_PORT_MANIFEST.json'))),
        case_sha=case['case_sha'],physical_sha=native['electrical_certificate']['sha256'],
        time_axis_sha=digest(dict(issue=args['begin'],D00=args['begin']+21600,end=args['end'],dt=900)),
        qos_sha=digest(dict(Known=freeze['scientific_input']['WINDOWS.json'],Unknown=case['source_receipts'][4])),
        cc4_sha=cc4_binding['interface']['prediction']['sha256'],runtime_sha=native['runtime_provider']['sha256'],
        response_sha=digest(sorted({c.coefficient_sha256 for c in coeff})),
        initial_state_sha=read(case['initialization']['path'])['initialization_sha'],
        aidc_anchor=certificate['planning_freeze']['sha256'],
        interface_sha=digest(dict(contract='V43_PR189_PENDING_PRESITE',basic='CAUSAL_GRID_BLIND_REFERENCE',
            source_change='UID_DESTINATION_CONSENT_AND_READY_DATA',Known_commands_modified=False)))
    mess_sites=sorted({name.split('[',1)[1][:-1] for name in coeff[0].control_names if name.startswith('mess_')})
    mess=dict(P_by_site={s:[0.]*96 for s in mess_sites},Q_by_site={s:[0.]*96 for s in mess_sites},
        units=4,initial_sites=native['initial_MESS_sites'],
        authority='GOLDEN003_ALL_MESS_PQ_ZERO_ALREADY_PHYSICALLY_VALIDATED',
        Golden003=certificate['planning_freeze'])
    mess['plan_sha']=digest(mess);bindings['mess_anchor']=mess['plan_sha']
    cc4_authority=dict(model_id=cc4_binding['interface']['model'],prediction_sha=bindings['cc4_sha'],
        kernel_sha=record(kernel)['sha256'],timing_envelope_sha=record(timing)['sha256'],
        aidc_anchor=bindings['aidc_anchor'],q50_hourly_GPUh=native['C0_Q50'],q90_hourly_GPUh=native['C0_Q90'],
        forecast_modifications=0,future_Actual_or_UID_inputs_used=False)
    identity=dict(CC4_Q50=native['C0_Q50'],CC4_Q90=native['C0_Q90'],CC4_service=service,CC4_carryout=carry,
        Timing_CDF_Q10=envelope.Q10.tolist(),Timing_CDF_Q90=envelope.Q90.tolist(),
        CC4_source_authority=cc4_authority,C1_Power_Model_SHA=args['power_model'].authority_sha,
        Golden003=certificate['planning_freeze'],initial_state=case['initialization'])
    reference=TrackingReference(known,anonymous,arrays['IT_kw'],arrays['PCC_P_kw'],arrays['PCC_Q_kvar'],
        sites=sites,begin=args['begin']+21600,commands=args['known_schedule'],identity=identity)
    aidc=dict(aidc_anchor=bindings['aidc_anchor'],
        AIDC_P_by_site={s:arrays['PCC_P_kw'][:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:arrays['PCC_Q_kvar'][:,j].tolist() for j,s in enumerate(sites)})
    authority=SimpleNamespace(voltage_lower_squared=.95**2,voltage_upper_squared=1.05**2,
        transformer_current_authority_sha256=coeff[0].transformer_current_authority_sha256)
    with physical_authority():
        packet=OriginalGridPacket(coeff,power,swing,native['capacities'],aidc,mess,authority,bindings,
            begin_seconds=reference.begin,known_gpu=known,power_factor=.95,
            rack_compatibility=read(BUNDLE/'PLANNING_INPUT_BUNDLE.json')['rack_compatibility'],
            mess_validation=dict(plan_sha=mess['plan_sha'],frozen_execution_validated=True,
                evidence=certificate['operations'],scope='ZERO_PQ_FROM_NEW_GOLDEN_ONLY'))
    _,cohort=anonymous_cohort_residual(reference,{},reference.begin)
    if cohort['status'] != 'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS':
        raise ValueError('NEW_GOLDEN_CC4_REFERENCE_NOT_CERTIFIED:'+str(cohort))
    receipt=dict(PASS=True,Native_calls=0,optimization_repeated=False,
        Known_selected_UIDs=len(freeze['selected_jobs']),reference_target_sha=reference.sha,bindings=bindings,
        projected_anonymous_numerical_floor=numerical_floor,CC4=cohort,
        electrical_coefficients_regenerated=False,C1_refitted=False,UB_LB_transferred_to_new_CASE=False)
    reference.save(output/'REFERENCE.npz')
    atomic(output/'REFERENCE_PROOF.json',receipt)
    return reference,packet,bindings,receipt
