"""Bind original M mathematics to an explicit May01 AIDC stage freeze."""
from copy import deepcopy
from pathlib import Path

import numpy as np

from v43.common import DOC,read,record,verify_records,atomic
from v42_native.contracts import digest


def golden_a1():
    from v43_actual.case import accepted
    certificate,freeze,native,windows,arrays=accepted()
    verify_records([certificate['source_freeze']])
    source=read(certificate['source_freeze']['path'])
    verify_records(source['sources']+source['support']+source['scientific_inputs'])
    atomic(DOC/'V43_B3_A1_GOLDEN003_REUSE_EQUIVALENCE.json',dict(PASS=True,
        scope='B3_A1_EXACT_ACCEPTED_PR189_B1_A1_REUSE_ONLY_NOT_A2',
        source=certificate['source_freeze'],case_input=freeze['scientific_input'],
        planning=certificate['planning_freeze'],arrays=certificate['planning_arrays'],
        new_optimization_run=False,Native_calls=0,A2_certified=False))
    return dict(bundle=native,planning=arrays,
        identity=dict(PASS=True,day=native['day'],parent_case_sha=certificate['planning_freeze']['sha256'],
            aidc_anchor=certificate['planning_freeze']['sha256'],stage='A1',arm='B1',
            parent_acceptance=record(DOC/'GOLDEN003_CERTIFIED_NUMERICAL_CASE.json'),
            reused_exact_A1=True,A2_certified=False,selected_jobs_sha=digest(freeze['selected_jobs'])))


def build(payload,request,progress=None):
    from .library import load,current_identity
    from v42_may_campaign_native90.m_model import build_case,verify_case
    from v44.config import DAYS,JOINT_SECONDS
    if request['day'] not in DAYS or request['arm'] not in ('B2','B3') or request['stage'] not in ('M1','M2'):
        raise ValueError('MAY01_FIXED_AIDC_M_STAGE_REQUIRED')
    if request['arm']=='B2' and payload['identity'].get('arm')!='B0':
        raise ValueError('B2_MUST_FIX_B0_NOT_B1_AIDC')
    if request['arm']=='B3' and payload['identity']['stage']!=('A1' if request['stage']=='M1' else 'A2'):
        raise ValueError('B3_A1_M1_A2_M2_HANDOFF_REQUIRED')
    load()
    from .performance import profiled_build
    def report(value):
        if progress:progress(dict(value,arm=request['arm'],stage=request['stage']))
    from v44.planning import check_native
    check_native(payload['bundle'])
    case=profiled_build(build_case,stage=request['stage'])(payload,request,report)
    verify_case(case)
    inherited=deepcopy(case.identity)
    case.identity=dict(inherited,schema='V44_DATED_FIXED_AIDC_MESS_CASE_V1',
        arm=request['arm'],stage=request['stage'],source_sha=request['source_sha'],
        parent_case_sha=payload['identity']['parent_case_sha'],aidc_anchor=payload['identity']['aidc_anchor'],
        upstream_A_stage=payload['identity']['stage'],qos_sha=digest(payload['bundle']['known_population']),
        physical_contract_sha=digest(payload['bundle']['electrical_certificate']))
    case.case_sha=digest(case.identity)
    current_identity(case)
    # Metadata comes from the very same original archive. It changes no
    # coefficient, row, bound, power, objective or device control.
    electrical=case.bundle['electrical_certificate'];verify_records([electrical])
    archive=read(electrical['path'])['outputs']['planning_coefficients'];verify_records([archive])
    with np.load(archive['path'],allow_pickle=False) as z:
        branches=z['branch_names'].astype(str)
        if not np.array_equal(branches,np.asarray(case.coefficients[0].branch_names).astype(str)):
            raise ValueError('ORIGINAL_M_BRANCH_METADATA_DRIFT')
        nodes=z['node_names'].copy()
    # Expose names to K48's existing metadata-only interface, leaving the
    # original normalized coefficient records intact for physical validation.
    case._v43_coefficient_metadata=dict(node_names=nodes,branch_names=branches,
        transformer_ratings=np.asarray(case.coefficients[0].transformer_ratings))
    case.plan_exporter=load()['m_engine'].export_plan
    case.mess_stage_budget_seconds=JOINT_SECONDS
    atomic(case.output/'INHERITED_MATHEMATICAL_CASE_IDENTITY.json',inherited)
    atomic(case.output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**case.identity))
    return case
