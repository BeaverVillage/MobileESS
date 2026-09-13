"""Independent fresh engine, scalar bus/element magnitudes, signed test steps."""
import sys,time
import numpy as np
import ac8500 as ac
sys.dont_write_bytecode=True
def main():
    started=time.perf_counter();f=ac.H/'preflight/INDEPENDENT_COMPLEX_V2';f.mkdir(parents=True,exist_ok=False)
    base=ac.Engine(f/'baseline',independent=True);e=ac.Engine(f/'held_controls',independent=True);e.d.Text.Command('Set tolerance=1e-10');e.d.Solution.ControlMode(-1)
    tests=[(0,10.),(1,10.),(22,-10.),(24,30.),(25,40.),(48,-30.),(71,-40.)];rows=[]
    for t in range(96):
        base.set_slot(t);base.d.Solution.SolveSnap();assert base.d.Solution.Converged() and base.d.Solution.ControlActionsDone()
        if t not in [0,24,48,70,95]:continue
        state=base.controls(t);file=next((ac.H/'coefficients_v2').glob(f'block_*/slot_{t:02d}.npz'))
        with np.load(file) as z:
            for j,step in tests:
                e.set_slot(t);e.restore(state);e.perturb(ac.channels()[j],step);st=time.perf_counter();e.d.Solution.SolveSnap();exact=e.values()
                errors={k:float(np.max(np.abs(a-np.abs(z[k+'_anchor']+step*z[k][j])))) for k,a in zip(ac.KEYS,exact)}
                rows.append(dict(slot=t,channel=j,step=step,errors=errors,seconds=time.perf_counter()-st,converged=e.d.Solution.Converged(),passed=e.d.Solution.Converged() and errors[ac.KEYS[0]]<=.001 and max(errors[k] for k in ac.KEYS[1:])<=.005))
    ac.save(f/'VALIDATION.json',dict(status='PASS' if all(r['passed'] for r in rows) else 'FAIL',independent_fresh_engine=True,measurement='scalar bus puVmagAngle and element CurrentsMagAng/Powers; derivative generation uses bulk PDE API',thresholds_pu=dict(voltage=.001,loadings=.005),tests=rows,wall_seconds=time.perf_counter()-started));base.close();e.close();assert all(r['passed'] for r in rows),rows
    print('INDEPENDENT_COMPLEX_V2_PASS',flush=True)
if __name__=='__main__':main()
