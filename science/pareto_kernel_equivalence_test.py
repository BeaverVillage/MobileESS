import numpy as np,pandas as pd,time,json
from collections import defaultdict
H=54

def legacy(route_df,z,conn_delay):
 moves={};counts=[]
 for h in range(H):
  keep=[]
  for od in range(552):
   rr=route_df[route_df["od_index"].astype(int)==od].sort_values("rank")
   cand=[]
   for x in rr.itertuples(index=False):
    slot=int(x.slot);travel=int(z["profile_safe_horizon_steps"][h,slot]);D=travel+conn_delay;e=float(z["safe_energy_kWh"][h,slot])
    if h+D<=H:cand.append((slot,D,e,int(x.rank),str(x.source_service_id),str(x.destination_service_id)))
   for a in cand:
    dominated=False
    for b in cand:
     if a==b:continue
     if b[1]<=a[1] and b[2]<=a[2]+1e-9 and (b[1]<a[1] or b[2]<a[2]-1e-9 or (b[1]==a[1] and abs(b[2]-a[2])<=1e-9 and b[3]<a[3])):
      dominated=True;break
    if not dominated:keep.append(a)
  for slot,D,e,rank,s,d in keep:
   moves[(h,slot)]={"h":h,"slot":slot,"D":D,"travel_steps":D-conn_delay,"energy_kWh":e,"rank":rank,"source":s,"dest":d,"safe_eta_sec":float(z["route_safe_eta_sec"][h,slot]),"template_id":int(z["e4b_template_id"][h,slot]),"q50_energy_kWh":float(z["energy_quantiles_kWh"][h,slot,1])}
  counts.append(len(keep))
 return moves,counts

def fast(route_df,z,conn_delay):
 cols=route_df[["od_index","slot","rank","source_service_id","destination_service_id"]].copy();cols["od_index"]=cols["od_index"].astype(np.int64);cols["slot"]=cols["slot"].astype(np.int64);cols["rank"]=cols["rank"].astype(np.int64);cols=cols.sort_values(["od_index","rank"],kind="mergesort")
 groups=[[] for _ in range(552)]
 for x in cols.itertuples(index=False):groups[int(x.od_index)].append((int(x.slot),int(x.rank),str(x.source_service_id),str(x.destination_service_id)))
 prof=np.asarray(z["profile_safe_horizon_steps"]);safeE=np.asarray(z["safe_energy_kWh"]);eta=np.asarray(z["route_safe_eta_sec"]);tmpl=np.asarray(z["e4b_template_id"]);eq=np.asarray(z["energy_quantiles_kWh"])
 moves={};counts=[]
 for h in range(H):
  keep=[]
  for od in range(552):
   cand=[]
   for slot,rank,s,d in groups[od]:
    travel=int(prof[h,slot]);D=travel+conn_delay;e=float(safeE[h,slot])
    if h+D<=H:cand.append((slot,D,e,rank,s,d))
   for a in cand:
    dominated=False
    for b in cand:
     if a==b:continue
     if b[1]<=a[1] and b[2]<=a[2]+1e-9 and (b[1]<a[1] or b[2]<a[2]-1e-9 or (b[1]==a[1] and abs(b[2]-a[2])<=1e-9 and b[3]<a[3])):
      dominated=True;break
    if not dominated:keep.append(a)
  for slot,D,e,rank,s,d in keep:
   moves[(h,slot)]={"h":h,"slot":slot,"D":D,"travel_steps":D-conn_delay,"energy_kWh":e,"rank":rank,"source":s,"dest":d,"safe_eta_sec":float(eta[h,slot]),"template_id":int(tmpl[h,slot]),"q50_energy_kWh":float(eq[h,slot,1])}
  counts.append(len(keep))
 return moves,counts

rng=np.random.default_rng(2044);rows=[];slot=0
for od in range(552):
 for rank in (1,2,3):rows.append((od,slot,rank,f"S{od%24:02d}",f"D{(od+rank)%24:02d}"));slot+=1
df=pd.DataFrame(rows,columns=["od_index","slot","rank","source_service_id","destination_service_id"])
z={"profile_safe_horizon_steps":rng.integers(1,16,size=(H,slot),dtype=np.int16),"safe_energy_kWh":rng.uniform(1,100,size=(H,slot)),"route_safe_eta_sec":rng.uniform(60,5000,size=(H,slot)),"e4b_template_id":rng.integers(0,1000,size=(H,slot),dtype=np.int32),"energy_quantiles_kWh":rng.uniform(1,100,size=(H,slot,3))}
t0=time.perf_counter();a,ca=legacy(df,z,2);t1=time.perf_counter();b,cb=fast(df,z,2);t2=time.perf_counter()
assert ca==cb and list(a.keys())==list(b.keys())
for k in a: assert a[k]==b[k],(k,a[k],b[k])
print(json.dumps({"PASS":True,"moves":len(a),"legacy_s":t1-t0,"fast_s":t2-t1,"speedup":(t1-t0)/max(t2-t1,1e-9)}))
