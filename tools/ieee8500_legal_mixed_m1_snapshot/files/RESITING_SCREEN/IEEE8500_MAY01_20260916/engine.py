from inventory import *
from screen_ac import read,s,odd,STATES
NATIVE=ROOT/'IEEE8500_scalability_20260910/source/Master-unbal.dss'
IDS=['STA01','STA12','STA08','STA06','STA03','STA10']

def overlay(layout,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);cmd=[];inv=[]
 for i,b in enumerate(layout['aidc']):
  ident=f'AIDC{i+1:02}';pcc=f'pcc8500_aidc_{ident.lower()}_lv';tx=f'pcc8500_aidc_{ident.lower()}_tx'
  cmd.extend([f'New Transformer.{tx} Phases=3 Windings=2 XHL=5.75 %Rs=[0.8 0.2] %NoLoadLoss=0 %Imag=0',f'~ Buses=[{b}.1.2.3 {pcc}.1.2.3] Conns=[wye wye] kVs=[12.47 0.48] kVAs=[1500 1500]'])
  inv.append(dict(location_id=ident,PCC_role='AIDC',PCC_bus=pcc,host_bus=b,phases=3))
 for i,c in enumerate(layout['mess']):
  ident=IDS[i];pcc=f'resite_{ident.lower()}_lv';ph=c['phases'];sec='.1.2.3' if ph==3 else '.1.0';primary=c['key']+('.0' if ph==1 else '')
  cmd.extend([f'New Transformer.resite_{ident.lower()}_tx Phases={ph} Windings=2 XHL=5.75 %Rs=[0.8 0.2] %NoLoadLoss=0 %Imag=0',f'~ Buses=[{primary} {pcc}{sec}] Conns=[wye wye] kVs=[{c["kv"]} 0.48] kVAs=[750 750]'])
  inv.append(dict(location_id=ident,PCC_role='MESS',PCC_bus=pcc,host_bus=c['bus'],phases=ph,connection=sec))
 cmd.append('CalcVoltageBases')
 for r in inv:
  if r['phases']==1:cmd.append(f'SetkVBase Bus={r["PCC_bus"]} kVLN=0.48')
 path=folder/'PCC_OVERLAY.dss';path.write_text('\n'.join(cmd),encoding='utf-8');save(folder/'PLACEMENT.json',layout);return path,inv

class ResiteEngine(Engine):
 def __init__(self,layout,folder):
  folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);path,self.inv=overlay(layout,folder)
  self.rule=read(AUTH/'SCREENING_RULE.json');fc=read(AUTH/'D1_AEMO_VIC1_FORECAST.json');d=self.d=odd.NewContext()
  d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False);d.Basic.DataPath(str(folder));d.Text.Command(f'Compile "{NATIVE}"');d.Basic.DataPath(str(folder))
  self.loads=s.frozen.native_inventory(d);self.P=np.array([r['base_kw'] for r in self.loads]);self.Q=np.array([r['base_kvar'] for r in self.loads])
  d.Text.Command(f'Redirect "{path}"');d.Text.Command(f'Redirect "{s.overlay_path(self.rule["source_pu"],self.rule["Vreg_V"])}"')
  self.ax=s.frozen.measurement_axes(d);self.nodes=np.array(d.Circuit.AllNodeNames());s.frozen.add_resources(d,self.loads,self.rule['PV_ratio'],self.inv)
  self.services=IDS
  for r in self.inv:
   if r['PCC_role']=='MESS':d.Text.Command(f'New Load.fast_mess_{r["location_id"].lower()} phases={r["phases"]} bus1={r["PCC_bus"]}{r["connection"]} conn=wye kv=0.48 kw=0 kvar=0 Model=1 Vminpu=.85 Vmaxpu=1.15 Status=Fixed')
  self.md=np.array(fc['demand_mw_96']);self.md/=self.md.max();self.mpv=np.array(fc['pv_mw_96']);self.mpv/=self.mpv.max()
  d.Solution.MaxIterations(100);d.Solution.MaxControlIterations(1000);d.Solution.Convergence(1e-10)

def replay(layout,p,folder,mess=None,slots=SLOTS):
 start=time.perf_counter();e=ResiteEngine(layout,Path(folder)/'runtime');rows=[];prev=None
 for t in slots:
  if prev is None or t!=prev+1:e.restore(t)
  e.inputs(t,p,p*(BASE_Q/BASE_P),mess);r,a=e.measure(t);rows.append(r);prev=t
 keys=['max_phase_line_loading_pu','Vmin_pu','Vmax_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu']
 result={k:(min if k=='Vmin_pu' else max)(r[k] for r in rows) for k in keys}
 result.update(physical_pass=all(r['physical_pass'] for r in rows),slots=len(rows),runtime_seconds=time.perf_counter()-start)
 result['critical_witness']=max(rows,key=lambda r:r['max_phase_line_loading_pu'])['line_witness']
 table(Path(folder)/'SLOTS.csv',rows);save(Path(folder)/'SUMMARY.json',result);e.close();return result

def arrays(e):
 d=e.d;ax=e.ax;v=np.asarray(d.Circuit.AllBusMagPu());ia=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2);ii=ia[:,0]*np.exp(1j*np.deg2rad(ia[:,1]));pw=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
 ss=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],0])+1j*np.bincount(ax['power_group'],weights=pw[ax['power_pos'],1])
 return v,np.r_[ii[ax['line_pos']]/ax['line_rating'],ii[ax['tx_pos']]/ax['tx_rating'],ss/ax['kva_rating']]
