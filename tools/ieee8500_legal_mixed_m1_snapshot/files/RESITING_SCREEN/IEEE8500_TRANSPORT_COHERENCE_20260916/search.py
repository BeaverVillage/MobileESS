from spatial import *
from itertools import permutations
from scipy.spatial import cKDTree

def ports():
 # Native service conductor with largest native P, not a traffic identity choice.
 e=Engine(H/'port_inventory_runtime');pwr={}
 for r in e.loads:
  b=r['bus_connection'].split('.')[0];node=int(r['bus_connection'].split('.')[1]);pwr[b,node]=pwr.get((b,node),0)+r['base_kw']
 e.close();out=[]
 for r in INV:
  if not r['MESS_phase_adapted_candidate']:continue
  if any(x in r['bus'] for x in ['hvmv','_cap','_int']) or r['bus'].startswith('_'):continue
  nodes=[1,2,3] if r['AIDC_candidate'] else [max(r['nodes'],key=lambda n:pwr.get((r['bus'],n),0))]
  out.append(dict(bus=r['bus'],key=r['bus']+'.'+'.'.join(map(str,nodes)),nodes=nodes,phases=len(nodes),kv=r['kV_LN']*(np.sqrt(3) if len(nodes)==3 else 1),AIDC_candidate=r['AIDC_candidate'],x=r['x'],y=r['y']))
 save(H/'LEGAL_PORT_POOL.json',out);return out

def main():
 start=time.perf_counter();pp=ports();ids=[r['bus'] for r in pp];G=np.array([[r['x'],r['y']] for r in pp]);aid=np.array([r['AIDC_candidate'] for r in pp]);initial=[LABELS.index(x) for x in IDS]
 critical=['sx3101194c','sx2767340c','sx3027670b'];ci=[ids.index(b) for b in critical];transforms=[]
 for n in [2,3]:
  for ti in permutations(initial,n):
   tf=fit(T[list(ti)],G[ci[:n]])
   if tf['determinant']<=0:continue
   A=np.array(tf['matrix']);b=np.array(tf['translation']);transforms.append((f'anchor{n}_'+','.join(LABELS[i] for i in ti),A,b,dict(zip(ti,ci[:n]))))
   if n==2:
    direction=G[ci[1]]-G[ci[0]];direction/=np.linalg.norm(direction);normal=np.array([-direction[1],direction[0]])
    for ratio in [.65,.8,1.2,1.5]:
     aa=A@(np.outer(direction,direction)+ratio*np.outer(normal,normal));bb=G[ci[0]]-T[ti[0]]@aa;transforms.append((f'anchor2_affine_{ratio}_'+','.join(LABELS[i] for i in ti),aa,bb,dict(zip(ti,ci[:n]))))
   else:
    af=fit(T[list(ti)],G[ci[:n]],True)
    if af['determinant']>0 and af['condition']<3:transforms.append(('anchor3_affine_'+','.join(LABELS[i] for i in ti),np.array(af['matrix']),np.array(af['translation']),dict(zip(ti,ci[:n]))))
 # Shape-only baselines: one common transform for all 24, no separate STA fit.
 old=read(OLD/'placements/legal_mixed_M1/LAYOUT.json');basefit=fit(T[:12],xy(old['aidc']));A0=np.array(basefit['matrix']);b0=np.array(basefit['translation'])
 for deg in range(-30,31,10):
  a=np.deg2rad(deg);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
  for scale in [.6,.8,1.,1.2]:
   A=A0@rot*scale
   for dx in [-.1,0,.1]:
    for dy in [-.1,0,.1]:transforms.append((f'global_{deg}_{scale}_{dx}_{dy}',A,b0+np.array([dx,dy])*TRMS*np.sqrt(np.linalg.det(A0)),{}))
 # Broader deterministic embedding search; identity order stays fixed.
 low=G.min(0);span=np.ptp(G,axis=0)
 for deg in range(0,360,10):
  a=np.deg2rad(deg);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
  for scale in range(100,901,100):
   for ratio in [.75,1.]:
    A=scale*np.diag([1.,ratio])@rot
    for fx in np.linspace(.15,.85,9):
     for fy in np.linspace(.2,.8,7):transforms.append((f'wide_{deg}_{scale}_{ratio}_{fx:.3f}_{fy:.3f}',A,low+span*[fx,fy],{}))
 ta=cKDTree(G[aid]);ts=cKDTree(G)
 seen=set();retained=[]
 for method,A,b,forced in transforms:
  target=T@A+b;radius=P0['local_assignment_radius_RMS']*TRMS*np.sqrt(np.linalg.det(A))
  if ta.query(target[:12])[0].max()>radius or ts.query(target[12:])[0].max()>radius:continue
  cost=cdist(target,G,'sqeuclidean');cost[:12,~aid]=1e30
  cost[cost>radius**2]=1e30
  for i,j in forced.items():
   if cost[i,j]>=1e29:break
   val=cost[i,j];cost[i,:]=1e30;cost[:,j]=1e30;cost[i,j]=val
  else:
   ii,jj=linear_sum_assignment(cost)
   if cost[ii,jj].max()>=1e29:continue
   key=tuple(jj.tolist())
   if key in seen:continue
   seen.add(key);buses=[ids[j] for j in jj];m=metrics(buses)
   if not m['coherence_pass']:continue
   initialb=[buses[i] for i in initial];coverage=sum(x in initialb for x in critical)
   name=f'COH_{len(retained):03}';layout=dict(name=name,aidc=buses[:12],mess=[pp[jj[i]] for i in initial],station_ids=IDS,all_STA_mapping={LABELS[i]:pp[jj[i]] for i in range(12,24)},all_identity_bus_mapping=dict(zip(LABELS,buses)),s_DC=1.,s_MESS=1.,transport_identity_permutation=False,phase_interface_adaptation_authorized=True)
   entry=dict(name=name,method=method,transform=dict(matrix=A.tolist(),translation=b.tolist(),fixed_before_local_assignment=True),bounded_radius_native=radius,max_assignment_distance=float(np.sqrt(cost[ii,jj].max())),critical_initial_station_coverage=coverage,metrics=m,layout=layout)
   retained.append(entry)
 save(H/'SPATIAL_FEASIBLE_CANDIDATES.json',retained)
 ranked=sorted(retained,key=lambda x:(-x['critical_initial_station_coverage'],x['metrics']['pairwise_distortion'],-x['metrics']['STA_AIDC_top2']))
 save(H/'SPATIAL_SEARCH_SUMMARY.json',dict(transforms=len(transforms),unique_assignments=len(seen),P0_pass=len(retained),runtime_seconds=time.perf_counter()-start,critical_coverage_counts={str(k):sum(r['critical_initial_station_coverage']==k for r in retained) for k in range(4)},identity_permutation=False,traffic_coordinates_changed=False,road_metrics_used_as_electrical_distances=False))
 # Deterministic, geometry-first shortlist with coverage diversity for AC gates.
 shortlist=[]
 for cov in [3,2,1,0]:shortlist.extend([r for r in ranked if r['critical_initial_station_coverage']==cov][:18 if cov>=2 else 6])
 save(H/'SPATIAL_AC_SHORTLIST.json',shortlist)
 for r in shortlist:save(H/'candidates'/r['name']/'LAYOUT.json',r['layout']);save(H/'candidates'/r['name']/'SPATIAL.json',{k:v for k,v in r.items() if k!='layout'})
 print(json.dumps(read(H/'SPATIAL_SEARCH_SUMMARY.json')),flush=True)
 print([(r['name'],r['critical_initial_station_coverage'],r['metrics']['pairwise_distortion'],r['method']) for r in shortlist[:10]],flush=True)
if __name__=='__main__':main()
