"""Full original-feeder affine coefficients, with independent fixed-state probes.

No controller setting, original rating, route or objective row is selected by
the results. Planning S0 is deliberately different from Actual SVR3 hardware.
"""
import math,time,json
import numpy as np
from .full_common import *
from .full_physical import engine

CONTROLS=tuple([f'aidc_load_kw[AIDC{i:02d}]' for i in range(1,13)]+
    [f'mess_p_kw[{s}{i:02d}]' for s in ('IDC','STA') for i in range(1,13)]+
    [f'mess_q_kvar[{s}{i:02d}]' for s in ('IDC','STA') for i in range(1,13)])

def vectors(e):
    d=e.d;current=np.asarray(d.PDElements.AllCurrents()).reshape(-1,2)
    power=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
    ip=current[e._line_indices];lp=power[e._line_indices]
    tp=np.add.reduceat(power[e._tx_power_indices],e._tx_winding_starts,axis=0)
    return dict(line=np.linalg.norm(ip,axis=1)/e._line_ratings,
        lp=lp[:,0],lq=lp[:,1],v=np.asarray(d.Circuit.AllBusMagPu())**2,
        tc=np.linalg.norm(current[e._tx_indices],axis=1)/e._tx_ratings,
        tp=tp[:,0],tq=tp[:,1])

def perturb(e,k,amount):
    name=CONTROLS[k];site=name.split('[')[1][:-1]
    d=e.d;p,q=e.base_pcc[site]
    if k<12:
        p+=amount;q+=amount*math.tan(math.acos(.95))
    elif k<36:p=-amount
    else:q=-amount
    # Set the pair together. A single kW property update at zero-kW/zero-kvar
    # can retain the prior PF and manufacture unintended reactive demand.
    d.Text.Command(f'edit {e.pccs[site]["element"]} kw={p:.15g} kvar={q:.15g}')
    d.Solution.Solve()
    if not d.Solution.Converged():raise ValueError(f'FIXED_STATE_PROBE_NOT_CONVERGED:{k}:{amount}:iterations={d.Solution.MaxIterations()}')
    return vectors(e)

def coefficient_digest(z):return digest({k:sha(np.ascontiguousarray(z[k]).tobytes()) for k in sorted(z)})

def generate():
    init();res=resources();start=time.perf_counter();folder=RUN/'grid_text_pq';folder.mkdir(exist_ok=True)
    # Reuse the prior TIME state trajectory, not a repeated/reset STATIC policy.
    prior=RUNTIME/'correction_time100/TIME_2.00_PLANNING_B0'
    states=read(prior/'STATES.json');e=engine('PLANNING_COEFFICIENTS','PLANNING');e.capture=False
    e.d.Solution.ControlMode(-1);h=.25;records=[];holdouts=[];rows=[]
    # Nominal kVA phase ratings use the actual terminal bus base, all original
    # NormalAmps remain authoritative for current and both-end safety rows.
    ratings=[];inv={x['element']:x for x in e.inventory['lines']}
    for a in e.line_axes:
        bus=inv[a['element']]['buses'][a['terminal']-1].split('.')[0]
        e.d.Circuit.SetActiveBus(bus);ratings.append(e.d.Bus.kVBase()*a['normal_amps'])
    axes=dict(controls=CONTROLS,line=e.line_axes,nodes=e.node_axes,transformer_current=e.transformer_axes,
        transformer_winding=e.transformer_winding_axes,parent_mask=e.canonical.tolist(),security_mask=e.security.tolist(),
        line_phase_kVA=ratings,tx_kVA=e._tx_nameplate_ratings.tolist())
    put('GRID_AXES.json',axes)
    identity=dict(source=SOURCE,base=BASE,beta_BG=2.,role='PLANNING_S0',controls=CONTROLS,step=h,
        original_input=record(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz'),
        state_trajectory=record(prior/'STATES.json'),hardware=record(OUT/'IDC_ORIGINAL_PHYSICAL_CONTRACT.json'),
        axes_sha=digest(axes),code=record(Path(__file__)),difference='central fixed-Tap/Cap; original TIME trajectory retained; no auto controls inside derivative probes')
    for t in range(96):
        guard(start);p=folder/f'{t:02d}.npz'
        e.apply('PLANNING',t,2.);e.restore_control_state(states[t]);e.d.Solution.ControlMode(-1);e.d.Solution.Solve()
        assert e.d.Solution.MaxIterations()==100 and e.d.Solution.Converged()
        y=vectors(e);anchor=np.zeros(60);anchor[:12]=e.inputs['PLANNING_AIDC_P_kw'][t]
        if not p.exists():
            jac={k:np.zeros((60,len(v))) for k,v in y.items()}
            for k in range(60):
                plus=perturb(e,k,h);minus=perturb(e,k,-h);perturb(e,k,0.)
                for key in y:jac[key][k]=(plus[key]-minus[key])/(2*h)
            z=dict(anchor=anchor,**{k:v for k,v in y.items()},**{k+'_J':v for k,v in jac.items()})
            np.savez_compressed(p,**z)
        else:
            with np.load(p) as a:z={k:a[k] for k in a.files}
            assert np.max(abs(z['v']-y['v']))<1e-7 and np.array_equal(z['anchor'],anchor)
        # Independent finite displacement (20x derivative step), not a mirror
        # of the affine implementation. No feasibility inference beyond it.
        if t in (0,31,74):
            for k in (0,12,23,24,35,36,47,48,59):
                actual=perturb(e,k,5.);perturb(e,k,0.)
                holdouts.append(dict(slot=t,control=CONTROLS[k],amount=5.,
                    max_line_rho_error=float(np.max(abs(actual['line']-(z['line']+5*z['line_J'][k])))),
                    max_v_squared_error=float(np.max(abs(actual['v']-(z['v']+5*z['v_J'][k]))))))
        records.append(dict(slot=t,**record(p),array_sha256=coefficient_digest(z)))
        rows.append(dict(slot=t,rho_global=float(y['line'][e.canonical].max()),rho_MV=float(y['line'][e.cmv].max()),
            rho_LV=float(y['line'][e.clv].max()),Vmin=float(np.sqrt(y['v'].min())),Vmax=float(np.sqrt(y['v'].max())),
            tx_current_max=float(y['tc'].max()),tx_nameplate_max=float((np.hypot(y['tp'],y['tq'])/e._tx_nameplate_ratings).max())))
        put('GRID_COEFFICIENT_PROGRESS.json',dict(completed=len(records),total=96,wall_seconds=time.perf_counter()-start))
        if t%8==0:print('GRID COEFFICIENT',t,round(time.perf_counter()-start,1),flush=True)
    table('GRID_PLANNING_ANCHOR.csv',rows);table('GRID_INDEPENDENT_HOLDOUT.csv',holdouts)
    put('GRID_COEFFICIENT_MANIFEST.json',dict(identity=identity,records=records,resources=res,wall_seconds=time.perf_counter()-start,
        coefficient_horizon_PASS=len(records)==96,control_count=60,original_lines=3703,Triplex=1177,
        parent_objective_cells=int(e.canonical.sum()),both_terminal_security_cells=int(e.security.sum()),
        all_voltage_nodes=len(e.node_axes),transformer_current_cells=len(e.transformer_axes),transformer_winding_cells=len(e.transformer_winding_axes),
        source_IEEE123_coefficients_reused=False,physical_settings_changed=False,Native_calls=0,
        fixed_anchor_voltage_PASS=all(x['Vmin']>=.95 and x['Vmax']<=1.05 for x in rows),
        Planning_TIME_certified=False,Actual_SVR3_authority='Independent chronological Actual/Fresh; not installed in Planning S0'))
    print('GRID96 COMPLETE',flush=True)

if __name__=='__main__':generate()
