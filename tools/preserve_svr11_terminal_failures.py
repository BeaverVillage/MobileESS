"""Carry original FAILs across an equivalent-cache epoch, never reroll physics."""
from pathlib import Path
import sys,copy
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now

def retry_technical(result,attempts):
    return (not result.get('source_global_integrity_block') and not result.get('physical_failures')
        and len(attempts)<3 and bool(result.get('retryable_technical_error') or result.get('retryable_pre_native_technical_error')))

def admit(root,origin):
    from v42_svr11.authority import verify
    from v42_svr11.controller import record_terminal,following_date
    root=Path(root);origin=Path(origin);m=verify(root/'CAMPAIGN_MANIFEST.json')
    eq=read(root/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json')
    assert eq['PASS'] and eq['successor_source_SHA']==m['execution_SHA'] and not eq['physical_model_objective_integer_domain_constraints_budgets_changed']
    old=read(origin/'CAMPAIGN_MANIFEST.json');assert eq['generation_source_SHA']==old['execution_SHA']
    assert read(old['hardware']['path'])['equipment_SHA']==read(m['hardware']['path'])['equipment_SHA']==eq['equipment_SHA']
    source=read(origin/'CAMPAIGN_LEDGER.json');ledger=read(root/'CAMPAIGN_LEDGER.json');evidence=[]
    for key,current in list(ledger['dates'].items()):
        if current['arm']!='B2' or current['status']!='NOT_EXECUTED' or current['attempts']:continue
        original=source['dates'][key]
        path=Path(read(original['request'])['result']) if original.get('request') else None
        if path is None or not path.exists():continue
        result=read(path)
        if result.get('PASS'):continue
        assert result['source_SHA']==old['execution_SHA'] and result['status']=='FAIL'
        assert not result.get('source_global_integrity_block'),'COMMON_ORIGIN_INTEGRITY_FAILURE_REQUIRES_DIAGNOSIS'
        row=copy.deepcopy(original)
        if row['status']=='RUNNING':record_terminal(row,path)
        assert row['status']=='FAIL' and row['result_SHA']==record(path)['sha256']
        after=following_date(row['day']);nextrow=source['dates'].get('B2/'+str(after),{})
        technical=retry_technical(result,row['attempts'])
        row.update(execution_source_SHA=old['execution_SHA'],validation_source_SHA=m['execution_SHA'],
            retry_pending=technical,retry_eligible_after=None if nextrow.get('attempts') else after,
            previous_epoch_Native_Runtime=result.get('Native_Runtime'),previous_epoch_runtime_pending=False,
            original_terminal_FAILURE_preserved=True,failures_promoted_to_PASS=0,
            same_equipment_epoch_failure=record(path),performance_equivalence=record(root/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'))
        ledger['dates'][key]=row;evidence.append(dict(key=key,result=record(path),technical_retry_pending=technical,
            original_Native_Runtime=result.get('Native_Runtime'),physical_FAIL_reexecution_allowed=False))
    if evidence:
        atomic(root/'CAMPAIGN_LEDGER.json',ledger)
        atomic(root/'SAME_EQUIPMENT_TERMINAL_FAILURE_ADMISSION.json',dict(PASS=True,evidence=evidence,
            failures_promoted_to_PASS=0,physical_failures_reexecuted=0,Native_calls=0,AC_calls=0,UTC=now()))
    return evidence
