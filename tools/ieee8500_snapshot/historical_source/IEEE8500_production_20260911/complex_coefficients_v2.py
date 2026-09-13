"""Version 2: signed phasor derivatives, including zero-injection PCCs."""
import sys,time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import ac8500 as ac
sys.dont_write_bytecode=True
H=ac.H/'coefficients_v2'

def complex_values(e):
    d=e.d;a=e.ax
    volts=np.asarray(d.Circuit.AllBusVolts()).reshape(-1,2)
    z=volts[:,0]+1j*volts[:,1]
    v=z*np.asarray(d.Circuit.AllBusMagPu())/np.maximum(np.abs(z),1e-100)
    raw=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2)
    current=raw[:,0]*np.exp(1j*np.deg2rad(raw[:,1]))
    pq=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
    power=(np.bincount(a['power_group'],weights=pq[a['power_pos'],0])+1j*np.bincount(a['power_group'],weights=pq[a['power_pos'],1]))/a['kva_rating']
    return [v,current[a['line_pos']]/a['line_rating'],current[a['tx_pos']]/a['tx_rating'],power]

def block(bounds):
    lo,hi=bounds;f=H/f'block_{lo:02d}_{hi:02d}';f.mkdir(parents=True,exist_ok=False)
    base=ac.Engine(f/'base');e=ac.Engine(f/'perturb');d=e.d;d.Text.Command('Set tolerance=1e-10');d.Solution.ControlMode(-1)
    rows=[];calls=0
    for t in range(hi):
        base.set_slot(t);base.d.Solution.SolveSnap();assert base.d.Solution.Converged() and base.d.Solution.ControlActionsDone()
        if t<lo:continue
        start=time.perf_counter();state=base.controls(t);e.set_slot(t);e.restore(state);d.Solution.SolveSnap();anchor=complex_values(e)
        matrices=[np.empty((72,len(z)),dtype=np.complex128) for z in anchor]
        for j,ch in enumerate(ac.channels()):
            samples=[]
            for step in (1.,-1.):
                e.set_slot(t);e.restore(state);e.perturb(ch,step);d.Solution.SolveSnap();calls+=1;assert d.Solution.Converged();samples.append(complex_values(e))
            for m,p,n in zip(matrices,*samples):m[j]=(p-n)/2
        np.savez_compressed(f/f'slot_{t:02d}.npz',**{k:m for k,m in zip(ac.KEYS,matrices)},**{k+'_anchor':v for k,v in zip(ac.KEYS,anchor)})
        rows.append(dict(slot=t,seconds=time.perf_counter()-start));print('COMPLEX_COEFFICIENT_SLOT',t,round(rows[-1]['seconds'],3),flush=True)
    base.close();e.close();ac.save(f/'TIMING.json',dict(slots=rows,perturbation_solves=calls));return dict(slots=rows,perturbation_solves=calls)

def main():
    freeze=ac.read(ac.H/'COEFFICIENT_V2_EXECUTION_FREEZE.json')
    for r in freeze['files']:assert ac.sha(r['path'])==r['sha256'],r['path']
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as p:rs=list(p.map(block,[(0,24),(24,48),(48,72),(72,96)]))
    ac.save(H/'GENERATION_RECEIPT.json',dict(status='GENERATED_PENDING_INDEPENDENT_VALIDATION',wall_seconds=time.perf_counter()-start,channels=ac.channels(),representation='complex normalized voltage and current phasors; normalized winding P+jQ; magnitudes evaluated after linear combination',central_step_kw_kvar=1.,controls='held accepted native B0 states in derivatives only',final_AC_controls='native chronological',IEEE123_coefficients_reused=False,blocks=rs,perturbation_solve_count=sum(r['perturbation_solves'] for r in rs)))
if __name__=='__main__':main()
