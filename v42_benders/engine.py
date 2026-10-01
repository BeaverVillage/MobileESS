"""Sequential master/LP loop. Only certified cuts and validated points count."""
from time import perf_counter
import numpy as np
import gurobipy as gp
from .certificates import create,verify,Uncertifiable

def relative_gap(upper,lower):
    if upper is None or lower is None:return None
    if not np.isfinite([upper,lower]).all():return None
    if lower>upper+1e-7:raise Uncertifiable('GLOBAL_BOUND_CONTRADICTION')
    return max(0.,upper-lower)/max(abs(upper),1e-10)

def configure(m,threads,time_limit,log=None):
    m.Params.OutputFlag=1 if log else 0
    m.Params.LogToConsole=0
    if log:m.Params.LogFile=str(log)
    for name,value in dict(Threads=threads,Seed=20260929,Method=1,NodeMethod=1,
        FeasibilityTol=1e-7,OptimalityTol=1e-7,IntFeasTol=1e-7,NumericFocus=1,
        InfUnbdInfo=1,DualReductions=0,SoftMemLimit=12.,MIPGap=0.,TimeLimit=max(.001,time_limit)).items():
        setattr(m.Params,name,value)

class Recourse:
    def __init__(self,can,env,threads=1,objective=True,log=None):
        self.can=can;self.model=gp.Model('EXACT_CONTINUOUS_RECOURSE',env=env)
        m=self.model;configure(m,threads,1,log)
        self.y=m.addMVar(len(can.yi),lb=-gp.GRB.INFINITY,ub=gp.GRB.INFINITY,vtype='C',name='y')
        self.rows=m.addMConstr(can.A,self.y,'<',can.b,name='canonical')
        m.setObjective((can.c@self.y+can.objective_constant) if objective else 0.)
        m.update()
        assert m.NumIntVars==m.NumQConstrs==m.NumSOS==m.NumGenConstrs==0
        self.messages=[];self.objective=objective

    def solve(self,x,seconds=60):
        m=self.model;self.rows.RHS=self.can.rhs(x);m.Params.TimeLimit=max(.001,seconds)
        warnings=[]
        def callback(model,where):
            if where==gp.GRB.Callback.MESSAGE:
                message=model.cbGet(gp.GRB.Callback.MSG_STRING).strip()
                if any(t in message.lower() for t in ['warning','numerical','quad precision','dropped']):warnings.append(message)
        m.optimize(callback)
        row=dict(status=m.Status,seconds=m.Runtime,primal_residual=None,dual_residual=None,
            Farkas_residual=None,warnings=warnings,feasibility_tolerance=m.Params.FeasibilityTol,
            optimality_tolerance=m.Params.OptimalityTol,objective=None)
        y=None;w=None
        if m.Status==gp.GRB.OPTIMAL:
            y=np.asarray(self.y.X);row['objective']=m.ObjVal
            row['primal_residual']=self.can.residual(x,y)
            w=np.asarray(self.rows.Pi);row['dual_residual']=float(np.max(abs((self.can.c if self.objective else 0)-self.can.A.T@w),initial=0))
            # Feasibility recourse has zero c; dual is unused in that stage.
            if row['primal_residual']>1e-7:raise Uncertifiable('RECOURSE_PRIMAL_RESIDUAL')
        elif m.Status==gp.GRB.INFEASIBLE:
            try:w=np.asarray(self.rows.FarkasDual)
            except gp.GurobiError as e:raise Uncertifiable('FARKAS_UNAVAILABLE') from e
            row['Farkas_residual']=float(np.max(abs(self.can.A.T@w),initial=0))
        self.messages.extend(warnings)
        return row,y,w

    def close(self):self.model.dispose()

def solve(can,*,env,seconds=60,threads=1,feasibility=False,known=(),warm_start=None,
          validate=None,progress=None,log_dir=None,movement=None,count=None,accepted_p1=None,
          initial_lower=0.,initial_upper=None,target_gap=.005):
    """P1 or threshold feasibility; P2 supplies movement/count and locked can.

    No callback lazy heuristic: every master candidate gets an independent LP.
    Objective bounds count only after master terminal/limited solve with finite
    ObjBound; no LP limit status produces a cut. Cuts persist across P2 levels.
    """
    started=perf_counter();master=gp.Model('EXACT_DISCRETE_MASTER',env=env)
    configure(master,threads,seconds,None if log_dir is None else log_dir/'master.log')
    x=master.addMVar(len(can.xi),lb=can.xlower,ub=can.xupper,vtype='B',name='x')
    dr=can.discrete_rows
    master.addMConstr(can.B[dr],x,'<',can.b[dr],name='original_discrete')
    p2=movement is not None
    if p2 and accepted_p1 is None:raise ValueError('P2_REQUIRES_ACCEPTED_P1')
    theta=None if feasibility or p2 else master.addVar(lb=initial_lower,name='theta')
    if warm_start is not None:
        z=np.asarray(warm_start)
        if len(z)!=len(can.names) or not np.isfinite(z).all():raise ValueError('WARM_START_AXIS')
        if np.max(abs(z[can.xi]-np.rint(z[can.xi])),initial=0)>1e-7:raise ValueError('WARM_START_BINARY')
        if can.residual(z[can.xi],z[can.yi])>1e-6:raise ValueError('WARM_START_NOT_FEASIBLE')
        x.Start=z[can.xi]
        if theta is not None:theta.Start=float(can.c@z[can.yi]+can.objective_constant)
    objectives=[('movement_energy',movement),('movement_count',count)] if p2 else [('feasibility',None)] if feasibility else [('rho',None)]
    lp=Recourse(can,env,threads,not(feasibility or p2),None if log_dir is None else log_dir/'recourse.log')
    cuts=[];hashes=set();logs=[];history=[];upper=initial_upper;lower=initial_lower
    best=None;levels=[];status='TIME_LIMIT';master_time=0.;recourse_time=0.;iteration=0
    try:
        for level,coeff in objectives:
            master.setObjective(coeff@x if p2 else 0. if feasibility else theta)
            level_complete=False
            while perf_counter()-started<seconds:
                iteration+=1;remaining=seconds-(perf_counter()-started)
                master.Params.TimeLimit=max(.001,remaining);master.optimize();master_time+=master.Runtime
                mr=dict(iteration=iteration,level=level,master_status=master.Status,master_seconds=master.Runtime,
                    wall_seconds=perf_counter()-started,recourse_status=None,cut_id=None,lower=None,upper=upper)
                if master.Status==gp.GRB.INFEASIBLE:
                    status='MASTER_INFEASIBLE';history.append(mr);break
                if master.Status in [gp.GRB.NUMERIC,gp.GRB.INTERRUPTED,gp.GRB.INF_OR_UNBD]:
                    status='UNSAFE_MASTER_STATUS';history.append(mr);break
                if not feasibility and not p2:
                    bd=float(master.ObjBound)
                    if np.isfinite(bd) and abs(bd)<1e90:lower=max(lower,bd)
                    mr['lower']=lower
                if not master.SolCount:
                    status='TIME_LIMIT';history.append(mr);break
                xv=np.asarray(x.X)
                if np.max(abs(xv-np.rint(xv)),initial=0)>1e-7:raise Uncertifiable('MASTER_NOT_INTEGER')
                # Candidate snapping is representational only, checked in recourse.
                xv=np.rint(xv)
                for cut in cuts:
                    value=cut['record']['intercept']+float(cut['coefficients']@xv)
                    if cut['record']['type']=='optimality':value=float(theta.X)-value
                    cut['record']['active_inactive_history'].append(dict(iteration=iteration,slack=value,active=abs(value)<=1e-7))
                remaining=seconds-(perf_counter()-started)
                if remaining<=0:history.append(mr);break
                rr,y,w=lp.solve(xv,remaining);recourse_time+=rr['seconds'];rr.update(iteration=iteration,level=level)
                logs.append(rr);mr['recourse_status']=rr['status']
                if rr['status'] not in [gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE]:
                    status='RECOURSE_NONTERMINAL_NO_CUT';history.append(mr);break
                if rr['status']==gp.GRB.OPTIMAL:
                    z=can.assemble(xv,y)
                    check=validate(z) if validate else {'PASS':can.residual(xv,y)<=1e-7}
                    if not check.get('PASS',False):raise Uncertifiable('ASSEMBLED_POINT_VALIDATION')
                    value=rr['objective']
                    if feasibility or p2:
                        best=z
                        if feasibility:status='VALIDATED_WITNESS';level_complete=True
                        elif master.Status==gp.GRB.OPTIMAL:
                            optimum=float(coeff@xv);levels.append(dict(level=level,objective=optimum,complete=True))
                            if level=='movement_energy':master.addConstr(coeff@x<=optimum+1e-8,name='energy_lex_lock')
                            status='P2_LEX_COMPLETE' if level=='movement_count' else 'P2_ENERGY_COMPLETE'
                            level_complete=True
                        else:status='P2_UNPROVEN_CANDIDATE'
                        history.append(mr)
                        if progress:progress(mr,rr,cuts)
                        break
                    if upper is None or value<upper:upper=value;best=z
                    if relative_gap(upper,lower)<=target_gap or (target_gap==0 and upper-lower<=1e-7):
                        status='P1_GAP_TARGET';level_complete=True;history.append(mr)
                        if progress:progress(mr,rr,cuts)
                        break
                    cut=create(can,w,xv,'optimality',rr['status'],iteration,value)
                else:cut=create(can,w,xv,'feasibility',rr['status'],iteration)
                audit=verify(can,cut,known);cut['record']['independent_validation']=audit
                # verify ignores only its runtime annotation when called again.
                if cut['record']['cut_hash'] in hashes:raise Uncertifiable('DUPLICATE_CUT_WITH_UNRESOLVED_SOURCE')
                hashes.add(cut['record']['cut_hash']);cuts.append(cut)
                affine=cut['record']['intercept']+cut['coefficients']@x
                master.addConstr(affine>=0 if cut['record']['type']=='feasibility' else theta>=affine,name=cut['record']['id'])
                mr.update(cut_id=cut['record']['id'],upper=upper,lower=lower if not feasibility and not p2 else None,
                    wall_seconds=perf_counter()-started)
                history.append(mr)
                if progress:progress(mr,rr,cuts)
            if not level_complete:break
    except Uncertifiable as e:
        status='STOP_UNCERTIFIABLE';history.append(dict(iteration=iteration,reason=str(e)))
    finally:
        lp.close();master.dispose()
    result=dict(status=status,iterations=iteration,recourse_calls=len(logs),
        feasibility_cuts=sum(c['record']['type']=='feasibility' for c in cuts),
        optimality_cuts=sum(c['record']['type']=='optimality' for c in cuts),
        upper=upper,lower=lower if not feasibility and not p2 else None,
        relative_gap=relative_gap(upper,lower) if not feasibility and not p2 else None,
        master_seconds=master_time,recourse_seconds=recourse_time,wall_seconds=perf_counter()-started,
        progress=history,recourse_log=logs,levels=levels,cut_records=[c['record'] for c in cuts],
        accepted=False,P2_complete=status=='P2_LEX_COMPLETE',no_cut_deletion=True,sequential=True)
    return result,best,cuts
