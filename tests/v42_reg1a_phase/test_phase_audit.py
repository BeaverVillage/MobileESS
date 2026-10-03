"""Verify conductor identity, measured partitions and unchanged frozen authority."""
import json
import math
import numpy as np
import pandas as pd
import pytest
from v42_reg1a_audit.common import OUT,DAYS,VIOLATION_SLOTS,CONTROL_SLOTS,read
from v42_reg1a_audit.diagnose import terminal_phase,active

@pytest.mark.parametrize('pcc',range(1,13))
def test_compiled_pcc_and_host_transformer_ABC(pcc):
    rows=pd.read_csv(OUT/'AIDC_PCC_COMPILED_PHASE_AUDIT.csv')
    r=rows.iloc[pcc-1]
    assert r.Phases==3 and r.NumConductors==4 and r.connection=='wye' and r.kV==.48
    assert json.loads(r.NodeOrder)==[1,2,3,0]
    assert r.upstream_Phases==3 and json.loads(r.upstream_NodeOrder)==[1,2,3,0,1,2,3,0]
    assert json.loads(r.model_source_line)[0]['text'].lower().startswith('new load.idc_idc')

@pytest.mark.parametrize('day',DAYS)
def test_every_frozen_slot_exactly_reproduced(day):
    r=read(OUT/(day+'_REPRODUCTION.json'))
    assert r['PASS'] and r['slots']==96
    assert not any(r['max_absolute_difference'].values())
    assert r['selected_slots']==sorted(VIOLATION_SLOTS[day]+CONTROL_SLOTS[day])
    assert r['selected_controls_have_no_reg1a_current_violation']
    assert r['interventions']==r['PQ_repair']==r['parameter_edits']==0
    assert not r['tap_replay']
    assert all(c['converged'] for c in r['all_96_controller_logs'])

@pytest.mark.parametrize('day',DAYS)
def test_actual_terminal_conductor_PQ_matches_raw_snapshot(day):
    data=pd.read_csv(OUT/'AIDC_PCC_PER_PHASE_PQ.csv')
    r=read(OUT/(day+'_RAW_TERMINAL_SNAPSHOTS.json'))
    for slot in r['slots']:
        for e in slot['elements']:
            if not e['name'].lower().startswith('load.idc_idc'):continue
            measured=terminal_phase(e,0)
            row=data[(data.day==day)&(data.slot==slot['slot'])&(data.PCC==e['name'])].iloc[0]
            for ph in 'ABC':
                for label in ('P','Q','I'):assert row[label+'_'+ph]==pytest.approx(measured[ph][label],abs=1e-10)

@pytest.mark.parametrize('day',DAYS)
def test_downstream_category_partition_matches_device_terminal_ledger(day):
    ledger=pd.read_csv(OUT/'DOWNSTREAM_DEVICE_PHASE_LEDGER.csv')
    balance=pd.read_csv(OUT/'REG1A_DOWNSTREAM_PHASE_BALANCE.csv')
    for _,r in balance[balance.day==day].iterrows():
        cell=ledger[(ledger.day==day)&(ledger.slot==r.slot)&(ledger.phase==r.phase)]
        for cat in ('native_feeder_load','PV','AIDC_PCC','fixed_capacitor','MESS_zero'):
            subset=cell[cell.category==cat]
            assert subset.P_kW.sum()==pytest.approx(r[cat+'_P_kW'],abs=1e-8)
            assert subset.Q_kvar.sum()==pytest.approx(r[cat+'_Q_kvar'],abs=1e-8)
        assert cell.P_kW.sum()+r.network_loss_and_phase_transfer_P_kW==pytest.approx(r.reg1a_downstream_out_P_kW,abs=1e-8)
        assert cell.Q_kvar.sum()+r.network_loss_and_phase_transfer_Q_kvar==pytest.approx(r.reg1a_downstream_out_Q_kvar,abs=1e-8)

def test_node_order_mapping_not_conductor_position_or_total_division():
    s=dict(conductors=4,nodes=[3,0,1,2],powers=[30,3,0,0,10,1,20,2],
        currents=[300,0,0,0,100,0,200,0],voltages=[3,0,0,0,1,0,2,0])
    x=terminal_phase(s,0)
    assert [x[p]['P'] for p in 'ABC']==[10,20,30]
    assert [x[p]['Q'] for p in 'ABC']==[1,2,3]
    assert [x[p]['I'] for p in 'ABC']==[100,200,300]

def test_exact_element_guard_rejects_stale_active_object():
    class Fake:
        class Circuit:
            @staticmethod
            def SetActiveElement(name):return 1
        class CktElement:
            @staticmethod
            def Name():return 'Transformer.reg1a'
    with pytest.raises(ValueError,match='EXACT_COMPILED_ELEMENT_REQUIRED'):active(Fake(),'Transformer.reg1b')

def test_nameplate_normal_and_CT_authorities_are_distinct():
    r=read(OUT/'REG1A_CURRENT_RATING_AUTHORITY.json')
    assert r['denominator_A']==pytest.approx(5000/(math.sqrt(3)*4.16),abs=1e-12)
    assert r['NormalAmps_A']==pytest.approx(r['denominator_A']*1.1)
    assert r['EmergAmps_A']==pytest.approx(r['denominator_A']*1.5)
    assert r['CTPrim_A']==700 and not r['CTPrim_used_by_backend'] and not r['CTPrim_is_thermal_rating']
    assert r['line_rating_reg1a_matches']==[] and r['line_rating_file_only_edits_lines']
    assert not r['NormalAmps_used_for_transformer_backend']

def test_phase_peaks_and_nameplate_violations_match_original_ledger():
    r=read(OUT/'ROOT_CAUSE_CLASSIFICATION.json');v=pd.read_csv(OUT/'FULL_MAY_REG1A_VIOLATIONS_RECHECK.csv')
    assert len(v)==12 and v.phase.unique().tolist()==['A']
    assert v.day.nunique()==4
    for day in DAYS:assert tuple(v[v.day==day].slot)==VIOLATION_SLOTS[day]
    assert r['reg1a_full_May_phase_peaks']['A']['current_A']==pytest.approx(730.9052641854221)
    assert r['H3']['full_May_NormalAmps_exceedances']==0

def test_native_source_imbalance_and_balanced_AIDC_are_distinguished():
    r=read(OUT/'ROOT_CAUSE_CLASSIFICATION.json')
    assert r['H2']['source_base_P_kW']==dict(A=1400.,B=952.5,C=1137.5)
    assert r['H2']['source_base_Q_kvar']==dict(A=762.5,B=540.,C=617.5)
    assert r['H2']['all_12_violation_slots_native_A_P_greater_than_B_and_C']
    assert r['H1']['maximum_P_phase_spread_kW']<.003
    assert r['H1']['maximum_Q_phase_spread_kvar']<.003
    assert r['H1']['status']=='NOT_SUPPORTED' and r['H2']['status']=='STRONGLY_SUPPORTED'
    assert not r['PCC_mapping_fix_needed'] and r['physical_changes']==0

def test_strict_network_check_failure_is_preserved_and_quantified():
    r=read(OUT/'NETWORK_CONSERVATION_RECEIPT.json');n=read(OUT/'NETWORK_NUMERICAL_LIMITATION.json')
    frame=pd.read_csv(OUT/'NETWORK_PHASE_CONSERVATION.csv')
    observed=frame[['P_conservation_error_kW','Q_conservation_error_kvar']].abs().max().max()
    assert not r['PASS'] and r['maximum_absolute_error_kW_kvar']==pytest.approx(observed)
    assert not n['strict_algebraic_1e_7_check_passed'] and not n['solver_tolerance_changed']
    assert n['frozen_OpenDSS_convergence_tolerance']==.0001
    # The independently calculated magnitude/angle nodal sum retains its observed discrepancy.
    assert n['nodal_power_and_terminal_remainder_discrepancy_kW_kvar']>0
