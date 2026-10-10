"""Saved paired full-native-auto intervention readback; no DSS or optimizer."""
import csv,json,shutil,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'D:/v42voltage')
from v42_pr134_b1.common import read,record
from v42_b3_joint.contracts import digest
from v42_voltage_control import authority
base=Path('D:/v42_voltage_control_development_20261011')
output=base/'SVR7_ENGINE_COMPARATIVE_READBACK_AUDIT_01';output.mkdir(exist_ok=False)
source=authority.source_files();source_sha=digest(source)
evidence=[];summaries=[];deltas=[];hardware=[];branches=[]
for arm,day in (('B2','2025-05-01'),('B1','2025-05-28')):
    fourbase=base/'AC_ONLY_SVR4_SVR7_CANARY_02/SVR4/days'/arm/day
    four=read(fourbase/'AC_ONLY_DAY_RESULT.json');assert four['PASS'] and four['source_SHA']==source_sha
    with np.load(authority.checked(four['raw_AC']),allow_pickle=False) as z:old={k:z[k].copy() for k in z.files}
    evidence.extend([record(fourbase/'AC_ONLY_DAY_RESULT.json'),four['raw_AC']])
    summaries.append(dict(arm=arm,day=day,configuration='SVR4',Vmin=four['metric']['Vmin'],Vmax=four['metric']['Vmax'],line_loading_max_percent=four['metric']['max_line_loading_percent'],all_original_and_added_voltage_cells=0,all_current_and_kva_violation_cells=0,loss_energy_slot_end_estimate_kwh=four['metric']['loss_energy_slot_end_estimate_kWh'],Original7_slot_end_change_count=four['metric']['Original7_slot_end_tap_change_count'],original7_tap_cells_different_from_SVR4=0,largest_original_node_voltage_delta_from_SVR4=0.0,native_physical_solves=four['metric']['native_physical_solve_count']))
    for alternative in ('BUS48','BUS50'):
        folder=base/'SVR7_CANDIDATE_COMPARISON_01'/alternative/arm/day
        rp=folder/'CANDIDATE_DEVELOPMENT_RESULT.json';result=read(rp)
        assert result['PASS'] and result['strict_saved_physical_gate_PASS'] and result['source_SHA']==source_sha
        with np.load(authority.checked(result['raw_AC_receipt']),allow_pickle=False) as z:new={k:z[k].copy() for k in z.files}
        for key in ('node_names','branch_names','branch_phases','branch_kinds'):assert np.array_equal(old[key],new[key])
        audit=read(authority.checked(result['physical_audit']));slots=read(authority.checked(audit['slots_receipt']))
        assert len(slots)==96 and [r['slot'] for r in slots]==list(range(96))
        assert audit['Original_Source_SHA_before_after_equal'] and audit['retired_objects_count']==0
        fullvolts=np.asarray([[r['voltage_pu'] for r in row['physical']['nodes']] for row in slots])
        assert fullvolts.shape==(96,407) and np.isfinite(fullvolts).all()
        vcount=int(((fullvolts<.95)|(fullvolts>1.05)).sum())
        assert vcount==0 and all(row['physical']['all_original_and_added_axes_checked'] for row in slots)
        maxI=max(t['current_loading_pu'] for row in slots for d in row['svr']['devices'] for ph in d['phases'] for t in ph['terminals'])
        maxS=max(t['apparent_loading_pu'] for row in slots for d in row['svr']['devices'] for ph in d['phases'] for t in ph['terminals'])
        assert maxI<=1 and maxS<=1
        voltage_delta=new['voltage_pu']-old['voltage_pu']
        summaries.append(dict(arm=arm,day=day,configuration='SVR7_'+alternative,Vmin=float(fullvolts.min()),Vmax=float(fullvolts.max()),line_loading_max_percent=result['metrics']['actual_maximum_line_loading_percent'],all_original_and_added_voltage_cells=vcount,all_current_and_kva_violation_cells=sum(result['metrics'][k] for k in ('line_current_violation_cells','original_service_and_grid_transformer_current_violation_cells','original_service_and_grid_transformer_kva_violation_cells')),loss_energy_slot_end_estimate_kwh=float(new['losses_kw_kvar'][:,0].sum()*.25),Original7_slot_end_change_count=result['metrics']['regulator_tap_change_count'],original7_tap_cells_different_from_SVR4=int((np.abs(new['regulator_taps']-old['regulator_taps'])>1e-10).sum()),largest_original_node_voltage_delta_from_SVR4=float(np.abs(voltage_delta).max()),native_physical_solves=audit['total_physical_SolveSnap_count']))
        for k,node in enumerate(new['node_names']):
            ds=voltage_delta[:,k];j=int(np.argmax(np.abs(ds)))
            deltas.append(dict(arm=arm,day=day,alternative=alternative,node_phase=str(node),SVR4_Vmin=float(old['voltage_pu'][:,k].min()),SVR4_Vmax=float(old['voltage_pu'][:,k].max()),SVR7_Vmin=float(new['voltage_pu'][:,k].min()),SVR7_Vmax=float(new['voltage_pu'][:,k].max()),max_abs_intervention_delta_pu=float(abs(ds[j])),signed_delta_at_largest_effect_pu=float(ds[j]),effect_slot_1based=j+1,interpretation='whole-native-auto-trajectory hardware intervention; not local tap derivative'))
        for unit in slots[0]['svr']['devices']:
            for phase in (1,2,3):
                rows=[next(ph for d in row['svr']['devices'] if d['id']==unit['id'] for ph in d['phases'] if ph['phase']==phase) for row in slots]
                values=[t for r in rows for t in r['terminals']]
                hardware.append(dict(arm=arm,day=day,alternative=alternative,unit_id=unit['id'],phase=phase,nameplate_kva=values[0]['nameplate_kva'],normal_current_a=values[0]['normal_current_a'],max_current_a=max(t['current_a'] for t in values),max_apparent_kva=max(t['apparent_kva'] for t in values),max_current_loading_pu=max(t['current_loading_pu'] for t in values),max_apparent_loading_pu=max(t['apparent_loading_pu'] for t in values),tap_min=min(r['tap'] for r in rows),tap_max=max(r['tap'] for r in rows),slot_end_tap_change_count=sum(abs(rows[i]['tap']-rows[i-1]['tap'])>1e-10 for i in range(1,96)),loss_energy_slot_end_estimate_kwh=sum(r['losses_kw'] for r in rows)*.25,strict_voltage_current_kva_PASS=all(r['tap_range_PASS'] and all(t['thermal_PASS'] for t in r['terminals']) for r in rows)))
        for k,name in enumerate(new['branch_names']):
            if str(name).lower() in ('line.l47','line.l49','line.l79','line.l105'):
                branches.append(dict(arm=arm,day=day,alternative=alternative,line=str(name),phase=str(new['branch_phases'][k]),SVR4_max_current_a=float(old['phase_current_a'][:,k].max()),SVR7_max_current_a=float(new['phase_current_a'][:,k].max()),SVR4_max_loading_pu=float(old['phase_current_loading_pu'][:,k].max()),SVR7_max_loading_pu=float(new['phase_current_loading_pu'][:,k].max())))
        evidence.extend([record(rp),result['raw_AC_receipt'],result['physical_audit'],audit['slots_receipt']])
def csvwrite(name,rows):
    path=output/name
    with path.open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return record(path)
files=[csvwrite('SUMMARY.csv',summaries),csvwrite('ALL_ORIGINAL_NODE_PHASE_RESPONSE.csv',deltas),csvwrite('SVR_ALL_PHASE_NAMEPLATE_AND_READBACK.csv',hardware),csvwrite('ADDITIONAL_SITE_BRANCH_CURRENT.csv',branches)]
assert all(record(authority.checked(r))==dict(r,path=str(authority.checked(r))) for r in evidence)
assert authority.source_files()==source
value=dict(schema='V42_SVR7_SAVED_NATIVE_AUTO_COMPARATIVE_READBACK_AUDIT_V1',PASS=True,source_SHA=source_sha,all_four_known_date_candidate_runs_PASS=True,all_original_and_added407_phase_voltage_current_hardware_PASS=True,evidence=evidence,files=files,Native_optimizer_calls=0,OpenDSS_compile_calls=0,OpenDSS_solve_calls=0,Source_edits=0,interpretation='Matched known-date 96-slot finite hardware intervention with native original7 AUTO and unchanged TIME settings. Endogenous tap/queue histories allowed; no local Jacobian or measured partial derivative claimed.',selection_recommendation='BUS50',selection_rationale='Both alternatives safe in both known-date tests; BUS50 directly covers four distinct IDC04/IDC02 LV PCCs, BUS48 two IDC06 PCCs. BUS50 has slightly lower May28 original line peak but slightly higher May28 Vmax. No future-date or universal-dominance claim.',selection_status='RECOMMENDED_PENDING_ROOT_FREEZE',allMay_qualification=False,new_model_E2E_qualified=False,loss_energy_method='Sum final-slot loss_kW * .25h; not within-slot event integration',measurement_scope='96 chronological slot-end readback, no transient certification',script=record(__file__))
with (output/'COMPARATIVE_READBACK_AUDIT.json').open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
shutil.copyfile(__file__,output/'AUDIT_SCRIPT_USED.py')
print(json.dumps({'audit':str(output/'COMPARATIVE_READBACK_AUDIT.json'),'summary':summaries},indent=2))
