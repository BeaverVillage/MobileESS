from .common import *
from .audit import Block,Master,corrected_rows,pure_binary_equalities
import time,hashlib,math
import numpy as np
import gurobipy as gp
import v42_dw_root.run as original_run
from v42_dw_root.partition import axes
from v42_degen.identity import inputs,signature

class Resume(original_run.Pilot):
    def __init__(self):
        gate('resume_start');commit=verify_execution_freeze();assert read(OUT/'DW_RESUME_CHECKPOINT_AUDIT.json')['PASS']
        assert sha(OUT/'NUMERICAL_GATE_CORRECTION_ADDENDUM.json')==read(OUT/'RESUME_EXECUTION_SOURCE_FREEZE.json')['addendum_SHA']
        LOCAL.mkdir(parents=True,exist_ok=True)
        with (LOCAL/'DW_CORRECTION_RESUME_STARTED.json').open('x',encoding='utf8') as f:json.dump(dict(preopt_commit=commit,restart_from_zero=False),f)
        for k,v in dict(OUT=OUT,write=self.compat_write,table=table,gate=gate).items():setattr(original_run,k,v)
        import v42_single_thread.resources as resources
        resources.OUT=OUT;resources.write=write;resources.ENV=ENV
        self.resource=resources.Timeline('DW_RESUME');self.previous=read(ORIGINAL/'DW_ROOT_RESULT.json');self.previous_wall=self.previous['total_pilot_wall_seconds']
        self.begin=time.perf_counter();self.deadline=self.begin+(3600-self.previous_wall)
        self.A,self.d,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        assert signature(self.B,self.e)==read(ORIGINAL/'DW_BASE_MODEL_IDENTITY.json')['reference']
        with np.load(ORIGINAL/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        self.blocks=[Block(self.B,self.e,self.owner,self.row_owner,native,m) for m in range(4)]
        self.prices=[];self.columns=[];self.hashes=[];self.rmps=[];self.duals=[];self.alphas=[];self.dual_iterations=[]
        self.seen=[set() for _ in range(4)];self.last_start=[None]*4;self.iteration=210;self.call=836;self.final_certs=[False]*4;self.final_bounds=[None]*4
        self.stop_reason=None;self.status='INCONCLUSIVE';self.certified_lb=None;self.total_solver_wall=0.;self.initial_objective=self.previous['initial_RMP_objective']
        build_start=time.perf_counter();self.master=Master(self.B,self.e,self.owner,self.row_owner,native)
        for h in ledger('DW_COLUMN_HASH_LEDGER.csv'):
            m=UNITS.index(h['MESS'])
            with np.load(ORIGINAL/h['file']) as z:
                x=z['local_values'];a=z['master_coefficients'];c=float(z['objective']);key=self.blocks[m].column(x)[2]
                assert key==h['SHA256'];self.master.add(m,x,a,c,key);self.seen[m].add(key);self.last_start[m]=x.copy()
        self.rebuild_seconds=time.perf_counter()-build_start;assert len(self.master.lambdas)==840
        self.route_mask=pure_binary_equalities(self.A,self.d)
        (OUT/'logs').mkdir(exist_ok=True)
        write('DW_RESUME_RMP_BUILD_RECEIPT.json',dict(PASS=True,preopt_source_commit=commit,restored_columns=840,initial_columns=4,generated_columns=836,
              RMP_rebuild_seconds=self.rebuild_seconds,phase_setup_seconds=self.elapsed(),cold_rebuild=True,basis_used=False,failed_iteration_210_dual_reused=False,
              original_row_column_axes_and_coefficients_exact=True,master_rows=self.master.model.NumConstrs,master_columns=self.master.model.NumVars,
              original_base_signature=signature(self.B,self.e),pricing_model_census=[b.census() for b in self.blocks],remaining_after_rebuild=self.remaining(),old_pricing_replay_calls=0))
        self.save()
    @staticmethod
    def compat_write(name,value):
        if name=='DW_ROOT_CERTIFICATE.json':name='DW_CORRECTED_ROOT_CERTIFICATE.json'
        write(name,value)
    def remaining(self):return 3600-self.previous_wall-self.elapsed()
    def save(self):
        if not hasattr(self,'master'):return
        table('DW_RESUME_PRICING_LEDGER.csv',self.prices,original_run.PRICE_FIELDS)
        table('DW_RESUME_COLUMN_VALIDATION_LEDGER.csv',self.columns,original_run.COL_FIELDS)
        table('DW_RESUME_COLUMN_HASH_LEDGER.csv',self.hashes,original_run.HASH_FIELDS)
        fields=original_run.RMP_FIELDS+['full_original_row_max_violation','convexity_max_violation','bound_max_violation','manual_native_RC_max_difference','cumulative_heavy_wall_seconds']
        table('DW_RESUME_ITERATION_LEDGER.csv',self.rmps,fields)
        write('DW_RESUME_LIVE_STATUS.json',dict(global_iteration=self.iteration,new_RMP_solves=len(self.rmps),new_pricing_calls=len(self.prices),new_columns=len(self.master.lambdas)-840,
              restored_columns=840,resumed_wall_seconds=self.elapsed(),cumulative_heavy_wall_seconds=self.previous_wall+self.elapsed(),remaining_seconds=max(0,self.remaining()),
              last_RMP=self.rmps[-1] if self.rmps else None,last_pricing=self.prices[-1] if self.prices else None,status=self.status if self.stop_reason else 'RUNNING',stop_reason=self.stop_reason))
    def solve_master(self):
        if self.remaining()<30:self.stop_reason='ORIGINAL_CUMULATIVE_WALL_BUDGET';return None
        self.iteration+=1;self.final_certs=[False]*4;self.final_bounds=[None]*4;m=self.master.model
        settings=dict(Threads=1,Method=2,Crossover=1,TimeLimit=min(300,self.remaining()-20),FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929)
        for k,v in settings.items():m.setParam(k,v)
        log=f'logs/RMP_{self.iteration:04d}.log';m.Params.LogFile=(OUT.relative_to(ROOT)/log).as_posix()
        self.resource.active_model=m;start=time.perf_counter();m.optimize();wall=time.perf_counter()-start;self.total_solver_wall+=wall;self.resource.active_model=None
        entry=dict(iteration=self.iteration,status=m.Status,objective_not_global_LB=m.ObjVal if m.SolCount else None,runtime=m.Runtime,wall_seconds=wall,
              trajectory_columns=len(self.master.lambdas),total_master_columns=m.NumVars,rows=m.NumConstrs,nnz=m.NumNZs,dual_SHA=None,row_max_violation=None,dual_violation=None,
              pilot_wall_seconds=self.elapsed(),log=log,full_original_row_max_violation=None,convexity_max_violation=None,bound_max_violation=None,manual_native_RC_max_difference=None,cumulative_heavy_wall_seconds=self.previous_wall+self.elapsed())
        self.rmps.append(entry)
        if m.Status!=2:self.stop_reason='RMP_NOT_OPTIMAL';self.save();return None
        checked=self.master.raw_audit();point=np.zeros(self.B.shape[1]);point[self.master.columns]=m.getAttr('X',self.master.z)
        for v,c in zip(self.master.lambdas,self.master.column_data):point[self.blocks[c['unit']].columns]+=float(v.X)*c['x']
        full=corrected_rows(self.A,self.d,point,False,self.route_mask)
        entry.update(row_max_violation=checked['master_row_max_violation'],dual_violation=m.DualVio,full_original_row_max_violation=full['max_constraint_violation'],
                     convexity_max_violation=checked['convexity_max_violation'],bound_max_violation=max(full['max_bound_violation'],checked['bounds_max_violation']))
        np.savez_compressed(OUT/f'RMP_POINT_{self.iteration:04d}.npz',original_reconstructed_point=point,shared_values=np.asarray(m.getAttr('X',self.master.z)),lambda_values=np.asarray(m.getAttr('X',self.master.lambdas)))
        if not checked['PASS'] or not full['PASS'] or m.DualVio>STRICT_TOL:
            self.status='INCONCLUSIVE_NUMERICAL';self.stop_reason='CORRECTED_RMP_NUMERICAL_AUDIT_FAIL';write(f'RMP_AUDIT_{self.iteration:04d}.json',dict(PASS=False,master=checked,full_original=full,settings=settings));self.save();return None
        pi=np.asarray(m.getAttr('Pi',self.master.coupling));alpha=np.asarray(m.getAttr('Pi',self.master.conv))
        sign_ok=np.all(pi[self.master.d['sense']=='<']<=0) and np.all(pi[self.master.d['sense']=='>']>=0)
        if not sign_ok:self.stop_reason='RMP_DUAL_SIGN_NOT_EXACT';self.save();return None
        key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest();entry['dual_SHA']=key
        manual=np.asarray([c['c']-float(pi@c['a'])-alpha[c['unit']] for c in self.master.column_data]);native=np.asarray(m.getAttr('RC',self.master.lambdas))
        error=float(np.max(abs(manual-native),initial=0.));entry['manual_native_RC_max_difference']=error
        if error>STRICT_TOL:self.stop_reason='REDUCED_COST_SIGN_NUMERICAL_AUDIT_FAIL';self.save();return None
        self.duals.append(pi);self.alphas.append(alpha);self.dual_iterations.append(self.iteration)
        write(f'RMP_AUDIT_{self.iteration:04d}.json',dict(PASS=True,master=checked,full_original=full,settings=settings,new_dual_SHA=key,failed_iteration_210_dual_reused=False,manual_native_RC_max_difference=error))
        self.save();print('RESUME_RMP_OPTIMAL',self.iteration,m.ObjVal,entry['row_max_violation'],self.elapsed(),flush=True);return pi,alpha,key
    def certify(self,pi,alpha,key):
        if self.remaining()<60:self.stop_reason='EXACT_CERTIFICATE_AUDIT_REMAINING_BUDGET_INSUFFICIENT';return
        super().certify(pi,alpha,key)
    def run(self):
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
                while self.stop_reason is None and self.remaining()>30 and not all(self.final_certs):
                    for m in range(4):
                        if self.final_certs[m] or self.stop_reason:continue
                        added=self.pricing(m,pi,alpha,key,resume=True) or added
                    if added:break
                if self.stop_reason:break
                if not added and all(self.final_certs):self.certify(pi,alpha,key);break
            if self.stop_reason is None:self.stop_reason='ORIGINAL_CUMULATIVE_WALL_BUDGET'
        except Exception as error:
            self.status='FAILED';self.stop_reason='RESUME_EXECUTION_ERROR:'+repr(error);write('DW_RESUME_EXECUTION_ERROR.json',dict(error=repr(error)));raise
        finally:
            self.resource.close(self.status);self.finish();self.master.model.dispose()
            for b in self.blocks:b.model.dispose()
    def finish(self):
        wall=self.elapsed();certified=self.certified_lb is not None and all(self.final_certs)
        if not (OUT/'DW_CORRECTED_ROOT_CERTIFICATE.json').exists():
            write('DW_CORRECTED_ROOT_CERTIFICATE.json',dict(PASS=False,DW_ROOT_OPTIMAL_CERTIFIED=False,status=self.status,reason=self.stop_reason,L_DW=None,final_pricing_certificates=dict(zip(UNITS,self.final_certs)),incomplete_RMP_objective_not_global_LB=True))
        np.savez_compressed(OUT/'DW_RESUME_DUAL_HISTORY.npz',coupling_duals=np.asarray(self.duals),convexity_duals=np.asarray(self.alphas),iterations=np.asarray(self.dual_iterations))
        result=dict(status=self.status,stop_reason=self.stop_reason,original_pilot_status='INCONCLUSIVE',original_pilot_preserved=True,checkpoint_columns=840,
              new_RMP_solves=len(self.rmps),new_pricing_calls=len(self.prices),new_validated_columns=len(self.master.lambdas)-840,
              cumulative_RMP_calls=210+len(self.rmps),cumulative_pricing_calls=836+len(self.prices),cumulative_columns=len(self.master.lambdas),final_master_columns=self.master.model.NumVars,
              original_heavy_wall_seconds=self.previous_wall,resumed_heavy_wall_seconds=wall,cumulative_heavy_wall_seconds=self.previous_wall+wall,remaining_original_budget_seconds=max(0,self.remaining()),wall_budget_PASS=self.previous_wall+wall<=3600,
              RMP_rebuild_seconds=self.rebuild_seconds,first_resumed_RMP_objective=self.rmps[0]['objective_not_global_LB'] if self.rmps else None,
              first_resumed_RMP_max_residual=self.rmps[0]['row_max_violation'] if self.rmps else None,last_RMP_objective=self.rmps[-1]['objective_not_global_LB'] if self.rmps else None,
              last_RMP_max_residual=self.rmps[-1]['row_max_violation'] if self.rmps else None,total_new_solver_optimize_wall=self.total_solver_wall,
              DW_ROOT_OPTIMAL_CERTIFIED=certified,DW_root_LB=self.certified_lb,material_gate=material(self.certified_lb,certified),final_pricing_certificates=dict(zip(UNITS,self.final_certs)),
              failed_iteration_210_dual_reused=False,old_pricing_replay_calls=0,restarted_from_zero=False,postsolve_audit_tolerance=POST_TOL,solver_tolerance=STRICT_TOL,
              no_column_BestBd_threshold=-1e-8,negative_column_threshold=-1e-7,branch_and_price_run=False,production_M1_run=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,
              campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0)
        write('DW_CORRECTED_ROOT_RESULT.json',result);self.save();print('DW_RESUME_DONE',result,flush=True)
if __name__=='__main__':Resume().run()
