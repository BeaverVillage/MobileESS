"""Single-process, full-domain MILP pricing, bounded root-only CG."""
from .common import *
from .partition import axes
from .models import Block,Master
import time,hashlib
import numpy as np
import gurobipy as gp
from fractions import Fraction as F
from v42_degen.identity import inputs
from v42_disjunctive.certificate import down

PRICE_FIELDS=['call','iteration','dual_SHA','MESS','native_status','OPTIMAL','classification','global_BestBd','validated_reduced_cost','NO_NEGATIVE_COLUMN_CERTIFIED','runtime','wall_seconds','pilot_wall_seconds','nodes','callback_errors','full_domain','log']
COL_FIELDS=['column','iteration','MESS','kind','PASS','integer_exact','local_row_max','bound_max','reduced_cost','coupling_transport_error','added','duplicate','file']
HASH_FIELDS=['column','MESS','SHA256','local_vector_SHA','master_vector_SHA','objective','added','duplicate','file']
RMP_FIELDS=['iteration','status','objective_not_global_LB','runtime','wall_seconds','trajectory_columns','total_master_columns','rows','nnz','dual_SHA','row_max_violation','dual_violation','pilot_wall_seconds','log']

def no_negative(bound):return bound is not None and bound>=-1e-8
def exact_rc(block,x,pi,alpha):
    # c-B'pi is an exact +/-1 sign change at each native injection leaf.
    cost=block.d['objective']-block.B.T@pi
    result=-F(float(alpha))
    for j in np.flatnonzero(cost):result+=F(float(cost[j]))*F(float(x[j]))
    return result

class Pilot:
    def __init__(self):
        gate('pilot_prepare');assert read(OUT/'DW_MATRIX_RECONSTRUCTION_PROOF.json')['PASS'] and read(OUT/'DW_REDUCED_COST_SIGN_PROOF.json')['PASS']
        _,_,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        with np.load(OUT/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        self.blocks=[Block(self.B,self.e,self.owner,self.row_owner,native,m) for m in range(4)]
        self.master=Master(self.B,self.e,self.owner,self.row_owner,native)
        self.prices=[];self.columns=[];self.hashes=[];self.rmps=[];self.duals=[];self.alphas=[];self.dual_iterations=[]
        self.seen=[set() for _ in range(4)];self.last_start=[];self.iteration=0;self.call=0;self.begin=None;self.deadline=None;self.final_certs=[False]*4;self.final_bounds=[None]*4
        self.stop_reason=None;self.status='INCONCLUSIVE';self.certified_lb=None;self.total_solver_wall=0.;self.initial_objective=None
        with np.load(OUT/'DW_INITIAL_COLUMNS.npz') as z:point=z['source_values']
        for m,b in enumerate(self.blocks):
            x=point[b.columns];self.last_start.append(x.copy());assert self.add(m,x,None,None,0,'INITIAL')
        # Actual blocks + coupling pieces must reassemble the native matrix.
        local_nnz=sum(b.A.nnz for b in self.blocks);coupling_nnz=self.master.A.nnz+sum(b.B.nnz for b in self.blocks)
        assert local_nnz+coupling_nnz==self.B.nnz
        assert sum(len(b.rows) for b in self.blocks)+len(self.master.rows)==self.B.shape[0]
        assert sum(len(b.columns) for b in self.blocks)+len(self.master.columns)==self.B.shape[1]
        write('DW_PRICING_MODEL_CENSUS.json',dict(PASS=True,blocks=[b.census() for b in self.blocks],shared_master_columns=len(self.master.columns),global_rows=len(self.master.rows),
              original_all_rows_reconstructed=True,local_nnz=local_nnz,coupling_nnz=coupling_nnz,no_pruned_routes_sites_times=True))
        self.save()
    def elapsed(self):return 0. if self.begin is None else time.perf_counter()-self.begin
    def remaining(self):return 3600-self.elapsed()
    def save(self):
        table('DW_PRICING_RUN_LEDGER.csv',self.prices,PRICE_FIELDS);table('DW_COLUMN_VALIDATION_LEDGER.csv',self.columns,COL_FIELDS)
        table('DW_COLUMN_HASH_LEDGER.csv',self.hashes,HASH_FIELDS);table('DW_RMP_ITERATION_LEDGER.csv',self.rmps,RMP_FIELDS)
        write('DW_LIVE_STATUS.json',dict(iteration=self.iteration,pricing_calls=self.call,initial_columns=4,added_columns=len(self.master.lambdas)-4,
              pilot_wall_seconds=self.elapsed(),remaining_seconds=max(0,self.remaining()),last_pricing=self.prices[-1] if self.prices else None,
              last_RMP=self.rmps[-1] if self.rmps else None,status='RUNNING' if self.stop_reason is None else self.status,stop_reason=self.stop_reason))
    def add(self,m,x,pi,alpha,iteration,kind):
        b=self.blocks[m];checked=b.validate(x,physical=True);a,c,key=b.column(x);exact,error=b.exact_coupling(x,a)
        rc=None if pi is None else float(exact_rc(b,x,pi,alpha));duplicate=key in self.seen[m]
        accepted=bool(checked['PASS'] and error<=1e-12 and (pi is None or rc<=-1e-7) and not duplicate)
        number=len(self.columns);file=f'columns/COLUMN_{number:06d}_{b.unit}.npz';(OUT/'columns').mkdir(exist_ok=True)
        ix=sorted(i for i,q in exact.items() if q)
        np.savez_compressed(OUT/file,local_values=x,original_columns=b.columns,master_coefficients=a,objective=np.asarray(c),
                            exact_rows=np.asarray(ix,dtype=np.int64),exact_numerators=np.asarray([str(exact[i].numerator) for i in ix]),exact_denominators=np.asarray([str(exact[i].denominator) for i in ix]))
        self.columns.append(dict(column=number,iteration=iteration,MESS=b.unit,kind=kind,PASS=checked['PASS'],integer_exact=checked['integer_pattern_exact'],
             local_row_max=checked['raw']['max_constraint_violation'],bound_max=checked['raw']['max_bound_violation'],reduced_cost=rc,coupling_transport_error=error,added=accepted,duplicate=duplicate,file=file))
        self.hashes.append(dict(column=number,MESS=b.unit,SHA256=key,local_vector_SHA=hashlib.sha256(x.tobytes()).hexdigest(),master_vector_SHA=hashlib.sha256(a.tobytes()).hexdigest(),objective=c,added=accepted,duplicate=duplicate,file=file))
        write(f'column_audits/COLUMN_{number:06d}.json',checked)
        if accepted:self.master.add(m,x,a,c,key);self.seen[m].add(key);self.last_start[m]=x.copy() if len(self.last_start)>m else x.copy()
        if kind=='INITIAL':assert accepted
        if error>1e-12:self.stop_reason='NUMERICAL_COUPLING_TRANSPORT_AMBIGUITY'
        if duplicate and rc is not None and rc<=-1e-7:self.stop_reason='NEGATIVE_EXACT_DUPLICATE_AT_OPTIMAL_RMP_DUAL'
        return accepted
    def solve_master(self):
        if self.remaining()<30:self.stop_reason='OVERALL_WALL_BUDGET';return None
        self.iteration+=1;self.final_certs=[False]*4;self.final_bounds=[None]*4
        m=self.master.model
        for k,v in dict(Threads=1,Method=2,Crossover=1,TimeLimit=min(300,self.remaining()-20),FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929).items():m.setParam(k,v)
        log=f'logs/RMP_{self.iteration:04d}.log';(OUT/'logs').mkdir(exist_ok=True);m.Params.LogFile=(OUT.relative_to(ROOT)/log).as_posix()
        self.resource.active_model=m;start=time.perf_counter();m.optimize();wall=time.perf_counter()-start;self.total_solver_wall+=wall;self.resource.active_model=None
        entry=dict(iteration=self.iteration,status=m.Status,objective_not_global_LB=m.ObjVal if m.SolCount else None,runtime=m.Runtime,wall_seconds=wall,
                   trajectory_columns=len(self.master.lambdas),total_master_columns=m.NumVars,rows=m.NumConstrs,nnz=m.NumNZs,dual_SHA=None,row_max_violation=None,dual_violation=None,pilot_wall_seconds=self.elapsed(),log=log)
        self.rmps.append(entry)
        if m.Status!=2:self.stop_reason='RMP_NOT_OPTIMAL';self.save();return None
        checked=self.master.raw_audit();entry['row_max_violation']=checked['master_row_max_violation'];entry['dual_violation']=m.DualVio
        if not checked['PASS'] or m.DualVio>1e-8:self.stop_reason='RMP_NUMERICAL_AUDIT_FAIL';self.save();return None
        pi=np.asarray(m.getAttr('Pi',self.master.coupling));alpha=np.asarray(m.getAttr('Pi',self.master.conv))
        sign_ok=np.all(pi[self.master.d['sense']=='<']<=0) and np.all(pi[self.master.d['sense']=='>']>=0)
        if not sign_ok:self.stop_reason='RMP_DUAL_SIGN_NOT_EXACT';self.save();return None
        digest=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest();entry['dual_SHA']=digest
        self.duals.append(pi);self.alphas.append(alpha);self.dual_iterations.append(self.iteration)
        manual=[c['c']-float(pi@c['a'])-alpha[c['unit']] for c in self.master.column_data]
        native=np.asarray(m.getAttr('RC',self.master.lambdas));assert np.max(abs(np.asarray(manual)-native),initial=0.)<=1e-8
        if self.iteration==1:
            self.initial_objective=m.ObjVal
            assert abs(m.ObjVal-U_REF)<=1e-8,'INITIAL_RMP_OBJECTIVE_REPRODUCTION_FAIL'
            write('DW_INITIAL_RMP_REPRODUCTION.json',dict(PASS=True,status=m.Status,initial_columns=4,objective=m.ObjVal,reference=U_REF,delta=m.ObjVal-U_REF,
                  master_audit=checked,lambda_values=[v.X for v in self.master.lambdas],all_lambdas_one=all(abs(v.X-1)<=1e-8 for v in self.master.lambdas),
                  original_global_rows_kept=True,global_bounds_objective_preserved=True,restricted_objective_is_not_global_LB=True))
        self.save();print('RMP_OPTIMAL',self.iteration,m.ObjVal,len(self.master.lambdas),self.elapsed(),flush=True)
        return pi,alpha,digest
    def pricing(self,m,pi,alpha,dual_SHA,resume=False):
        b=self.blocks[m];model=b.model;self.call+=1
        if not resume:
            b.price(pi,alpha[m]);model.setAttr('Start',b.vars,self.last_start[m].tolist())
        remaining=self.remaining()
        if remaining<30:self.call-=1;self.stop_reason='OVERALL_WALL_BUDGET';return False
        policy=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,MIPGap=0.,MIPGapAbs=0.,
                    TimeLimit=min(600,remaining-20),FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929)
        for k,v in policy.items():model.setParam(k,v)
        log=f'logs/PRICE_{self.call:04d}_{b.unit}.log';model.Params.LogFile=(OUT.relative_to(ROOT)/log).as_posix()
        found=[];errors=[];observations=[]
        def callback(native,where):
            if where!=gp.GRB.Callback.MIPSOL:return
            try:
                x=np.asarray(native.cbGetSolution(b.vars));checked=b.validate(x,physical=False)
                rc=float(exact_rc(b,x,pi,alpha[m]));observations.append(dict(time=float(native.cbGet(gp.GRB.Callback.RUNTIME)),reduced_cost=rc,raw_PASS=checked['PASS'],integer_exact=checked['integer_pattern_exact']))
                if checked['PASS'] and rc<=-1e-7:found.append(x);native.terminate()
            except Exception as error:errors.append(repr(error));native.terminate()
        self.resource.active_model=model;start=time.perf_counter();model.optimize(callback);wall=time.perf_counter()-start;self.total_solver_wall+=wall;self.resource.active_model=None
        bound=finite(model.ObjBound);cert=no_negative(bound) and not errors;added=False;rc=None
        candidates=found[:1]
        if not candidates and model.SolCount:candidates=[np.asarray(model.getAttr('X'))]
        for x in candidates:
            checked=b.validate(x,physical=True);value=float(exact_rc(b,x,pi,alpha[m]));rc=value if checked['PASS'] else None
            if checked['PASS'] and value<=-1e-7:
                added=self.add(m,x,pi,alpha[m],self.iteration,'NEGATIVE_PRICING')
                if cert:self.stop_reason='PRICING_NEGATIVE_POINT_CONTRADICTS_GLOBAL_BOUND';cert=False
            elif not checked['PASS']:
                # Preserve invalid raw candidates; never repair or insert.
                self.add(m,x,pi,alpha[m],self.iteration,'REJECTED_NUMERICAL_CANDIDATE')
        classification='NEGATIVE_COLUMN_FOUND' if added else 'CERTIFIED_NO_COLUMN' if cert else 'INCONCLUSIVE'
        if cert:
            self.final_certs[m]=True;self.final_bounds[m]=bound
        entry=dict(call=self.call,iteration=self.iteration,dual_SHA=dual_SHA,MESS=b.unit,native_status=model.Status,OPTIMAL=model.Status==2,
                   classification=classification,global_BestBd=bound,validated_reduced_cost=rc,NO_NEGATIVE_COLUMN_CERTIFIED=cert,
                   runtime=model.Runtime,wall_seconds=wall,pilot_wall_seconds=self.elapsed(),nodes=model.NodeCount,callback_errors=';'.join(errors),full_domain=True,log=log)
        self.prices.append(entry);write(f'pricing_receipts/PRICE_{self.call:04d}.json',dict(entry,settings=policy,resume_same_full_model=resume,callback_observations=observations,
              global_optimum_claimed=model.Status==2,early_negative_is_not_most_negative=True,timeout_is_not_no_column=True))
        self.save();print('PRICING_DONE',self.call,b.unit,classification,rc,bound,wall,self.elapsed(),flush=True)
        return added
    def certify(self,pi,alpha,dual_SHA):
        assert all(self.final_certs) and all(no_negative(v) for v in self.final_bounds)
        # Exact weak duality on original global rows plus globally valid local
        # MILP pricing bounds. Box residuals of shared variables are paid for.
        import v42_disjunctive.certificate as c
        c.OUT=OUT;c.write=write
        lo,hi=c.enclosures(self.B,self.e)
        proof=c.rational_bound(self.master.A,self.master.d,pi,lo[self.master.columns],hi[self.master.columns],save='DW_GLOBAL_DUAL_CERTIFICATE.npz')
        value=F(int(proof['exact_bound_numerator']),int(proof['exact_bound_denominator']))
        for bound,a in zip(self.final_bounds,alpha):value+=F(float(bound))+F(float(a))-F(1e-8)
        lb=down(value);objective=float(self.master.model.ObjVal)
        if lb<BASE_LB-1e-8:self.status='FAILED';self.stop_reason='CERTIFIED_DW_BOUND_BELOW_ARC_ROOT';return
        if objective-lb>1e-6 or lb>objective+1e-8:self.stop_reason='PRIMAL_CERTIFICATE_NUMERICAL_AMBIGUITY';return
        self.certified_lb=lb;gate_result=material(lb,True);self.status='CERTIFIED' if gate_result['status']=='PASS' else 'NONMATERIAL';self.stop_reason='ALL_FOUR_GLOBAL_PRICING_CERTIFICATES_SAME_DUAL'
        write('DW_ROOT_CERTIFICATE.json',dict(PASS=True,DW_ROOT_OPTIMAL_CERTIFIED=True,status=self.status,same_RMP_dual_SHA=dual_SHA,
              final_pricing_bounds=dict(zip(UNITS,self.final_bounds)),final_pricing_certificates=dict(zip(UNITS,self.final_certs)),
              RMP_objective=objective,L_DW=lb,certified_lower_bound=lb,primal_minus_certified_LB=objective-lb,
              exact_global_weak_duality=proof,exact_bound_numerator=str(value.numerator),exact_bound_denominator=str(value.denominator),
              fixed_pricing_bound_safety_epsilon_each=1e-8,numerical_optimality_scope='User pricing threshold -1e-8 and primal/certified bound agreement <=1e-6; exact global dual arithmetic includes every shared-variable residual. Native global MILP BestBd provides full-domain pricing certificates.',
              proof='Sign-valid original coupling Pi: rho objective >= Pi*h + min_box_z(cz-G^T Pi)*z + sum_m min_Xm(cm-Bm^T Pi)*v. Each pricing BestBd bounds the corresponding local minimum after adding back alpha. Exact Fraction global arithmetic and outward rounding yield L_DW. RMP objective alone is not promoted.'))
    def run(self):
        import v42_single_thread.resources as resources
        resources.OUT=OUT;resources.write=write;resources.ENV=ENV
        self.resource=resources.Timeline('DW_PILOT');once('DW_PILOT');self.begin=time.perf_counter();self.deadline=self.begin+3600
        try:
            while self.stop_reason is None and self.remaining()>30:
                dual=self.solve_master()
                if dual is None:break
                pi,alpha,key=dual;added=False
                for m in range(4):
                    if self.stop_reason:break
                    added=self.pricing(m,pi,alpha,key) or added
                if self.stop_reason:break
                if added:continue
                if all(self.final_certs):self.certify(pi,alpha,key);break
                # Incomplete searches may resume at this frozen dual. Bounds
                # are never carried across dual changes, and domains stay full.
                while self.stop_reason is None and self.remaining()>30 and not all(self.final_certs):
                    for m in range(4):
                        if self.final_certs[m]:continue
                        if self.stop_reason:break
                        added=self.pricing(m,pi,alpha,key,resume=True) or added
                    if added:break
                if self.stop_reason:break
                if not added and all(self.final_certs):self.certify(pi,alpha,key);break
            if self.stop_reason is None:self.stop_reason='OVERALL_WALL_BUDGET'
        except Exception as error:
            self.status='FAILED';self.stop_reason='EXECUTION_OR_GATE_ERROR:'+repr(error)
            write('DW_EXECUTION_ERROR.json',dict(error=repr(error),iteration=self.iteration,pricing_calls=self.call))
            raise
        finally:
            self.resource.close(self.status);self.finish()
            self.master.model.dispose()
            for b in self.blocks:b.model.dispose()
    def finish(self):
        wall=self.elapsed();certified=self.certified_lb is not None and all(self.final_certs)
        if not (OUT/'DW_ROOT_CERTIFICATE.json').exists():
            write('DW_ROOT_CERTIFICATE.json',dict(PASS=False,DW_ROOT_OPTIMAL_CERTIFIED=False,status=self.status,reason=self.stop_reason,
                  final_pricing_certificates=dict(zip(UNITS,self.final_certs)),same_final_dual_only=True,L_DW=None,RMP_objective_is_not_global_LB=True))
        np.savez_compressed(OUT/'DW_DUAL_HISTORY.npz',coupling_duals=np.asarray(self.duals),convexity_duals=np.asarray(self.alphas),iterations=np.asarray(self.dual_iterations))
        result=dict(status=self.status,DW_ROOT_OPTIMAL_CERTIFIED=certified,stop_reason=self.stop_reason,
              CG_iterations=self.iteration,pricing_calls=self.call,pricing_OPTIMAL=sum(r['OPTIMAL'] for r in self.prices),
              negative_column_calls=sum(r['classification']=='NEGATIVE_COLUMN_FOUND' for r in self.prices),certified_no_column_calls=sum(r['NO_NEGATIVE_COLUMN_CERTIFIED'] for r in self.prices),
              inconclusive_calls=sum(r['classification']=='INCONCLUSIVE' for r in self.prices),initial_columns=4,added_columns=len(self.master.lambdas)-4,
              final_trajectory_columns=len(self.master.lambdas),final_master_columns=self.master.model.NumVars,
              final_pricing_certificates=dict(zip(UNITS,self.final_certs)),final_pricing_bounds=dict(zip(UNITS,self.final_bounds)),
              initial_RMP_objective=self.initial_objective,final_RMP_objective=self.rmps[-1]['objective_not_global_LB'] if self.rmps else None,
              RMP_objectives_are_not_global_LBs=True,arc_root_LB=BASE_LB,DW_root_LB=self.certified_lb,material_gate=material(self.certified_lb,certified),
              total_pilot_wall_seconds=wall,total_solver_optimize_wall_seconds=self.total_solver_wall,overall_wall_budget_seconds=3600,wall_budget_PASS=wall<=3600,
              per_call_maximum_TimeLimit=600,sequential_heavy_workers=1,Gurobi_Threads=1,branch_and_price_run=False,production_integer_DW_run=False,P2_RUN=False,A2='NOT_RUN',M2='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',
              campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0)
        write('DW_ROOT_RESULT.json',result);self.save();print('DW_ROOT_DONE',result,flush=True)
if __name__=='__main__':Pilot().run()
