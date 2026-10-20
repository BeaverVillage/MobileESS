"""Read-only original network adapter and reproducible May01 AC audit."""
from pathlib import Path
import csv
import datetime as dt
import hashlib
import json
import re
import time
import numpy as np
import dss

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/ckt24_v44_r043_may01'
RUNTIME = Path('D:/ckt24_v44_r043_may01_runtime')
ORIGINAL = RUNTIME / 'original_ckt24'
FROZEN = 'affc7226a519adbe072d7debbc3ae25ea71c3487'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(name, data):
    DOC.mkdir(parents=True, exist_ok=True)
    (DOC/name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False,
        default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+'\n', encoding='utf8')

def csvout(name, rows, fields=None):
    rows=list(rows)
    raw_names={'ORIGINAL_NODE_VOLTAGES.csv','ORIGINAL_LINE_CURRENTS.csv','ORIGINAL_TRANSFORMER_LOADING.csv'}
    folder=RUNTIME/'raw' if name in raw_names else DOC
    folder.mkdir(exist_ok=True)
    with (folder/name).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

def context(label='ac'):
    """Execute only unchanged definition prefix, with absolute dependency paths.

    Original master warns against executing all its mutually exclusive demos.
    No source property, control definition, rating, or coordinate is edited.
    """
    e=dss.DSS.NewContext()
    e.AllowChangeDir=False
    out=RUNTIME/label;out.mkdir(exist_ok=True)
    e.DataPath=str(out)
    text=(ORIGINAL/'master_ckt24.dss').read_text()
    prefix=text.split('//-------------------- Normal yearly simulation')[0]
    lines=[]
    for line in prefix.splitlines():
        s=line.strip()
        if not s or s.startswith(('!','//')): continue
        m=re.match(r'(Redirect|Buscoords)\s+(\S+)',s,re.I)
        if m:
            target=next((p for p in ORIGINAL.iterdir() if p.name.lower()==m[2].lower()),None)
            if target is None: raise FileNotFoundError(m[2])
            s=s[:m.start(2)]+'"'+target.as_posix()+'"'+s[m.end(2):]
        s=re.sub(r'file=([\w.]+)',lambda m:'file="'+(ORIGINAL/m[1]).as_posix()+'"',s,flags=re.I)
        lines.append(s)
        e.Text.Command=s
    (out/'DEFINITION_ADAPTER.dss').write_text('\n'.join(lines)+'\n',encoding='utf8')
    e.DataPath=str(out)
    # Tighten independent AC numerical residuals for small finite differences.
    # This does not modify MILP feasibility, gap, or integrality tolerances.
    e.ActiveCircuit.Solution.Tolerance=1e-10
    e.ActiveCircuit.Solution.MaxIterations=100
    return e

def inventory(e):
    c=e.ActiveCircuit
    buses=[]
    for name in c.AllBusNames:
        c.SetActiveBus(name);b=c.ActiveBus
        buses.append(dict(bus=name,kv_ln=b.kVBase,kv_ll=b.kVBase*3**.5,nodes=list(b.Nodes),
                          coord_defined=b.Coorddefined,x=b.x,y=b.y))
    lines=[]
    for name in c.Lines.AllNames:
        c.Lines.Name=name;a=c.ActiveCktElement
        lines.append(dict(line=name,bus1=a.BusNames[0],bus2=a.BusNames[1],
                          phases=a.NumPhases,conductors=a.NumConductors,normamps=a.NormalAmps,
                          emergamps=a.EmergAmps,nodes=list(a.NodeOrder)))
    transformers=[]
    for name in c.Transformers.AllNames:
        c.Transformers.Name=name;a=c.ActiveCktElement;windings=[]
        for w in range(1,c.Transformers.NumWindings+1):
            c.Transformers.Wdg=w
            windings.append(dict(winding=w,kv=c.Transformers.kV,kva=c.Transformers.kVA,
                                 tap=c.Transformers.Tap,bus=a.BusNames[w-1]))
        transformers.append(dict(transformer=name,phases=a.NumPhases,windings=windings))
    return buses,lines,transformers

def measurements(e,buses,lines,transformers,slot):
    c=e.ActiveCircuit
    v=[]
    for b in buses:
        c.SetActiveBus(b['bus']);bus=c.ActiveBus
        mags=np.asarray(bus.puVmagAngle)[::2]
        v.extend(dict(slot=slot,bus=b['bus'],phase=int(n),v_pu=float(m))
                 for n,m in zip(bus.Nodes,mags) if n>0 and bus.kVBase>0)
    lr=[];bm={b['bus']:b for b in buses}
    for line in lines:
        c.Lines.Name=line['line'];a=c.ActiveCktElement
        amps=np.asarray(a.CurrentsMagAng)[::2];nodes=a.NodeOrder;nc=a.NumConductors
        for t in range(a.NumTerminals):
            bus=a.BusNames[t].split('.')[0].lower();kv=bm[bus]['kv_ll']
            for k in range(nc):
                j=t*nc+k;phase=int(nodes[j])
                if phase<=0:continue
                lr.append(dict(slot=slot,line=line['line'],terminal=t+1,phase=phase,
                    current_a=float(amps[j]),normamps=line['normamps'],
                    loading_pu=float(amps[j]/line['normamps']) if line['normamps']>0 else None,
                    kv_ll=kv,voltage_class='MV' if kv>=1 else 'LV',bus=bus,
                    bus1=line['bus1'],bus2=line['bus2']))
    tr=[]
    for xf in transformers:
        c.Transformers.Name=xf['transformer'];a=c.ActiveCktElement;nc=a.NumConductors
        p=np.asarray(a.Powers).reshape(-1,2);amps=np.asarray(a.CurrentsMagAng)[::2]
        for w in xf['windings']:
            sl=slice((w['winding']-1)*nc,w['winding']*nc)
            pq=p[sl].sum(axis=0);kva=float(np.hypot(*pq))
            tr.append(dict(slot=slot,transformer=xf['transformer'],winding=w['winding'],
                kv=w['kv'],rated_kva=w['kva'],p_kw=float(pq[0]),q_kvar=float(pq[1]),
                kva=kva,loading_pu=kva/w['kva'],max_current_a=float(max(amps[sl]))))
    controls=[]
    for name in c.RegControls.AllNames:
        if name=='NONE':continue
        c.RegControls.Name=name
        controls.append(dict(slot=slot,type='RegControl',name=name,transformer=c.RegControls.Transformer,
                             state=str(c.RegControls.TapNumber)))
    for name in c.Capacitors.AllNames:
        if name=='NONE':continue
        c.Capacitors.Name=name
        controls.append(dict(slot=slot,type='Capacitor',name=name,transformer='',state=str(list(c.Capacitors.States))))
    return v,lr,tr,controls

def audit():
    start=time.time();DOC.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((RUNTIME/'ORIGINAL_DOWNLOAD_MANIFEST.json').read_text())
    for row in manifest['files']:
        if sha(ORIGINAL/row['file'])!=row['sha256']:raise ValueError('ORIGINAL_SHA_DRIFT')
    save('ORIGINAL_DSS_SHA256_MANIFEST.json',manifest)
    e=context();buses,lines,xfs=inventory(e)
    save('NETWORK_INVENTORY.json',dict(buses=buses,lines=lines,transformers=xfs))
    c=e.ActiveCircuit
    save('ORIGINAL_CKT24_NETWORK_AUDIT.json',dict(svn_revision=4176,engine=e.Version,
        buses=len(buses),nodes=c.NumNodes,lines=len(lines),transformers=len(xfs),loads=c.Loads.Count,
        mv_buses=sum(1<=b['kv_ll']<69 for b in buses),lv_buses=sum(0<b['kv_ll']<1 for b in buses),
        regcontrols=c.RegControls.Count,capcontrols=c.CapControls.Count,pv_systems=c.PVSystems.Count,
        buses_with_coordinates=sum(b['coord_defined'] for b in buses),
        coordinate_authority='ORIGINAL_EPRI_BUSCOORDS; CRS/units/geographic provenance not documented in downloaded folder',
        original_network_properties_edited=False,original_file_sha_verified=True,
        SVR12_policy='NOT_APPLICABLE_PENDING_NEW_EQUIPMENT_ENGINEERING; no IEEE123 devices copied'))
    allv=[];alll=[];allt=[];allc=[];summary=[];top=[]
    # Local synthetic study-day assignment to original 8760-hour normalized shapes.
    # This is not an assertion that EPRI shapes were measured in calendar year 2025.
    hour=(dt.date(2025,5,1)-dt.date(2025,1,1)).days*24
    e.Text.Command='set mode=yearly number=1 stepsize=900s controlmode=static'
    for slot in range(96):
        e.Text.Command=f'set hour={hour+slot//4} sec={(slot%4)*900}'
        # SolveSnap evaluates exactly the assigned hour; it does not increment time.
        c.Solution.SolveSnap()
        if not c.Solution.Converged:raise RuntimeError(f'AC_NONCONVERGENCE:{slot}')
        v,lr,tr,co=measurements(e,buses,lines,xfs,slot)
        allv.extend(v);alll.extend(lr);allt.extend(tr);allc.extend(co)
        unique={}
        for row in sorted(lr,key=lambda x:x['loading_pu'],reverse=True):
            unique.setdefault((row['line'],row['phase']),row)
        ranked=list(unique.values());top.extend(dict(rank=k+1,**r) for k,r in enumerate(ranked[:20]))
        worst=ranked[0];vs=[r['v_pu'] for r in v];tx=max(tr,key=lambda r:r['loading_pu'])
        summary.append(dict(slot=slot,time=f'{slot//4:02}:{(slot%4)*15:02}',hour=c.Solution.Hour,
            seconds=c.Solution.Seconds,converged=True,p_feeder_kw=float(-c.TotalPower[0]),q_feeder_kvar=float(-c.TotalPower[1]),
            rho_max=worst['loading_pu'],worst_line=worst['line'],phase=worst['phase'],voltage_class=worst['voltage_class'],
            v_min=min(vs),v_max=max(vs),transformer_loading_max=tx['loading_pu'],worst_transformer=tx['transformer']))
        if slot%16==0:print('AC',slot,summary[-1],flush=True)
    csvout('ORIGINAL_BASELINE_96.csv',summary)
    csvout('B0_MV_LV_BOTTLENECKS.csv',top)
    csvout('ORIGINAL_NODE_VOLTAGES.csv',allv);csvout('ORIGINAL_LINE_CURRENTS.csv',alll)
    csvout('ORIGINAL_TRANSFORMER_LOADING.csv',allt);csvout('ORIGINAL_CONTROL_STATES.csv',allc)
    result=dict(status='ORIGINAL_ONLY_DIAGNOSTIC_NOT_B0_WITH_AIDC',slots=96,
        study_date='2025-05-01',shape_hour_origin=hour,time_semantics='calendar-day assignment to original shapes, timestamps at interval start; no 2025 measurement claim',
        control_mode='static_original_controls; original master demo uses off; original definitions unchanged',
        v_min=min(r['v_min'] for r in summary),v_max=max(r['v_max'] for r in summary),
        rho_max=max(r['rho_max'] for r in summary),peak_slot=max(summary,key=lambda r:r['rho_max'])['slot'],
        max_transformer_loading=max(r['transformer_loading_max'] for r in summary),
        voltage_violating_slots=sum(r['v_min']<.95 or r['v_max']>1.05 for r in summary),
        line_overload_slots=sum(r['rho_max']>1 for r in summary),
        transformer_overload_slots=sum(r['transformer_loading_max']>1 for r in summary),
        wall_seconds=time.time()-start,algorithm_source_sha=FROZEN,UTC=dt.datetime.now(dt.timezone.utc).isoformat())
    save('ORIGINAL_BASELINE_SUMMARY.json',result)
    save('RAW_AC_RECEIPTS.json',dict(UTC=result['UTC'],algorithm_source_sha=FROZEN,files=[
        dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in (RUNTIME/'raw').glob('*.csv')]))
    for row in manifest['files']:
        if sha(ORIGINAL/row['file'])!=row['sha256']:raise ValueError('POST_AC_ORIGINAL_SHA_DRIFT')
    print(json.dumps(result,indent=2))

if __name__=='__main__':audit()
