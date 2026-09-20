"""Q-first, current-slot minimum-P correction, causal energy recovery.

Pure controller: no filesystem, global mutable state, feeder imports or future
Actual arrays. Each campaign constructs its own instance and exact evaluator.
P minimization is local exact-AC constrained search; no global claim is made.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize

REVISION = 'QFIRST_MINP_CAUSAL_V1_20260920'
TOL = 1e-9


def ac_constraints(r):
    return np.r_[20*(r['v']-.95),20*(1.05-r['v']),1-r['ipu'],
                 1-r['kva'][np.isfinite(r['kva'])]]


def ac_feasible(r):
    return bool(r['converged'] and r.get('settled',True)
                and np.min(ac_constraints(r)) >= -TOL)


@dataclass(frozen=True)
class Limits:
    pmax: float
    smax: float
    emin: float
    emax: float
    eta_c: float
    eta_d: float
    dt: float
    faces: int = 16


def energy_next(e,p,a):
    return e+a.eta_c*np.maximum(-p,0)*a.dt-np.maximum(p,0)*a.dt/a.eta_d


def q_bounds(p,connected,a):
    h=np.sqrt(np.maximum(0,a.smax*a.smax-p*p))
    lo=-h;hi=h.copy();ap=a.smax*np.cos(np.pi/a.faces)
    for k in range(a.faces):
        co=np.cos(2*np.pi*k/a.faces);si=np.sin(2*np.pi*k/a.faces)
        if si>1e-12:hi=np.minimum(hi,(ap-co*p)/si)
        elif si < -1e-12:lo=np.maximum(lo,(ap-co*p)/si)
        else:assert np.all(co*p<=ap+1e-7)
    return np.where(connected,lo,0.),np.where(connected,hi,0.)


class Controller:
    def __init__(self,limits,initial_energy,q_corrector):
        self.a=limits;self.energy=np.array(initial_energy,dtype=float)
        self.shadow=self.energy.copy();self.q_corrector=q_corrector;self.slot=0

    def p_bounds(self,e,connected,p_da):
        a=self.a;cap=min(a.pmax,a.smax*np.cos(np.pi/a.faces))
        lo=np.maximum(-cap,-np.maximum(0,a.emax-e)/(a.eta_c*a.dt))
        hi=np.minimum(cap,np.maximum(0,e-a.emin)*a.eta_d/a.dt)
        # Preserve the frozen charge/discharge commitment. A zero DA command
        # is not permission to introduce a new charge/discharge commitment.
        lo=np.where(p_da<0,lo,0.);hi=np.where(p_da>0,hi,0.)
        return np.where(connected,lo,0.),np.where(connected,hi,0.)

    def _minimal_p(self,evaluate,p0,q0,q_da,lo,hi,connected):
        a=self.a;idx=np.flatnonzero(connected);n=len(idx);cache={};runs=[]
        if not n:return None,{'status':'NO_CONNECTED_P_VARIABLE'}
        def unpack(x):
            p=p0.copy();q=q0.copy();p[idx]=x[:n]*a.pmax;q[idx]=x[n:2*n]*a.smax
            return p,q
        def ev(x):
            p,q=unpack(x);key=np.r_[p,q].tobytes()
            if key not in cache:cache[key]=(p,q,evaluate(p,q))
            return cache[key][2]
        def cons(x):
            p,q=unpack(x);r=ev(x)
            g=ac_constraints(r) if r['converged'] else np.full_like(ac_constraints(r),-10.)
            pcs=[1-(p[idx]**2+q[idx]**2)/a.smax**2]
            for k in range(a.faces):
                theta=2*np.pi*k/a.faces
                pcs.append(np.cos(np.pi/a.faces)-(p[idx]*np.cos(theta)+q[idx]*np.sin(theta))/a.smax)
            delta=(p[idx]-p0[idx])/a.pmax;u=x[2*n:]
            return np.r_[g,*pcs,u-delta,u+delta]
        bounds=list(zip(lo[idx]/a.pmax,hi[idx]/a.pmax))+[(-1.,1.)]*n+[(0.,2.)]*n
        def point(p,q):return np.r_[p[idx]/a.pmax,q[idx]/a.smax,np.abs(p[idx]-p0[idx])/a.pmax]
        def obj(x):return float(np.sum(x[2*n:]))
        seeds=[point(p0,q0)]
        neutral=np.clip(np.zeros_like(p0),lo,hi)
        lq,hq=q_bounds(neutral,connected,a);seeds.append(point(neutral,np.clip(q_da,lq,hq)))
        for seed in seeds:
            res=minimize(obj,seed,method='SLSQP',bounds=bounds,
                         constraints=[{'type':'ineq','fun':cons}],
                         options={'maxiter':100,'ftol':1e-11,'disp':False})
            ev(res.x);runs.append({'success':bool(res.success),'message':str(res.message),'iterations':int(res.nit)})
        def valid(p,q,r):
            if not ac_feasible(r) or np.any(p<lo-1e-7) or np.any(p>hi+1e-7):return False
            lq,hq=q_bounds(p,connected,a)
            return bool(np.all(q>=lq-1e-7) and np.all(q<=hq+1e-7))
        choices=[v for v in cache.values() if valid(*v)]
        proof={'solver_runs':runs,'unique_trials':len(cache),'global_minimum_proven':False,
               'objective':'lexicographic total absolute delta P, then squared delta Q to frozen DA',
               'optimality':'Best exact-feasible candidate from local constrained searches'}
        if not choices:return None,{**proof,'status':'MINIMAL_P_SEARCH_UNRESOLVED'}
        best=min(choices,key=lambda v:(float(np.abs(v[0]-p0).sum()),float(np.square(v[1]-q_da).sum())))
        bound=float(np.abs(best[0]-p0).sum())/a.pmax+1e-8
        res=minimize(lambda x:float(np.square(unpack(x)[1]-q_da).sum()/a.smax**2),
                     point(best[0],best[1]),method='SLSQP',bounds=bounds,
                     constraints=[{'type':'ineq','fun':cons},{'type':'ineq','fun':lambda x:bound-obj(x)}],
                     options={'maxiter':60,'ftol':1e-11,'disp':False})
        r=ev(res.x);p,q=unpack(res.x)
        if valid(p,q,r) and np.abs(p-p0).sum()/a.pmax<=bound+1e-8:best=(p,q,r)
        return best,{**proof,'status':'P_CORRECTED','sum_absolute_delta_P_kw':float(np.abs(best[0]-p0).sum())}

    def step(self,*,slot,p_da,q_da,connected,travel_energy,evaluate,allow_correct=True):
        assert slot==self.slot,'NONCAUSAL_OR_OUT_OF_ORDER_SLOT'
        a=self.a;p_da=np.asarray(p_da,dtype=float);q_da=np.asarray(q_da,dtype=float)
        connected=np.asarray(connected,dtype=bool);travel=np.asarray(travel_energy,dtype=float)
        before=self.energy.copy();available=before-travel;shadow_available=self.shadow-travel
        if np.any(available<a.emin-1e-7):raise RuntimeError('CAUSAL_DEPARTURE_ENERGY_INFEASIBLE')
        lo,hi=self.p_bounds(available,connected,p_da)
        p0=np.clip(p_da,lo,hi);ql,qh=q_bounds(p0,connected,a);q0=np.clip(q_da,ql,qh)
        sl,sh=self.p_bounds(shadow_available,connected,p_da)
        self.shadow=energy_next(shadow_available,np.clip(p_da,sl,sh),a)
        baseline=evaluate(p0,q0);p=p0.copy();q=q0.copy();r=baseline
        event={'slot':slot,'status':'UNCHANGED','Q_search':None,'P_search':None,
               'current_actual_slot_exposed':slot,'future_actual_rows_exposed':0,
               'baseline_feasible':ac_feasible(baseline),'energy_before_kwh':before.tolist(),
               'travel_energy_kwh':travel.tolist(),'baseline_P_EXEC':p0.tolist()}
        if allow_correct and not ac_feasible(r):
            q,r,proof=self.q_corrector(lambda v:evaluate(p0,v),q0,ql,qh,q_da=q_da)
            event['Q_search']=proof;event['status']=proof['status']
            if not ac_feasible(r):
                # First P domain: only reduce existing charging toward zero.
                clo=p0.copy();chi=np.where(p0<0,0.,p0)
                best,proof=self._minimal_p(evaluate,p0,q,q_da,clo,chi,connected)
                event['P_search']={'charging_curtailment':proof}
                if best is None:
                    best,proof=self._minimal_p(evaluate,p0,q,q_da,lo,hi,connected)
                    event['P_search']['remaining_physical_domain']=proof
                if best is not None:p,q,r=best;event['status']='P_CORRECTED'
                else:p,q,r=p0,q0,baseline;event['status']='HARD_LIMIT_UNRESOLVED'
        recovery=np.zeros_like(p)
        # Repay only accumulated energy deviation, within this slot's frozen
        # commitment and exact headroom. The controller receives no future data.
        if allow_correct and ac_feasible(r):
            debt=self.shadow-energy_next(available,p,a)
            target=p.copy()
            charging=(p_da<0)&connected&(debt>1e-8)
            target[charging]=np.maximum(lo[charging],p[charging]-debt[charging]/(a.eta_c*a.dt))
            excess=(p_da>0)&connected&(debt < -1e-8)
            target[excess]=np.minimum(hi[excess],p[excess]-debt[excess]*a.eta_d/a.dt)
            if np.max(np.abs(target-p))>1e-7:
                original=p.copy();lower=0.;upper=1.;chosen=(p.copy(),q.copy(),r)
                for it in range(22):
                    frac=1. if it==0 else (lower+upper)/2
                    trial=original+frac*(target-original);lq,hq=q_bounds(trial,connected,a)
                    tq=np.clip(q,lq,hq);tr=evaluate(trial,tq)
                    if ac_feasible(tr):lower=frac;chosen=(trial,tq,tr)
                    else:upper=frac
                    if lower==1. or (upper-lower)*np.max(np.abs(target-original))<1e-6:break
                p,q,r=chosen;recovery=p-original
        # Commit selected state even if the last diagnostic trial was rejected.
        r=evaluate(p,q);self.energy=energy_next(available,p,a)
        assert np.all(self.energy>=a.emin-1e-7) and np.all(self.energy<=a.emax+1e-7)
        assert np.all(np.hypot(p,q)<=a.smax+1e-7)
        assert np.all(p[~connected]==0) and np.all(q[~connected]==0)
        event.update(P_EXEC=p.tolist(),Q_EXEC=q.tolist(),delta_P_DA=(p-p_da).tolist(),
                     corrective_delta_P=(p-p0-recovery).tolist(),recovery_P=recovery.tolist(),
                     energy_after_kwh=self.energy.tolist(),energy_deviation_kwh=(self.energy-self.shadow).tolist(),
                     AC_PASS=ac_feasible(r),P_intervention=bool(np.max(np.abs(p-p0))>1e-6),
                     Q_intervention=bool(np.max(np.abs(q-q0))>1e-6))
        self.slot+=1
        return p,q,r,event
