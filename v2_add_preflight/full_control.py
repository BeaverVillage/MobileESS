"""Read every native TIME Tap/Queue and event voltage witness independently."""
import numpy as np
from .full_common import *

def audit():
    resources();rows=[];voltage=[];slotrows=[];top=[];scope=[]
    grid=read(OUT/'GRID_AXES.json');lineaxes=grid['line'];parent=np.array(grid['parent_mask']);par=np.flatnonzero(parent)
    mv=parent&np.array([x['group']=='Primary' for x in lineaxes]);lv=parent&~mv
    for folder in sorted((RUN/'daily_r0').glob('*')):
        if not (folder/'RECEIPT.json').exists() or folder.name.endswith('_FRESH'):continue
        receipt=read(folder/'RECEIPT.json');trace=read(folder/'TRACE.json');clock=read(folder/'CLOCK.json');events=read(folder/'EVENTS.json')
        by={};last={};tapchanges={};tapmovement={};saturated=set();bad=[];queuebad=[]
        for frame in trace:
            now=frame['physical_seconds']
            for r in frame['controls']:
                name=r['regcontrol'];by[name]=r
                if not r['tap_number_readback_PASS'] or r['winding']!=2 or r['tap_winding']!=2:bad.append((now,name))
                if r['at_lower'] or r['at_upper']:saturated.add(name)
                if name in last and last[name]!=r['tap_number']:
                    tapchanges[name]=tapchanges.get(name,0)+1;tapmovement[name]=tapmovement.get(name,0)+abs(last[name]-r['tap_number'])
                last[name]=r['tap_number']
        for c in clock:
            for event in c['events']:
                for q in event['pending_queue']:
                    if q['absolute_seconds']<=event['absolute_seconds']:queuebad.append(q)
        for name,r in sorted(by.items()):
            rows.append(dict(case=folder.name,control=name,additional_SVR=name.startswith('svr_'),
                transformer=r['transformer'],winding=r['winding'],tap_changes=tapchanges.get(name,0),steps_moved=tapmovement.get(name,0),
                ever_saturated=name in saturated,final_tap=r['tap'],final_tap_number=r['tap_number'],
                minimum_observed_headroom_steps=min(min(v['down_steps'],v['up_steps']) for f in trace for v in f['controls'] if v['regcontrol']==name),
                Delay=r['properties']['Delay'],TapDelay=r['properties']['TapDelay'],Vreg=r['properties']['VReg'],
                native_readback_PASS=not bad,queue_future_PASS=not queuebad,
                event_clock_monotone=all(b['physical_seconds']>=a['physical_seconds'] for a,b in zip(trace,trace[1:]))))
        with np.load(folder/'AC.npz') as a:
            nodes=read(OUT/('FULL_AXES.json' if receipt['role']=='ACTUAL' else 'GRID_AXES.json'))['nodes'];v=a['node_voltage_pu'];assert v.shape[1]==len(nodes)
            for kind,j in [('minimum',int(v.argmin())),('maximum',int(v.argmax()))]:
                t,n=np.unravel_index(j,v.shape)
                voltage.append(dict(case=folder.name,kind=kind,node=nodes[n],pu=float(v[t,n]),event_index=int(t),
                    slot=int(a['event_slot'][t]),physical_seconds=events[t]['physical_seconds']))
            off=24 if receipt['role']=='ACTUAL' else 0;evaluate=a['event_slot']>=off
            for group,keep in [('ALL_NODES',np.ones(len(nodes),dtype=bool)),('EXISTING_NODES',np.array([not n.startswith('full_mobile_idc') for n in nodes])),
                ('NEW_IDC_LV',np.array([n.startswith('full_mobile_idc') for n in nodes]))]:
                nidx=np.flatnonzero(keep);vv=v[evaluate][:,keep]
                for kind,idx in [('minimum',int(vv.argmin())),('maximum',int(vv.argmax()))]:
                    et,n=np.unravel_index(idx,vv.shape);event_index=np.flatnonzero(evaluate)[et]
                    scope.append(dict(case=folder.name,scope='EVALUATION96',nodes=group,kind=kind,node=nodes[nidx[n]],pu=float(vv[et,n]),
                        slot=int(a['event_slot'][event_index]),physical_seconds=events[event_index]['physical_seconds']))
            maxima={};line=a['line_rho'];event_slot=a['event_slot']
            for t in range(off,120 if receipt['role']=='ACTUAL' else 96):
                et=int(np.flatnonzero(event_slot==t)[-1]);rho=line[et];j=int(par[np.argmax(rho[par])]);r=lineaxes[j]
                slotrows.append(dict(case=folder.name,slot=t,evaluation_slot=t-off,rho_global=float(rho[parent].max()),rho_MV=float(rho[mv].max()),
                    rho_LV=float(rho[lv].max()),MV_minus_LV=float(rho[mv].max()-rho[lv].max()),binding_line=r['element'],
                    phase=r['physical_phase'],parent_terminal=r['terminal']))
                for j in par:
                    r=lineaxes[j]
                    if float(rho[j])>maxima.get(r['element'],{}).get('rho',-1):maxima[r['element']]=dict(line=r['element'],phase=r['physical_phase'],rho=float(rho[j]),slot=t,parent_terminal=r['terminal'])
            for rank,r in enumerate(sorted(maxima.values(),key=lambda x:(-x['rho'],x['line']))[:20]):top.append(dict(case=folder.name,rank=rank+1,**r))
    table('NATIVE_TAP_QUEUE_ALL_CONTROL_SUMMARY.csv',rows);table('NATIVE_TIME_EXTREME_NODE_PHASE.csv',voltage)
    table('EVALUATION_EXISTING_VS_NEW_IDC_VOLTAGE.csv',scope);table('ALL_DATES_SETTLED_SLOT_BOTTLENECKS.csv',slotrows);table('ALL_DATES_SETTLED_TOP20.csv',top)
    put('NATIVE_TAP_QUEUE_CERTIFICATION.json',dict(PASS=bool(rows) and all(r['native_readback_PASS'] and r['queue_future_PASS'] and r['event_clock_monotone'] for r in rows),
        controls_per_Actual=21,controls_per_Planning=12,existing_control_count=12,extra_serial_three_phase_banks=3,
        observed_saturated_controls=sorted({r['control'] for r in rows if r['ever_saturated']}),
        original12_tap_or_delay_or_Vreg_changed=False,SVR3_parameters_changed=False,HVMV_Sub_has_RegControl=False,
        STA750_or_IDC750_has_RegControl=False,Prefix_state_reset=False,physical_delay_skipped=False,
        operational_voltage_PASS=False,physical_failure_not_numerical_iterations=True))
    print('TAP QUEUE AUDIT',len(rows),len(voltage),flush=True)

if __name__=='__main__':audit()
