"""Continuous RMP with inherited global physics and elastic initialization."""
from collections import defaultdict
from time import perf_counter
import numpy as np
import gurobipy as gp
from v42_compact.native import grid
from v42_final.reserve import risk_exposure
from .column import METRICS
from .common import require, PHASE1_TOL

class Master:
    def __init__(self,factory,initial,fixed,grid_binder=None,context=None,phase1=True):
        started=perf_counter();self.factory=factory;self.rows={};self.columns={};self.variables={};self.levels=[]
        self.m=gp.Model('V42_DW_CONTINUOUS_RMP');m=self.m
        m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=20260929
        m.Params.FeasibilityTol=1e-9;m.Params.OptimalityTol=1e-9
        self.artificial=[];self.phase1_zero=False;self.artificial_expr=gp.LinExpr();self.locks=[]
        r=factory.r;tail=max(b.latest_completion for b in factory.bounds.values());known={};risk={}
        fg=defaultdict(float);fr=defaultdict(float);fw=defaultdict(float);fa=defaultdict(float);fm=defaultdict(float)
        for c in fixed.values():
            for target,source in ((fg,c.gpu),(fr,c.risk),(fw,c.wan),(fa,c.active),(fm,c.metrics)):
                for key,v in source.items():target[key]+=v
        if factory.bundle:
            bundle=factory.bundle
            for uid,row in factory.raw.items():
                if uid not in factory.jobs:
                    for key,n in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():fr[key]+=bundle['runtime_reserve_gamma']*n
        for k,cap in r.capacities.items():
            for t in range(tail):
                known[k,t]=m.addVar(lb=0,ub=cap,name=f'known_GPU[{k},{t}]')
                self.row(('GPU',k,t),known[k,t]==r.fixed_gpu.get((k,t),0)+fg[k,t])
            for t in range(120) if grid_binder else range(24,120):
                risk[k,t]=m.addVar(lb=0,name=f'runtime_target[{k},{t}]')
                self.row(('RISK',k,t),risk[k,t]==fr[k,t])
        for (l,t),rate in r.wan_capacities.items():self.row(('WAN',l,t),gp.LinExpr()<=rate-r.fixed_wan.get((l,t),0)-fw[l,t])
        for t in range(r.control_end):self.row(('ACTIVE',t),gp.LinExpr()<=r.max_active_transfers-r.fixed_transfers.get(t,0)-fa[t])
        for uid in sorted(initial):self.row(('CONVEXITY',uid),gp.LinExpr()==1)
        metric={n:m.addVar(lb=0,name=n) for n in METRICS}
        for n,v in metric.items():self.row(('METRIC',n),v==fm[n])
        if grid_binder:
            primary=grid_binder(m,known,risk)
        else:
            primary,timing,self.controls=grid(m,factory.bundle,known,risk)
            primary += [('CC4_reference_deviation',timing['deviation'])]
        self.levels=primary+list(metric.items());m.update();self.global_rows=m.NumConstrs
        for c in initial.values():self.add(c)
        m.update();self.physical_size=self.size();self.global_build_seconds=perf_counter()-started
        if context:context.progress(dict(phase='RMP_PHYSICAL_BUILT',**self.physical_size))
        if phase1:self.elasticize(context)
        self.initial_size=self.size();self.build_seconds=perf_counter()-started

    def row(self,key,expression):
        self.rows[key]=self.m.addConstr(expression,name='DW_'+str(key));return self.rows[key]

    def add(self,c,vtype=gp.GRB.CONTINUOUS):
        if c.signature in self.columns:return False
        require(not self.factory.graphs[c.job_id].fixed,'NO_LAMBDA_FOR_SINGLETON')
        coefficients=c.master_coefficients()
        require(set(coefficients)<=set(self.rows),'UNREGISTERED_COLUMN_ROW')
        v=self.m.addVar(lb=0,vtype=vtype,obj=0,column=gp.Column(list(coefficients.values()),[self.rows[k] for k in coefficients]),name=f'lambda[{c.job_id},{c.signature[:16]}]')
        self.columns[c.signature]=c;self.variables[c.signature]=v;return True

    def elasticize(self,context=None):
        """Scaled generic L1 feasibility objective, excluding exact convexity."""
        m=self.m;m.update();constraints=m.getConstrs();A=m.getA()
        maxima=np.asarray(abs(A).max(axis=1).toarray()).ravel()
        rhs=m.getAttr('RHS',constraints);senses=m.getAttr('Sense',constraints)
        convexity={row.index for key,row in self.rows.items() if key[0]=='CONVEXITY'}
        metadata=[]
        for i,row in enumerate(constraints):
            if i in convexity:continue
            scale=max(1.,abs(rhs[i]),float(maxima[i]))
            signs=(1.,-1.) if senses[i]=='=' else ((-1.,) if senses[i]=='<' else (1.,))
            for sign in signs:metadata.append((row,sign*scale))
        variables=m.addVars(len(metadata),lb=0,obj=1.,name='phase1_artificial')
        for i,(row,coefficient) in enumerate(metadata):
            m.chgCoeff(row,variables[i],coefficient)
            if context and i%20000==0:context.check()
        self.artificial=list(variables.values());self.artificial_expr=gp.quicksum(self.artificial)
        m.update()

    def disable_artificial(self):
        require(self.m.SolCount>0 and self.artificial_expr.getValue()<=PHASE1_TOL,'POSITIVE_PHASE1_NOT_PHYSICAL')
        self.m.setAttr('UB',self.artificial,[0.]*len(self.artificial));self.m.update();self.phase1_zero=True

    def duals(self):
        require(self.m.Status==gp.GRB.OPTIMAL,'NONOPTIMAL_MASTER_HAS_NO_PRICING_CERTIFICATE')
        keys=list(self.rows);return dict(zip(keys,self.m.getAttr('Pi',[self.rows[k] for k in keys])))

    def lock(self,name,expr,value):
        self.locks.append(self.m.addConstr(expr<=value+(1e-7 if name=='rho' else 1e-8),name='DW_LOCK_'+name))
        self.m.update()

    def size(self):
        self.m.update()
        return dict(columns=len(self.columns),variables=self.m.NumVars,constraints=self.m.NumConstrs,nonzeros=self.m.NumNZs,binaries=self.m.NumBinVars)

    def dispose(self):self.m.dispose()
