"""Full 96-slot AIDC finite differences; no MESS-domain assumption."""
from start_validation import *
from engine import arrays
def main():
 layout=read(H/'LAYOUT.json');states=read(H/'B0_DA/CONTROL_STATES.json');start=time.perf_counter()
 folder=H/'B1_coefficients';folder.mkdir(exist_ok=True);records=[]
 for t in range(96):
  out=folder/f'slot_{t:02}';out.mkdir(exist_ok=False);e=ResiteEngine(layout,out/'runtime');d=e.d
  try:
   e.inputs(t,BASE_P,BASE_Q)
   d.Solution.ControlMode(-1)
   for r in states[t]['regulators']:d.RegControls.Name(r['name']);d.RegControls.TapNumber(r['tap_number'])
   for r in states[t]['capacitors']:d.Capacitors.Name(r['name']);d.Capacitors.States(r['step_states'])
   d.Solution.SolveSnap();assert d.Solution.Converged()
   v,f=arrays(e);v=v*v;jv=np.empty((12,len(v)));jf=np.empty((12,len(f)),complex)
   for k in range(12):
    sides=[]
    for sign in [1,-1]:
     d.Loads.Name(f'op8500_aidc{k+1:02}');d.Loads.kW(float(BASE_P[t,k]+sign));d.Loads.kvar(float(BASE_Q[t,k]+sign*BASE_Q[t,k]/BASE_P[t,k]))
     d.Solution.SolveSnap();assert d.Solution.Converged();a,b=arrays(e);sides.append((a*a,b))
    jv[k]=(sides[0][0]-sides[1][0])/2;jf[k]=(sides[0][1]-sides[1][1])/2
    d.Loads.Name(f'op8500_aidc{k+1:02}');d.Loads.kW(float(BASE_P[t,k]));d.Loads.kvar(float(BASE_Q[t,k]))
   np.savez_compressed(out/'AIDC_COEFFICIENTS.npz',x=BASE_P[t],v2=v,flow=f,v2_J=jv,flow_J=jf)
   if t==0:save(folder/'AXES.json',dict(nodes=e.nodes.tolist(),line=e.ax['line_label'].tolist(),tx=e.ax['tx_label'].tolist(),winding=e.ax['kva_label'].tolist(),winding_rating_kVA=e.ax['kva_rating'].tolist()))
  finally:e.close()
  records.append(dict(slot=t,solves=25))
  save(H/'COEFFICIENT_STATUS.json',dict(status='RUNNING',stage='B1_FULL_96_COEFFICIENTS',completed_slots=t+1,pid=os.getpid(),wall_seconds=time.perf_counter()-start))
  print('B1_COEFFICIENTS',t+1,'/96',flush=True)
 save(H/'COEFFICIENT_STATUS.json',dict(status='COMPLETE',stage='B1_FULL_96_COEFFICIENTS',completed_slots=96,pid=os.getpid(),wall_seconds=time.perf_counter()-start,scope='AIDC controls only; MESS coefficients require production PCC domain decision'))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'COEFFICIENT_STATUS.json',dict(status='FAILED',error=repr(e),traceback=traceback.format_exc()));raise
