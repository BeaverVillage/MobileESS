from copy import deepcopy
import sys
import pytest
from dayahead.paper_analysis.storage import write_json,read
from dayahead.v41 import campaign


def test_windows_duplicate_campaign_lock_is_rejected(tmp_path):
    with campaign.campaign_lock(tmp_path):
        with pytest.raises(RuntimeError,match='ALREADY_RUNNING'):
            with campaign.campaign_lock(tmp_path): pass
    with campaign.campaign_lock(tmp_path): pass


def test_graceful_stop_only_writes_request_preserves_scientific_results(tmp_path,monkeypatch):
    monkeypatch.setattr(campaign,'RUNTIME',tmp_path); monkeypatch.setattr(sys,'argv',['campaign','--stop'])
    complete=tmp_path/'2025-05-01/B0/UNIT_RECEIPT.json'; write_json(complete,{'status':'COMPLETE','hash':'fixed'})
    before=complete.read_bytes(); campaign.main()
    assert read(tmp_path/'STOP_REQUESTED.json')['mode']=='FINISH_CURRENT_PHASE'
    assert complete.read_bytes()==before


def test_valid_completed_phase_is_reopened_and_skipped_without_solver(tmp_path,monkeypatch):
    monkeypatch.setattr(campaign,'RUNTIME',tmp_path)
    frozen=dict(scientific_commit='same',science={'manifest_SHA':'source'})
    supervisor=campaign.Supervisor(frozen)
    row=supervisor.state['units']['2025-05-01/B0']
    path=tmp_path/'2025-05-01/B0/dayahead/DAYAHEAD_RECEIPT.json'
    receipt=dict(status='COMPLETE',scientific_commit='same',science=frozen['science'])
    write_json(path,receipt); checked=[]
    monkeypatch.setattr(campaign,'verify_receipt',lambda p,f:checked.append((p,f)))
    monkeypatch.setattr(campaign.subprocess,'Popen',lambda *a,**k:pytest.fail('valid completed phase recomputed'))
    supervisor.phase(row,'dayahead')
    assert len(checked)==1 and row['dayahead_receipt']['path']==str(path)


def test_different_scientific_commit_cannot_resume(tmp_path,monkeypatch):
    monkeypatch.setattr(campaign,'RUNTIME',tmp_path)
    frozen=dict(scientific_commit='new',science={'manifest_SHA':'source'})
    supervisor=campaign.Supervisor(frozen)
    write_json(tmp_path/'2025-05-01/B0/dayahead/DAYAHEAD_RECEIPT.json',dict(scientific_commit='old',science=frozen['science']))
    with pytest.raises(ValueError,match='DIFFERENT_SCIENCE'): supervisor.phase(supervisor.state['units']['2025-05-01/B0'],'dayahead')
