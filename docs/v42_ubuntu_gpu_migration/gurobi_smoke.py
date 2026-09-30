"""Same deterministic LP on CPU/GPU PDHG, with presolve disabled to exercise PDHG."""
import json,sys,time,re,importlib.metadata as md
from pathlib import Path
import numpy as np,gurobipy as gp
out=Path(sys.argv[1]);label=sys.argv[2];gpu=int(sys.argv[3]);out.mkdir(parents=True,exist_ok=True)
log=out/('GUROBI_GPU_SMOKE_'+label+'.log')
if log.exists():raise RuntimeError('DO_NOT_OVERWRITE:'+str(log))
rng=np.random.default_rng(20260930);a=rng.uniform(.05,1,(100,200));b=rng.uniform(3,6,100);c=rng.uniform(.5,2,200)
m=gp.Model('migration_pdhg_smoke');x=m.addMVar(200,lb=0,ub=1);m.addMConstr(a,x,'>',b);m.setObjective(c@x)
for k,v in dict(Method=6,PDHGGPU=gpu,Presolve=0,Threads=1,Seed=20260929,TimeLimit=60,LogFile=str(log)).items():m.setParam(k,v)
start=time.perf_counter();m.optimize();wall=time.perf_counter()-start
text=log.read_text();xx=x.X if m.SolCount else None
vio=float(max(0,np.max(b-a@xx),np.max(-xx),np.max(xx-1))) if xx is not None else None
result=dict(label=label,gpu_requested=gpu,status=m.Status,objective=m.ObjVal if m.SolCount else None,feasibility_max_violation=vio,wall_seconds=wall,solver_runtime=m.Runtime,iterations=m.IterCount,PDHG_iterations=getattr(m,'PDHGIterCount',None),gurobipy=md.version('gurobipy'),gurobi=list(gp.gurobi.version()),GPU_model_log='GPU model:' in text,GPU_PDHG_log='Start PDHG on GPU' in text,CPU_fallback=bool(re.search('running on CPU instead',text)),settings=dict(Method=6,PDHGGPU=gpu,Presolve=0,Threads=1,Seed=20260929,TimeLimit=60),fingerprint=hex(m.Fingerprint))
(out/('SMOKE_'+label+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));m.dispose()
