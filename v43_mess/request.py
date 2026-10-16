"""Freeze explicit May01 stage sources; never dispatch another date or worker."""
from pathlib import Path
import sys

from v43.common import ROOT,DOC,RUNS,read,record,verify_records,source_records,atomic,git,now
from v42_native.contracts import digest


def sources():
    rows=source_records()
    rows += [record(p) for folder in ('v43_mess','v43_a2','v43_arms','v43_followup','v43_actual')
        for p in sorted((ROOT/folder).rglob('*.py'))]
    library=read(DOC/'V43_MESS_REUSE_SOURCE_MANIFEST.json')
    rows += [r['source'] for r in library['sources']]
    unique={r['path']:r for r in rows}
    rows=[unique[k] for k in sorted(unique)]
    verify_records(rows)
    return rows


def freeze(arm,stage,attempt_name,*,fixed_AIDC_reference=None,M1_result=None):
    valid=(arm=='B2' and stage=='M1') or (arm=='B3' and stage in ('M1','A2','M2'))
    if not valid or Path(attempt_name).name!=attempt_name:raise ValueError('EXPLICIT_MAY01_STAGE_ATTEMPT_NAME_REQUIRED')
    output=RUNS/attempt_name
    if output.exists():raise ValueError('NEW_INDEPENDENT_STAGE_ATTEMPT_REQUIRED')
    rows=sources()
    request=dict(day='2025-05-01',arm=arm,stage=stage,root=str(output),output=str(output),
        sources=rows,source_sha=digest(rows),source_commit=git('rev-parse','HEAD').decode().strip(),
        UTC=now(),Worker=1,Threads=1,P2_calls=0,allowed_execution_dates=['2025-05-01'],
        May02_to_31_authorized=False,Global_Gap_target=.005 if stage=='A2' else .03)
    if arm=='B2' or stage=='M2':
        if fixed_AIDC_reference is None:raise ValueError('M_REQUIRES_EXPLICIT_FIXED_AIDC_REFERENCE_FOLDER')
        reference=Path(fixed_AIDC_reference);doc=read(reference/'AIDC_REFERENCE.json');i=doc['identity']
        if (arm=='B2' and i['arm']!='B0') or (stage=='M2' and (i['arm'],i['stage'])!=('B3','A2')):
            raise ValueError('M_AIDC_PARENT_ARM_STAGE_DRIFT')
        request['fixed_AIDC_reference']=str(reference)
        request['fixed_AIDC_record']=record(reference/'AIDC_REFERENCE.json')
    if stage=='A2':
        from v43_actual.case import accepted
        gold_request=read(read(DOC/'GOLDEN003_CERTIFIED_NUMERICAL_CASE.json')['request']['path'])
        if M1_result is None:raise ValueError('A2_REQUIRES_EXPLICIT_CURRENT_M1_RESULT')
        request.update(input_folder=gold_request['input_folder'],physical_domain_request=gold_request,
            physical_cache_case_proof=gold_request['physical_cache_case_proof'],
            output=str(output/'A2_OUTPUT'),M1_result=record(M1_result))
        from v43_a2.adapter import require_m1
        require_m1(read(M1_result))
    destination=RUNS/'requests'/(attempt_name+'.json')
    if destination.exists():
        prior=destination
        # A request is not an executed attempt. Preserve an unused prior
        # source freeze, and issue a new immutable revision before any worker.
        if read(prior)['source_sha']==request['source_sha']:
            raise ValueError('SAME_STAGE_SOURCE_ALREADY_FROZEN_USE_EXISTING_POINTER')
        destination=destination.with_name(attempt_name+'.source_'+request['source_sha'][:12]+'.json')
        if destination.exists():raise ValueError('STAGE_SOURCE_REVISION_ALREADY_FROZEN')
        request['supersedes_unused_source_freeze']=record(prior)
        request['superseded_request_worker_started']=False
    atomic(destination,request)
    atomic(DOC/f'V43_MAY01_{arm}_{stage}_REQUEST_POINTER.json',dict(request=record(destination),
        status='SOURCE_FROZEN_NOT_DISPATCHED',case_native0='NOT_RUN',Native_calls=0,
        concurrency='WAIT_FOR_CURRENT_ARM_OFFICIAL_TERMINATION_AND_LEDGER_RECONCILIATION'))
    return destination


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('arm');p.add_argument('stage');p.add_argument('attempt_name')
    p.add_argument('--fixed-aidc');p.add_argument('--m1-result');a=p.parse_args()
    print(freeze(a.arm,a.stage,a.attempt_name,fixed_AIDC_reference=a.fixed_aidc,M1_result=a.m1_result))
