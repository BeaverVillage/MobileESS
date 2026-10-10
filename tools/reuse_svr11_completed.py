"""Admit a completed B0 day without executing AC or changing original evidence."""
from pathlib import Path
import sys, copy
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now,sha,digest
from v42_svr11.authority import verify
from verify_svr11_handoff37 import audit_date,require

# These reviewed changes affect lifetime/dispatch or remove the erroneous
# additional original nominal-current guard. B0 has no model/Native solver.
B0_REVIEWED_CHANGES={'v42_svr11/migration.py','v42_svr11/processes.py',
 'v42_voltage_control/integration.py','v42_svr11/model.py','v42_svr11/prepare.py',
 'v42_svr11/authority.py','v42_svr11/context_lifecycle.py'}

def qualify(root,origin,day):
    root=Path(root).resolve();origin=Path(origin).resolve()
    m=verify(root/'CAMPAIGN_MANIFEST.json');old=read(origin/'CAMPAIGN_MANIFEST.json')
    require(old['execution_SHA']==digest(old['execution_sources']),'REUSE_ORIGIN_SOURCE_DIGEST')
    for name,value in old['execution_sources'].items():
        require(sha(Path(old['code_root'])/name)==value,'REUSE_ORIGIN_SOURCE_DRIFT:'+name)
    receipts=[record(origin/'CAMPAIGN_MANIFEST.json')]
    for key in ('hardware','scenario','thermal'):
        require(record(old[key]['path'])==old[key],'REUSE_ORIGIN_FREEZE_DRIFT')
        receipts.extend([old[key],m[key]])
    h=read(m['hardware']['path']);oh=read(old['hardware']['path'])
    require(h['equipment_SHA']==oh['equipment_SHA'] and h['SVR_count']==oh['SVR_count']==11,
        'REUSE_EQUIPMENT_DIFFERENT')
    require(m['scenario']['sha256']==old['scenario']['sha256'] and
        m['thermal']['sha256']==old['thermal']['sha256'],'REUSE_PHYSICAL_CONTRACT_DIFFERENT')
    changes={k for k in set(old['execution_sources'])|set(m['execution_sources'])
        if old['execution_sources'].get(k)!=m['execution_sources'].get(k)}
    require(changes<=B0_REVIEWED_CHANGES,'REUSE_UNREVIEWED_SCIENTIFIC_CHANGE')
    # B0 excludes B1/B2 operations and optimization templates. Every actual
    # B0 load/PV/power, forecast, domain and traffic input must be byte equal.
    exclude={'OPERATIONS_TEMPLATE_B1.json','OPERATIONS_TEMPLATE_B2.json',
        'NATIVE_INPUT_TEMPLATE_B1.json','NATIVE_INPUT_TEMPLATE_B2.json'}
    axes=[]
    for manifest in (old,m):
        axis={}
        for r in manifest['input_receipts'][day]:
            if Path(r['path']).name in exclude:continue
            require(record(r['path'])==r,'REUSE_RAW_INPUT_DRIFT')
            axis[Path(r['path']).name]=(r['sha256'],r['bytes']);receipts.append(r)
        axes.append(axis)
    require(axes[0]==axes[1] and {'ACTUAL_INPUT_BUNDLE.json','PLANNING_INPUT_BUNDLE.json',
        'POWER_AUTHORITY.json','WINDOWS.json'}<=set(axes[0]),'REUSE_INPUT_DIFFERENT')
    row=read(origin/'CAMPAIGN_LEDGER.json')['dates']['B0/'+day]
    require(row['status']=='PASS','REUSE_ORIGINAL_PASS_REQUIRED')
    validation=audit_date(origin,old,row)
    require(validation['PASS'] is True,'REUSE_FULL_96_SLOT_REQUIRED')
    # Old PASS passed the stricter erroneous guard too; every literal native
    # NormalAmps/kVA/SVR/voltage check is retained in this independent audit.
    receipts.extend(validation['evidence'])
    proof=dict(schema='SVR11_COMPLETED_B0_REUSE_V1',PASS=True,arm='B0',day=day,
        origin_root=str(origin),execution_source_SHA=old['execution_SHA'],
        validation_source_SHA=m['execution_SHA'],equipment_SHA=h['equipment_SHA'],
        original_result=row['result'],original_result_SHA=row['result_SHA'],
        changed_sources_reviewed=sorted(changes),validation=validation,evidence=receipts,
        validator=record(Path(__file__)),Native_calls=0,AC_calls=0,
        original_result_bytes_changed=False,original_execution_relabelled=False,UTC=now())
    path=root/'reuse'/(day+'_B0.json');atomic(path,proof)
    return path,proof,copy.deepcopy(row)

def verify_reuse(root,m,row):
    receipt=row['reuse_proof'];p=Path(receipt['path']).resolve()
    require(p.is_relative_to(Path(root).resolve()/'reuse'),'REUSE_PROOF_OWNERSHIP')
    require(record(p)==receipt,'REUSE_PROOF_SHA_DRIFT');v=read(p)
    require(v['PASS'] is True and v['arm']==row['arm']=='B0' and v['day']==row['day']
        and v['validation_source_SHA']==m['execution_SHA'] and
        v['original_result']==row['result'] and v['original_result_SHA']==row['result_SHA'],
        'REUSE_PROOF_IDENTITY')
    require(all(record(r['path'])==r for r in v['evidence']),'REUSE_PROTECTED_BYTE_DRIFT')
    result=dict(v['validation'],source_SHA=m['execution_SHA'],
        execution_source_SHA=v['execution_source_SHA'],validation_source_SHA=m['execution_SHA'],
        reused=True,evidence=v['evidence']+[receipt])
    return result

def admit(root,origin,day):
    import psutil
    from v42_svr11.processes import live,workers
    from v42_svr11.controller import record_terminal
    from v42_common_campaign.authority import singleton
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json')
    q=read(root/'REUSE_DISPATCH_QUIESCENCE.json');sup=q['supervisor']
    require(live(sup),'REUSE_QUIESCED_SUPERVISOR_IDENTITY')
    process=psutil.Process(sup['PID'])
    require(process.status()==psutil.STATUS_STOPPED,'REUSE_DISPATCH_MUST_BE_QUIESCED')
    require(not workers(root,m['execution_SHA']),'REUSE_WAIT_HEALTHY_WORKER_DRAIN')
    path,proof,oldrow=qualify(root,origin,day)
    with singleton(root/'WATCHDOG.lock'):
        ledger=read(root/'CAMPAIGN_LEDGER.json');key='B0/'+day
        require(ledger['dates'][key]['status']=='NOT_EXECUTED' and not ledger['dates'][key]['attempts'],
            'REUSE_NEVER_REPLACE_STARTED_ATTEMPT')
        before=root/'reuse'/'PRE_ADMISSION_LEDGER.json';require(not before.exists(),'REUSE_ALREADY_ADMITTED')
        atomic(before,ledger)
        # The last existing Worker completed naturally while dispatch alone
        # was paused; reconcile its real RESULT before changing the controller.
        for row in ledger['dates'].values():
            if row['status']=='RUNNING':
                result=Path(read(row['request'])['result'])
                require(result.exists(),'REUSE_DRAIN_RESULT_REQUIRED');record_terminal(row,result)
        oldrow.update(reused=True,reuse_proof=record(path),
            execution_source_SHA=proof['execution_source_SHA'],validation_source_SHA=m['execution_SHA'],
            admission='USER_VERIFIED_COMPLETED_RESULT_REUSE',retry_pending=False)
        ledger['dates'][key]=oldrow;ledger.update(active_workers=[],UTC=now())
        verify_reuse(root,m,oldrow)
        # Only replace the drained, intentionally suspended control process
        # to load the new ledger; no Worker/Solver is terminated or hot-patched.
        process.terminate();process.wait(timeout=15)
        atomic(root/'CAMPAIGN_LEDGER.json',ledger)
        from v42_svr11.watchdog import launch
        successor=launch('v42_svr11.controller',root)
        atomic(root/'REUSE_ADMISSION.json',dict(PASS=True,day=day,proof=record(path),
            previous_ledger=record(before),successor_PID=successor.pid,
            old_dispatcher_PID=sup['PID'],healthy_workers_terminated=0,Native_calls=0,AC_calls=0,UTC=now()))
    print('REUSED',day,'SUPERVISOR',successor.pid)

if __name__=='__main__':
    mode,root,origin,day=sys.argv[1:5]
    if mode=='qualify':print(qualify(root,origin,day)[1]['PASS'])
    elif mode=='admit':admit(root,origin,day)
    else:raise ValueError(mode)
