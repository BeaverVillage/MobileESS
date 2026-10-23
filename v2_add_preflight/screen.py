"""G2: actual B0 96/120 and fresh replay for every preregistered beta."""
import json
import math
import os
import time
from datetime import datetime,timezone
import numpy as np
import psutil
from .audit import DOC,BETA,read,save,table,sha,snapshot
from .physical import Physical,RUNTIME
from .gates import configure


def run_case(beta,role,fresh=False):
    tag=f'B0_beta{beta:.2f}_{role}'+('_FRESH' if fresh else '')
    folder=RUNTIME/'phase2'/tag;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'RECEIPT.json'
    config_sha=sha((DOC/'PHYSICAL_CONFIGURATION_FREEZE.json').read_bytes())
    if receipt.exists():
        r=read(receipt)
        if r.get('complete') and r['configuration_sha256']==config_sha:
            print('REUSE',tag,flush=True)
            return read(folder/'ROWS.json'),read(folder/'STATES.json'),r
        raise RuntimeError('Existing case requires explicit preservation before retry: '+tag)
    e=Physical(tag);rows=[];states=[];arrays={k:[] for k in ('line_rho','node_voltage_pu','transformer_current_rho','transformer_winding_nameplate_kva_rho')}
    portrows=[]
    count=96 if role=='PLANNING' else 120
    started=time.perf_counter()
    for t in range(count):
        e.apply(role,t,beta)
        row,a,state,ports=e.measure(role,t,beta,state=e.initial_state if t==0 else None)
        row['case']=tag;rows.append(row);states.append(state)
        for key in arrays:arrays[key].append(a[key])
        portrows.extend(dict(slot=t,**p) for p in ports)
        if t and t%32==0:print(tag,'slot',t,'rho',round(row['rho_global'],6),flush=True)
    e.check_parameters()
    np.savez_compressed(folder/'AC_FULL.npz',**{k:np.stack(v) for k,v in arrays.items()})
    (folder/'ROWS.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (folder/'STATES.json').write_text(json.dumps(states,indent=2),encoding='utf-8')
    (folder/'PORTS.json').write_text(json.dumps(portrows,indent=2),encoding='utf-8')
    axes=dict(line=e.line_axes,nodes=e.node_axes,transformer_current=e.transformer_axes,
              transformer_winding=e.transformer_winding_axes)
    (folder/'AXES.json').write_text(json.dumps(axes),encoding='utf-8')
    r=dict(complete=True,case=tag,role=role,beta_BG=beta,configuration_sha256=config_sha,
           slots=count,operating_solve_count=e.solve_count,initial_controls=e.initial_state,
           elapsed_s=time.perf_counter()-started,archive_path=str(folder/'AC_FULL.npz'),
           archive_sha256=sha((folder/'AC_FULL.npz').read_bytes()),
           rows_path=str(folder/'ROWS.json'),rows_sha256=sha((folder/'ROWS.json').read_bytes()),
           states_path=str(folder/'STATES.json'),states_sha256=sha((folder/'STATES.json').read_bytes()),
           axes_path=str(folder/'AXES.json'),axes_sha256=sha((folder/'AXES.json').read_bytes()),
           physics_PASS=all(v['physics_PASS'] for v in rows),native_solver_calls=0)
    receipt.write_text(json.dumps(r,indent=2),encoding='utf-8')
    print('DONE',tag,'s',round(r['elapsed_s'],2),'PASS',r['physics_PASS'],flush=True)
    return rows,states,r


def compare_fresh(base,fresh,states,freshstates):
    a=np.load(base['archive_path']);b=np.load(fresh['archive_path'])
    differences={k:float(np.max(abs(a[k]-b[k]),initial=0)) for k in a.files}
    return dict(beta_BG=base['beta_BG'],role=base['role'],
        arrays_bit_identical=all(np.array_equal(a[k],b[k]) for k in a.files),
        control_states_identical=states==freshstates,max_abs_differences=differences,
        PASS=all(differences[k]<1e-9 for k in differences) and states==freshstates)


def top20(rows,receipt):
    a=np.load(receipt['archive_path'])['line_rho']
    axes=read(receipt['axes_path'])['line']
    offset=24 if receipt['role']=='ACTUAL' else 0
    maxima={}
    for j,r in enumerate(axes):
        if r['node']<=0:continue
        t=int(np.argmax(a[offset:,j]))+offset;rho=float(a[t,j])
        name=r['element']
        if name not in maxima or rho>maxima[name]['rho']:
            maxima[name]=dict(beta_BG=receipt['beta_BG'],role=receipt['role'],line=name,
                phase=r['physical_phase'],local_node=r['node'],terminal=r['terminal'],slot=t-offset,
                voltage_class=r['group'],rho=rho,original_NormalAmps=r['normal_amps'],
                original_enabled=r['enabled'],status='MEASURED_B0')
    return [dict(rank=k+1,**v) for k,v in enumerate(sorted(maxima.values(),key=lambda r:-r['rho'])[:20])]


def main():
    assert read(DOC/'PREFLIGHT_GATES.json')['G1']['status']=='PASS','G1 required; G3/G4 not required'
    configure()
    p=psutil.Process()
    try:
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        efficient=[i for i in p.cpu_affinity() if i>=12]
        if efficient:p.cpu_affinity(efficient[:1])
    except (AttributeError,psutil.AccessDenied):pass
    snapshot(RUNTIME,'PHASE2_BEFORE')
    save('SCREENING_EXECUTION_SCOPE.json',dict(experiment_id='V2_add',
        authority='User follow-up on PR236: evaluate each of all nine preregistered beta candidates in order',
        beta=BETA,conditional_high_beta_scope_override=True,original_preregistration_unchanged=True,
        no_B1_B2_B3_results_used=True,no_beyond_range=True,
        own_cpu_affinity=p.cpu_affinity(),own_priority=str(p.nice()),G2_dependencies=['G1']))
    g=read(DOC/'PREFLIGHT_GATES.json');g['G2']['status']='RUNNING';save('PREFLIGHT_GATES.json',g)
    summaries=[];slotrows=[];crit=[];receipts=[];freshchecks=[]
    for beta in BETA:
        results={}
        for role in ('PLANNING','ACTUAL'):
            rows,states,r=run_case(beta,role)
            frows,fstates,fr=run_case(beta,role,True)
            freshcheck=compare_fresh(r,fr,states,fstates);freshchecks.append(freshcheck)
            assert freshcheck['PASS'],'Independent Fresh mismatch; preserve failed pair'
            receipts.extend([r,fr]);slotrows.extend(rows);crit.extend(top20(rows,r))
            ev=rows[24:] if role=='ACTUAL' else rows
            peak=max(ev,key=lambda v:v['rho_global'])
            results[role]=dict(rho=max(v['rho_global'] for v in ev),MV=max(v['rho_MV'] for v in ev),
                LV=max(v['rho_LV'] for v in ev),Triplex=max(v['rho_Triplex'] for v in ev),
                Vmin=min(v['Vmin'] for v in rows),Vmax=max(v['Vmax'] for v in rows),
                transformer=max(v['transformer_nameplate_max'] for v in rows),
                line_violations=sum(v['line_violation_cells'] for v in rows),
                node_violations=sum(v['node_voltage_violation_cells'] for v in rows),
                transformer_violations=sum(v['transformer_violation_cells'] for v in rows),
                port_violations=sum(v['port_violation_cells'] for v in rows),
                balance_max=max(abs(v[k]) for v in rows for k in ('balance_P_error_kw','balance_Q_error_kvar')),
                PV_error_max=max(v['PV_total_abs_error_kw'] for v in rows),
                peak_line=peak['binding_line'],peak_phase=peak['binding_physical_phase'],peak_slot=peak['evaluation_slot'],
                PASS=r['physics_PASS'] and fr['physics_PASS'] and freshcheck['PASS'],elapsed_s=r['elapsed_s']+fr['elapsed_s'])
        a,b=results['ACTUAL'],results['PLANNING']
        summary=dict(beta_BG=beta,status='MEASURED_PASS' if a['PASS'] and b['PASS'] else 'MEASURED_PHYSICS_FAIL',
            planning_rho=b['rho'],actual_rho=a['rho'],planning_MV=b['MV'],planning_LV=b['LV'],
            actual_MV=a['MV'],actual_LV=a['LV'],actual_Triplex=a['Triplex'],H_daily_actual=a['MV']-a['LV'],
            planning_Vmin=b['Vmin'],planning_Vmax=b['Vmax'],actual_Vmin=a['Vmin'],actual_Vmax=a['Vmax'],
            transformer_rho_max=max(a['transformer'],b['transformer']),
            line_violation_cells=a['line_violations']+b['line_violations'],
            node_violation_cells=a['node_violations']+b['node_violations'],
            transformer_violation_cells=a['transformer_violations']+b['transformer_violations'],
            port_violation_cells=a['port_violations']+b['port_violations'],
            balance_abs_max=max(a['balance_max'],b['balance_max']),PV_abs_max=max(a['PV_error_max'],b['PV_error_max']),
            actual_peak_line=a['peak_line'],actual_peak_phase=a['peak_phase'],actual_peak_slot=a['peak_slot'],
            target_75_85=.75<=a['rho']<=.85,target_70_85=.70<=a['rho']<=.85,
            MV_LV_daily_headroom_5pp=(a['MV']-a['LV'])>=.05,elapsed_s=a['elapsed_s']+b['elapsed_s'])
        summaries.append(summary)
        table('BACKGROUND_SCALE_SCREENING.csv',list(summaries[0]),summaries)
        table('MV_LV_LOADING_COMPARISON.csv',list(slotrows[0]),slotrows)
        table('TOP20_GLOBAL_CRITICAL_LINES.csv',list(crit[0]),crit)
        save('B0_AC_ARCHIVE_RECEIPTS.json',receipts);save('B0_FRESH_REPLAY_CHECKS.json',freshchecks)
        save('B0_CASE_SUMMARIES.json',{**(read(DOC/'B0_CASE_SUMMARIES.json') if (DOC/'B0_CASE_SUMMARIES.json').exists() else {}),f'{beta:.2f}':results})
        print('BETA',beta,'Actual',round(a['rho']*100,5),'MV-LVpp',round((a['MV']-a['LV'])*100,5),summary['status'],flush=True)
    g=read(DOC/'PREFLIGHT_GATES.json')
    g['G2'].update(status='COMPLETE',candidate_count=len(summaries),
        physics_pass_count=sum(r['status']=='MEASURED_PASS' for r in summaries),
        target_75_85_count=sum(r['target_75_85'] for r in summaries),
        target_70_85_count=sum(r['target_70_85'] for r in summaries),
        operating_solve_count=sum(r['operating_solve_count'] for r in receipts),
        independent_Fresh_pairs=len(freshchecks),all_Fresh_PASS=all(r['PASS'] for r in freshchecks))
    if g['G3']['status']=='PENDING_B0':g['G3']['status']='READY_B0_OBTAINED'
    save('PREFLIGHT_GATES.json',g)
    snapshot(RUNTIME,'PHASE2_AFTER')
    print('G2 COMPLETE',g['G2'],flush=True)


if __name__=='__main__':main()
