"""Fresh Source-YY Planning96 DSS derivatives, independent P and Q axes.

Native control states come from the frozen causal Source-YY TIME trajectory.
No DY response, IEEE123 sensitivity, future Actual state, or new optimizer is
used. Physical policy and coefficient identity are fixed before probing.
"""
import math, time
import numpy as np
from .static_common import *
from .full_grid import vectors, coefficient_digest

CONTROLS=tuple([f'aidc_load_kw[AIDC{i:02d}]' for i in range(1,13)]+
    [f'aidc_load_kvar[AIDC{i:02d}]' for i in range(1,13)]+
    [f'mess_p_kw[{s}{i:02d}]' for s in ('IDC','STA') for i in range(1,13)]+
    [f'mess_q_kvar[{s}{i:02d}]' for s in ('IDC','STA') for i in range(1,13)])

def engine(tag,role='PLANNING'):
    from . import may01_voltage as v
    old=v.RUN;v.RUN=RUN
    try:return v.engine('STATIC_'+tag,role,'H0_SOURCE_YY')
    finally:v.RUN=old

def generate():
    res=init();start=time.perf_counter();folder=RUN/'coefficients';folder.mkdir(exist_ok=True)
    hardware=read(OUT/'SOURCE_YY_HARDWARE_FREEZE.json')
    trajectory=HIST_RUN/'source_yy/ZERO/2025-05-01_PLANNING/STATES.json'
    states=read(trajectory);assert len(states)==96
    e=engine('COEFFICIENTS');e.capture=False;e.d.Solution.ControlMode(-1)
    ratings=[];inv={r['element']:r for r in e.inventory['lines']}
    for a in e.line_axes:
        b=inv[a['element']]['buses'][a['terminal']-1].split('.')[0]
        e.d.Circuit.SetActiveBus(b);ratings.append(e.d.Bus.kVBase()*a['normal_amps'])
    axes=dict(controls=CONTROLS,line=e.line_axes,nodes=e.node_axes,transformer_current=e.transformer_axes,
        transformer_winding=e.transformer_winding_axes,parent_mask=e.canonical.tolist(),security_mask=e.security.tolist(),
        line_phase_kVA=ratings,tx_kVA=e._tx_nameplate_ratings.tolist())
    put('SOURCE_YY_GRID_AXES.json',axes)
    identity=dict(source=SOURCE,baseline=BASE,day='2025-05-01',role='PLANNING_S0',beta_BG=2.,
        hardware_sha=hardware['hardware_sha'],hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),
        state_trajectory=record(trajectory),axes_sha=digest(axes),controls=CONTROLS,
        step=.25,method='central finite difference at fixed original TIME end-of-slot Tap/Cap states',
        AIDC_Q_policy='Independent Q derivatives; original A-stage PF=.95 equality must still be enforced',
        code=record(__file__))
    put('SOURCE_YY_COEFFICIENT_PREREGISTRATION.json',identity)
    records=[];holdouts=[];anchors=[]
    def probe(k,delta):
        site=CONTROLS[k].split('[')[1][:-1];p,q=e.base_pcc[site]
        if k<12:p+=delta
        elif k<24:q+=delta
        elif k<48:p=-delta
        else:q=-delta
        e.d.Text.Command(f'edit {e.pccs[site]["element"]} kw={p:.15g} kvar={q:.15g}')
        e.d.Solution.Solve()
        if not e.d.Solution.Converged():raise ValueError('SOURCE_YY_FIXED_STATE_PROBE_NONCONVERGENCE')
        return vectors(e)
    for t in range(96):
        guard(start);p=folder/f'{t:02d}.npz'
        e.apply('PLANNING',t,2.);e.restore_control_state(states[t]);e.d.Solution.ControlMode(-1);e.d.Solution.Solve()
        assert e.d.Solution.Converged();y=vectors(e)
        anchor=np.r_[e.inputs['PLANNING_AIDC_P_kw'][t],e.inputs['PLANNING_AIDC_P_kw'][t]*math.tan(math.acos(.95)),np.zeros(48)]
        if not p.exists():
            jac={k:np.empty((72,len(v))) for k,v in y.items()}
            for k in range(72):
                plus=probe(k,.25);minus=probe(k,-.25);probe(k,0.)
                for key in y:jac[key][k]=(plus[key]-minus[key])/.5
            z=dict(anchor=anchor,**y,**{k+'_J':v for k,v in jac.items()})
            np.savez_compressed(p,**z)
        else:
            with np.load(p) as zf:z={k:zf[k] for k in zf.files}
            assert np.array_equal(z['anchor'],anchor) and np.max(abs(z['v']-y['v']))<1e-7
        if t in (0,31,74):
            for k in (0,11,12,23,24,35,36,47,48,59,60,71):
                actual=probe(k,5.);probe(k,0.)
                holdouts.append(dict(slot=t,control=CONTROLS[k],amount=5.,
                    max_line_rho_error=float(np.max(abs(actual['line']-(z['line']+5*z['line_J'][k])))),
                    max_v_squared_error=float(np.max(abs(actual['v']-(z['v']+5*z['v_J'][k]))))))
        records.append(dict(slot=t,**record(p),array_sha256=coefficient_digest(z)))
        anchors.append(dict(slot=t,rho=float(y['line'][e.canonical].max()),
            Vmin=float(np.sqrt(y['v'].min())),Vmax=float(np.sqrt(y['v'].max()))))
        put('SOURCE_YY_COEFFICIENT_PROGRESS.json',dict(completed=t+1,total=96,wall_seconds=time.perf_counter()-start))
        if t%4==0:print('SOURCE_YY COEFFICIENT',t,round(time.perf_counter()-start,1),flush=True)
    table('SOURCE_YY_PLANNING_ANCHOR.csv',anchors);table('SOURCE_YY_INDEPENDENT_HOLDOUT.csv',holdouts)
    put('SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json',dict(PASS=len(records)==96,identity=identity,
        case_sha=digest(dict(identity=identity,records=records)),records=records,wall_seconds=time.perf_counter()-start,
        independent_controls=72,original_lines=3703,Triplex=1177,parent_cells=int(e.canonical.sum()),
        both_terminal_cells=int(e.security.sum()),voltage_nodes=len(e.node_axes),
        transformer_current_cells=len(e.transformer_axes),transformer_winding_cells=len(e.transformer_winding_axes),
        DY_coefficients_reused=False,IEEE123_coefficients_reused=False,
        finite_difference_is_local_linearization_not_global_AC_equivalence=True,
        Actual_SVR3='Separate nonlinear AC/Fresh; not installed in Planning',
        A1_A2_domain_proofs_required=True,M1_fixed_B0_and_M2_fixed_A2_require_distinct_anchor=True,
        Native_optimize_calls=0,resources=res))
    e.d.Basic.ClearAll()

if __name__=='__main__':generate()
