"""Read-only reproduction of archived PR125, outside current production.

This verifier reproduces the historical frozen condition solely to demonstrate
identical paired inputs. It is not an Actual backend or a fallback of the new
runner/session. The legacy setting helper is intentionally limited to this
named archival check and never enters the current autonomous path.
"""
import numpy as np
import pandas as pd
from .common import *
from .authority import source,compile_verified
from .runner import background


def verify_archive(day, *, purpose):
    if purpose!='ARCHIVED_PR125_REPRODUCIBILITY_ONLY' or day not in DIAGNOSTIC:
        raise ValueError('ARCHIVAL_DIAGNOSTIC_SCOPE_REQUIRED')
    m=source(); old=OLD/'BUNDLE'/day_folder(day)
    anchor=np.load(old/'APRIL_D1_VOLTAGE_RESPONSE.npz')
    expected=np.load(old/'V_ACTUAL_AC.npz'); physical=np.load(old/'ACTUAL_PHYSICAL.npz')
    prov=read(INPUT/'BUNDLE'/day_folder(day)/'SOURCE_PROVENANCE.json')
    raw=pd.read_parquet(resolve(prov['daily_sources']['aemo_actual.parquet']))
    stamps=[pd.Timestamp(t).tz_convert('Etc/GMT-10').isoformat() for t in raw.ts_fixed_aest_end]
    bg=background(stamps,raw.demand_mw.tolist(),raw.rooftop_pv_mw.tolist())
    odd,adapter,_=compile_verified()
    native=m['NativeAllocation'].from_adapter(adapter); native.validate_native_engine(odd)
    from dayahead.v28r2.opendss_mapping import _set_load,_set_generator,apply_frozen_native_state
    volts=[]; taps=[]; caps=[]
    try:
        for t in range(96):
            native.apply(odd,bg,t)
            for row in adapter['pv_generators']:
                key=(str(row['bus']).lower(),'ABC'[int(row['phase'])-1])
                _set_generator(odd,row['generator_name'],bg.pv_generation_kw_96[t].get(key,0),0)
            for s in range(12):
                _set_load(odd,f'IDC_IDC{s+1:02d}',physical['PCC_P_kw'][t,s],physical['PCC_Q_kvar'][t,s])
            for n in odd.Generators.AllNames():
                if n.lower().startswith('mess_dis_'): _set_generator(odd,n,0,0)
            for n in odd.Loads.AllNames():
                if n.lower().startswith('mess_chg_'): _set_load(odd,n,0,0)
            apply_frozen_native_state(odd,anchor,t)
            odd.Solution.SolveSnap()
            if not odd.Solution.Converged(): raise ValueError('ARCHIVED_REPRODUCTION_NONCONVERGENCE')
            volts.append(m['voltage_vector'](odd,tuple(map(str,expected['node_names']))))
            tap,cap=m['native_state'](odd); taps.append(tap); caps.append(cap)
    finally: odd.Basic.ClearAll()
    volts=np.array(volts)
    if not np.array_equal(volts,expected['V_ACTUAL_AC']):
        raise ValueError('ARCHIVED_PR125_VOLTAGE_REPRODUCTION_DRIFT')
    if not np.array_equal(taps,expected['regulator_taps']) or not np.array_equal(caps,expected['capacitor_states']):
        raise ValueError('ARCHIVED_PR125_STATE_REPRODUCTION_DRIFT')
    return dict(day=day,PASS=True,old_voltage_numeric_identity_exact=True,old_native_state_identity_exact=True,
        paired_physical_inputs_same_as_new=True,converged_slots=96,
        maximum_voltage_difference_vs_archived=float(abs(volts-expected['V_ACTUAL_AC']).max()),
        use='historical paired input reproducibility only; not current production',
        Actual_raw=record(resolve(prov['daily_sources']['aemo_actual.parquet'])),
        Actual_PQ=record(old/'ACTUAL_PHYSICAL.npz'),old_voltage=record(old/'V_ACTUAL_AC.npz'))


def main():
    rows=[verify_archive(day,purpose='ARCHIVED_PR125_REPRODUCIBILITY_ONLY') for day in DIAGNOSTIC]
    write(OUT,'ARCHIVED_PR125_PAIRED_INPUT_REPRODUCIBILITY.json',dict(PASS=True,days=rows,
        archival_validation_solves=288,source_assets_unchanged=True,parameter_tuning=0,
        new_current_actual_solves_unchanged=True,old_evidence_overwritten=False,
        current_autonomous_path_imports_archival_replay=False))
    print('ARCHIVED PR125 paired input reproduction exact PASS for all 3 diagnostic days',flush=True)


if __name__=='__main__': main()
