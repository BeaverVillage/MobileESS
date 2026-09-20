from engine import *
import scipy.sparse as sp
from scipy.optimize import linprog

def coefficients(layout,p,folder,mess=None,include_aidc=False):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);e=ResiteEngine(layout,folder/'runtime');d=e.d;prev=None;result={}
 for t in SLOTS:
  if prev is None:e.restore(t)
  e.inputs(t,p,p*(BASE_Q/BASE_P),mess);r,a=e.measure(t);v,f=arrays(e);state=s.control_state(d,t,e.rule['source_pu'],e.rule['Vreg_V']);Jv=[];Jf=[]
  x=np.r_[p[t],[((mess or {}).get((t,sid),(0,0)))[0] for sid in IDS],[((mess or {}).get((t,sid),(0,0)))[1] for sid in IDS]]
  for j in range(24):
   if j<12 and not include_aidc:Jv.append(np.zeros_like(v));Jf.append(np.zeros_like(f));continue
   for rr in state['regulators']:d.RegControls.Name(rr['name']);d.RegControls.TapNumber(rr['tap_number'])
   for rr in state['capacitors']:d.Capacitors.Name(rr['name']);d.Capacitors.States(rr['step_states'])
   d.CtrlQueue.ClearQueue();step=1. if j<12 or layout['mess'][(j-12)%6]['phases']==3 else .1
   if j<12:
    pp=p.copy();pp[t,j]+=step;e.inputs(t,pp,pp*(BASE_Q/BASE_P),mess)
   else:
    mm=dict(mess or {});sid=IDS[(j-12)%6];pq=list(mm.get((t,sid),(0,0)));pq[int(j>=18)]+=step;mm[t,sid]=pq;e.inputs(t,p,p*(BASE_Q/BASE_P),mm)
   rr,_=e.measure(t);assert rr['converged'] and d.Solution.ControlActionsDone();vv,ff=arrays(e);Jv.append((vv-v)/step);Jf.append((ff-f)/step)
  for rr in state['regulators']:d.RegControls.Name(rr['name']);d.RegControls.TapNumber(rr['tap_number'])
  for rr in state['capacitors']:d.Capacitors.Name(rr['name']);d.Capacitors.States(rr['step_states'])
  e.inputs(t,p,p*(BASE_Q/BASE_P),mess);e.measure(t);prev=t
  z=dict(x=x,v=v,f=f,V=np.array(Jv).T,F=np.array(Jf).T,nl=len(e.ax['line_pos']),line_labels=np.array(e.ax['line_label']),voltage_labels=e.nodes,tx_labels=np.array(e.ax['tx_label']),kva_labels=np.array(e.ax['kva_label']))
  np.savez_compressed(folder/f'slot_{t:02}.npz',**z);result[t]=z
 e.close();return result

def load_coeff(folder):
 return {t:dict(np.load(Path(folder)/f'slot_{t:02}.npz')) for t in SLOTS}

def linear_rows(z):
 # Complex-flow supporting directions, re-anchored by each exact AC iterate.
 yield 'vhi',z['V'],z['v']-z['V']@z['x'],1.0498,False
 yield 'vlo',-z['V'],-z['v']+z['V']@z['x'],-.9502,False
 nl=int(z['nl']);f=z['f'];J=z['F'];angles=np.angle(f)
 for k in range(64):
  rot=np.exp(-1j*(angles+2*np.pi*k/64));w=(rot[:,None]*J).real;b=(rot*f).real-w@z['x']
  yield 'line',w[:nl],b[:nl],0.,True
  yield 'tx',w[nl:],b[nl:],.9998,False

def limits(layout,p):
 lo=np.r_[p,np.zeros(6),np.full(6,-400.)];hi=np.r_[p,np.full(6,300.),np.full(6,400.)]
 return lo,hi

def solve_lp(layout,p,coeff):
 nt=len(SLOTS);n=12*nt+1;rows=[];rhs=[];bounds=[]
 for ti,t in enumerate(SLOTS):
  z=coeff[t];lo,hi=limits(layout,p[t])
  if globals().get('TRUST_REGION',False):
   step=np.array([40. if c['phases']==3 else 2. for c in layout['mess']]*2)
   lo[12:]=np.maximum(lo[12:],z['x'][12:]-step);hi[12:]=np.minimum(hi[12:],z['x'][12:]+step)
  bounds.extend(zip(lo[12:],hi[12:]))
  for kind,w,b,lim,isline in linear_rows(z):
   ww=w[:,12:];bb=b+w[:,:12]@p[t];mx=bb+np.maximum(ww,0)@hi[12:]+np.minimum(ww,0)@lo[12:]
   keep=mx>(.75 if isline else lim)-1e-9
   if not keep.any():continue
   left=sp.csr_matrix((sum(keep),ti*12));right=sp.csr_matrix((sum(keep),(nt-1-ti)*12));last=-np.ones((sum(keep),1)) if isline else np.zeros((sum(keep),1))
   rows.append(sp.hstack([left,sp.csr_matrix(ww[keep]),right,sp.csr_matrix(last)]));rhs.extend((lim-bb[keep]).tolist())
  for j in range(6):
   for k in range(16):
    a=np.zeros(n);a[ti*12+j]=np.cos(2*np.pi*k/16);a[ti*12+6+j]=np.sin(2*np.pi*k/16);rows.append(sp.csr_matrix(a[None,:]));rhs.append(400*np.cos(np.pi/16))
 for j in range(6):
  a=np.zeros(n);a[j:n-1:12]=1;rows.append(sp.csr_matrix(a[None,:]));rhs.append((760-440)*.95/.25)
 c=np.zeros(n);c[-1]=1;bounds.append((.75,1.))
 matrix=sp.vstack(rows,format='csr');rhs=np.array(rhs)
 ans=linprog(c,A_ub=matrix,b_ub=rhs,bounds=bounds,method='highs',options={'dual_feasibility_tolerance':1e-8,'primal_feasibility_tolerance':1e-8})
 if not ans.success:raise RuntimeError(ans.message)
 # Among equal-rho solutions prefer low throughput/Q; avoid gratuitous reverse
 # power on a low-voltage service and needless terminal recharge.
 optimum=float(ans.fun);bounds[-1]=(.75,max(optimum+1e-6,globals().get('TARGET_RHO',.889)));nq=6*nt;c2=np.zeros(n+nq)
 extra=[]
 for ti in range(nt):
  for j in range(6):
   c2[ti*12+j]=1.;c2[n+ti*6+j]=.2
   for sign in (-1,1):
    rr=np.zeros(n+nq);rr[ti*12+6+j]=sign;rr[n+ti*6+j]=-1;extra.append(rr)
 ans=linprog(c2,A_ub=sp.vstack([sp.hstack([matrix,sp.csr_matrix((matrix.shape[0],nq))]),sp.csr_matrix(np.array(extra))],format='csr'),b_ub=np.r_[rhs,np.zeros(2*nq)],bounds=bounds+[(0,None)]*nq,method='highs')
 if not ans.success:raise RuntimeError(ans.message)
 ans.fun=float(ans.x[n-1]);ans.primary_optimum=optimum
 return ans,{(t,sid):(float(ans.x[ti*12+j]),float(ans.x[ti*12+6+j])) for ti,t in enumerate(SLOTS) for j,sid in enumerate(IDS)}

def energy_recovery(mess):
 mm=dict(mess)
 for sid in IDS:
  total=sum(mm[t,sid][0] for t in SLOTS);charge=total/(.95*.95*20)
  for t in range(34,54):mm[t,sid]=(-charge,0.)
 return mm

def physics(mess):
 rows=[];passed=True
 for sid in IDS:
  E=760.;low=E;high=E;mp=mq=ms=0.
  for t in range(96):
   p,q=mess.get((t,sid),(0,0));E+=.25*(-p/.95 if p>=0 else -p*.95);low=min(low,E);high=max(high,E);mp=max(mp,abs(p));mq=max(mq,abs(q));ms=max(ms,np.hypot(p,q))
  ok=low>=440-1e-6 and high<=1080+1e-6 and abs(E-760)<1e-6 and mp<=300+1e-6 and ms<=400+1e-6;passed &= ok
  rows.append(dict(station=sid,Emin=low,Emax=high,Eterminal=E,Pmax=mp,Qmax=mq,Smax=ms,pass_=ok))
 return dict(status='PASS' if passed else 'FAIL',stations=rows,travel='all six units connected at their remapped initial stations for all slots; no movement, zero travel energy')

def capability(name):
 layout=read(H/'placements'/name/'LAYOUT.json');folder=H/'placements'/name/'capability';folder.mkdir(exist_ok=True);p=BASE_P;mess=None;best=None
 for it in range(5):
  z=coefficients(layout,p,folder/f'coeff_{it}',mess);ans,mm=solve_lp(layout,p,z);mm=energy_recovery(mm);ac=replay(layout,p,folder/f'AC_{it}',mm);ph=physics(mm)
  record=dict(iteration=it,proxy_rho=ans.fun,linear_model_primary_optimum=ans.primary_optimum,**ac,storage=ph['status']);print(name,json.dumps(record),flush=True)
  save(folder/f'ITERATION_{it}.json',record);save(folder/f'MESS_{it}.json',[dict(slot=t,station=sid,P=pq[0],Q=pq[1]) for (t,sid),pq in mm.items()]);save(folder/f'PHYSICS_{it}.json',ph)
  if ac['physical_pass'] and ph['status']=='PASS' and (best is None or ac['max_phase_line_loading_pu']<best['max_phase_line_loading_pu']):best=dict(record,iteration=it)
  if ac['physical_pass'] and ac['max_phase_line_loading_pu']<.90 and abs(ac['max_phase_line_loading_pu']-ans.fun)<.0015:break
  mess=mm
 if best:
  mm={(r['slot'],r['station']):(r['P'],r['Q']) for r in read(folder/f'MESS_{best["iteration"]}.json')}
  recovery=replay(layout,p,folder/'RECOVERY_AC',mm,slots=list(range(34,54)));best['recovery_AC']=recovery;best['physical_pass'] &= recovery['physical_pass']
 else:best=dict(physical_pass=False,status='NO_EXACT_AC_WITNESS')
 save(folder/'RESULT.json',best);return dict(placement=name,**best)

def main():
 names=sys.argv[1:] or [r['placement'] for r in read(H/'B0_PLACEMENT_GATES.json') if r['physical_pass']]
 results=[]
 for name in names:
  results.append(capability(name));save(H/f'CAPABILITY_BATCH_{names[0]}.json',results);table(H/f'CAPABILITY_BATCH_{names[0]}.csv',results)
if __name__=='__main__':main()
