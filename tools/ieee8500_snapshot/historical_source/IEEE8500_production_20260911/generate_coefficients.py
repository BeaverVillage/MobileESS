import sys,time,os,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
sys.dont_write_bytecode=True
import ac8500 as ac
H=ac.H
def one_block(bounds):
    lo,hi=bounds;folder=H/'coefficients'/f'block_{lo:02d}_{hi:02d}';folder.mkdir(parents=True,exist_ok=False);base=ac.Engine(folder/'base_runtime');e=ac.Engine(folder/'perturbation_runtime');d=e.d;d.Text.Command('Set tolerance=1e-10');d.Solution.ControlMode(-1);chs=ac.channels();rep=[];timings=[];calls=0
    # Each baseline context reconstructs its native chronological prefix.
    for t in range(hi):
        base.set_slot(t);base.d.Solution.SolveSnap();assert base.d.Solution.Converged() and base.d.Solution.ControlActionsDone()
        if t<lo:continue
        start=time.perf_counter();state=base.controls(t);e.set_slot(t);e.restore(state);d.Solution.SolveSnap();anchor=e.values();mat=[np.empty((len(chs),len(x)),dtype=np.float64) for x in anchor]
        for j,ch in enumerate(chs):
            samples=[]
            for sign in (1.,-1.):
                e.set_slot(t);e.restore(state);e.perturb(ch,sign);d.Solution.SolveSnap();calls+=1;assert d.Solution.Converged();samples.append(e.values())
            for target,p,m in zip(mat,samples[0],samples[1]):target[j]=(p-m)/2.
        # Predetermined representative signed P/Q steps; held accepted native controls.
        if t in [0,24,48,70,95]:
            for j,amount in [(0,10.),(1,10.),(22,-10.),(24,30.),(25,40.),(48,-30.),(71,-40.)]:
                e.set_slot(t);e.restore(state);e.perturb(chs[j],amount);d.Solution.SolveSnap();calls+=1;exact=e.values();errors=[float(np.max(np.abs(x-(b+amount*m[j])))) for x,b,m in zip(exact,anchor,mat)]
                rep.append(dict(slot=t,channel=j,amount=amount,errors=dict(zip(ac.KEYS,errors)),converged=d.Solution.Converged(),pass_local=errors[0]<=.001 and max(errors[1:])<=.005))
        np.savez_compressed(folder/f'slot_{t:02d}.npz',**{k:m for k,m in zip(ac.KEYS,mat)},**{k+'_anchor':x for k,x in zip(ac.KEYS,anchor)})
        timings.append(dict(slot=t,seconds=time.perf_counter()-start));print('COEFFICIENT_SLOT',t,'seconds',timings[-1]['seconds'],flush=True)
    ac.save(folder/'REPRESENTATIVE_LOCAL_AC_VALIDATION.json',rep);ac.save(folder/'TIMING.json',dict(slots=timings,perturbation_AC_solves=calls));base.close();e.close();return dict(block=[lo,hi],calls=calls,representative=rep,timing=timings)
def main():
    freeze=ac.read(H/'PREFLIGHT_EXECUTION_FREEZE.json')
    for r in freeze['files']:assert ac.sha(Path(r['path']))==r['sha256'],r['path']
    started=time.perf_counter();reference=ac.replay(H/'preflight'/'B0_FROZEN_REPRODUCTION',independent=True)
    authority=ac.read(ac.STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json')
    with np.load(authority['selected_phase_arrays']['path']) as old,np.load(H/'preflight/B0_FROZEN_REPRODUCTION/AC_PHASE_ARRAYS.npz') as new:diff={k:float(np.max(np.abs(old[k]-new[k]))) for k in ac.KEYS}
    assert reference['feasible'] and max(diff.values())<=1e-10,diff;ac.save(H/'preflight/B0_REPRODUCTION_AUDIT.json',dict(status='PASS',max_differences=diff,reference=reference))
    coeff_start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as pool:blocks=list(pool.map(one_block,[(0,24),(24,48),(48,72),(72,96)]))
    assert sum(len(x['timing']) for x in blocks)==96;representatives=[r for b in blocks for r in b['representative']];assert all(r['pass_local'] for r in representatives),representatives
    ac.save(H/'coefficients/COEFFICIENT_GENERATION_RECEIPT.json',dict(status='PASS',generation_wall_seconds=time.perf_counter()-coeff_start,total_preflight_electrical_seconds=time.perf_counter()-started,channels=ac.channels(),axis_order='channel x physical axis; one file per slot',units='pu per kW or kvar',derivative='central +/-1 kW or kvar exact OpenDSS, holding independently accepted native tap/cap states',derivative_only_solver_tolerance=1e-10,production_replay_tolerance='unchanged default',native_controls_in_final_validation=True,IEEE123_coefficients_reused=False,perturbation_AC_solve_count=sum(b['calls'] for b in blocks),representatives=representatives,blocks=blocks,baseline=ac.record(H/'preflight/B0_FROZEN_REPRODUCTION/AC_PHASE_ARRAYS.npz')))
    print('COEFFICIENT_GENERATION_COMPLETE',time.perf_counter()-coeff_start,flush=True)
if __name__=='__main__':main()
