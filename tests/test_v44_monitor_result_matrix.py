"""The existing monitor's compact date-by-arm result matrix and live states."""
from pathlib import Path
from unittest.mock import patch
import importlib.util
import hashlib
import json
import sys
import pytest

REPO=Path(__file__).resolve().parents[1]
UI=REPO/'v44_monitor_live_ui'
with patch.object(sys,'path',[str(UI),*sys.path]):
    spec=importlib.util.spec_from_file_location('v44_release_monitor',UI/'monitor_binding.py')
    monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf8')

def current_days():return [f'2025-05-{i:02d}' for i in range(8,15)]

def test_corrective_peak_excludes_prefix_and_keeps_all_96_slots(tmp_path):
    p=tmp_path/'fresh.json'
    write(p,dict(prefix_slots=24,evaluation_slots=96,PASS=True,physical_steps=[
        dict(slot=i,maximum_phase_line_loading=9 if i<24 else i/200,PASS=True) for i in range(120)]))
    raw=p.read_bytes();s=p.stat()
    result=monitor.corrective_fresh_loading(str(p),hashlib.sha256(raw).hexdigest(),len(raw),s.st_mtime_ns)
    assert result==dict(peak_line_phase_loading=.595,Fresh_actual_slots=96,Fresh96_physical_PASS=True)

def test_changed_corrective_fresh_bytes_are_not_displayed(tmp_path):
    p=tmp_path/'fresh.json';p.write_text('{}')
    with pytest.raises(ValueError,match='SHA_MISMATCH'):
        monitor.corrective_fresh_loading(str(p),'0'*64,p.stat().st_size,p.stat().st_mtime_ns)

def test_unverified_or_wrong_slot_axis_cannot_be_promoted(tmp_path):
    p=tmp_path/'fresh.json';write(p,dict(prefix_slots=24,evaluation_slots=96,PASS=True,physical_steps=[]))
    raw=p.read_bytes()
    with pytest.raises(ValueError,match='EXACT_AXIS_REQUIRED'):
        monitor.corrective_fresh_loading(str(p),hashlib.sha256(raw).hexdigest(),len(raw),p.stat().st_mtime_ns)

def add_history(root):
    source=REPO/'docs/v44/r043_release_20261019/week2/COMPLETED_WEEK_LOADING_TABLE.json'
    path=root/'OPERATIONS/COMPLETED_WEEK_LOADING_TABLE.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(source.read_bytes())
    write(path.with_name('COMPLETED_WEEK_LOADING_TABLE_RECEIPT.json'),monitor.record(path))
    return path

def test_reference_matrix_has_seven_completed_and_seven_current_dates(tmp_path):
    add_history(tmp_path)
    with patch.object(monitor,'campaign_days',return_value=current_days()):data=monitor.case_loading_table(tmp_path,[])
    assert len(data['rows'])==14 and data['historical_rows']==7 and data['current_rows']==7
    assert data['rows'][0]['cells'][0]['percent']==pytest.approx(72.37383548632289,abs=.001)
    assert round(data['rows'][6]['cells'][3]['percent'],3)==59.817
    assert all(c['physical_pass'] for r in data['rows'][:7] for c in r['cells'])
    assert all(c['percent'] is None for r in data['rows'][7:] for c in r['cells'])
    assert data['rows'][7]['current_start'] is True

def test_history_cache_digest_failure_keeps_only_current_unmeasured_cells(tmp_path):
    cache=add_history(tmp_path);cache.write_text('{}')
    with patch.object(monitor,'campaign_days',return_value=current_days()):data=monitor.case_loading_table(tmp_path,[])
    assert len(data['rows'])==7 and data['history_warning']
    assert all(c['percent'] is None for r in data['rows'] for c in r['cells'])

def test_current_fail_ready_and_followup_stay_distinct(tmp_path):
    jobs=[dict(day='2025-05-08',arm=a,status=s) for a,s in zip(('B0','B1','B2','B3'),('EXCLUDED','PREPARED','BASELINE_QUEUED','PENDING'))]
    jobs[0]['exclusion_reason']='ORIGINAL_R0_ROSTER_REQUIRED'
    with patch.object(monitor,'campaign_days',return_value=current_days()),patch.object(monitor,'campaign_batch',return_value=dict(jobs=jobs)):
        cells=monitor.case_loading_table(tmp_path,[])['rows'][0]['cells']
    assert [c['state'] for c in cells]==['실패 제외','Actual 대기','후속 대기','Planning 대기']
    assert all(c['percent'] is None for c in cells)

def test_main_table_is_before_active_worker_and_verbose_details_are_folded():
    with patch.object(monitor,'ROOT',REPO):html=monitor.existing_index().decode('utf8')
    assert html.index('id="case-loading-card"')<html.index('id="day"')
    assert '<details id="actual-ticks-card"' in html
    assert '<details id="actual-ticks-card" class="card" hidden open' not in html
    assert '<th scope="col">B0</th>' in html and '<th scope="col">B3</th>' in html
