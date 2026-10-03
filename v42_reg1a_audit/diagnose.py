"""Read compiled nodes and terminal powers; reproduce PR129 without interventions.

One fresh source context per day, all 96 chronological slots. Selection of an
active element or winding is a read cursor, not a physical equipment edit.
No counterfactual solve, rating edit, PCC remapping or tap/PQ repair is performed.
"""
import inspect
import math
from collections import defaultdict
import numpy as np
import pandas as pd
from .common import *
from v42_regcontrol.authority import source, compile_verified, common_contract
from v42_regcontrol.session import AutonomousSession
from v42_regcontrol.runner import background


def active(odd, name):
    if odd.Circuit.SetActiveElement(name) < 0 or odd.CktElement.Name().lower() != name.lower():
        raise ValueError('EXACT_COMPILED_ELEMENT_REQUIRED:' + name)


def snapshot(odd, name):
    active(odd, name)
    e = odd.CktElement
    return dict(name=e.Name(), enabled=bool(e.Enabled()), phases=int(e.NumPhases()),
        conductors=int(e.NumConductors()), terminals=int(e.NumTerminals()),
        buses=list(e.BusNames()), nodes=list(map(int,e.NodeOrder())),
        powers=list(map(float,e.Powers())), currents=list(map(float,e.CurrentsMagAng())),
        voltages=list(map(float,e.VoltagesMagAng())))


def terminal_phase(s, terminal):
    """Read complex P/Q and I by actual terminal NodeOrder, never total/3."""
    n=s['conductors']; result={p:dict(P=0.,Q=0.,I=0.,V=0.,I_angle=0.,V_angle=0.) for p in 'ABC'}
    for local in range(n):
        i=terminal*n+local; node=s['nodes'][i]
        if node in (1,2,3):
            result['ABC'[node-1]]=dict(P=s['powers'][2*i], Q=s['powers'][2*i+1],
                I=s['currents'][2*i], I_angle=s['currents'][2*i+1],
                V=s['voltages'][2*i], V_angle=s['voltages'][2*i+1])
    return result


def descendants(branches, phase):
    children=defaultdict(list)
    for b in branches:
        if b.phase==phase: children[b.parent_bus].append(b.child_bus)
    seen={'150r'}; todo=['150r']
    while todo:
        for child in children[todo.pop()]:
            if child not in seen: seen.add(child); todo.append(child)
    return seen


def source_lines(path, token):
    lines=path.read_text(encoding='utf-8-sig').splitlines()
    return [dict(line=i+1,text=line) for i,line in enumerate(lines) if token.lower() in line.lower()]


def compile_audit():
    odd,adapter,inventory=compile_verified(); m=source(); rows=[]
    try:
        for i in range(1,13):
            name=f'Load.IDC_IDC{i:02d}'; s=snapshot(odd,name)
            odd.Loads.Name(name.split('.')[1]); kv=float(odd.Loads.kV())
            conn=odd.Properties.Value('Conn'); model=odd.Properties.Value('Model')
            tx=snapshot(odd,f'Transformer.IDC_IDC{i:02d}_TX')
            rows.append(dict(PCC=name,Phases=s['phases'],NumConductors=s['conductors'],
                BusNames=s['buses'],NodeOrder=s['nodes'],connection=conn,kV=kv,Model=model,
                ABC_normal=s['phases']==3 and s['nodes'][:3]==[1,2,3] and conn=='wye',
                source_path=str(m['assets'].pcc),source_sha256=sha(m['assets'].pcc),
                model_source_line=source_lines(m['assets'].pcc,'New '+name),
                upstream_transformer=tx['name'],upstream_Phases=tx['phases'],
                upstream_BusNames=tx['buses'],upstream_NodeOrder=tx['nodes']))
        emit_csv('AIDC_PCC_COMPILED_PHASE_AUDIT.csv',rows)
        write(OUT,'COMPILED_AUDIT_RECEIPT.json',dict(PCC_count=12,ABC_normal=sum(r['ABC_normal'] for r in rows),
            source_inventory=inventory,source_contract=common_contract('B0'),
            every_upstream_PCC_transformer_ABC=all(r['upstream_Phases']==3 and
                r['upstream_NodeOrder']==[1,2,3,0,1,2,3,0] for r in rows)))
    finally: odd.Basic.ClearAll()


def diagnose_day(day, *, network_check=False):
    m=source(); old=MAY/'BUNDLE'/day_folder(day); inp=MAY/'INPUT/BUNDLE'/day_folder(day)
    with np.load(old/'ACTUAL_PHYSICAL.npz') as z:p=z['PCC_P_kw'].copy();q=z['PCC_Q_kvar'].copy()
    with np.load(old/'V_ACTUAL_AC.npz') as z:expected={k:z[k].copy() for k in z.files}
    prov=read(inp/'SOURCE_PROVENANCE.json'); realized=pd.read_parquet(resolve(prov['daily_sources']['aemo_actual.parquet']))
    stamps=[pd.Timestamp(t).tz_convert('Etc/GMT-10').isoformat() for t in realized.ts_fixed_aest_end]
    bg=background(stamps,realized.demand_mw.tolist(),realized.rooftop_pv_mw.tolist())
    session=AutonomousSession(arm='B0'); odd=session.odd; adapter=session.adapter
    native=m['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(odd)
    branches,topology=m['oriented_branches'](odd)
    downstream={ph:descendants(branches,ph) for ph in 'ABC'}
    assert np.array_equal([f'{b.branch_id}::{b.phase}' for b in branches],expected['branch_names'])
    from dayahead.v28r2.opendss_mapping import _set_load,_set_generator
    pcc_rows=[];reg_rows=[];balance_rows=[];device_rows=[];raw=[];diffs=[];control_logs=[];network_rows=[];network_raw=[]
    selected=set(VIOLATION_SLOTS[day]+CONTROL_SLOTS[day])
    try:
        for t in range(96):
            totals,ledger,allocation=native.apply(odd,bg,t)
            for row in adapter['pv_generators']:
                key=(str(row['bus']).lower(),'ABC'[int(row['phase'])-1])
                _set_generator(odd,row['generator_name'],bg.pv_generation_kw_96[t].get(key,0),0)
            for i in range(12):_set_load(odd,f'IDC_IDC{i+1:02d}',p[t,i],q[t,i])
            for n in odd.Generators.AllNames():
                if n.lower().startswith('mess_dis_'):_set_generator(odd,n,0,0)
            for n in odd.Loads.AllNames():
                if n.lower().startswith('mess_chg_'):_set_load(odd,n,0,0)
            control=session.solve_next(t);control_logs.append(control)
            v=m['voltage_vector'](odd,tuple(map(str,expected['node_names'])))
            measured=np.array([m['branch_measurement'](odd,b) for b in branches])
            errors=dict(voltage=float(np.max(np.abs(v-expected['V_ACTUAL_AC'][t]))),
                current_A=float(np.max(np.abs(measured[:,0]-expected['current_A'][t]))),
                current_pu=float(np.max(np.abs(measured[:,1]-expected['current_pu'][t]))),
                transformer_kVA_pu=float(np.nanmax(np.abs(measured[:,2]-expected['transformer_kVA_pu'][t]))),
                taps=float(np.max(np.abs(np.array(control['actual_taps'])-expected['regulator_taps'][t]))))
            if max(errors.values())>1e-8:raise ValueError('PR129_REPRODUCTION_DRIFT:'+str(errors))
            assert np.array_equal(control['capacitor_states'],expected['capacitor_states'][t])
            diffs.append(errors)
            if t not in selected:continue
            kind='violation' if t in VIOLATION_SLOTS[day] else 'normal_control'
            elements=[]; sums={cat:{ph:[0.,0.] for ph in 'ABC'} for cat in ('native_feeder_load','PV','AIDC_PCC','fixed_capacitor','MESS_zero')}
            for cls,names in [('Load',odd.Loads.AllNames()),('Generator',odd.Generators.AllNames()),('Capacitor',odd.Capacitors.AllNames())]:
                for n in names:
                    s=snapshot(odd,f'{cls}.{n}');elements.append(s)
                    if not s['enabled']:continue
                    low=n.lower()
                    cat=('MESS_zero' if low.startswith(('mess_chg_','mess_dis_')) else
                        'AIDC_PCC' if cls=='Load' and low.startswith('idc_idc') else
                        'native_feeder_load' if cls=='Load' else 'PV' if cls=='Generator' else 'fixed_capacitor')
                    bus=s['buses'][0].split('.')[0].lower(); phases=terminal_phase(s,0)
                    for ph,r in phases.items():
                        if bus not in downstream[ph]:
                            if r['P'] or r['Q']:raise ValueError('DEVICE_OUTSIDE_REG1A_DOWNSTREAM:'+s['name'])
                            continue
                        sums[cat][ph][0]+=r['P'];sums[cat][ph][1]+=r['Q']
                        device_rows.append(dict(day=day,slot=t,kind=kind,category=cat,element=s['name'],bus=bus,
                            phase=ph,P_kW=r['P'],Q_kvar=r['Q'],I_A=r['I'],NodeOrder=s['nodes'],connection=None))
                    if cat=='AIDC_PCC':
                        row=dict(day=day,slot=t,kind=kind,PCC=s['name'],applied_total_P_kW=p[t,int(low[-2:])-1],applied_total_Q_kvar=q[t,int(low[-2:])-1])
                        for ph,r in phases.items():
                            for key,label in [('P','P'),('Q','Q'),('I','I')]:row[f'{label}_{ph}']=r[key]
                        row['P_phase_spread_kW']=max(r['P'] for r in phases.values())-min(r['P'] for r in phases.values())
                        row['Q_phase_spread_kvar']=max(r['Q'] for r in phases.values())-min(r['Q'] for r in phases.values())
                        row['I_phase_spread_A']=max(r['I'] for r in phases.values())-min(r['I'] for r in phases.values())
                        pcc_rows.append(row)
            reg=snapshot(odd,'Transformer.reg1a');up=terminal_phase(reg,0);down=terminal_phase(reg,1)
            regcontrol=next(r for r in m['inventory'](odd)['regulators'] if r['transformer']=='reg1a')
            odd.Transformers.Name('reg1a');odd.Transformers.Wdg(1);rating=float(odd.Transformers.kVA())/(math.sqrt(3)*float(odd.Transformers.kV()))
            passive={ph:[0.,0.] for ph in 'ABC'}; passive_elements=[]
            if network_check:
                for name in sorted({b.branch_id for b in branches if b.branch_id!='transformer.reg1a'}):
                    s=snapshot(odd,name);passive_elements.append(s)
                    for terminal in range(s['terminals']):
                        bus=s['buses'][terminal].split('.')[0].lower()
                        for ph,r in terminal_phase(s,terminal).items():
                            if bus in downstream[ph]:
                                passive[ph][0]+=r['P'];passive[ph][1]+=r['Q']
                network_raw.append(dict(day=day,slot=t,passive_elements=passive_elements))
            for ph in 'ABC':
                b=next(b for b in branches if b.branch_id=='transformer.reg1a' and b.phase==ph)
                ix=list(expected['branch_names']).index(f'transformer.reg1a::{ph}')
                ur=up[ph];dr=down[ph]
                odd.Circuit.SetActiveBus('150');baseup=odd.Bus.kVBase()*1000
                odd.Circuit.SetActiveBus('150r');basedown=odd.Bus.kVBase()*1000
                reg_rows.append(dict(day=day,slot=t,kind=kind,phase=ph,upstream_bus='150',downstream_bus='150r',
                    upstream_I_A=ur['I'],downstream_I_A=dr['I'],upstream_current_pu=ur['I']/rating,
                    backend_current_pu=float(expected['current_pu'][t,ix]),current_limit_A=rating,
                    upstream_V_pu=ur['V']/baseup,downstream_V_pu=dr['V']/basedown,
                    upstream_P_kW=ur['P'],upstream_Q_kvar=ur['Q'],downstream_out_P_kW=-dr['P'],downstream_out_Q_kvar=-dr['Q'],
                    tap=control['actual_taps'][list(m['REGULATORS']).index('reg1a')],
                    tap_num=regcontrol['resolved_properties']['TapNum'],RegControl_enabled=regcontrol['enabled'],
                    control_iterations=control['control_iterations'],regulator_state=regcontrol,
                    all_regulator_taps=control['actual_taps'],all_capacitor_states=control['capacitor_states']))
                netp=sum(c[ph][0] for c in sums.values());netq=sum(c[ph][1] for c in sums.values())
                row=dict(day=day,slot=t,kind=kind,phase=ph)
                for cat,values in sums.items():row[cat+'_P_kW'],row[cat+'_Q_kvar']=values[ph]
                row.update(net_device_P_kW=netp,net_device_Q_kvar=netq,reg1a_downstream_out_P_kW=-dr['P'],reg1a_downstream_out_Q_kvar=-dr['Q'],
                    network_loss_and_phase_transfer_P_kW=-dr['P']-netp,network_loss_and_phase_transfer_Q_kvar=-dr['Q']-netq)
                balance_rows.append(row)
                if network_check:
                    network_rows.append(dict(day=day,slot=t,kind=kind,phase=ph,
                        passive_terminal_net_P_kW=passive[ph][0],passive_terminal_net_Q_kvar=passive[ph][1],
                        decomposition_remainder_P_kW=row['network_loss_and_phase_transfer_P_kW'],
                        decomposition_remainder_Q_kvar=row['network_loss_and_phase_transfer_Q_kvar'],
                        P_conservation_error_kW=passive[ph][0]-row['network_loss_and_phase_transfer_P_kW'],
                        Q_conservation_error_kvar=passive[ph][1]-row['network_loss_and_phase_transfer_Q_kvar']))
            raw.append(dict(day=day,slot=t,kind=kind,reg1a=reg,elements=elements,controller=control))
        if network_check:
            write(OUT,day+'_NETWORK_TERMINAL_SNAPSHOTS.json',dict(day=day,slots=network_raw,
                second_read_only_reproduction=True,max_absolute_difference={k:max(e[k] for e in diffs) for k in diffs[0]}))
            return network_rows
        write(OUT,day+'_RAW_TERMINAL_SNAPSHOTS.json',dict(day=day,slots=raw,
            sign_convention='OpenDSS Powers: into terminal; PV/capacitor generation is negative',
            downstream_phase_buses={ph:sorted(bs) for ph,bs in downstream.items()}))
        write(OUT,day+'_REPRODUCTION.json',dict(day=day,slots=96,selected_slots=sorted(selected),
            max_absolute_difference={k:max(e[k] for e in diffs) for k in diffs[0]},
            selected_controls_have_no_reg1a_current_violation=all(r['upstream_current_pu']<=1 for r in reg_rows if r['kind']=='normal_control'),
            physical_input=record(old/'ACTUAL_PHYSICAL.npz'),original_actual=record(old/'V_ACTUAL_AC.npz'),
            source_provenance=record(inp/'SOURCE_PROVENANCE.json'),topology=topology,
            source_initial_inventory=session.initial_inventory,all_96_controller_logs=control_logs,
            PASS=True,interventions=0,PQ_repair=0,tap_replay=False,parameter_edits=0))
    finally:session.close()
    print(day,'96 slots reproduced; diagnostic slots',len(selected),flush=True)
    return pcc_rows,reg_rows,balance_rows,device_rows


def rating_audit():
    m=source();odd,adapter,inventory=compile_verified()
    try:
        active(odd,'Transformer.reg1a');props={p:odd.Properties.Value(p) for p in odd.CktElement.AllPropertyNames()}
        odd.Transformers.Name('reg1a');windings=[]
        for w in (1,2):
            odd.Transformers.Wdg(w);kv=float(odd.Transformers.kV());kva=float(odd.Transformers.kVA())
            windings.append(dict(winding=w,kV=kv,kVA=kva,nameplate_current_A=kva/(math.sqrt(3)*kv)))
        regulator=next(r for r in inventory['regulators'] if r['transformer']=='reg1a')
        backend=Path(inspect.getsourcefile(m['branch_measurement']))
        write(OUT,'REG1A_CURRENT_RATING_AUTHORITY.json',dict(
            transformer='transformer.reg1a',compiled_properties=props,windings=windings,
            nameplate_source=record(m['assets'].master),nameplate_source_lines=source_lines(m['assets'].master,'reg1a'),
            backend_source=record(backend),backend_source_function=inspect.getsource(m['branch_measurement']),
            measurement_terminal='upstream parent 150, winding 1, conductor selected by NodeOrder',
            denominator_formula='5000 kVA / (sqrt(3) * 4.16 kV)',denominator_A=windings[0]['nameplate_current_A'],
            NormalAmps_A=float(props['NormAmps']),EmergAmps_A=float(props['EmergAmps']),
            NormHkVA=float(props['NormHkVA']),EmergHkVA=float(props['EmergHkVA']),
            CTPrim_A=float(regulator['resolved_properties']['CTPrim']),CTPrim_is_thermal_rating=False,
            CTPrim_used_by_backend=False,NormalAmps_used_for_transformer_backend=False,
            line_rating_source=record(m['assets'].ratings),line_rating_reg1a_matches=source_lines(m['assets'].ratings,'reg1a'),
            line_rating_file_only_edits_lines=all(line.lower().startswith('edit line.') for line in
                m['assets'].ratings.read_text().splitlines() if line.strip() and not line.lstrip().startswith('!')),
            interpretation='Frozen backend checks 100% transformer winding nameplate, not OpenDSS 110% normal or 150% emergency ampacity. This difference is audited, not relaxed.',
            current_conductor_mapping='exact NodeOrder 1/2/3 at terminal 150; no neutral inclusion',
            regulator=regulator))
    finally:odd.Basic.ClearAll()


def main():
    if (OUT/'PREREGISTRATION.json').exists():raise ValueError('SEALED_DIAGNOSTIC_EXISTS')
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT,'PREREGISTRATION.json',dict(exact_base=BASE,diagnostic_days=DAYS,
        violation_slots=VIOLATION_SLOTS,normal_control_slots=CONTROL_SLOTS,
        chronological_solves_per_day=96,diagnostic_only=True,
        order=['compiled_PCC','terminal_phase_PQI','reg1a_currents','downstream_decomposition','rating_authority'],
        source_contract=common_contract('B0'),new_scientific_B1_B2_B3_M1_A2_M2_runs=0,
        grid_edits=0,physical_interventions=0,tuning=0,margin_changes=0))
    compile_audit()
    combined=[[],[],[],[]]
    for day in DAYS:
        for output,rows in zip(combined,diagnose_day(day)):output.extend(rows)
    for name,rows in zip(('AIDC_PCC_PER_PHASE_PQ.csv','REG1A_PHASE_CURRENT_AUDIT.csv',
                          'REG1A_DOWNSTREAM_PHASE_BALANCE.csv','DOWNSTREAM_DEVICE_PHASE_LEDGER.csv'),combined):emit_csv(name,rows)
    rating_audit()

if __name__=='__main__':main()
