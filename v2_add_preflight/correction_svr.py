"""Append-only S0 tap diagnosis and preregistered physical S1 series hardware.

Never imports a campaign, worker or optimizer. Original feeder bytes and every
original line impedance/rating are immutable. Models are research equipment.
"""
import csv,json,sys,math,re,types,heapq
from pathlib import Path
from collections import defaultdict
import numpy as np
from .audit import ROOT,DOC,read,sha
from .correction import OUT,RUNTIME,put,csvout,priority

SV=OUT/'svr';SV.mkdir(exist_ok=True)
RUN=RUNTIME/'correction_svr'
BETAS=[1.,1.5,2.,2.05,2.1]

def save(name,data):
    (SV/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def table(name,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (SV/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def graph(e):
    adj=defaultdict(list);meta={}
    for r in e.inventory['lines']+e.inventory['transformers']:
        if not r['enabled']:continue
        a=r['buses'][0].split('.')[0].lower()
        for b in r['buses'][1:]:
            b=b.split('.')[0].lower();adj[a].append((b,r['element']));adj[b].append((a,r['element']))
        meta[r['element'].lower()]=r
    for name in e.d.Reactors.AllNames():
        e.d.Reactors.Name(name)
        if not e.d.CktElement.Enabled():continue
        a,b=[x.split('.')[0].lower() for x in e.d.CktElement.BusNames()]
        adj[a].append((b,'Reactor.'+name));adj[b].append((a,'Reactor.'+name))
    parents={'sourcebus':None};q=['sourcebus']
    for a in q:
        for b,el in sorted(adj[a]):
            if b not in parents:parents[b]=(a,el);q.append(b)
    return parents,meta

def path_to(bus,parents):
    path=[]
    while parents[bus] is not None:
        a,el=parents[bus];path.append(dict(parent=a,child=bus,element=el));bus=a
    return path[::-1]

def regulator_readback(e):
    d=e.d;rows=[]
    for name in d.RegControls.AllNames():
        d.RegControls.Name(name);tx=d.RegControls.Transformer();w=int(d.RegControls.Winding());num=int(d.RegControls.TapNumber())
        props={p:d.Properties.Value(p) for p in d.CktElement.AllPropertyNames()}
        d.Transformers.Name(tx);d.Transformers.Wdg(w)
        tap=float(d.Transformers.Tap());lo=float(d.Transformers.MinTap());hi=float(d.Transformers.MaxTap());nt=int(d.Transformers.NumTaps())
        step=(hi-lo)/nt if nt else 0
        rows.append(dict(regcontrol=name,transformer=tx,winding=w,tap_winding=int(props['TapWinding']),
            tap_number=num,tap=tap,min_tap=lo,max_tap=hi,num_taps=nt,tap_step=step,
            tap_number_readback_PASS=bool(step and abs((tap-1)/step-num)<1e-7),
            at_lower=abs(tap-lo)<1e-8,at_upper=abs(tap-hi)<1e-8,
            down_steps=round((tap-lo)/step) if step else 0,up_steps=round((hi-tap)/step) if step else 0,
            properties=props))
    return rows

def diagnose():
    priority()
    from .physical import Physical
    e=Physical('SVR_READ_ONLY_DIAGNOSIS');parents,meta=graph(e)
    readback=regulator_readback(e);assert len(readback)==12
    assert all(r['winding']==r['tap_winding']==2 and r['tap_number_readback_PASS'] for r in readback)
    controlled={r['transformer'].lower() for r in readback}
    fixed=[r for r in e.inventory['transformers'] if r['element'].split('.')[1].lower()=='hvmv_sub' or r['element'].startswith('Transformer.high_mv_sta')]
    for r in fixed:r['automatic_regcontrol_present']=r['element'].split('.')[1].lower() in controlled
    save('EXISTING_REGULATOR_FULL_STATIC_AUDIT.json',dict(original_bank_count=4,original_single_phase_controls=12,
        initial_readbacks=readback,fixed_main_and_STA_transformers=fixed,P5_changes='Only original12 VReg123.5, Source1.04, CAPBank3 initiallyOFF',
        original_source=read(OUT/'CONTROL_PROPERTY_AUDIT.json'),TapNumber_per_event='New S0/S1 instrumented runs; old archives did not save this readback'))
    lows=[];worst={};saturation=[];candidate_score={}
    for beta in BETAS:
        p=RUNTIME/'correction_time100'/f'TIME_{beta:.2f}_ACTUAL_B0'
        with np.load(p/'AC_FULL.npz') as z:a=z['node_voltage_pu'];slots=z['event_slot']
        axes=read(p/'AXES.json')['nodes'];er=read(p/'EVENT_ROWS.json');events=read(p/'EVENTS.json');states=read(p/'STATES.json')
        last=np.array([np.flatnonzero(slots==t)[-1] for t in range(120)])
        for scope,indices in [('SETTLED96',last[24:]),('ALL_EVENTS96',np.flatnonzero(slots>=24)),('ALL_EVENTS_PREFIX24',np.flatnonzero(slots<24))]:
            for kind,op in [('LOW',np.argmin),('HIGH',np.argmax)]:
                ij=np.unravel_index(op(a[indices]),a[indices].shape);j=int(indices[ij[0]]);n=int(ij[1]);node=axes[n];bus=node.rsplit('.',1)[0].lower()
                path=path_to(bus,parents);s=int(slots[j]);row=dict(beta_BG=beta,scope=scope,kind=kind,node=node,voltage_pu=float(a[j,n]),slot=s,evaluation_slot=s-24,
                    physical_seconds=er[j]['physical_seconds'],path=path,final_slot_taps=states[s]['taps'])
                lows.append(row)
        # Every settled undervoltage node, not only the scalar minimum.
        for n in np.flatnonzero(a[last[24:]].min(axis=0)<.95-1e-8):
            node=axes[n];bus=node.rsplit('.',1)[0].lower();v=float(a[last[24:],n].min())
            if node not in worst or v<worst[node]['voltage_pu']:worst[node]=dict(node=node,voltage_pu=v,beta_BG=beta,path=path_to(bus,parents))
        for t,state in enumerate(states):
            for r in readback:
                tap=state['taps'][r['transformer']][1]
                saturation.append(dict(beta_BG=beta,slot=t,evaluation_slot=t-24,regcontrol=r['regcontrol'],tap=tap,
                    tap_number_derived=round((tap-1)/r['tap_step']),at_lower=abs(tap-r['min_tap'])<1e-8,at_upper=abs(tap-r['max_tap'])<1e-8))
    save('S0_VOLTAGE_EXTREMA_PATHS.json',lows);save('S0_ALL_SETTLED_UNDERVOLTAGE_PATHS.json',list(worst.values()));table('S0_TAP_SATURATION_SLOT_AUDIT.csv',saturation)
    # Hardware placement uses only the sealed S0 bad-voltage graph. For each
    # affected leaf choose its nearest *three-phase MV line ancestor*. Distinct
    # cuts are ranked by downstream undervoltage coverage then worst voltage.
    for row in worst.values():
        legal=[]
        for edge in row['path']:
            r=meta.get(edge['element'].lower())
            if not r or not edge['element'].lower().startswith('line.') or r['nphase']!=3 or r['group']!='Primary':continue
            if r['buses'][0].split('.')[0].lower()!=edge['parent']:continue
            if r['node_order'][:3]!=[1,2,3] or r['node_order'][r['ncond']:r['ncond']+3]!=[1,2,3]:continue
            legal.append((edge,r))
        if not legal:continue
        edge,r=legal[-1];key=r['element'];c=candidate_score.setdefault(key,dict(edge=edge,line=r,covered_nodes=[],worst_voltage=1.))
        c['covered_nodes'].append(row['node']);c['worst_voltage']=min(c['worst_voltage'],row['voltage_pu'])
    ranked=sorted(candidate_score.values(),key=lambda r:(-len(r['covered_nodes']),r['worst_voltage'],r['line']['element']))
    # If fewer than12 distinct bad-leaf stems exist, fill using each next
    # nearest legal ancestor, ordered deepest first; no AC outcomes are used.
    used={r['line']['element'] for r in ranked}
    extras={}
    for row in worst.values():
        for depth,edge in enumerate(row['path']):
            r=meta.get(edge['element'].lower())
            if r and r['element'] not in used and r['element'].lower().startswith('line.') and r['nphase']==3 and r['group']=='Primary' and r['node_order'][:3]==[1,2,3] and r['buses'][0].split('.')[0].lower()==edge['parent']:
                extras[r['element']]=dict(edge=edge,line=r,covered_nodes=[],worst_voltage=row['voltage_pu'],depth=depth)
    ranked+=sorted(extras.values(),key=lambda r:(-r['depth'],r['line']['element']))
    assert len(ranked)>=12
    reference=ROOT/'docs/v44/v43_planning_svr12_actual_v1/hardware/SCENARIO.json'
    source=read(reference)['svr'];template=source['units'][0];units=[]
    for i,r in enumerate(ranked[:12]):
        edge=r['edge'];line=r['line'];kv=12.47/math.sqrt(3);u={k:template[k] for k in ('band_volts','delay_seconds','max_tap','max_tap_change','min_tap','no_load_loss_pct','num_taps','phases','reverse_policy','tap_delay_seconds','vreg_volts','winding_r_pct','xhl_pct','engineering_assumptions')}
        # Capacity exactly equals the unchanged original line normal-current
        # rating; full-power transformer model/losses match the r043 model.
        u.update(id=f'B{i+1:02d}',cut_element=line['element'],cut_terminal=1,original_bus_spec=line['buses'][0],
            upstream_new_bus=f'v2svr_b{i+1:02d}',downstream_bus=edge['child'],sensed_bus=edge['child'],
            nominal_kv_ln=kv,sensed_kv_ln=kv,phase_kva=line['normal_amps']*kv,ctprim=line['normal_amps'],ptratio=kv*1000/120,remote_ptratio=kv*1000/120,
            series_orientation='UPSTREAM_OF_EXISTING_BRANCH',source_receipts=[dict(path=str(reference),sha256=sha(reference.read_bytes()))],
            site_selection_S0_only=True,downstream_undervoltage_nodes=r['covered_nodes'])
        units.append(u)
    contracts={}
    for n in (3,6,12):
        contract={k:source[k] for k in ('schema','Q_injection_devices','autonomous_native_control','bus_voltage_assignment','tap_optimization_variables')}
        contract['units']=units[:n];contracts[f'S1_{n:02d}']=contract
    save('SVR_CANDIDATE_PREREGISTRATION.json',dict(status='FROZEN_BEFORE_S1_AC',betas=BETAS,order=['S0','S1_03','S1_06','S1_12'],
        selection='S0 settled undervoltage leaves nearest legal three-phase12.47kV ancestor; coverage descending then worst voltage; nested additional nearest ancestors when fewer than12 distinct stems',
        source_hardware=dict(path=str(reference),sha256=sha(reference.read_bytes()),original_banks=len(source['units'])),contracts=contracts,
        original_RegControl_count=12,Planning='S0 original hardware, native TIME same P5',Actual='S0 or fixed preregistered S1 hardware; all arms B0/B1/B2/B3 must share selected Actual physical model and controls',
        new_Vreg=120.,new_Delay_seconds=30,new_TapDelay_seconds=2,existing_P5_unchanged=True,
        assumptions='Full-power grounded-wye1:1 regulator transformers, XHL1%, each R.2%, no-load.05%, .9..1.1/32steps, source line ampacity sized; research equipment not manufacturer/site certification',
        no_line_deleted=True,no_original_rating_change=True,no_optimization=True))
    print('DIAGNOSED',len(worst),'undervoltage nodes; candidates',len(units),flush=True)

if __name__=='__main__':diagnose()
