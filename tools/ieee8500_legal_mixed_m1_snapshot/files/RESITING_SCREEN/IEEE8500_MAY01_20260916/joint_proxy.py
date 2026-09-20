from optimize import *
import inspect,gzip,gc
FAST=ROOT/'independent_screening/IEEE8500_FAST_SCALE_20260916'
import proxy as original_proxy
gp=original_proxy.gp
GRB=gp.GRB
CTX={}

def grid(model,dc,controls,bounds,folder,rho=None):
 layout=CTX['layout'];coeff=CTX['coeff'];joint=CTX['policy']=='B3'
 if rho is None:rho=model.addVar(lb=0,ub=1,name='rho_proxy')
 rho.UB=1.;rho.LB=0.;plist={};qlist={}
 for t in SLOTS:
  lo=np.r_[bounds[t][0][:12],np.zeros(6),np.full(6,-400. if joint else 0),np.zeros(36)]
  hi=np.r_[bounds[t][1][:12],np.full(6,300. if joint else 0),np.full(6,400. if joint else 0),np.zeros(36)]
  if joint:
   for j in range(6):
    p=plist[t,j]=model.addVar(lb=0,ub=300,name=f'RES_P[{t},{j}]');q=qlist[t,j]=model.addVar(lb=-400,ub=400,name=f'RES_Q[{t},{j}]')
    controls[t][12+j]=gp.LinExpr(p);controls[t][18+j]=gp.LinExpr(q)
    for k in range(16):model.addConstr(np.cos(2*np.pi*k/16)*p+np.sin(2*np.pi*k/16)*q<=400*np.cos(np.pi/16))
  pp=model.addMVar(60,lb=lo,ub=hi,name=f'physical_ports_{t}')
  for j in range(60):model.addConstr(pp[j]==controls[t][j])
  xx=gp.MVar.fromlist(pp[:24].tolist()+[rho]);z=coeff[t]
  for k,(kind,w,b,lim,isline) in enumerate(linear_rows(z)):
   mx=b+np.maximum(w,0)@hi[:24]+np.minimum(w,0)@lo[:24];keep=mx>(.75 if isline else lim)-1e-9
   if not keep.any():continue
   mat=sp.hstack([sp.csr_matrix(w[keep]),sp.csr_matrix(-np.ones((sum(keep),1)) if isline else np.zeros((sum(keep),1)))],format='csr')
   model.addMConstr(mat,xx,'<',lim-b[keep],name=f'RESITE_{t}_{kind}_{k}')
 if joint:
  for j in range(6):model.addConstr(gp.quicksum(plist[t,j] for t in SLOTS)<=(760-440)*.95/.25)
 model.update();return rho

def capture(model,folder):
 mm={}
 if CTX['policy']=='B3':
  for t in SLOTS:
   for j,sid in enumerate(IDS):mm[t,sid]=(model.getVarByName(f'RES_P[{t},{j}]').X,model.getVarByName(f'RES_Q[{t},{j}]').X)
  mm=energy_recovery(mm)
 CTX['mess']=mm;save(Path(folder)/'MESS.json',[dict(slot=t,station=sid,P=pq[0],Q=pq[1]) for (t,sid),pq in mm.items()]);save(Path(folder)/'STORAGE_PHYSICS.json',physics(mm))

def wrapped_replay(p,folder):
 result=replay(CTX['layout'],p,folder,mess=CTX.get('mess'),slots=SLOTS)
 if CTX['policy']=='B3':
  rec=replay(CTX['layout'],p,Path(folder).parent/'RECOVERY_AC',mess=CTX['mess'],slots=list(range(34,54)));result['recovery_AC']=rec;result['physical_pass'] &= rec['physical_pass'] and physics(CTX['mess'])['status']=='PASS'
 return result

def selected_options():
 p=original_proxy;selection=read(FAST/'B1_PROXY_DOMAIN.json');selected=selection['groups'];uids={u for i in selected for u in p.COHORTS[i]['members']};opts={}
 manifest=read(p.REPO/'frozen_artifacts/v41r4_may/audit/2025-05-01/domain/combined/V41R1_FULL_CANDIDATE_MANIFEST.json');path=Path(manifest['candidate_artifact']['path']);assert original.sha(path)==manifest['candidate_artifact']['sha256']
 with gzip.open(path,'rb') as f:
  for raw in f:
   row=json.loads(raw)
   if row['job_id'] in uids:opts[row['job_id']]=tuple(p.Option(*o) for o in row['options'])
 return selected,opts

def main():
 global SLOTS
 import optimize as op
 if '--expanded' in sys.argv:SLOTS=list(range(68,86));op.SLOTS=SLOTS;original_proxy.SLOTS=SLOTS
 name=sys.argv[1];policy=sys.argv[2];layout=read(H/'placements'/name/'LAYOUT.json');home=H/'placements'/name/policy;home.mkdir(exist_ok=True)
 anchor=BASE_P.copy();mm=None
 if policy=='B3':
  bpath=H/'placements'/name/'B1_R2/B_DC_1/POWER.npz'
  if not bpath.exists():bpath=H/'placements'/name/'B1/B_DC_1/POWER.npz'
  with np.load(bpath) as z:anchor=z['pcc'].copy()
  capname='capability_expanded' if '--expanded' in sys.argv else 'capability'
  c=read(H/'placements'/name/capname/'RESULT.json');mm={(r['slot'],r['station']):(r['P'],r['Q']) for r in read(H/'placements'/name/capname/f'MESS_{c["iteration"]}.json')}
 reuse=H/'placements'/name/'B1/coefficients'
 coeff=load_coeff(reuse) if policy=='B1_R2' and (reuse/'slot_79.npz').exists() else coefficients(layout,anchor,home/'coefficients',mm,include_aidc=True)
 CTX.update(layout=layout,policy=policy,coeff=coeff)
 p=original_proxy;p.H=home;p.grid=grid;p.replay=wrapped_replay;p.capture=capture;p.FAST=FAST
 baseline=read(H/'placements'/name/'B0/SUMMARY.json');save(home/'A_DC_1/SUMMARY.json',baseline)
 source=inspect.getsource(p.b1).replace("modelpath=H/'ORIGINAL_PRIMARY_MODEL.mps'","modelpath=FAST/'ORIGINAL_PRIMARY_MODEL.mps'")
 source=source.replace('model=gp.read(modelpath.name);','os.chdir(modelpath.parent);model=gp.read(modelpath.name);os.chdir(H);')
 source=source.replace("model.remove([r for r in model.getConstrs()", "\n with np.load(FAST/'B_DC_1/PROXY_ASSIGNMENT.npz') as zz:\n  assert names==zz['names'][:len(names)].tolist();seed=zz['values'][:len(names)].copy()\n model.remove([r for r in model.getConstrs()")
 source=source.replace('model.dispose();del vs,by,model;gc.collect()','capture(model,folder);model.dispose();del vs,by,model;gc.collect()')
 exec(source,p.__dict__);sel,opts=selected_options();save(home/'DOMAIN.json',dict(selected_groups=sel,restriction='Same 24 frozen critical-window cohorts as prior restricted B1; all their original legal options; other jobs fixed; full original 96-slot resource/WAN/job/PWL constraints and P1-P5 hierarchy retained; no B0>B1>B2>B3 ordering constraints'))
 p.b1(1.,sel,opts)
if __name__=='__main__':main()
