"""Original r043 measurement-time projection, from saved native TIME events.

r043 PhysicalScenario.settle_actual measures after CommonClock.settle_slot;
OriginalCurrentAC then reads branches at that settled state. The event envelope
is an additional security diagnostic, never the V44 objective. No Solve here.
"""
from pathlib import Path
import csv,json
import numpy as np
from .audit import ROOT,DOC,read,sha
from .correction import OUT,RUNTIME,put,csvout,priority

CAN=OUT/'canonical'

def write(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (CAN/name).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def project(receipt_file):
    p=Path(receipt_file).parent;rec=read(receipt_file);key=rec['scientific_inputs'];role=key['role'];off=24 if role=='ACTUAL' else 0
    with np.load(p/'AC_FULL.npz') as archive:arr={k:archive[k] for k in archive.files}
    axes=read(p/'AXES.json')['line'];parent={r['element']:r['parent_terminal'] for r in read(p/'AXES.json')['orientation']}
    ids=[j for j,r in enumerate(axes) if r['enabled'] and r['node']>0 and r['terminal']==parent[r['element']]]
    both=[j for j,r in enumerate(axes) if r['node']>0];mv=[j for j in ids if axes[j]['group']=='Primary'];lv=[j for j in ids if axes[j]['group']!='Primary']
    eventslot=arr['event_slot'];eventrows=read(p/'EVENT_ROWS.json');events=read(p/'EVENTS.json')
    assert len(eventrows)==len(eventslot)
    selected=[];slots=[]
    for t in range(120 if off else 96):
        # Literal last ordered event; does not select the largest current.
        indices=np.flatnonzero(eventslot==t);j=int(indices[-1]);selected.append(j)
        raw=eventrows[j];assert raw['slot']==t
        assert raw['physical_seconds']==events[t]['last_solve_seconds']
        rho=arr['line_rho'][j];binding=max(ids,key=lambda col:float(rho[col]));v=axes[binding]
        assert abs(float(rho[binding])-raw['rho_global'])<1e-12
        voltage=arr['node_voltage_pu'][j]
        slots.append(dict(case=rec['case'],role=role,beta_BG=key['beta'],slot=t,evaluation_slot=t-off,
            measurement_scope='V44_CANONICAL_OBJECTIVE_SETTLED_SLOT',selected_native_event_index=j,last_solve_seconds=raw['physical_seconds'],
            rho_objective=float(rho[binding]),rho_all_terminals=float(rho[both].max()),
            rho_MV_objective=float(rho[mv].max()),rho_LV_objective=float(rho[lv].max()),
            line=v['element'],phase=v['physical_phase'],terminal=v['terminal'],Vmin=float(voltage.min()),Vmax=float(voltage.max()),
            settled_physics_PASS=raw['physics_PASS'],all_terminal_thermal_PASS=float(rho[both].max())<=1+1e-8,
            all_event_security_PASS=all(eventrows[k]['physics_PASS'] for k in indices),
            event_envelope_rho=float(arr['line_rho'][indices][:,ids].max()),
            event_envelope_Vmin=float(arr['node_voltage_pu'][indices].min()),event_envelope_Vmax=float(arr['node_voltage_pu'][indices].max())))
    evaluation=slots[off:];peak=max(evaluation,key=lambda r:r['rho_objective']);schedule=key['schedule']
    evmask=eventslot>=off
    result=dict(case=rec['case'],role=role,beta_BG=key['beta'],kind='B0' if schedule is None else schedule['name'],
        fresh=rec['case'].endswith('_FRESH'),measurement_scope='V44_CANONICAL_OBJECTIVE_SETTLED_SLOT',
        rho_objective=max(r['rho_objective'] for r in evaluation),rho_all_terminals=max(r['rho_all_terminals'] for r in evaluation),
        rho_MV_objective=max(r['rho_MV_objective'] for r in evaluation),rho_LV_objective=max(r['rho_LV_objective'] for r in evaluation),
        MV_LV_headroom_pp=100*(max(r['rho_MV_objective'] for r in evaluation)-max(r['rho_LV_objective'] for r in evaluation)),
        peak_slot=peak['evaluation_slot'],line=peak['line'],phase=peak['phase'],terminal=peak['terminal'],
        Vmin=min(r['Vmin'] for r in evaluation),Vmax=max(r['Vmax'] for r in evaluation),
        physics_PASS=all(r['settled_physics_PASS'] for r in evaluation),
        prefix_settled_physics_PASS=all(r['settled_physics_PASS'] for r in slots[:off]),
        all_interval_settled_physics_PASS=all(r['settled_physics_PASS'] for r in slots),
        all_event_security_PASS=all(r['physics_PASS'] for r in eventrows),
        evaluation_all_event_security_PASS=all(r['physics_PASS'] for j,r in enumerate(eventrows) if evmask[j]),
        all_event_Vmin=float(arr['node_voltage_pu'].min()),all_event_Vmax=float(arr['node_voltage_pu'].max()),
        evaluation_all_event_Vmin=float(arr['node_voltage_pu'][evmask].min()),evaluation_all_event_Vmax=float(arr['node_voltage_pu'][evmask].max()),
        event_envelope_rho=float(arr['line_rho'][evmask][:,ids].max()),physical_solve_count=rec['physical_solve_count'],
        receipt=str(receipt_file))
    top=[];line_peak={}
    values=arr['line_rho'][selected[off:]]
    for j in ids:
        v=axes[j];rho=float(values[:,j].max())
        if rho>line_peak.get(v['element'],{}).get('rho',-1):line_peak[v['element']]=dict(line=v['element'],rho=rho,phase=v['physical_phase'],terminal=v['terminal'])
    for rank,row in enumerate(sorted(line_peak.values(),key=lambda r:(-r['rho'],r['line']))[:20]):top.append(dict(case=rec['case'],beta_BG=key['beta'],role=role,rank=rank+1,**row))
    selection=dict(case=rec['case'],archive_path=str(p/'AC_FULL.npz'),archive_sha256=rec['files']['AC_FULL.npz'],
        selected_last_event_indices=selected,source_clock_slot_count=len(slots),PASS=True)
    return result,slots,top,selection

def main():
    priority();CAN.mkdir(exist_ok=True);results=[];slots=[];top=[];selections=[];bycase={}
    for namespace in ('correction_time100','correction_old_pilot_time100','correction_charge_spread_time100'):
        for file in sorted((RUNTIME/namespace).glob('*/RECEIPT.json')):
            r,s,t,sel=project(file);r['runtime_namespace']=namespace
            results.append(r);slots.extend(s);top.extend(t);selections.append(sel);bycase[r['case']]=s
    assert len(results)==140,len(results)
    baselines={(r['beta_BG'],r['role']):r for r in results if r['kind']=='B0' and not r['fresh']}
    energy={}
    for name in ('MESS8_TEMPORAL_PILOT_COMPARISON.csv','MESS8_CHARGE_SPREAD_COMPARISON.csv'):
        with (OUT/name).open(encoding='utf-8') as f:
            energy.update({r['case']:r for r in csv.DictReader(f)})
    for r in results:
        base=baselines[r['beta_BG'],r['role']];r['baseline_rho']=base['rho_objective'];r['delta_global_pp']=100*(base['rho_objective']-r['rho_objective'])
        if r['case'] in energy:
            old=energy[r['case']]
            for key in ('charge_kwh','discharge_kwh','SOC_min','SOC_max'):r[key]=old.get(key)
            r['schedule']=r['kind'];r['base_peak_slot']=base['peak_slot']
            row=bycase[r['case']][base['peak_slot']+(24 if r['role']=='ACTUAL' else 0)]
            r['at_original_peak_reduction_pp']=100*(base['rho_objective']-row['rho_objective'])
            r['status']='V44_SETTLED_FEASIBLE_PILOT' if r['physics_PASS'] else 'V44_SETTLED_PHYSICAL_FAIL'
    write('ALL_TIME_CASES_CANONICAL_RESULTS.csv',results);write('TIME_EXPLICIT_OBJECTIVE_SLOT_CONTRACT.csv',slots)
    write('CANONICAL_TIME_TOP20.csv',top)
    for filename,predicate in [
        ('TIME_B0_ANCHOR_RESULTS.csv',lambda r:r['kind']=='B0' and r['beta_BG'] in (1.,1.5)),
        ('EXTENDED_BETA_B0_RESULTS.csv',lambda r:r['kind']=='B0' and r['beta_BG']>1.5),
        ('LEGACY_BETA_TIME_REVALIDATION.csv',lambda r:r['kind']=='B0' and r['beta_BG'] not in (1.,1.5) and r['beta_BG']<1.5),
        ('MESS8_TEMPORAL_PILOT_COMPARISON.csv',lambda r:r['runtime_namespace']=='correction_time100' and r['kind']!='B0'),
        ('MESS8_CHARGE_SPREAD_COMPARISON.csv',lambda r:r['runtime_namespace']=='correction_charge_spread_time100'),
        ('LEGACY_PILOT_TIME_REVALIDATION.csv',lambda r:r['runtime_namespace']=='correction_old_pilot_time100')]:
        write(filename,[r for r in results if not r['fresh'] and predicate(r)])
    write('EXTENDED_BETA_MV_LV_HEADROOM.csv',[r for r in slots if r['beta_BG']>1.5 and '_B0' in r['case'] and not r['case'].endswith('_FRESH')])
    comparisons=[]
    for beta in (1.,1.5):
        for role in ('PLANNING','ACTUAL'):
            p=RUNTIME/'phase2'/f'B0_beta{beta:.2f}_{role}';axes=read(p/'AXES.json')['line'];a=np.load(p/'AC_FULL.npz')['line_rho']
            parents={r['element']:r['parent_terminal'] for r in read(OUT/'INDEPENDENT_PARENT_ORIENTATION.json')}
            ids=[j for j,r in enumerate(axes) if r['enabled'] and r['node']>0 and r['terminal']==parents[r['element']]]
            both=[j for j,r in enumerate(axes) if r['node']>0]
            states=read(p/'STATES.json');newstates=read(RUNTIME/'correction_time100'/f'TIME_{beta:.2f}_{role}_B0/STATES.json')
            for t,row in enumerate(bycase[f'TIME_{beta:.2f}_{role}_B0']):
                comparisons.append(dict(beta_BG=beta,role=role,slot=t,evaluation_slot=row['evaluation_slot'],
                    static_canonical=float(a[t,ids].max()),time_canonical=row['rho_objective'],
                    canonical_difference_pp=100*(row['rho_objective']-float(a[t,ids].max())),
                    static_all_terminal=float(a[t,both].max()),time_all_terminal=row['rho_all_terminals'],
                    final_taps_differ=states[t]['taps']!=newstates[t]['taps'],final_caps_differ=states[t]['capacitors']!=newstates[t]['capacitors']))
    write('STATIC_VS_TIME_CONTROL_AUDIT.csv',comparisons)
    (CAN/'SETTLED_EVENT_SELECTION_RECEIPTS.json').write_text(json.dumps(selections,indent=2),encoding='utf-8')
    put('CURRENT_MEASUREMENT_CONTRACT.json',dict(status='V44_PARENT_TERMINAL_AND_SETTLED_TIME_PROJECTION_CERTIFIED',
        final_TIME_results_directory='canonical/',
        original_source='v44/svr11_frozen/v42_voltage_control/integration.py:PhysicalScenario.settle_actual measures after clock; v43_actual/current_ac.py:_probe and v44/svr11_ac.py:probe_body',
        objective='Parent Terminal / original NormalAmps at the final native solved state in each15min slot; evaluation96 maximum',
        all_event_envelope='Separate security diagnostic; existing root correction TIME CSVs are preserved intermediate event-envelope reductions and must not be used as the V44 objective',
        Actual_acceptance_scope='Original r043 Fresh96 uses settled physical_steps[24:]; prefix and all-event120/evaluation96 safety are separately reported',
        no_new_solve=True,preserved_all_raw_receipts=True,no_physical_retuning=True,
        code_sha256=sha(Path(__file__).read_bytes())))
    print('CANONICAL SETTLED PROJECTION COMPLETE',len(results),flush=True)

if __name__=='__main__':main()
