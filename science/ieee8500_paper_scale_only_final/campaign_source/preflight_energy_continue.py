from bootstrap import *
import actual_energy_exception as exception
import actual_binding as binding
from dayahead.v41.data import SOURCE_REPO
R=H/'b3_energy_continue_preflight_20260914'
if __name__=='__main__':
    R.mkdir(exist_ok=False)
    cases=0
    for energy in (450.,760.,1070.):
        for p in (-300.,0.,300.):
            for connected in (False,True):
                kw=dict(connected=connected,travel_energy=5.,e_min=440.,e_max=1080.,eta_charge=.95,eta_discharge=.95,pcs_kva=400.,dt_hours=.25)
                assert exception.ORIGINAL_PROJECT(p,20.,energy,**kw)==exception.project_command(p,20.,energy,**kw)
                cases+=1
    kw=dict(connected=False,travel_energy=10.922985413328822,e_min=440.,e_max=1080.,eta_charge=.95,eta_discharge=.95)
    row=exception.project_command(0.,0.,450.9216722210126,**kw)
    assert row['energy_after_kWh']==439.9986868076838 and row['P_EXEC']==row['Q_EXEC']==0.
    try:exception.project_command(0.,0.,1.,connected=False,travel_energy=2.)
    except Exception:pass
    else:raise AssertionError('NEGATIVE_PHYSICAL_ENERGY_NOT_REJECTED')
    exception.install()
    src=H/'actual_B3/B3/FROZEN_MESS_COMMANDS.json';before=sha(src)
    replay=binding.replay_fleet(SOURCE_REPO,dict(day='2025-05-01',case='B3',final_PQ_source=str(src)))
    assert len(replay['frame'])==576 and before==sha(src)
    assert replay['audit']['physical_0_to_1080kWh_verified']
    replay['frame'].to_parquet(R/'MESS_REPLAY.parquet',index=False)
    save(R/'INDEPENDENT_AUDIT.json',replay['audit'])
    result=dict(status='PASS',unchanged_above_floor_test_cases=cases,no_energy_clipping=True,physical_negative_energy_rejected=True,vehicle_slot_rows=576,operating_440kWh_floor_feasible=replay['audit']['operating_440kWh_floor_feasible'],energy_floor_exceptions=replay['audit']['energy_floor_exceptions'],rule=exception.RULE,input=record(src),sources=[record(Path(__file__)),record(Path(exception.__file__))],new_optimization_calls=0)
    save(R/'PREFLIGHT.json',result)
    print(result)
