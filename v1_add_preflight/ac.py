"""Isolated equipment inventory. Operating AC requires a certified input gate.

The static initialization solve below establishes NodeOrder only. It is not a
May01 power-flow result and its nominal load values are never an operating input.
"""
from pathlib import Path
import csv
import hashlib
import json
import re
import numpy as np
import dss

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT/'docs/smartds_gso_substation2_v44_r043'
RUN = Path('D:/smartds_gso_substation2_v44_r043_runtime')
MODEL = RUN/'official/SMART-DS/v1.0/peak/GSO/urban-suburban/scenarios/base_peak/opendss/uhs2_1247'


def save(name, value):
    DOC.mkdir(parents=True, exist_ok=True)
    (DOC/name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+'\n', encoding='utf8')


def csvout(name, rows, fields=None):
    rows=list(rows)
    with (DOC/name).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)


def context():
    e=dss.DSS.NewContext();e.AllowChangeDir=False
    target=RUN/'ac';target.mkdir(exist_ok=True)
    e.DataPath=str(target)
    commands=[]
    def emit(path):
        for line in path.read_text().splitlines():
            s=line.strip()
            if not s or s.startswith(('!','//')):continue
            if re.match(r'(solve|plot|export)\b',s,re.I):continue
            m=re.match(r'Redirect\s+(.+)',s,re.I)
            if m:
                emit(path.parent/m[1].strip('"'));continue
            m=re.match(r'Buscoords\s+(.+)',s,re.I)
            if m:s='Buscoords "'+(path.parent/m[1].strip('"')).as_posix()+'"'
            commands.append(s);e.Text.Command=s
    emit(MODEL/'Master.dss')
    e.DataPath=str(target)
    e.ActiveCircuit.Solution.Tolerance=1e-10
    e.ActiveCircuit.Solution.MaxIterations=100
    e.Text.Command='Set controlmode=off'
    e.Text.Command='Solve mode=snapshot'  # initialize nodes without settling peak-load taps
    e.Text.Command='Set controlmode=time'
    (target/'DEFINITION_ADAPTER.dss').write_text('\n'.join(commands)+'\n')
    return e


def inventory(e):
    c=e.ActiveCircuit
    buses=[];lines=[];xf=[];loads=[]
    for name in c.AllBusNames:
        c.SetActiveBus(name);b=c.ActiveBus
        buses.append(dict(bus=name,kv_ln=b.kVBase,kv_ll=b.kVBase*3**.5,
            nodes=list(b.Nodes),x=b.x,y=b.y,coords=bool(b.Coorddefined)))
    for name in c.Lines.AllNames:
        c.Lines.Name=name;a=c.ActiveCktElement
        lines.append(dict(line=name,bus1=a.BusNames[0],bus2=a.BusNames[1],
            phases=a.NumPhases,conductors=a.NumConductors,normamps=a.NormalAmps,
            emergamps=a.EmergAmps,nodes=list(a.NodeOrder) if a.Enabled else [],
            enabled=bool(a.Enabled),length=c.Lines.Length))
    for name in c.Transformers.AllNames:
        c.Transformers.Name=name;a=c.ActiveCktElement;windings=[]
        for w in range(1,c.Transformers.NumWindings+1):
            c.Transformers.Wdg=w
            windings.append(dict(winding=w,kv=c.Transformers.kV,kva=c.Transformers.kVA,
                tap=c.Transformers.Tap,bus=a.BusNames[w-1],delta=bool(c.Transformers.IsDelta)))
        xf.append(dict(transformer=name,phases=a.NumPhases,conductors=a.NumConductors,
            windings=windings,nodes=list(a.NodeOrder),normalamps=a.NormalAmps))
    for name in c.Loads.AllNames:
        c.Loads.Name=name;a=c.ActiveCktElement
        loads.append(dict(load=name,bus=a.BusNames[0],phases=a.NumPhases,
            kv=c.Loads.kV,kw=c.Loads.kW,kvar=c.Loads.kvar))
    return dict(engine=e.Version,buses=c.NumBuses,nodes=c.NumNodes,lines=len(lines),
        transformers=len(xf),loads=len(loads),regcontrols=c.RegControls.Count,
        capacitors=c.Capacitors.Count,pv=c.PVSystems.Count,storage=c.Storages.Count,
        bus_rows=buses,line_rows=lines,transformer_rows=xf,load_rows=loads)


def measure(e, inv):
    gate=DOC/'INPUT_MAPPING_GATE.json'
    if not gate.exists() or not json.loads(gate.read_text())['AC_ALLOWED']:
        raise RuntimeError('INPUT_MAPPING_NOT_VERIFIED: operating AC measurement blocked')
    c=e.ActiveCircuit;lr=[];xr=[]
    for row in inv['line_rows']:
        if not row['enabled']:
            lr.append(0.0);continue  # original disabled tie; retained in inventory
        c.SetActiveElement('Line.'+row['line']);a=c.ActiveCktElement
        values=np.array(a.CurrentsMagAng)[::2];nodes=np.array(a.NodeOrder)
        use=(nodes>0)&(nodes<=3)
        amp=float(values[use].max());ratio=amp/row['normamps'] if row['normamps']>0 else None
        lr.append(ratio)
    for row in inv['transformer_rows']:
        c.SetActiveElement('Transformer.'+row['transformer']);a=c.ActiveCktElement
        p=np.array(a.Powers).reshape(a.NumTerminals,a.NumConductors,2)
        currents=np.array(a.CurrentsMagAng)[::2].reshape(a.NumTerminals,a.NumConductors)
        ratios=[]
        for w in row['windings']:
            wi=w['winding']-1
            apparent=abs(complex(*p[wi].sum(axis=0)))
            rated=w['kva']/w['kv']/(3**.5 if row['phases']==3 else 1)
            node=np.array(row['nodes']).reshape(a.NumTerminals,a.NumConductors)[wi]
            ratios.extend([apparent/w['kva'],float(currents[wi][node>0].max()/rated)])
        xr.append(max(ratios))
    v=np.array(c.AllBusVmagPu)
    taps={}
    for name in c.RegControls.AllNames:
        if name=='NONE':continue
        c.RegControls.Name=name
        taps[name]=c.RegControls.TapNumber
    return dict(converged=bool(c.Solution.Converged),vmin=float(v.min()),vmax=float(v.max()),
        voltage_violations=int(np.sum((v<.95)|(v>1.05))),
        rho_max=max(x for x in lr if x is not None),line_violations=sum(x>1 for x in lr if x is not None),
        transformer_max=max(xr),transformer_violations=sum(x>1 for x in xr),
        taps=taps,total_kw=float(-c.TotalPower[0]),total_kvar=float(-c.TotalPower[1]),
        line_ratios=np.array(lr),transformer_ratios=np.array(xr),voltages=v)


if __name__=='__main__':
    e=context(); inv=inventory(e);save('NETWORK_INVENTORY.json',inv)
    summary={k:v for k,v in inv.items() if not k.endswith('_rows')};print(summary)
    print('native P/Q',sum(x['kw'] for x in inv['load_rows']),sum(x['kvar'] for x in inv['load_rows']))
    print('three phase LV transformers',[(x['transformer'],x['windings'][-1]['kva'],x['windings'][-1]['bus']) for x in inv['transformer_rows'] if x['phases']==3 and x['windings'][-1]['kv']<1 and x['windings'][-1]['kva']>=100][:50])
