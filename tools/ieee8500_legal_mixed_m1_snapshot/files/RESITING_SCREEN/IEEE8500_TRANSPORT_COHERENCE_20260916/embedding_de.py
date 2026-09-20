from search import *
from scipy.optimize import differential_evolution

def main():
 start=time.perf_counter();pp=read(H/'LEGAL_PORT_POOL.json');ids=[r['bus'] for r in pp];G=np.array([[r['x'],r['y']] for r in pp]);aid=np.array([r['AIDC_candidate'] for r in pp]);ta=cKDTree(G[aid]);ts=cKDTree(G);initial=[LABELS.index(x) for x in IDS];rows=read(H/'SPATIAL_FEASIBLE_CANDIDATES.json');seen={tuple(r['layout']['all_identity_bus_mapping'].values()) for r in rows}
 center=G[aid].mean(0);lo=G[aid].min(0);hi=G[aid].max(0);span=hi-lo;critical=['sx3101194c','sx2767340c','sx3027670b']
 def transform(z):
  angle,ls,ratio,fx,fy=z;a=np.deg2rad(angle);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]]);A=np.exp(ls)*np.diag([1.,ratio])@rot;b=lo+span*[fx,fy];return A,b
 def obj(z):
  A,b=transform(z);target=T@A+b;den=TRMS*np.sqrt(np.linalg.det(A));di=np.r_[ta.query(target[:12])[0],ts.query(target[12:])[0]]/den
  return di.max()+.2*np.sqrt(np.mean(di**2))
 trials=[]
 for seed in range(6):
  ans=differential_evolution(obj,[(0,360),(np.log(80),np.log(1000)),(.65,1.5),(.05,.95),(.05,.95)],seed=20260916+seed,popsize=25,maxiter=450,tol=1e-7,polish=True,workers=1)
  z=ans.x;A,b=transform(z);target=T@A+b;radius=P0['local_assignment_radius_RMS']*TRMS*np.sqrt(np.linalg.det(A));cost=cdist(target,G,'sqeuclidean');cost[:12,~aid]=1e30;ii,jj=linear_sum_assignment(cost);d=np.sqrt(cost[ii,jj]);buses=[ids[j] for j in jj];m=metrics(buses)
  trials.append(dict(seed=seed,objective=ans.fun,max_local_normalized=float(d.max()/(radius/.2)),metrics=m,transform=dict(matrix=A.tolist(),translation=b.tolist()),buses=buses))
  if d.max()<=radius and m['coherence_pass'] and tuple(buses) not in seen:
   seen.add(tuple(buses));name=f'COH_{len(rows):03}';initialb=[buses[i] for i in initial];layout=dict(name=name,aidc=buses[:12],mess=[pp[jj[i]] for i in initial],station_ids=IDS,all_STA_mapping={LABELS[i]:pp[jj[i]] for i in range(12,24)},all_identity_bus_mapping=dict(zip(LABELS,buses)),s_DC=1.,s_MESS=1.,transport_identity_permutation=False,phase_interface_adaptation_authorized=True)
   entry=dict(name=name,method=f'geometry_only_DE_seed{seed}',transform=dict(matrix=A.tolist(),translation=b.tolist(),fixed_before_local_assignment=True),bounded_radius_native=radius,max_assignment_distance=float(d.max()),critical_initial_station_coverage=sum(x in initialb for x in critical),metrics=m,layout=layout);rows.append(entry)
   save(H/'candidates'/name/'LAYOUT.json',layout);save(H/'candidates'/name/'SPATIAL.json',{k:v for k,v in entry.items() if k!='layout'})
  save(H/'CONTINUOUS_EMBEDDING_TRIALS.json',trials);save(H/'SPATIAL_FEASIBLE_CANDIDATES.json',rows)
  print(json.dumps(dict(seed=seed,obj=ans.fun,max_local=trials[-1]['max_local_normalized'],P0=m['coherence_pass'],feasible=len(rows),seconds=time.perf_counter()-start)),flush=True)
 save(H/'SPATIAL_AC_SHORTLIST.json',rows[:24])
if __name__=='__main__':main()
