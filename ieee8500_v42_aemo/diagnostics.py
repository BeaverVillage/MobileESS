"""Phase-aware source paths and original regulator measurement forensics."""
from collections import defaultdict, deque
import numpy as np
from ieee8500_v42.ac import _complex
from .common import *
from .engine import StudyEngine
from .run_b0 import summary


def topology(e, phase=None):
    graph=defaultdict(list)
    records=e.inventory['lines']+e.inventory['transformers']
    for name in e.d.Reactors.AllNames():
        e.d.Reactors.Name(name)
        records=records+[dict(element='Reactor.'+name,buses=e.d.CktElement.BusNames(),
                             enabled=e.d.CktElement.Enabled())]
    for r in records:
        if not r['enabled']:continue
        buses=r['buses']
        if len(buses)<2:continue
        explicit=[int(x) for x in buses[0].split('.')[1:]]
        if phase and explicit and phase not in explicit and r['element'].lower().startswith('transformer.'):
            continue
        a=buses[0].split('.')[0].lower()
        for bus in buses[1:]:
            b=bus.split('.')[0].lower()
            if a!=b:
                graph[a].append((b,r['element']));graph[b].append((a,r['element']))
    parent={'sourcebus':None};queue=deque(['sourcebus'])
    while queue:
        a=queue.popleft()
        for b,element in graph[a]:
            if b not in parent:
                parent[b]=(a,element);queue.append(b)
    return parent


def path_to(parent,bus):
    bus=bus.lower();out=[]
    assert bus in parent,('DISCONNECTED_SOURCE_PATH',bus)
    while parent[bus] is not None:
        a,element=parent[bus];out.append(dict(parent_bus=a,child_bus=bus,element=element));bus=a
    return list(reversed(out))


def regulator_monitors(e,stage,slot):
    out=[]
    for r in e.inventory['regcontrols']:
        props=r['properties'];assert not props['Bus'] and props['Reversible']=='No'
        assert props['PTPhase']=='1' and float(props['LDC_Z'])==0
        e.d.RegControls.Name(r['name']);vreg=e.d.RegControls.ForwardVreg()
        tapnum=e.d.RegControls.TapNumber()
        winding=int(props['Winding']);e.d.Transformers.Name(r['transformer']);e.d.Transformers.Wdg(winding)
        nc=e.d.CktElement.NumConductors();vv=_complex(e.d.CktElement.Voltages()).reshape(-1,nc)
        ii=_complex(e.d.CktElement.Currents()).reshape(-1,nc)
        assert e.d.CktElement.NumPhases()==1 and nc==2
        voltage=vv[winding-1,0]-vv[winding-1,1]
        pt=float(props['PTRatio']);ct=float(props['CTPrim']);z=complex(float(props['R']),float(props['X']))
        # DSS-CAPI0.14.5 RegControl.Sample lines971-1017: currents INTO monitored terminal.
        monitor=voltage/pt+z*ii[winding-1,0]/ct
        band=float(props['Band']);tap=e.d.Transformers.Tap()
        out.append(dict(stage=stage,slot=slot,regcontrol=r['name'],transformer=r['transformer'],
            monitored_bus=e.d.CktElement.BusNames()[winding-1],winding=winding,
            Vreg_V=vreg,Band_V=band,PTRatio=pt,CTPrim=ct,R=float(props['R']),X=float(props['X']),
            winding_voltage_V=abs(voltage),uncompensated_control_V=abs(voltage/pt),
            compensated_control_V=abs(monitor),control_error_V=vreg-abs(monitor),
            inside_deadband=abs(vreg-abs(monitor))<=band/2,
            tap_number=tapnum,tap_ratio=tap,
            at_limit=abs(tap-e.d.Transformers.MinTap())<1e-12 or abs(tap-e.d.Transformers.MaxTap())<1e-12,
            VLimit=float(props['VLimit']),source_code='DSS-CAPI0.14.5 RegControl.Sample'))
    return out


def run():
    result=[];monitor=[];paths=[];snapshots=[]
    for stage,requested_slot in (('B0_PLANNING',None),('B0_ACTUAL',None),('TIME_VARIABLE_NO_PV',None),('TIME_VARIABLE_NO_PV',48)):
        source='ACTUAL' if stage=='B0_ACTUAL' else 'PLANNING'
        slots=rows(REPORT/'ac'/stage/'SLOTS.csv')
        peak=int(max(slots,key=lambda r:float(r['Vmax']))['slot']) if requested_slot is None else requested_slot
        e=StudyEngine('forensic_'+stage,'P3',True)
        with np.load(DATA/'derived'/f'{source}_INPUTS.npz') as z:
            for t in range(peak+1):
                e.apply_inputs(t,z['gross_factor'][t],z['pv_factor'][t],z['PCC_P_kw'][t],z['PCC_Q_kvar'][t],
                               pv_on=stage!='TIME_VARIABLE_NO_PV')
                a=e.settle()
        s=summary(e,a);expected=slots[peak]
        assert abs(s['Vmax']-float(expected['Vmax']))<1e-10
        capacitor_pq=[]
        for name in e.d.Capacitors.AllNames():
            e.d.Capacitors.Name(name)
            pq=np.asarray(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
            capacitor_pq.append(dict(name=name,states=e.d.Capacitors.States(),P_kw=float(pq[0]),Q_consumption_kvar=float(pq[1])))
        node=s['Vmax_node'];bus,phase=node.rsplit('.',1);path=path_to(topology(e,int(phase)),bus)
        regulators={r['transformer']:r['name'] for r in e.inventory['regcontrols']}
        monitor.extend(regulator_monitors(e,stage,peak))
        for n,r in enumerate(path):
            e.d.Circuit.SetActiveElement(r['element']);pq=np.asarray(e.d.CktElement.Powers()).reshape(-1,2)
            nc=e.d.CktElement.NumConductors()
            terminal=[b.split('.')[0].lower() for b in e.d.CktElement.BusNames()].index(r['parent_bus'])
            node_order=e.d.CktElement.NodeOrder()[terminal*nc:(terminal+1)*nc]
            phase_index=node_order.index(int(phase)) if int(phase) in node_order else None
            pu={}
            for b in (r['parent_bus'],r['child_bus']):
                e.d.Circuit.SetActiveBus(b)
                values=_complex(e.d.Bus.PuVoltage());pu[b]=dict(zip(map(str,e.d.Bus.Nodes()),map(float,np.abs(values))))
            paths.append(dict(stage=stage,slot=peak,path_index=n,**r,
                selected_primary_phase=phase,parent_phase_voltage_pu=pu[r['parent_bus']].get(phase,''),
                child_phase_voltage_pu=pu[r['child_bus']].get(phase,''),
                parent_terminal_P_kw=float(pq[terminal*nc:(terminal+1)*nc,0].sum()),
                parent_terminal_Q_kvar=float(pq[terminal*nc:(terminal+1)*nc,1].sum()),
                selected_phase_P_kw=float(pq[terminal*nc+phase_index,0]) if phase_index is not None else '',
                selected_phase_Q_kvar=float(pq[terminal*nc+phase_index,1]) if phase_index is not None else '',
                regulator=regulators.get(r['element'].split('.',1)[1],'')))
        result.append(dict(stage=stage,slot=peak,**s,regulated_path=[r['element'] for r in path
            if r['element'].split('.',1)[-1] in regulators],tap_limit_at_worst_slot=any(
                r['at_limit'] for r in monitor if r['stage']==stage)))
        snapshots.append(dict(stage=stage,slot=peak,control_state=e.control_state(),capacitor_actual_PQ=capacitor_pq))
    table(REPORT/'VOLTAGE_FORENSIC_PATH.csv',paths)
    table(REPORT/'REGULATOR_MONITOR_FORENSICS.csv',monitor)
    write(REPORT/'VOLTAGE_FORENSICS.json',dict(cases=result,states=snapshots,
        scope='exact worst-slot phase-aware source path; original local deadband is not a global all-node voltage controller',
        source='https://raw.githubusercontent.com/dss-extensions/dss_capi/0.14.5/src/Controls/RegControl.pas'))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':run()
