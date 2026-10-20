import copy
from pathlib import Path
from unittest.mock import patch
import pytest
from v44_week3 import preparation as op


def templates():
    from v44.config import axis
    rows=[]
    for day in op.DAYS:
        native=Path('D:/inputs')/day;bundle=Path('D:/bundle')/('DAY_'+day.replace('-',''))
        paths=dict(native=native/'NATIVE_INPUT.json',windows=native/'WINDOWS.json',planning_input=bundle/'PLANNING_INPUT_BUNDLE.json',
            actual_input=bundle/'ACTUAL_INPUT_BUNDLE.json',provenance=bundle/'SOURCE_PROVENANCE.json',power_authority=bundle/'POWER_AUTHORITY.json',
            request_descriptors=op.DOC/'input_metadata'/day/'PUBLIC_REQUEST_DESCRIPTORS.json',
            initial_running_authority=op.DOC/'initial_states'/day/'RUNNING/SYNTHETIC_INITIALIZATION_POLICY.json',
            initial_MESS_authority=op.DOC/'initial_states'/day/'MESS_DAILY_INITIAL_STATE.json')
        row=dict(day=day,axis=axis(day),native_folder=str(native),actual_bundle=str(bundle),files={k:dict(path=str(p)) for k,p in paths.items()})
        rows.extend(op.template(day,a,row) for a in op.ARMS)
    return rows


def check(rows):
    with op.bindings(),patch.object(op,'verify'):op.validate_templates(rows)


def test_all_28_dated_templates_remain_held():
    with op.bindings():rows=templates()
    check(rows)
    assert len(rows)==28 and all(r['execution_permit'] is None and r['lease'] is None for r in rows)


@pytest.mark.parametrize('change',['missing','duplicate','axis','folder','bundle','receipt','a1_dependency','execution','lease','permit','worker'])
def test_bad_dates_duplicate_cases_and_execution_permission_rejected(change):
    with op.bindings():rows=templates()
    if change=='missing':rows.pop()
    elif change=='duplicate':rows[-1]=copy.deepcopy(rows[0])
    elif change=='axis':rows[0]['axis']['issue_seconds']+=86400
    elif change=='folder':rows[0]['input_folder']='D:/inputs/2025-05-14'
    elif change=='bundle':rows[0]['actual_bundle']='D:/bundle/DAY_20250514'
    elif change=='receipt':rows[0]['input_records']['actual_input']['path']='D:/bundle/DAY_20250514/ACTUAL_INPUT_BUNDLE.json'
    elif change=='a1_dependency':rows[3]['same_date_B1_A1_required']=str(op.CAMPAIGN/'B1_A1/2025-05-14.json')
    elif change=='execution':rows[0]['execution_authorized']=True
    elif change=='lease':rows[0]['lease']={'pid':1}
    elif change=='permit':rows[0]['execution_permit']={'path':'D:/some-permit.json'}
    elif change=='worker':rows[0]['worker_started']=True
    with pytest.raises((PermissionError,ValueError)):check(rows)


def test_bindings_restore_original_dates_and_document_roots():
    from v44 import config,daily,inputs
    previous=(config.DAYS,daily.DOC,inputs.DOC)
    with op.bindings():assert config.DAYS==op.DAYS and daily.DOC==op.DOC
    assert (config.DAYS,daily.DOC,inputs.DOC)==previous


def test_actual_planning_and_native_methods_are_denied():
    import gurobipy as gp
    from v44 import worker,campaign
    old=gp.Model.optimize
    with op.no_execution():
        for method in (gp.Model.optimize,gp.Model.presolve,worker.actual,worker.a_stage,worker.m_stage,campaign.run_case,campaign.coordinator):
            with pytest.raises(PermissionError):method()
    assert gp.Model.optimize is old


def test_cli_has_no_run_or_worker_entry():
    for arg in ('--run','--worker'):
        with patch('sys.argv',['week3',arg]),pytest.raises(SystemExit) as error:op.main()
        assert error.value.code==2
