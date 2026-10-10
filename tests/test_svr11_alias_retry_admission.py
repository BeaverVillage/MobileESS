"""A diagnosed plumbing FAIL stays FAIL until a fresh independently run attempt."""
from pathlib import Path
import sys,copy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import reuse_svr11_completed as reuse
from v42_pr134_b1.common import atomic,read,record

@pytest.mark.parametrize('next_assigned',[False,True])
def test_failure_runtime_and_next_date_order_preserved(tmp_path,monkeypatch,next_assigned):
    root=tmp_path/'successor';origin=tmp_path/'origin';root.mkdir();origin.mkdir()
    day='2025-05-03';next_day='2025-05-04';key='B2/'+day
    request=origin/'request.json';result=origin/'RESULT.json';next_request=origin/'next_request.json'
    atomic(request,{'result':str(result)});atomic(next_request,{'day':next_day})
    atomic(result,dict(PASS=False,status='FAIL',arm='B2',day=day,source_SHA='original',Native_Runtime=131.25,
        reason="ValueError('CAPCONTROL_SVR_FORECAST_SOURCE_OR_DECISION_MUTATED')"))
    oldrow=dict(arm='B2',day=day,status='FAIL',request=str(request),result=str(result),attempts=[str(request)])
    atomic(origin/'CAMPAIGN_LEDGER.json',dict(dates={key:oldrow,'B2/'+next_day:dict(
        attempts=[str(next_request)] if next_assigned else [],request=str(next_request))}))
    atomic(root/'CAMPAIGN_LEDGER.json',dict(dates={key:dict(arm='B2',day=day,status='NOT_EXECUTED',attempts=[])}))
    oldmanifest=origin/'CAMPAIGN_MANIFEST.json';atomic(oldmanifest,dict(root=str(origin)))
    predecessor=root/'PREDECESSOR_DRAIN_CONTRACT.json';atomic(predecessor,dict(manifest=record(oldmanifest)))
    diagnosis=root/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json';atomic(diagnosis,dict(PASS=True))
    contract=root/'MODEL_CHECKPOINT_REUSE_CONTRACT.json';atomic(contract,dict(forecast_junction_diagnosis=record(diagnosis)))
    forecast=read(Path(r'D:\v42_svr11_may_20261011_06\raw\2025-05-03\SOURCE_PROVENANCE.json'))['daily_sources']['aemo_forecast.json']
    atomic(origin/'raw'/day/'SOURCE_PROVENANCE.json',dict(daily_sources={'aemo_forecast.json':forecast}))
    monkeypatch.setattr(reuse,'verify',lambda p:dict(execution_SHA='current',predecessor_drain_contract=record(predecessor),
        model_checkpoint_reuse_contract=record(contract)))
    before=result.read_bytes();reuse.admit_before_first_dispatch(root)
    row=read(root/'CAMPAIGN_LEDGER.json')['dates'][key]
    assert row['status']=='FAIL' and row['retry_pending'] and row['attempts']==[]
    assert row['Native_Runtime']==row['previous_epoch_Native_Runtime']==131.25
    assert row['retry_eligible_after']==(None if next_assigned else next_day)
    assert row['execution_source_SHA']=='original' and row['validation_source_SHA']=='current'
    assert result.read_bytes()==before and read(root/'TECHNICAL_FAIL_RETRY_ADMISSION.json')['failures_promoted_to_PASS']==0
