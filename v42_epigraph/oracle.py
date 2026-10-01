"""Full-horizon native MESS plus one original slot's P1 faces, nothing else."""
import math, time, gzip, os, threading
import gurobipy as gp
import psutil
from .common import *

def add_slot_lines(m,c,x,rho):
    from v42_m1_sparse.grid import expr
    cos=np.cos(2*np.pi*np.arange(16)/16);sin=np.sin(2*np.pi*np.arange(16)/16)
    ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
    pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
    raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
    grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
    correction=c.current_matrix.T-grad;bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
    for k,n in enumerate(c.branch_names):
        if n.lower().startswith('transformer.'):continue
        for f in range(16):
            w=(cos[f]*c.flow_p_matrix[k]+sin[f]*c.flow_q_matrix[k])/ap[k]+correction[k]
            b=(cos[f]*c.flow_p_constant[k]+sin[f]*c.flow_q_constant[k])/ap[k]-correction[k]@c.anchor+bias[k]
            m.addConstr(expr(b,w,x)<=rho,name=f'O1_line[{c.slot},{k},{f}]')

def template(t):
    import v42_native.mess as native
    from v42_bootstrap.m1 import OptimizeOnlyBudget
    from v42_bootstrap.grid import coefficients
    bundle,anchor,_,sites,initial,routes,b=inputs();_,coeff=coefficients(bundle)
    def grid(m,p,q):
        rho=m.addVar(lb=0,ub=1,name='rho_max');x=[]
        for i,n in enumerate(coeff[t].control_names):
            s=n.split('[')[1][:-1]
            x.append(float(anchor['controls'][t][i]) if n.startswith('aidc_load_kw') else p[s,t] if n.startswith('mess_p_kw') else q[s,t])
        add_slot_lines(m,coeff[t],x,rho)
        return [('rho',rho),('reserve_shortfall',0.)]
    def capture(m,obj,*args,**kwargs):
        m.setObjective(obj[0][1]);m.update();lb=m.getAttr('LB');ub=m.getAttr('UB')
        m.setAttr('VType',[gp.GRB.CONTINUOUS]*m.NumVars);m.setAttr('LB',lb);m.setAttr('UB',ub);m.update()
        assert all(abs(z)<1e90 for z in lb+ub),'UNBOUNDED_COLUMN_IN_CERTIFICATE'
        m.write(str(LOCAL/f'O1_{t}.mps'))
        dump(f'O1_TEMPLATE_{t}.json',dict(slot=t,rows=m.NumConstrs,columns=m.NumVars,nonzeros=m.NumNZs,binaries=m.NumBinVars,
            template_sha256=sha(LOCAL/f'O1_{t}.mps'),full_horizon_native=True,retained_grid='only original non-transformer P1 line faces at selected slot',
            dropped_grid='all voltage, transformer and other-time line rows',S1_S2_S3_carried=False,build_seconds=time.perf_counter()-begin))
        return None,dict(optimize_calls=0)
    begin=time.perf_counter();old=native.optimize;native.optimize=capture
    try:native.solve('M1',OptimizeOnlyBudget(),sites,initial,routes,b,96,grid)
    finally:native.optimize=old
    print('O1 TEMPLATE',t,read(OUT/f'O1_TEMPLATE_{t}.json'),flush=True)

def finite_bound_certificate(m,pi,primal_objective=None):
    """Box Lagrangian lower bound; finite column bounds absorb all stationarity error.

    pi >= 0 for >= rows and pi <= 0 for <= rows. For any such pi,
    pi*b + min_{l<=x<=u}(c-A'pi)*x <= primal optimum. Sign projection
    changes duals, never the primal model or root data. Conservative IEEE
    roundoff bounds cover sparse dot products; fsum handles scalar sums.
    """
    A=m.getA().tocsc();sense=np.asarray(m.getAttr('Sense'));rhs=np.asarray(m.getAttr('RHS'))
    pi=np.asarray(pi,dtype=float).copy();pi[sense=='<']=np.minimum(pi[sense=='<'],0);pi[sense=='>']=np.maximum(pi[sense=='>'],0)
    lo=np.asarray(m.getAttr('LB'));hi=np.asarray(m.getAttr('UB'));c=np.asarray(m.getAttr('Obj'))
    assert np.isfinite(pi).all() and np.max(abs(lo))<1e90 and np.max(abs(hi))<1e90
    atp=A.T@pi;rc=c-atp;terms=np.minimum(rc*lo,rc*hi)
    eps=np.finfo(float).eps;degree=np.diff(A.indptr);gamma=(degree+2)*eps/(1-(degree+2)*eps)
    dot_error=gamma*(abs(A).T@abs(pi))+eps*(abs(c)+abs(atp))
    rounding=math.fsum(map(float,dot_error*np.maximum(abs(lo),abs(hi))))
    rounding+=eps*math.fsum(map(float,abs(pi*rhs)))+eps*math.fsum(map(float,abs(terms)))
    raw=math.fsum(map(float,pi*rhs))+math.fsum(map(float,terms))+m.ObjCon
    certified=math.nextafter(raw-rounding,-math.inf)
    primal=m.ObjVal if primal_objective is None else primal_objective
    assert certified<=primal+OBJ_TOL
    return certified,dict(raw_lagrangian=raw,roundoff_upper_bound=rounding,certified_lower_bound=certified,
        primal_objective=primal,dual_gap=primal-certified,formula='pi*b + sum min(rc*lb,rc*ub); sign-feasible pi; outward roundoff bound'),pi

class Oracle:
    def __init__(self,t):
        self.t=t;self.env=gp.Env(empty=True);self.env.setParam('OutputFlag',0);self.env.start()
        self.m=gp.read(str(LOCAL/f'O1_{t}.mps'),env=self.env);self.m.Params.Threads=1;self.m.Params.Method=2
        self.m.Params.OutputFlag=1;self.m.Params.LogToConsole=0;self.m.Params.LogFile=''
        _,_,_,sites,initial,routes,_=inputs();self.indices=state_indices(arcs_for(sites,routes),t)
        self.vars={v.VarName:v for v in self.m.getVars()};self.peak=psutil.Process().memory_info().rss
    def expr(self,u,s):return gp.quicksum(self.vars.get(f'arc[{u},{k}]',0.) for k in self.indices[s])
    def solve(self,conditions,kind):
        key=f'{kind}_{self.t}_'+'_'.join(u+'-'+s for u,s in conditions)
        file=OUT/'oracle_certificates'/f'{key}.json';file.parent.mkdir(exist_ok=True)
        if file.exists():return read(file)
        rows=[self.m.addConstr(self.expr(u,s)==1,name=f'condition[{u},{s},{self.t}]') for u,s in conditions]
        self.m.update();messages=[];process=psutil.Process();stop=threading.Event();peak=[process.memory_info().rss];cpu0=process.cpu_times();begin=time.perf_counter()
        def sample():
            while not stop.wait(.1):peak[0]=max(peak[0],process.memory_info().rss)
        thread=threading.Thread(target=sample,daemon=True);thread.start()
        def cb(model,where):
            if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING))
        try:self.m.optimize(cb)
        finally:stop.set();thread.join(1)
        wall=time.perf_counter()-begin;cpu1=process.cpu_times();log=''.join(messages)
        (file.with_suffix('.log.gz')).write_bytes(gzip.compress(log.encode(),mtime=0))
        status=self.m.Status;cert=None;bound=None
        if status==gp.GRB.OPTIMAL:
            bound,cert,pi=finite_bound_certificate(self.m,self.m.getAttr('Pi'))
            nonzero=np.flatnonzero(pi);np.savez_compressed(file.with_suffix('.npz'),indices=nonzero,Pi=pi[nonzero])
            assert self.m.MaxVio<=TOL
        else:assert status==gp.GRB.INFEASIBLE,('ORACLE_NOT_CERTIFIED',key,status)
        result=dict(key=key,kind=kind,slot=self.t,conditions=conditions,status=int(status),optimal=status==gp.GRB.OPTIMAL,
            O1_lower_bound=bound,beta=max(DEFAULT,bound) if bound is not None else DEFAULT,
            conditional_infeasible=status==gp.GRB.INFEASIBLE,infeasible_state_policy='retain structural state with global default; no domain ban',
            certificate=cert,seconds=wall,RSS_bytes=peak[0],pid=os.getpid(),cpu_seconds=(cpu1.user-cpu0.user)+(cpu1.system-cpu0.system),
            rows=self.m.NumConstrs,columns=self.m.NumVars,nonzeros=self.m.NumNZs,Method=2,Threads=1,
            max_violation=self.m.MaxVio if status==gp.GRB.OPTIMAL else None,template_sha256=sha(LOCAL/f'O1_{self.t}.mps'))
        file.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8')
        self.m.remove(rows);self.m.update();self.peak=max(self.peak,peak[0])
        print('ORACLE',key,'LB',bound,'beta',result['beta'],'seconds',round(wall,2),flush=True)
        return result
    def close(self):self.m.dispose();self.env.dispose()

def build_templates():
    for t in read(OUT/'CRITICAL_SLOT_FREEZE.json')['slots']:
        if not (LOCAL/f'O1_{t}.mps').exists():template(t)

if __name__=='__main__':
    import sys
    if sys.argv[1]=='templates':build_templates()
    elif sys.argv[1]=='probe':
        axis=read(OUT/'ROOT_STATE_AXIS.json');t=read(OUT/'CRITICAL_SLOT_FREEZE.json')['slots'][0];u=sorted(inputs()[4])[0]
        s=max(axis[f'{u}:{t}']['root'],key=axis[f'{u}:{t}']['root'].get);o=Oracle(t)
        try:o.solve([(u,s)],'E1')
        finally:o.close()
