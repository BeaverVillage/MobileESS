"""Causal native Actual regulation with measured start/end state continuity."""
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from dayahead.paper_analysis.storage import read,write_json
from .authority import OUT

@contextmanager
def native_actual(output):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v28r2.opendss_mapping import REGULATORS,CAPACITORS
    from dayahead.run_v16_3_voltage_candidate import _enable_native_controls
    authority=read(OUT/'V41R3_ACTUAL_NATIVE_CONTROL_AUTHORITY.json')
    assert authority['status']=='FROZEN'
    old_apply,old_voltage=backend.apply_frozen_native_state,backend._voltage_vector
    starts=[];ends=[];capstates=[]
    def taps(odd):
        vals=[]
        for name in REGULATORS:
            odd.Transformers.Name(name);odd.Transformers.Wdg(2);vals.append(float(odd.Transformers.Tap()))
        return vals
    def apply(odd,voltage,slot):
        assert slot==len(starts) and odd.CapControls.Count()==0
        if slot==0:old_apply(odd,voltage,0)
        state=taps(odd)
        expected=voltage['regulator_taps'][0].tolist() if slot==0 else ends[-1]
        assert state==expected,'ACTUAL_REGULATOR_INITIALIZATION_OR_CONTINUITY'
        starts.append(state)
        caps=[]
        for name in CAPACITORS:
            odd.Capacitors.Name(name);caps.extend(map(int,odd.Capacitors.States()))
        assert caps==voltage['capacitor_states'][slot].tolist(),'FIXED_CAPACITOR_DRIFT'
        capstates.append(caps)
        _enable_native_controls(odd)
    def voltage(odd,nodes):
        result=old_voltage(odd,nodes);active=odd.CktElement.Name()
        ends.append(taps(odd));odd.Circuit.SetActiveElement(active)
        return result
    backend.apply_frozen_native_state=apply;backend._voltage_vector=voltage
    try:
        yield
        assert len(starts)==len(ends)==96 and len(starts[0])==7
        write_json(Path(output)/'NATIVE_ACTUAL_STATE_CONTINUITY.json',dict(status='PASS',D00='EXACT_DA_SLOT0',later_slots='PREVIOUS_ACTUAL_FINAL',independent_resets_after_D00=0,slots=96,regulators=list(REGULATORS),start_taps=starts,final_taps=ends,fixed_capacitor_states=capstates,lookahead=False,operator_redispatch=False,optimization_calls=0))
    finally:backend.apply_frozen_native_state=old_apply;backend._voltage_vector=old_voltage
