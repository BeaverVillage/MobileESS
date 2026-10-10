"""Unused forecast receipts may be skipped; native control physics must match."""
import numpy as np
import opendssdirect as dss
import pytest
from v42_voltage_control.timecontrol import CommonClock,queue,seconds
from v42_svr11.context_lifecycle import retire_completed_probe,flush_completed_probes

def execute(capture):
    e=dss.NewContext()
    try:
        e.Text.Command('new circuit.probe phases=3 bus1=a basekv=4.16 pu=1.04')
        e.Text.Command('new transformer.r phases=3 windings=2 buses=[a,b] conns=[wye,wye] kvs=[4.16,4.16] kvas=[1000,1000] xhl=1')
        e.Text.Command('new load.l bus1=b phases=3 kv=4.16 kw=100 kvar=30')
        e.Text.Command('set voltagebases=[4.16]')
        e.Text.Command('calcvoltagebases')
        e.Text.Command('new regcontrol.r transformer=r winding=2 vreg=120 band=2 ptratio=20 delay=30 tapdelay=2 maxtapchange=1')
        e.Solution.MaxControlIterations(100);e.Solution.MaxIterations(15)
        clock=CommonClock('DAYAHEAD','2025-05-01');clock.bind(e)
        rows=[]
        for t,pu in enumerate((1.04,.97,1.03)):
            e.Text.Command(f'edit vsource.source pu={pu}')
            r=clock.settle_slot(e,t,capture_events=capture)
            rows.append(dict(voltage=np.array(e.Circuit.AllBusVolts()),tap=e.Transformers.Tap(),
                queue=queue(e),seconds=seconds(e),solves=r['physical_solve_count']))
        return rows,clock.total_physical_solve_count
    finally:retire_completed_probe(e)

def test_identical_native_auto_taps_voltages_queues_clock_and_solves():
    full,solves=execute(True);fast,fast_solves=execute(False)
    assert fast_solves==solves
    for a,b in zip(full,fast):
        assert np.array_equal(a.pop('voltage'),b.pop('voltage'))
        assert a==b
    flush_completed_probes()

def test_cannot_suppress_an_observer_or_control_bank():
    clock=CommonClock('DAYAHEAD','2025-05-01')
    with pytest.raises(ValueError,match='CANNOT_SKIP_OBSERVER'):
        clock.settle_slot(None,0,capture_events=False,observer=lambda row:None)
