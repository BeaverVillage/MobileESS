from pathlib import Path
import threading
import pytest
from dayahead.paper_analysis.storage import read,write_json


def test_new_unit_storage_preserves_old_folder_and_existing_completed_results(tmp_path,monkeypatch):
    from dayahead.v41r1 import campaign_run as c
    runtime=tmp_path/'runtime';spill=tmp_path/'spill'
    monkeypatch.setattr(c,'RUNTIME',runtime);monkeypatch.setattr(c,'RESULT_STORAGE_ROOT',spill)
    old=runtime/'2025-05-04/B3';old.mkdir(parents=True);(old/'old.log').write_text('preserve')
    unit=c.provision_unit_storage('2025-05-04','B3')
    assert unit.resolve()==(spill/'2025-05-04/B3').resolve()
    assert next((runtime/'interrupted').glob('*/old.log')).read_text()=='preserve'
    assert c.provision_unit_storage('2025-05-04','B3').resolve()==unit.resolve()
    complete=runtime/'2025-05-04/B0';complete.mkdir();write_json(complete/'UNIT_RECEIPT.json',{'status':'COMPLETE'})
    c.provision_unit_storage('2025-05-04','B0')
    assert complete.resolve()==complete
    with pytest.raises(ValueError):c.provision_unit_storage('../../escape','B1')


def test_spilled_phase_keeps_actual_phase_status_and_command(tmp_path,monkeypatch):
    from dayahead.v41r1 import campaign_run as c
    monkeypatch.setattr(c,'RUNTIME',tmp_path);monkeypatch.setattr(c.native,'LOGS',tmp_path/'logs')
    monkeypatch.setattr(c.psutil,'process_iter',lambda *a:[])
    monkeypatch.setattr(c,'verify_release',lambda:{})
    monkeypatch.setattr(c,'verify_phase',lambda *a:{'status':'COMPLETE'})
    path=tmp_path/'2025-05-05/B2/actual/ACTUAL_RECEIPT.json';commands=[]
    class Process:
        pid=1
        def __init__(self,command,**kwargs):commands.append(command)
        def wait(self):write_json(path,{'status':'COMPLETE'});return 0
    monkeypatch.setattr(c.subprocess,'Popen',Process)
    owner=object.__new__(c.Supervisor);owner.lock=threading.RLock();owner.sha='frozen';owner.frozen={};owner.save=lambda:None
    row=dict(day='2025-05-05',policy='B2')
    owner.spilled_phase(row,'actual',path)
    assert row['status']=='ACTUAL_DONE' and commands[0][commands[0].index('--phase')+1]=='actual'
    assert row['actual_receipt']['path']==str(path.resolve())


def test_archive_stays_on_the_units_storage_volume(tmp_path,monkeypatch):
    from dayahead.v41r1 import campaign_run as c
    monkeypatch.setattr(c,'RUNTIME',tmp_path/'runtime');monkeypatch.setattr(c,'RESULT_STORAGE_ROOT',tmp_path/'spill')
    path=c.archive_location('2025-05-05','B1','dayahead',tmp_path/'spill/2025-05-05/B1/dayahead')
    assert path.is_relative_to(tmp_path/'spill/interrupted')
    with pytest.raises(ValueError):c.archive_location('2025-05-05','B1','dayahead',tmp_path/'unrelated')


def test_quality_report_keeps_missing_bounds_and_all_124_units(tmp_path):
    from dayahead.v41r1.fo_quality import aggregate
    unit=tmp_path/'2025-05-04/B1';write_json(unit/'UNIT_RECEIPT.json',{'status':'COMPLETE'})
    write_json(unit/'dayahead/A0/BOUNDED_SOLVER_REPORT.json',dict(classification='F_AND_O_NO_GLOBAL_CERTIFICATE',
        stages=[dict(achieved_relative_gap=None),dict(achieved_relative_gap=None)]))
    value=aggregate(tmp_path)
    assert len(value['days'])==124 and value['policies']['B1']['P1_global_gap']['count']==0
    assert value['policies']['B1']['P1_global_gap']['median'] is None
    assert value['policies']['B1']['P1_missing_global_certificate']==1


def test_monitor_detection_does_not_match_its_calling_shell_text(monkeypatch):
    from types import SimpleNamespace
    from dayahead.v41r1 import watchdog as w
    processes=[SimpleNamespace(pid=1,info={'cmdline':['powershell','-File','C:/repo/monitor_v41r1_may_live.ps1']}),
        SimpleNamespace(pid=2,info={'cmdline':['powershell','-Command',"Get-Content monitor_v41r1_may_live.ps1; python -c 'restart()'"]})]
    monkeypatch.setattr(w.psutil,'process_iter',lambda *args:processes)
    assert w._monitor_processes()==[1]
