import sys,time,json,collections
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;ROOT=H.parent.parent
sys.path.insert(0,str(ROOT/'independent_screening/IEEE8500_FAST_SCALE_20260916'))
from screen_ac import Engine,BASE_P,BASE_Q,SLOTS,save,table,np,original,AUTH

def main():
 start=time.perf_counter();e=Engine(H/'inventory_runtime');d=e.d
 e.restore(70); e.inputs(75,BASE_P,BASE_Q); r,a=e.measure(75)
 save(H/'ORIGINAL_B0_SLOT75.json',r)
 graph=collections.defaultdict(set);attached=collections.defaultdict(list);edge=[];excl=set()
 for name in d.Circuit.AllElementNames():
  d.Circuit.SetActiveElement(name)
  if not d.CktElement.Enabled():continue
  buses=[b.split('.')[0].lower() for b in d.CktElement.BusNames()]
  for b in buses:attached[b].append(name)
  if name.lower().startswith(('line.','transformer.')):
   for b in buses[1:]:graph[buses[0]].add(b);graph[b].add(buses[0])
   edge.append(dict(name=name,buses=buses,connections=d.CktElement.BusNames()))
  if name.lower().startswith('vsource.'):excl.update(buses)
 for name in d.RegControls.AllNames():
  d.RegControls.Name(name);d.Transformers.Name(d.RegControls.Transformer());excl.update(b.split('.')[0].lower() for b in d.CktElement.BusNames())
 source=list(excl);seen=set(source);q=collections.deque(source)
 while q:
  for b in graph[q.popleft()]:
   if b not in seen:seen.add(b);q.append(b)
 service={x['bus_connection'].split('.')[0].lower() for x in e.loads}
 records=[]
 for b in d.Circuit.AllBusNames():
  d.Circuit.SetActiveBus(b);nodes=d.Bus.Nodes();kv=d.Bus.kVBase()
  reasons=[]
  if b.startswith('pcc8500'):reasons.append('existing additive PCC; not native bus')
  if b in excl or 'reg' in b or '_int' in b or b.startswith('_') or 'hvmv' in b or '_cap' in b:reasons.append('source/regulator/capacitor/internal')
  if b not in seen:reasons.append('disconnected')
  if not nodes or kv<=0:reasons.append('invalid phase/base voltage')
  txinternal=any(x.lower().startswith('transformer.') for x in attached[b]) and kv<1 and b not in service
  if txinternal:reasons.append('transformer-secondary non-service node')
  mv3=set(nodes)=={1,2,3} and abs(kv*np.sqrt(3)-12.47)<.1
  admissible=not reasons
  records.append(dict(bus=b,nodes=nodes,kV_LN=kv,x=d.Bus.X(),y=d.Bus.Y(),native_service=b in service,AIDC_candidate=admissible and mv3,MESS_original_interface_candidate=admissible and mv3,MESS_phase_adapted_candidate=admissible and (mv3 or b in service),exclusion='; '.join(reasons)))
 save(H/'NATIVE_BUS_INVENTORY.json',records);table(H/'NATIVE_BUS_INVENTORY.csv',records);save(H/'NATIVE_EDGES.json',edge)
 line=np.asarray(a[1]);top=np.argsort(line)[::-1];rows=[];used=set()
 for i in top:
  label=e.ax['line_label'][i];name=label.split('|')[0]
  if name in used:continue
  used.add(name);d.Circuit.SetActiveElement(name)
  rows.append(dict(line=name,loading=float(line[i]),witness=label,buses=d.CktElement.BusNames()))
  if len(rows)==80:break
 save(H/'HIGH_LOADING_LINES.json',rows)
 save(H/'SOURCE_MANIFEST.json',[dict(path=str(p),sha256=original.sha(p)) for p in original.files()+[AUTH/'FLEET_AUTHORITY.json',AUTH/'PCC_OVERLAY_INVENTORY.json']])
 print(json.dumps(dict(native_buses=sum(not x['bus'].startswith('pcc8500') for x in records),AIDC_candidates=sum(x['AIDC_candidate'] for x in records),MESS_original=sum(x['MESS_original_interface_candidate'] for x in records),MESS_phase_adapted=sum(x['MESS_phase_adapted_candidate'] for x in records),high_loading=rows[:20],seconds=time.perf_counter()-start),default=lambda x:x.item()),flush=True)
 e.close()
if __name__=='__main__':main()
