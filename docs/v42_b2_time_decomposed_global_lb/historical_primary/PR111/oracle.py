"""Exact W7 conditional LP and separately labelled feasible-upper witnesses."""
from collections import Counter
import math,os,time,threading
import gurobipy as gp
import psutil
from .common import *
from .grid import frozen_window_grid

def certificate_box(m,bindings):
    m.update();lo=np.asarray(m.getAttr('LB'));hi=np.asarray(m.getAttr('UB'));inferred=[]
    for var,expression in bindings:
        if isinstance(expression,gp.Var):
            lower,upper=lo[expression.index],hi[expression.index]
        else:
            expression=gp.LinExpr(expression);lower_terms=[];upper_terms=[]
            for i in range(expression.size()):
                a=expression.getCoeff(i);v=expression.getVar(i);low=lo[v.index];high=hi[v.index]
                assert max(abs(low),abs(high))<1e90
                lower_terms.append(a*(low if a>=0 else high));upper_terms.append(a*(high if a>=0 else low))
            eps=np.finfo(float).eps
            error=4*eps*(math.fsum(abs(x) for x in lower_terms+upper_terms)+abs(expression.getConstant()))
            lower=math.nextafter(expression.getConstant()+math.fsum(lower_terms)-error,-math.inf)
            upper=math.nextafter(expression.getConstant()+math.fsum(upper_terms)+error,math.inf)
        lo[var.index]=max(lo[var.index],lower);hi[var.index]=min(hi[var.index],upper)
        inferred.append(dict(variable=var.VarName,lower=lo[var.index],upper=hi[var.index]))
    assert np.max(abs(lo))<1e90 and np.max(abs(hi))<1e90
    # Only a certificate bounding box: no solver variable bound is changed.
    np.savez_compressed(OUT/'W7_CERTIFICATE_BOX.npz',lower=lo,upper=hi,names=np.asarray(m.getAttr('VarName')))
    dump('W7_IMPLIED_AUXILIARY_BOUND_PROOF.json',dict(PASS=True,solver_bounds_changed=False,original_row_bindings_retained=True,
        reason='Sequential exact affine bindings and original finite physical bounds imply this outward-rounded box for every feasible W7 point. Used only in Lagrangian certificate, never as new model restrictions.',inferred=inferred))

def build():
    import v42_native.mess as native
    from v42_bootstrap.m1 import OptimizeOnlyBudget
    bundle,anchor,_,sites,initial,routes,b=inputs();bindings=[];start=time.perf_counter()
    assert not (LOCAL/'W7.mps').exists()
    def grid(m,p,q):return frozen_window_grid(m,bundle,anchor,p,q,WINDOW,bindings)[0]
    def capture(m,obj,*args,**kwargs):
        m.setObjective(obj[0][1]);m.update();original=Counter(m.getAttr('ConstrName'))
        certificate_box(m,bindings)
        lo=m.getAttr('LB');hi=m.getAttr('UB');m.setAttr('VType',[gp.GRB.CONTINUOUS]*m.NumVars);m.setAttr('LB',lo);m.setAttr('UB',hi);m.update()
        m.write(str(LOCAL/'W7.mps'))
        dump('W7_MATRIX_CENSUS.json',dict(rows=m.NumConstrs,columns=m.NumVars,nonzeros=m.NumNZs,binaries=m.NumBinVars,
            rows_by_family=dict(Counter(n.split('[')[0] for n in m.getAttr('ConstrName'))),window=list(WINDOW),full_horizon_MESS=True,
            all_window_grid_rows_retained=True,solver_auxiliary_bounds_changed=False,source_mps_sha256=sha(LOCAL/'W7.mps'),build_seconds=time.perf_counter()-start))
        return None,dict(optimize_calls=0)
    old=native.optimize;native.optimize=capture
    try:native.solve('M1',OptimizeOnlyBudget(),sites,initial,routes,b,96,grid)
    finally:native.optimize=old
    print('W7 BUILT',read(OUT/'W7_MATRIX_CENSUS.json'),flush=True)

def lower_certificate(m,pi,box,primal=None):
    A=m.getA().tocsc();sense=np.asarray(m.getAttr('Sense'));rhs=np.asarray(m.getAttr('RHS'))
    pi=np.asarray(pi,dtype=float).copy();pi[sense=='<']=np.minimum(pi[sense=='<'],0);pi[sense=='>']=np.maximum(pi[sense=='>'],0)
    lo,hi=box;c=np.asarray(m.getAttr('Obj'));assert np.isfinite(pi).all()
    atp=A.T@pi;rc=c-atp;terms=np.minimum(rc*lo,rc*hi);eps=np.finfo(float).eps;degree=np.diff(A.indptr)
    gamma=(degree+2)*eps/(1-(degree+2)*eps)
    error=gamma*(abs(A).T@abs(pi))+eps*(abs(c)+abs(atp))
    rounding=math.fsum(map(float,error*np.maximum(abs(lo),abs(hi))))+eps*math.fsum(map(float,abs(pi*rhs)))+eps*math.fsum(map(float,abs(terms)))
    raw=math.fsum(map(float,pi*rhs))+math.fsum(map(float,terms))+m.ObjCon
    bound=math.nextafter(raw-rounding,-math.inf);upper=m.ObjVal if primal is None else primal;assert bound<=upper+OBJ_TOL
    return bound,dict(certified_lower_bound=bound,primal_objective=upper,raw_lagrangian=raw,roundoff_upper_bound=rounding,dual_gap=upper-bound,implied_finite_box_used=True),pi

class Oracle:
    def __init__(self):
        self.env=gp.Env(empty=True);self.env.setParam('OutputFlag',0);self.env.start();self.m=gp.read(str(LOCAL/'W7.mps'),env=self.env)
        self.m.Params.Method=2;self.m.Params.Threads=1;self.m.Params.OutputFlag=1;self.m.Params.LogToConsole=0;self.m.Params.LogFile=''
        with np.load(OUT/'W7_CERTIFICATE_BOX.npz',allow_pickle=False) as z:self.box=(z['lower'],z['upper']);assert list(z['names'])==self.m.getAttr('VarName')
        self.variables={v.VarName:v for v in self.m.getVars()};_,_,_,sites,initial,routes,_=inputs();self.arcs=arcs_for(sites,routes);self.sites=sites;self.initial=initial
    def state(self,u,t,a):return gp.quicksum(self.variables.get(f'arc[{u},{k}]',0.) for k in state_indices(self.arcs,t)[a])
    def solve(self,kind,conditions=(),idle=()):
        key=kind+'_'+('_'.join(f'{u}-{t}-{a}' for u,t,a in conditions) if conditions else '-'.join(idle))
        folder=OUT/'oracle_certificates';folder.mkdir(exist_ok=True);p=folder/(key+'.json')
        if p.exists():return read(p)
        restrictions=[self.m.addConstr(self.state(u,t,a)==1,name=f'condition[{u},{t},{a}]') for u,t,a in conditions];changed=[]
        if idle:
            for v in self.m.getVars():
                if any(v.VarName.startswith(f'{prefix}[{u},') for u in idle for prefix in ['arc','Pch','Pdis','Q','charge_mode']):
                    value=0.
                    if v.VarName.startswith('arc['):
                        u,k=v.VarName[4:-1].split(',');k=int(k);value=float(k<len(self.sites)*96 and k//96==self.sites.index(self.initial[u]))
                    changed.append((v,v.LB,v.UB));v.LB=v.UB=value
        self.m.update();process=psutil.Process();cpu0=process.cpu_times();peak=[process.memory_info().rss];stop=threading.Event();messages=[];begin=time.perf_counter()
        def monitor():
            while not stop.wait(.1):peak[0]=max(peak[0],process.memory_info().rss)
        thread=threading.Thread(target=monitor,daemon=True);thread.start()
        def cb(m,where):
            if where==gp.GRB.Callback.MESSAGE:messages.append(m.cbGet(gp.GRB.Callback.MSG_STRING))
        try:self.m.optimize(cb)
        finally:stop.set();thread.join(1)
        wall=time.perf_counter()-begin;status=self.m.Status;cpu1=process.cpu_times();log=''.join(messages)
        p.with_suffix('.log.gz').write_bytes(gzip.compress(log.encode(),mtime=0));bound=cert=upper=None
        if status==gp.GRB.OPTIMAL:
            assert self.m.MaxVio<=TOL
            upper=self.m.ObjVal
            if not idle:
                bound,cert,pi=lower_certificate(self.m,self.m.getAttr('Pi'),self.box)
                nz=np.flatnonzero(pi);np.savez_compressed(p.with_suffix('.dual.npz'),indices=nz,Pi=pi[nz])
            else:np.savez_compressed(p.with_suffix('.upper.npz'),names=np.asarray(self.m.getAttr('VarName')),values=np.asarray(self.m.getAttr('X')))
        else:assert status==gp.GRB.INFEASIBLE,(key,status)
        result=dict(key=key,kind=kind,conditions=conditions,idle_units=idle,status=int(status),O1_W7_lower_bound=bound,
            beta=max(DEFAULT,bound) if bound is not None else DEFAULT,certificate=cert,feasible_upper=upper if idle else None,
            upper_never_used_as_lower_coefficient=bool(idle),seconds=wall,CPU_seconds=(cpu1.user-cpu0.user)+(cpu1.system-cpu0.system),RSS_bytes=peak[0],pid=os.getpid(),
            rows=self.m.NumConstrs,columns=self.m.NumVars,nonzeros=self.m.NumNZs,Method=2,Threads=1,max_violation=self.m.MaxVio if status==gp.GRB.OPTIMAL else None,
            template_sha256=sha(LOCAL/'W7.mps'))
        p.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8')
        for v,lo,hi in changed:v.LB=lo;v.UB=hi
        self.m.remove(restrictions);self.m.update();print('W7',key,'LB',bound,'upper',upper,'seconds',round(wall,2),flush=True)
        return result
    def close(self):self.m.dispose();self.env.dispose()
if __name__=='__main__':build()
