"""Current-slot Q-only finite-difference AC restoration with native-state isolation.

Trials reconstruct the SAME accepted causal prefix in a clean OpenDSS context.
No trial solution/tap state is ever reused by another trial. L2 Q deviation is
minimized locally; native discrete controls prevent a global optimality claim.
"""
from common import *
import numpy as np,time
from scipy.optimize import minimize
from dayahead.v28r2 import opendss_backend as backend
from dayahead.v28r2.opendss_mapping import FeederAssets
from dayahead.v28r2.opendss_results import OpenDSSResult
from dayahead.run_v16_3_voltage_candidate import _enable_native_controls
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY

HARD_TOLERANCE=1e-9  # inherited v37r3/OpenDSSResult comparison tolerance

class DiagnosticResult(OpenDSSResult):
    @property
    def summary(self):
        return {**super().summary,'diagnostic_namespace':'ETA95_QSAFE_ACTUAL',
            'clean_engine_count':self.diagnostic_clean_engines,
            'total_native_solve_count_including_trial_prefixes':self.diagnostic_solves,
            'accepted_trajectory_slots':96,'candidate_only':True}

def q_bounds(p,connected,authority):
    ap=authority.pcs_kva*np.cos(np.pi/authority.pcs_polygon_faces)
    lo=[];hi=[]
    for v,c in zip(p,connected):
        assert abs(v)<=authority.active_power_limit_kw+1e-9
        lower=-np.sqrt(max(0,authority.pcs_kva**2-v*v));upper=-lower
        for face in range(authority.pcs_polygon_faces):
            theta=2*np.pi*face/authority.pcs_polygon_faces;s=np.sin(theta);co=np.cos(theta)
            if s>1e-12:upper=min(upper,(ap-v*co)/s)
            elif s < -1e-12:lower=max(lower,(ap-v*co)/s)
            else:assert v*co<=ap+1e-9
        lo.append(lower if c else 0.);hi.append(upper if c else 0.)
    return np.array(lo),np.array(hi)

def constraints(r):
    v=r['v'];return np.r_[20*(v-.95),20*(1.05-v),1-r['ipu'],1-r['kva'][np.isfinite(r['kva'])]]
def feasible(r):
    return bool(r['converged'] and r['v'].min()>=.95-HARD_TOLERANCE and r['v'].max()<=1.05+HARD_TOLERANCE and r['ipu'].max()<=1+HARD_TOLERANCE and np.nanmax(r['kva'])<=1+HARD_TOLERANCE)

class PrefixEngine:
    def __init__(self,context,voltage,trajectory,folder):
        self.context=context;self.voltage=voltage;self.trajectory=trajectory;self.folder=folder
        self.assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
        self.nodes=tuple(map(str,voltage['node_names']))
        self.branches=tuple(context.legacy_context[3].factories[0].data.branches)
        self.accepted_taps=[];self.trace=[];self.version='';self.compile_count=0;self.solve_count=0;self.adapter=None
    def evaluate(self,t,q):
        # Prefix only. Future Actual rows exist in immutable input storage, but
        # are never applied or exposed to the current-slot Q optimizer.
        oldq=self.trajectory.mess_q_kvar[t].copy();self.trajectory.mess_q_kvar[t]=q
        oldcwd=Path.cwd();odd,adapter=backend.compile_clean_engine(self.assets)
        if self.adapter is None:self.adapter=adapter
        else:assert adapter==self.adapter
        adapter=self.adapter  # stable immutable identity for inherited allocation cache
        self.compile_count+=1
        odd.Basic.AllowChangeDir(False);odd.Basic.DataPath(str(self.folder));os.chdir(oldcwd)
        self.version=str(odd.Basic.Version())
        try:
            for s in range(t+1):
                backend.apply_trajectory_slot(odd,adapter,self.context,self.trajectory,s)
                if s==0:backend.apply_frozen_native_state(odd,self.voltage,0)
                starts,caps=backend._native_state(odd)
                assert caps==self.voltage['capacitor_states'][s].tolist()
                if s==t:
                    expected=self.voltage['regulator_taps'][0].tolist() if t==0 else self.accepted_taps[t-1]
                    assert starts==expected,('TRIAL_START_STATE_MISMATCH',t,starts,expected)
                _enable_native_controls(odd);odd.Solution.SolveSnap();self.solve_count+=1
                assert odd.Solution.Converged(),('DSS_NONCONVERGENCE',t,s)
                if s<t:
                    ts,_=backend._native_state(odd)
                    assert ts==self.accepted_taps[s],('PREFIX_REPRODUCTION_MISMATCH',t,s)
            v=backend._voltage_vector(odd,self.nodes)
            m=np.asarray([backend._branch_measurement(odd,b) for b in self.branches])
            losses=np.asarray(odd.Circuit.Losses())[:2]/1000
            taps,caps=backend._native_state(odd)
            # Independent engine setpoint readback at every candidate. Aggregate
            # co-located vehicles only once, and verify the untouched AIDC/P.
            expected={}
            for j,location in enumerate(self.trajectory.mess_locations_96x4[t]):
                if str(location).startswith('TRANSIT_'):continue
                target=expected.setdefault(str(location).upper(),[0.,0.])
                target[0]+=self.trajectory.mess_p_kw[t,j];target[1]+=q[j]
            delivered=[];maxerr=0.
            for prefix in ('IDC','STA'):
                for i in range(1,13):
                    service=f'{prefix}{i:02d}'
                    odd.Generators.Name('MESS_DIS_'+service);gp=float(odd.Generators.kW());gq=float(odd.Generators.kvar())
                    odd.Loads.Name('MESS_CHG_'+service);lp=float(odd.Loads.kW());lq=float(odd.Loads.kvar())
                    ep,eq=expected.get(service,[0.,0.]);maxerr=max(maxerr,abs(gp-lp-ep),abs(gq-lq-eq))
                    delivered.append(dict(service=service,P_EXEC_set=gp-lp,Q_EXEC_set=gq-lq))
            for i in range(12):
                odd.Loads.Name(f'IDC_IDC{i+1:02d}')
                maxerr=max(maxerr,abs(odd.Loads.kW()-self.trajectory.pcc_p_kw[t,i]),abs(odd.Loads.kvar()-self.trajectory.pcc_q_kvar[t,i]))
            assert maxerr<1e-9,('ENGINE_SETPOINT_BINDING',t,maxerr)
            r=dict(v=v,ia=m[:,0],ipu=m[:,1],kva=m[:,2],losses=losses,taps=taps,caps=caps,converged=True,readback=delivered,readback_max_error=maxerr)
            # Per-trial evidence includes the shared start and discarded end.
            self.trace.append(dict(slot=t,Q=q.tolist(),start_taps=starts,final_taps=taps,max_actual_slot_applied=t,
                Vmin=float(v.min()),Vmax=float(v.max()),max_current=float(m[:,1].max()),max_tx_kva=float(np.nanmax(m[:,2])),feasible=feasible(r),engine_PQ_setpoint_max_error=maxerr))
            return r
        finally:
            self.trajectory.mess_q_kvar[t]=oldq;odd.Basic.ClearAll()
            if self.compile_count%32==0:
                import gc
                gc.collect()
    def result(self,rows,elapsed):
        result=DiagnosticResult(self.trajectory.day,'ACTUAL',self.trajectory.case,self.trajectory.source_schedule_sha256,
            self.nodes,tuple('ABC'[int(n.rsplit('.',1)[1])-1] for n in self.nodes),
            tuple(b.branch_id for b in self.branches),tuple(b.phase for b in self.branches),
            tuple('transformer' if b.branch_id.startswith('transformer.') else 'line' for b in self.branches),
            np.array([r['converged'] for r in rows]),np.array([r['v'] for r in rows]),np.array([r['ia'] for r in rows]),
            np.array([r['ipu'] for r in rows]),np.array([r['kva'] for r in rows]),np.array([r['losses'] for r in rows]),
            np.array([r['taps'] for r in rows]),np.array([r['caps'] for r in rows]),self.version,elapsed)
        object.__setattr__(result,'diagnostic_clean_engines',self.compile_count)
        object.__setattr__(result,'diagnostic_solves',self.solve_count)
        return result

def correct_slot(evaluate,q_original,lower,upper):
    """Only current Q is variable. Exact AC feasibility, finite-difference Jacobian."""
    idx=np.where(upper>lower+1e-10)[0];q0=q_original.copy();cache={};solvers=[]
    def full(x):
        if np.array_equal(x,x0):return q0.copy()
        q=q0.copy();q[idx]=x*400;return q
    def ev(x):
        q=full(x);key=q.tobytes()
        if key not in cache:cache[key]=(q.copy(),evaluate(q))
        return cache[key][1]
    x0=q0[idx]/400;bounds=list(zip(lower[idx]/400,upper[idx]/400))
    r0=ev(x0)
    if feasible(r0):return q0,r0,dict(status='UNCHANGED',optimizer_calls=0,evaluations=1)
    if not len(idx):return q0,r0,dict(status='Q_ONLY_INFEASIBLE',optimizer_calls=0,evaluations=1,reason='NO_CONNECTED_Q_VARIABLE')
    def fun(x):return .5*float(np.dot(x-x0,x-x0))
    def jac(x):return x-x0
    def con(x):return constraints(ev(x))
    def cj(x):
        # Inherited fixed-discrete restoration pattern, restricted to Q. A
        # smaller 0.25 kvar central step resolves boundary placement accurately.
        base=con(x);g=np.zeros((len(base),len(idx)));h=.25/400
        for j,(lo,hi) in enumerate(bounds):
            xp=x.copy();xm=x.copy();xp[j]=min(hi,x[j]+h);xm[j]=max(lo,x[j]-h)
            g[:,j]=(con(xp)-con(xm))/(xp[j]-xm[j])
        return g
    for seed in (x0,np.zeros_like(x0)):
        seed=np.clip(seed,np.array(bounds)[:,0],np.array(bounds)[:,1])
        res=minimize(fun,seed,jac=jac,bounds=bounds,constraints=[dict(type='ineq',fun=con,jac=cj)],
                     method='SLSQP',options=dict(maxiter=25,ftol=1e-10,disp=False))
        final=ev(res.x);solvers.append(dict(success=bool(res.success),message=str(res.message),iterations=int(res.nit),objective=float(res.fun),feasible=feasible(final)))
        if res.success and feasible(final):break
    candidates=[(float(np.sum((q-q0)**2)),q,r) for q,r in cache.values() if feasible(r)]
    if candidates:
        obj,q,r=min(candidates,key=lambda z:z[0])
        return q,r,dict(status='Q_CORRECTED',optimizer_calls=len(solvers),evaluations=len(cache),sum_squared_delta_Q=obj,solvers=solvers,optimality='Best exact-feasible trial from local finite-difference SQP; global minimum not certified across native tap regimes')
    return q0,r0,dict(status='Q_ONLY_INFEASIBLE',optimizer_calls=len(solvers),evaluations=len(cache),solvers=solvers,reason='NO_EXACT_FEASIBLE_Q_FOUND_WITHIN_DIAGNOSTIC_SEARCH; not a global infeasibility proof; original Q retained and P unchanged')

def run_qsafe(context,voltage,trajectory,connected,authority,folder):
    begin=time.time();e=PrefixEngine(context,voltage,trajectory,folder);rows=[];events=[]
    initialq=trajectory.mess_q_kvar.copy();fixedp=trajectory.mess_p_kw.copy();fixedaidc=trajectory.pcc_p_kw.copy()
    for t in range(96):
        lo,hi=q_bounds(fixedp[t],connected[t],authority)
        assert np.all(initialq[t]>=lo-1e-7) and np.all(initialq[t]<=hi+1e-7),('ORIGINAL_Q_OUTSIDE_FIXED_P_PCS',t)
        q,r,event=correct_slot(lambda q:e.evaluate(t,q),initialq[t],lo,hi)
        assert np.all(q>=lo-1e-7) and np.all(q<=hi+1e-7)
        trajectory.mess_q_kvar[t]=q;rows.append(r);e.accepted_taps.append(r['taps'])
        assert np.all(np.hypot(fixedp[t],q)<=authority.pcs_kva+1e-9)
        angles=2*np.pi*np.arange(authority.pcs_polygon_faces)/authority.pcs_polygon_faces
        assert np.max(fixedp[t,:,None]*np.cos(angles)+q[:,None]*np.sin(angles))<=authority.pcs_kva*np.cos(np.pi/authority.pcs_polygon_faces)+1e-9
        event.update(slot=t,Q_original=initialq[t].tolist(),Q_accepted=q.tolist(),Delta_Q=(q-initialq[t]).tolist(),P_EXEC=fixedp[t].tolist(),start_taps=e.trace[-event['evaluations']]['start_taps'],final_taps=r['taps'])
        events.append(event)
        save(folder/'PROGRESS.json',dict(day=trajectory.day,policy=trajectory.case,slots_complete=t+1,interventions=sum(x['status']=='Q_CORRECTED' for x in events),infeasible=sum(x['status']=='Q_ONLY_INFEASIBLE' for x in events),elapsed_seconds=time.time()-begin))
        if t%8==0 or event['status']=='Q_ONLY_INFEASIBLE':print('QSAFE_SLOT',trajectory.day,trajectory.case,t,event['status'],event['evaluations'],round(time.time()-begin,1),flush=True)
    assert np.array_equal(fixedp,trajectory.mess_p_kw) and np.array_equal(fixedaidc,trajectory.pcc_p_kw)
    result=e.result(rows,time.time()-begin);result.validate();result.write(folder)
    save(folder/'Q_CONTROL_EVENTS.json',events)
    save(folder/'ACCEPTED_ENGINE_PQ_READBACK.json',dict(status='PASS',slots=[r['readback'] for r in rows],max_setpoint_error=max(r['readback_max_error'] for r in rows),AIDC_PQ_unchanged=True,exact_P_EXEC_binding=True))
    save(folder/'NATIVE_TRIAL_AUDIT.json',dict(status='PASS',method='Clean engine plus exact accepted prefix 0..t-1 for EVERY trial; no later Actual slot applied',trials=e.trace,clean_engines=e.compile_count,physical_solves=e.solve_count,scheduling_optimizer_calls=0,shared_slot_start_verified=True,accepted_prefix_taps_reproduced=True,no_future_leakage=True))
    return result,events
