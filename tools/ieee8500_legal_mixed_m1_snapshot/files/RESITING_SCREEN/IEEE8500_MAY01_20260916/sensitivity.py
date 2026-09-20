from inventory import *
from screen_ac import read,s

def candidates():
 inv=read(H/'NATIVE_BUS_INVENTORY.json');by={r['bus']:r for r in inv};chosen={};graph=collections.defaultdict(set)
 for e in read(H/'NATIVE_EDGES.json'):
  for b in e['buses'][1:]:graph[b].add(e['buses'][0]);graph[e['buses'][0]].add(b)
 def add(b,why,node=None):
  if b not in by or not by[b]['MESS_phase_adapted_candidate']:return
  r=by[b];nodes=[node] if node else ([1,2,3] if r['AIDC_candidate'] else r['nodes'])
  # LV service candidates are individual conductor-to-neutral ports.
  for nn in ([nodes] if r['AIDC_candidate'] else [[n] for n in nodes]):
   key=b+'.'+'.'.join(map(str,nn));chosen.setdefault(key,dict(key=key,bus=b,nodes=nn,phases=len(nn),kv=r['kV_LN']*(np.sqrt(3) if len(nn)==3 else 1),why=why,AIDC_candidate=r['AIDC_candidate']))
 for r in read(AUTH/'PCC_OVERLAY_INVENTORY.json'):
  if r['PCC_role']=='AIDC':
   b=r['host_bus'];add(b,'existing legal AIDC')
   for n in graph[b]:add(n,'legal neighbor of existing AIDC')
 for r in read(H/'HIGH_LOADING_LINES.json')[:45]:
  for bb in r['buses']:
   b=bb.split('.')[0];add(b,'high-loading corridor')
   for n in graph[b]:add(n,'adjacent high-loading corridor')
 # Greedy geographic spread avoids clustering and supplies remote receiving sites.
 mv=[r for r in inv if r['AIDC_candidate']]
 pos=np.array([[r['x'],r['y']] for r in mv]);pick=[0]
 for k in range(32):
  dd=((pos[:,None,:]-pos[pick][None,:,:])**2).sum(2).min(1);i=int(dd.argmax());pick.append(i)
 for i in pick:add(mv[i]['bus'],'spatially diverse MV receiver/stressed candidate')
 add('sx2748781a','original undervoltage witness')
 vals=list(chosen.values());save(H/'SENSITIVITY_CANDIDATES.json',vals);return vals

def main():
 start=time.perf_counter();cc=candidates();e=Engine(H/'sensitivity_runtime');d=e.d;d.Solution.Convergence(1e-10);out=H/'sensitivity';out.mkdir(exist_ok=True)
 for i,c in enumerate(cc):d.Text.Command(f'New Load.resiting_probe_{i} phases={c["phases"]} bus1={c["key"]} conn=wye kv={c["kv"]} kw=0 kvar=0 Model=1 Vminpu=.85 Vmaxpu=1.15 Status=Fixed')
 rows=[];prev=None
 for t in SLOTS:
  if prev is None:e.restore(t)
  e.inputs(t,BASE_P,BASE_Q);r,a=e.measure(t);state=s.control_state(d,t,e.rule['source_pu'],e.rule['Vreg_V']);base=np.array(a[1]);jP=[];jQ=[]
  def restore():
   for rr in state['regulators']:d.RegControls.Name(rr['name']);d.RegControls.TapNumber(rr['tap_number'])
   for rr in state['capacitors']:d.Capacitors.Name(rr['name']);d.Capacitors.States(rr['step_states'])
   d.CtrlQueue.ClearQueue()
  for i,c in enumerate(cc):
   delta=1. if c['phases']==3 else .1;vv=[];local=[]
   for typ in ('P','Q'):
    restore();d.Loads.Name(f'resiting_probe_{i}');d.Loads.kW(-delta if typ=='P' else 0);d.Loads.kvar(-delta if typ=='Q' else 0)
    rr,aa=e.measure(t);assert rr['converged'] and d.Solution.ControlActionsDone();der=(np.array(aa[1])-base)/delta
    (jP if typ=='P' else jQ).append(der);vv.append((rr['Vmin_pu']-r['Vmin_pu'])/delta)
    d.Loads.Name(f'resiting_probe_{i}');d.Loads.kW(0);d.Loads.kvar(0)
   idx=int(np.argmax(base));critical=[k for k,x in enumerate(e.ax['line_label']) if x.startswith('Line.tpx21459660c0|')]
   kcrit=max(critical,key=lambda k:base[k])
   rows.append(dict(slot=t,**c,d_rho_max_dP_injection=float(jP[-1][idx]),d_critical_rho_dP_injection=float(jP[-1][kcrit]),d_critical_rho_dQ_injection=float(jQ[-1][kcrit]),d_Vmin_dP_injection=vv[0],d_Vmin_dQ_injection=vv[1],step_kw_kvar=delta))
  np.savez_compressed(out/f'slot_{t:02}.npz',line=base,P=np.array(jP),Q=np.array(jQ),labels=np.array(e.ax['line_label']))
  restore();e.inputs(t,BASE_P,BASE_Q);e.measure(t);prev=t
  table(H/'SENSITIVITY_MAP.csv',rows);print(json.dumps(dict(slot=t,candidates=len(cc),seconds=time.perf_counter()-start)),flush=True)
 save(H/'SENSITIVITY_MAP.json',rows);save(H/'SENSITIVITY_METHOD.json',dict(candidates=len(cc),slots=SLOTS,method='Exact OpenDSS one-sided finite differences of positive native-bus P/Q injection; baseline tap/cap state restored before each perturbation, automatic controls active; diagnostic probes without PCC transformer losses; selected placement is separately replayed with its PCC transformers',runtime_seconds=time.perf_counter()-start));e.close()
if __name__=='__main__':main()
