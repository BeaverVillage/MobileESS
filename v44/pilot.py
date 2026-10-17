"""Explicitly authorized single May01 B2 SVR11 pilot; no campaign advance."""
from pathlib import Path
import argparse

from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,digest,now,NotReady
from .config import axis,K48_SECONDS,JOINT_SECONDS,JOINT_CALL_CAP

MODE='V44_MAY01_B2_SVR11_PILOT_V1'
OUT=RUNTIME/'may01_B2_SVR11_pilot001'
STAGES=['REFERENCE','K48_M1','M1','ACTUAL','FRESH']
POLICY=dict(Threads=1,K48_seconds=300.,Joint_seconds=900.,Joint_call_cap=140.,
    AIDC_optimization_calls=0,Actual96=True,Fresh96=True,automatic_advance=False)


def check_scope(permit,request):
    if (permit.get('mode')!=MODE or permit.get('explicit_user_approved') is not True
            or permit.get('day')!='2025-05-01' or permit.get('arm')!='B2'
            or permit.get('stages')!=STAGES or permit.get('policy')!=POLICY
            or request.get('day')!='2025-05-01' or request.get('arm')!='B2'
            or request.get('stage') not in (None,*STAGES)
            or request.get('case_root')!=permit.get('case_root')
            or request.get('source_sha')!=permit.get('case_source_sha')
            or request.get('scientific_source_sha')!=permit.get('scientific_source_sha')):
        raise PermissionError('EXACT_MAY01_B2_SVR11_SINGLE_PILOT_SCOPE_REQUIRED')
    return permit


def validate_permit(path,request):
    permit=read(path);check_scope(permit,request)
    if permit.get('permit_sha')!=digest({k:v for k,v in permit.items() if k!='permit_sha'}):
        raise ValueError('PILOT_PERMIT_SHA_DRIFT')
    verify(permit['evidence']+[permit['source_freeze']])
    freeze=read(permit['source_freeze']['path'])
    if freeze['source_sha']!=permit['scientific_source_sha'] or not freeze['source_PASS']:
        raise ValueError('PILOT_SCIENTIFIC_SOURCE_DRIFT')
    if read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')!=freeze:
        raise ValueError('PILOT_SOURCE_FREEZE_SUPERSEDED')
    verify(request['sources'])
    if digest(request['sources'])!=permit['case_source_sha']:raise ValueError('PILOT_CASE_SOURCE_INPUT_DRIFT')
    return permit


def prepare(root=OUT):
    from .daily import day_inputs
    from .svr11_grid import ready
    from .svr11_hardware import HARDWARE
    from .svr11_actual import certificate
    from .config import K48_SECONDS,JOINT_SECONDS,JOINT_CALL_CAP
    if (K48_SECONDS,JOINT_SECONDS,JOINT_CALL_CAP)!=(300.,900.,140.):raise ValueError('PILOT_BUDGET_POLICY_DRIFT')
    root=Path(root)
    if root.exists():raise FileExistsError('NEW_MAY01_B2_PILOT_ROOT_REQUIRED')
    freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
    if not freeze['source_PASS']:raise NotReady('PILOT_SOURCE_FREEZE_NOT_VERIFIED')
    row=day_inputs('2025-05-01');proof=ready('2025-05-01');h=read(HARDWARE/'HARDWARE.json')
    physical=read(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json')
    current=certificate(DOC/'svr11_revision01/CURRENT_AC_CERTIFICATION.json')
    if (not physical.get('PASS') or not physical.get('physical_test_PASS') or h['RegControl_count']!=40
            or proof['hardware']!=record(HARDWARE/'HARDWARE.json')):
        raise NotReady('PILOT_SVR11_SHORT_PHYSICAL_AND_CURRENT_SOURCE_REQUIRED')
    evidence=[record(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json'),record(HARDWARE/'HARDWARE.json'),
        record(DOC/'svr11_revision01/CURRENT_AC_CERTIFICATION.json'),proof['model'],proof['input']]
    for key in ('cache_requalification','MESS_sign_and_site_readback'):
        receipt=physical[key];verify([receipt])
        if not read(receipt['path'])['PASS']:raise NotReady('PILOT_PHYSICAL_IO_NOT_VERIFIED:'+key)
        evidence.append(receipt)
    binding=read(DOC/'svr11_revision01/SEVEN_DAY_COEFFICIENT_BINDING_NATIVE0.json')
    if not any(r['day']=='2025-05-01' and r['PASS'] for r in binding['days']):
        raise NotReady('PILOT_MAY01_ACTUAL_INPUT_LOADER_REQUIRED')
    evidence.append(record(DOC/'svr11_revision01/SEVEN_DAY_COEFFICIENT_BINDING_NATIVE0.json'))
    tests=read(DOC/'LIGHTWEIGHT_TEST_RECEIPT.json')
    if tests['failed'] or tests['passed']<=0:raise NotReady('PILOT_LIGHTWEIGHT_REGRESSION_NOT_PASS')
    evidence.append(record(DOC/'LIGHTWEIGHT_TEST_RECEIPT.json'))
    sources=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]
    sources += [r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']
    sources += list(row['files'].values())+evidence
    sources=list({r['path']:r for r in sources}.values());verify(sources)
    case_root=root/'2025-05-01/B2/attempt001'
    case=dict(day='2025-05-01',arm='B2',worker_slot=1,lane='B2',case_root=str(case_root),
        campaign_root=str(root),sources=sources,source_sha=digest(sources),scientific_source_sha=freeze['source_sha'],
        axis=axis('2025-05-01'))
    permit=dict(mode=MODE,explicit_user_approved=True,UTC=now(),day='2025-05-01',arm='B2',stages=STAGES,policy=POLICY,
        exact_user_authorization='작업 다 끝났으면 V44 5월 1일 B2 실행해봐.',
        case_root=str(case_root),case_source_sha=case['source_sha'],scientific_source_sha=freeze['source_sha'],
        source_freeze=record(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json'),evidence=evidence,
        new_M_FULL_and_K48_projection_required_before_first_Native=True,
        B1_B3_C1_proofs_not_needed_for_FCFS_B2=True,
        overall_7day_PRESTART_READY_claimed=False,old_7reg_planning_point_reused=False)
    permit['permit_sha']=digest(permit)
    root.mkdir(parents=True);path=root/'EXPLICIT_PILOT_PERMIT.json';atomic(path,permit)
    case['execution_permit']=record(path);atomic(root/'REQUEST.json',case)
    validate_permit(path,case);return case


def run(root=OUT):
    from .locks import coordinator
    from .campaign import run_case
    case=prepare(root);root=Path(root)
    with coordinator(root) as lease:
        case['lease']=lease;atomic(root/'PHASE.json',dict(lane='B2',UTC=now()))
        atomic(root/'REQUEST.json',case)
        atomic(RUNTIME/'ACTIVE_MAY01_B2_PILOT.json',dict(root=str(root),request=record(root/'REQUEST.json'),UTC=now()))
        result=run_case(case);atomic(root/'RESULT.json',result)
    print({k:result.get(k) for k in ('PASS','status','error','Actual96_execution_PASS','Fresh96_physical_PASS')},flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--root',type=Path,default=OUT)
    args=parser.parse_args()
    if not args.execute:print(dict(mode='PREPARED_SINGLE_CASE_ONLY',Native_calls=0))
    else:run(args.root)
