from engine import *
import math
def main():
 layout=read(H/'placements/legal_mixed_M1/LAYOUT.json');e=ResiteEngine(layout,H/'bound_runtime');d=e.d;e.restore(70);e.inputs(75,BASE_P,BASE_Q);e.measure(75)
 controlled={r['bus'] for r in layout['mess']}|set(layout['aidc']);bybus=collections.defaultdict(list)
 for r in e.loads:bybus[r['bus_connection'].split('.')[0]].append(r)
 edges=read(H/'NATIVE_EDGES.json');attachments=collections.defaultdict(set)
 for ed in edges:
  for b in ed['buses']:attachments[b].add(ed['name'])
 out=[]
 assert e.mpv[75]==0
 for ed in edges:
  if not ed['name'].lower().startswith('line.tpx'):continue
  leaf=ed['buses'][1]
  if leaf in controlled or leaf not in bybus or len(attachments[leaf])!=1:continue
  d.Circuit.SetActiveElement(ed['name']);n=d.CktElement.NumConductors()
  if n!=2:continue
  rating=d.CktElement.NormalAmps();raw=np.asarray(d.CktElement.YPrim()).reshape(-1,2);Y=(raw[:,0]+1j*raw[:,1]).reshape(4,4);Z=-np.linalg.inv(Y[:2,2:]);Ysh=Y[:2,:2]+Y[:2,2:]
  buses=d.CktElement.BusNames();nodes=d.CktElement.NodeOrder()[2:4];S=np.zeros(2,dtype=complex);meta={}
  for r in bybus[leaf]:
   assert r['model']==1 and r['phases']==1
   d.Loads.Name(r['load']);node=int(r['bus_connection'].split('.')[1]);j=nodes.index(node);S[j]+=1000*complex(d.Loads.kW(),d.Loads.kvar());meta[j]=r
  d.Circuit.SetActiveBus(leaf);vhi=d.Bus.kVBase()*1050;vlo=d.Bus.kVBase()*950;d.Circuit.SetActiveBus(buses[0].split('.')[0]);vs=d.Bus.kVBase()*1050;charging=np.abs(Ysh)@np.full(2,vhi)
  for j in range(2):
   k=1-j
   if j not in meta or k not in meta or abs(S[j])==0:continue
   assert vlo>meta[j]['base_kv']*1000*meta[j]['Vminpu']
   factor=max(1.,(vhi/(meta[k]['base_kv']*1000*meta[k]['Vmaxpu']))**2);iother=abs(S[k])*factor/vlo;delta=abs(Z[j,k])*iother+np.abs(Z[j])@charging
   alpha=Z[j,j].real*S[j].real+Z[j,j].imag*S[j].imag;beta=abs(Z[j,j])**2*abs(S[j])**2;B=vs+delta;disc=(B*B-2*alpha)**2-4*beta
   if disc<=0:continue
   vr=min(vhi,math.sqrt((B*B-2*alpha+math.sqrt(disc))/2));bound=abs(S[j])/vr/rating
   out.append(dict(line=ed['name'],leaf=leaf,node=nodes[j],slot=75,bound=float(bound),P_kw=S[j].real/1000,Q_kvar=S[j].imag/1000,rating_A=rating,receiving_voltage_upper_V=vr,controlled_PCC_present=False))
 out.sort(key=lambda r:r['bound'],reverse=True);save(H/'RESITED_NECESSARY_AC_BOUND.json',dict(status='NECESSARY LOWER BOUND, not attained optimum',scope='fixed tested M1 six-station infrastructure; arbitrary permitted AIDC schedules, MESS dispatch/route among those six stations',strongest=out[0],top20=out[:20],proof='KCL at unserved leaf, native constant-PQ load, original series impedance and hard 1.05 pu voltage ceiling; triangle bound for the other conductor and charging admittance. Adapted from separately verified original native-leaf certificate.'))
 e.close();print(out[:3])
if __name__=='__main__':main()
