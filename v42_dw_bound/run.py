"""Preregistered full-domain optimum/global-bound pricing; one native worker."""
from .common import *
from .certificate import global_dual,receipt,decide
from v42_dw_resume.audit import Block,Master,corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_dw_root.run import exact_rc
from v42_degen.identity import inputs,signature,digest
from fractions import Fraction as F
import numpy as np
import gurobipy as gp

class Experiment:
    def __init__(self):
        gate('scientific_start');self.commit=verify_freeze()
        assert read(OUT/'DW_BOUND_CHECKPOINT_AUDIT.json')['PASS'] and read(OUT/'DW_DUAL_SIGN_AND_BOUND_PROOF.json')['PASS']
        LOCAL.mkdir(exist_ok=True)
        with (LOCAL/'DW_CERTIFIED_DUAL_BOUND_STARTED.json').open('x',encoding='utf8') as f:json.dump(dict(preopt_commit=self.commit,base=BASE,new_budget=3600),f)
        import v42_single_thread.resources as resources
        resources.OUT=OUT;resources.write=write;resources.ENV=ENV
        self.resource=resources.Timeline('DW_BOUND');self.begin=time.perf_counter();self.heavy=0.;self.iteration=0;self.call=0
        self.rmps=[];self.prices=[];self.brackets=[];self.column_records=[];self.basis_records=[];self.start_records=[]
        self.bestL=None;self.bestU=None;self.materiality='INCONCLUSIVE';self.converged=False;self.stop=None;self.basis=None;self.price_context=[None]*4;self.optimal_starts=[None]*4
        start=time.perf_counter();self.A,self.d,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        assert signature(self.B,self.e)==read(OUT/'DW_BOUND_CHECKPOINT_AUDIT.json')['reference_signature']
        with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        self.blocks=[Block(self.B,self.e,self.owner,self.row_owner,native,m) for m in range(4)]
        self.master=Master(self.B,self.e,self.owner,self.row_owner,native);self.seen=[set() for _ in range(4)]
        for directory,h in pool():
            m=UNITS.index(h['MESS'])
            with np.load(directory/h['file']) as z:
                x=z['local_values'];a=z['master_coefficients'];c=float(z['objective']);key=h['SHA256']
                assert self.blocks[m].column(x)[2]==key;self.master.add(m,x,a,c,key);self.seen[m].add(key)
        assert len(self.master.lambdas)==1048;self.build_seconds=time.perf_counter()-start
        self.route_mask=pure_binary_equalities(self.A,self.d)
        import v42_disjunctive.certificate as enclosure
        enclosure.OUT=OUT;enclosure.write=write;start=time.perf_counter();self.lo,self.hi=enclosure.enclosures(self.B,self.e);self.enclosure_seconds=time.perf_counter()-start
        (OUT/'logs').mkdir(exist_ok=True)
        census=[b.census() for b in self.blocks];old=read(RESUME/'DW_RESUME_RMP_BUILD_RECEIPT.json')['pricing_model_census']
        assert all(a['signature']==b['signature'] for a,b in zip(census,old))
        write('DW_BOUND_BUILD_RECEIPT.json',dict(PASS=True,base=BASE,preopt_source_commit=self.commit,restored=1048,cold=True,old_basis_used=False,failed_terminal_dual_used=False,old_pricing_replay=0,
          build_seconds=self.build_seconds,enclosure_audit_seconds=self.enclosure_seconds,new_solver_bounds=0,master_rows=self.master.model.NumConstrs,master_columns=self.master.model.NumVars,pricing_census=census))
        self.save()
    def elapsed(self):return time.perf_counter()-self.begin
    def remaining(self):return 3600-self.heavy
    def optimize(self,model,callback=None):
        assert model.Params.Threads==1 and self.remaining()>3
        self.resource.active_model=model;t=time.perf_counter()
        try:
            if callback is None:model.optimize()
            else:model.optimize(callback)
        finally:self.heavy+=time.perf_counter()-t;self.resource.active_model=None
    def save(self):
        table('DW_OPTIMAL_PRICING_LEDGER.csv',self.prices,['call','iteration','dual_SHA','MESS','native_status','classification','ObjVal','ObjBound','ObjBoundC','MIPGap','valid_bound','rc_opt','runtime','wall_seconds','nodes','fingerprint','objective_SHA','first_negative_observed_seconds','receipt'])
        table('DW_RMP_LEDGER.csv',self.rmps,['iteration','status','objective','dual_SHA','wall_seconds','runtime','warm','master_row_max','full_row_max','bound_max','manual_RC_error','heavy_seconds','primal_SHA','point_file','basis_file'])
        table('DW_CORRECTED_BOUND_ITERATION.csv',[{k:b.get(k) for k in ('iteration','round','dual_SHA','certified','L_corr','U_RMP','materiality')} for b in self.brackets],['iteration','round','dual_SHA','certified','L_corr','U_RMP','materiality'])
        table('DW_ROOT_BOUND_BRACKET.csv',[dict(iteration=b['iteration'],round=b['round'],L=b['L_corr'],U=b['U_RMP'],certified=b['certified'],dual_SHA=b['dual_SHA']) for b in self.brackets],['iteration','round','L','U','certified','dual_SHA'])
        table('DW_NEW_COLUMN_LEDGER.csv',self.column_records,['number','iteration','MESS','SHA256','file','rc_opt','pricing_call','added','duplicate'])
        write('DW_RMP_WARMSTART_AUDIT.json',dict(PASS=True,hints=self.basis_records,same_rows_old_columns_unchanged=True,append_only=True,parameter_sweep=False))
        write('DW_PRICING_WARMSTART_AUDIT.json',dict(PASS=True,hints=self.start_records,previous_OPTIMAL_only=True,new_bounds_or_fixing=0,full_domain_preserved=True))
        write('DW_BOUND_LIVE_STATUS.json',dict(iteration=self.iteration,new_RMP=len(self.rmps),new_pricing=len(self.prices),new_columns=len(self.column_records),heavy_seconds=self.heavy,remaining_heavy_seconds=self.remaining(),elapsed_including_build_audit=self.elapsed(),best_L=self.bestL,best_U=self.bestU,materiality=self.materiality,stop=self.stop,last_pricing=self.prices[-1] if self.prices else None))
    def solve_master(self):
        if self.remaining()<5:self.stop='HEAVY_BUDGET';return None
        self.iteration+=1;model=self.master.model;warm=self.basis is not None
        if warm:
            vb,cb,keys=self.basis;assert keys==[c['key'] for c in self.master.column_data[:len(keys)]] and len(cb)==model.NumConstrs
            model.setAttr('VBasis',self.master.z+self.master.lambdas,vb+[-1]*(model.NumVars-len(vb)));model.setAttr('CBasis',model.getConstrs(),cb);model.update()
        settings=dict(Threads=1,Method=2,Crossover=1,PreDual=0,BarConvTol=1e-11,Seed=20260929,FeasibilityTol=EPS,OptimalityTol=EPS,IntFeasTol=EPS,TimeLimit=min(300,self.remaining()-3))
        for k,v in settings.items():model.setParam(k,v)
        log=f'logs/RMP_{self.iteration:04d}.log';model.Params.LogFile=(OUT.relative_to(ROOT)/log).as_posix();start=time.perf_counter();self.optimize(model);wall=time.perf_counter()-start
        self.basis_records.append(dict(iteration=self.iteration,cold=not warm,basis_supplied=warm,previous_OPTIMAL_only=True,solver_acceptance='not exposed as a native attribute; hint supply and raw log preserved',runtime=model.Runtime,wall_seconds=wall,iterations=model.IterCount))
        row=dict(iteration=self.iteration,status=model.Status,objective=None,dual_SHA=None,wall_seconds=wall,runtime=model.Runtime,warm=warm,master_row_max=None,full_row_max=None,bound_max=None,manual_RC_error=None,heavy_seconds=self.heavy,primal_SHA=None,point_file=None,basis_file=None);self.rmps.append(row)
        if model.Status!=2:self.stop='RMP_NOT_OPTIMAL';self.save();return None
        checked=self.master.raw_audit();point=np.zeros(self.B.shape[1]);point[self.master.columns]=model.getAttr('X',self.master.z)
        for v,c in zip(self.master.lambdas,self.master.column_data):point[self.blocks[c['unit']].columns]+=float(v.X)*c['x']
        full=corrected_rows(self.A,self.d,point,False,self.route_mask)
        row.update(objective=model.ObjVal,master_row_max=checked['master_row_max_violation'],full_row_max=full['max_constraint_violation'],bound_max=full['max_bound_violation'])
        if not checked['PASS'] or not full['PASS'] or model.DualVio>EPS:self.stop='RMP_NUMERICAL_OR_DUAL_AUDIT_FAIL';self.save();return None
        pi=np.array(model.getAttr('Pi',self.master.coupling));alpha=np.array(model.getAttr('Pi',self.master.conv));key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()
        assert np.all(pi[self.master.d['sense']=='<']<=0) and np.all(pi[self.master.d['sense']=='>']>=0),'ACTUAL_PI_SIGN_FAIL'
        manual=np.array([c['c']-float(pi@c['a'])-alpha[c['unit']] for c in self.master.column_data]);rc=np.array(model.getAttr('RC',self.master.lambdas))
        global_rc=self.master.d['objective']-self.master.A.T@pi;native_z=np.array(model.getAttr('RC',self.master.z))
        error=max(float(np.max(abs(manual-rc),initial=0.)),float(np.max(abs(global_rc-native_z),initial=0.)));assert error<=EPS,'MANUAL_NATIVE_RC_FAIL'
        row.update(dual_SHA=key,manual_RC_error=error,primal_SHA=hashlib.sha256(point.tobytes()).hexdigest())
        filename=f'RMP_POINT_{self.iteration:04d}.npz';np.savez_compressed(OUT/filename,point=point,pi=pi,alpha=alpha,shared_values=np.array(model.getAttr('X',self.master.z)),lambda_values=np.array(model.getAttr('X',self.master.lambdas)));row['point_file']=filename
        vb=list(model.getAttr('VBasis'));cb=list(model.getAttr('CBasis'));self.basis=(vb,cb,[c['key'] for c in self.master.column_data])
        basisfile=f'RMP_BASIS_{self.iteration:04d}.npz';np.savez_compressed(OUT/basisfile,VBasis=vb,CBasis=cb,row_names=np.array(model.getAttr('ConstrName')),column_names=np.array(model.getAttr('VarName')));row['basis_file']=basisfile
        start=time.perf_counter();global_value,proof=global_dual(self.master.A,self.master.d,pi,self.lo[self.master.columns],self.hi[self.master.columns])
        write(f'DW_ACTUAL_DUAL_SIGN_{self.iteration:04d}.json',dict(PASS=True,dual_SHA=key,all_actual_row_senses_checked=True,manual_lambda_RC_max=error,manual_global_z_RC_max=error,global_dual=proof,global_certificate_audit_seconds=time.perf_counter()-start,master=checked,full_original=full,settings=settings))
        self.bestU=model.ObjVal if self.bestU is None else min(self.bestU,model.ObjVal)
        if self.iteration==1:write('DW_BOUND_INITIAL_RMP.json',dict(PASS=True,objective=model.ObjVal,dual_SHA=key,master=checked,full_original=full,cold=True,restored=1048,settings=settings,point_SHA=sha(OUT/filename),global_dual=proof))
        self.save();print('BOUND_RMP_OPTIMAL',self.iteration,model.ObjVal,self.heavy,flush=True);return pi,alpha,key,global_value,proof
    def pricing(self,m,pi,alpha,key):
        b=self.blocks[m];model=b.model;continued=self.price_context[m]==key
        if not continued:
            cost=b.price(pi,alpha[m]);self.price_context[m]=key
            for j in np.flatnonzero(np.diff(b.CSC.indptr)):
                k=b.CSC.indptr[j];assert F(float(cost[j]))==F(float(b.d['objective'][j]))-F(float(b.CSC.data[k]))*F(float(pi[b.CSC.indices[k]])),'PRICING_OBJECTIVE_NOT_EXACT_TRANSPORT'
            if self.optimal_starts[m] is not None:model.setAttr('Start',b.vars,self.optimal_starts[m].tolist())
        else:cost=np.array(model.getAttr('Obj',b.vars))
        assert np.array_equal(cost,np.array(model.getAttr('Obj',b.vars))) and model.ObjCon==-float(alpha[m]) and model.ModelSense==1
        objective_SHA=hashlib.sha256(cost.tobytes()+np.array([-float(alpha[m])]).tobytes()).hexdigest();first_negative=[]
        def observe(native,where):
            if where==gp.GRB.Callback.MIPSOL and not first_negative and native.cbGet(gp.GRB.Callback.MIPSOL_OBJ)<-EPS:first_negative.append(float(native.cbGet(gp.GRB.Callback.RUNTIME)))
        settings=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=EPS,OptimalityTol=EPS,IntFeasTol=EPS,Seed=20260929,TimeLimit=min(300,self.remaining()-3))
        assert settings['TimeLimit']>0
        for k,v in settings.items():model.setParam(k,v)
        self.call+=1;log=f'logs/PRICE_{self.call:04d}_{b.unit}.log';model.Params.LogFile=(OUT.relative_to(ROOT)/log).as_posix();self.start_records.append(dict(call=self.call,MESS=b.unit,dual_SHA=key,previous_optimal_start_supplied=self.optimal_starts[m] is not None and not continued,same_native_search_continued=continued,start_acceptance='native log preserved; no fixing or bound changes'))
        start=time.perf_counter();self.optimize(model,observe);wall=time.perf_counter()-start
        def attr(name):
            try:return finite(float(getattr(model,name)))
            except (gp.GurobiError,AttributeError):return None
        obj=attr('ObjVal') if model.SolCount else None;bound=attr('ObjBound');rawC=attr('ObjBoundC');rc=None;candidate=None;checked=None;error=None
        valid=model.Status in (2,9) and bound is not None and not self.resource.policy_violations
        if model.SolCount:
            candidate=np.array(model.getAttr('X',b.vars));checked=b.validate(candidate,True);rc=float(exact_rc(b,candidate,pi,alpha[m]));error=abs(rc-obj) if obj is not None else None
            valid=bool(valid and checked['PASS'] and error is not None and error<=EPS and bound<=rc+EPS)
            path=f'pricing_points/PRICE_{self.call:04d}.npz';(OUT/'pricing_points').mkdir(exist_ok=True);np.savez_compressed(OUT/path,x=candidate,axis=b.columns)
        classification='OPTIMAL_NEGATIVE' if valid and model.Status==2 and rc is not None and rc<-EPS else 'OPTIMAL_NONNEGATIVE' if valid and model.Status==2 and rc is not None else 'TIME_LIMIT_WITH_VALID_BOUND' if valid and model.Status==9 else 'UNCERTIFIED'
        if classification.startswith('OPTIMAL'):self.optimal_starts[m]=candidate.copy()
        file=f'pricing_receipts/PRICE_{self.call:04d}.json'
        row=dict(call=self.call,iteration=self.iteration,dual_SHA=key,MESS=b.unit,native_status=model.Status,classification=classification,ObjVal=obj,ObjBound=bound,ObjBoundC=rawC,MIPGap=attr('MIPGap'),valid_bound=valid,rc_opt=rc if classification.startswith('OPTIMAL') else None,runtime=model.Runtime,wall_seconds=wall,nodes=model.NodeCount,fingerprint=model.Fingerprint,objective_SHA=objective_SHA,first_negative_observed_seconds=first_negative[0] if first_negative else None,receipt=file)
        self.prices.append(row);write(file,dict(row,settings=settings,base_model_signature=b.census()['signature'],full_original_domain=True,horizon=96,first_negative_termination=False,callback_termination=False,
          global_bound_includes_ObjCon=True,ObjCon=model.ObjCon,objective_coefficients_SHA=hashlib.sha256(cost.tobytes()).hexdigest(),manual_incumbent_objective_error=error,incumbent_audit=checked,
          time_limit_is_not_no_column=True,time_limit_incumbent_is_not_most_negative=True,continued_same_dual=continued,objective_transport_exact=True,point_file=path if candidate is not None else None))
        self.save();print('BOUND_PRICING',self.call,b.unit,classification,rc,bound,self.heavy,flush=True);return row,candidate
    def add_optimal(self,m,x,p,pi,alpha):
        b=self.blocks[m];assert p['classification']=='OPTIMAL_NEGATIVE' and p['rc_opt']<-EPS
        assert b.validate(x,True)['PASS'];a,c,key=b.column(x);exact,error=b.exact_coupling(x,a);assert error<=1e-12
        duplicate=key in self.seen[m];assert not duplicate,'OPTIMAL_NEGATIVE_DUPLICATE'
        number=len(self.column_records);file=f'columns/COLUMN_{number:06d}_{b.unit}.npz';(OUT/'columns').mkdir(exist_ok=True);ix=sorted(i for i,v in exact.items() if v)
        np.savez_compressed(OUT/file,x=x,axis=b.columns,a=a,c=np.array(c),exact_rows=ix,exact_numerators=np.array([str(exact[i].numerator) for i in ix]),exact_denominators=np.array([str(exact[i].denominator) for i in ix]))
        self.master.add(m,x,a,c,key);self.seen[m].add(key);self.column_records.append(dict(number=number,iteration=self.iteration,MESS=b.unit,SHA256=key,file=file,rc_opt=p['rc_opt'],pricing_call=p['call'],added=True,duplicate=False))
    def checkpoint(self,b,latest):
        write(f'bound_certificates/ITER_{self.iteration:04d}_ROUND_{b["round"]:03d}.json',b)
        value=dict(base=BASE,iteration=self.iteration,round=b['round'],retained_columns=1048+len(self.column_records),base_checkpoint_SHA=sha(OUT/'DW_BOUND_CHECKPOINT_AUDIT.json'),new_columns=self.column_records,
          RMP=self.rmps[-1],basis=self.rmps[-1]['basis_file'],four_pricing=latest,beta_vector=b.get('beta_safe'),corrected_LB=b['L_corr'],bracket=[b['L_corr'],b['U_RMP']],materiality=b['materiality'],best_L=self.bestL,best_U=self.bestU,cumulative_heavy_seconds=self.heavy,cumulative_wall_including_build_audit=self.elapsed(),source_commit=self.commit)
        write('DW_BOUND_CHECKPOINT_LATEST.json',value);self.save()
    def run(self):
        try:
            while self.stop is None and self.remaining()>5:
                dual=self.solve_master()
                if dual is None:break
                pi,alpha,key,global_value,proof=dual;latest=[None]*4;candidates=[None]*4;round_number=0
                if self.bestU<=T_MATERIAL:self.materiality='PROVEN_NONMATERIAL';self.stop='RMP_UPPER_PROVES_NONMATERIAL';break
                while self.stop is None and self.remaining()>5:
                    round_number+=1
                    for m in range(4):
                        if self.remaining()<=5:self.stop='HEAVY_BUDGET';break
                        if latest[m] is not None and latest[m]['classification'].startswith('OPTIMAL'):continue
                        latest[m],candidates[m]=self.pricing(m,pi,alpha,key)
                    if self.stop:break
                    b=receipt(self.iteration,round_number,pi,alpha,key,global_value,proof,latest,self.rmps[-1]['objective'],self.master,self.blocks);self.brackets.append(b)
                    if b['certified']:self.bestL=b['L_corr'] if self.bestL is None else max(self.bestL,b['L_corr'])
                    self.materiality=decide(self.bestL,self.bestU)
                    self.converged=bool(b['certified'] and all(p['classification']=='OPTIMAL_NONNEGATIVE' for p in latest) and b['U_RMP']-b['L_corr']<=POST)
                    self.checkpoint(b,latest)
                    if self.materiality!='INCONCLUSIVE':self.stop='CERTIFIED_MATERIALITY_DECISION';break
                    if self.converged:self.stop='EXACT_CG_CONVERGENCE';break
                    negatives=[m for m,p in enumerate(latest) if p['classification']=='OPTIMAL_NEGATIVE']
                    if negatives:
                        for m in negatives:self.add_optimal(m,candidates[m],latest[m],pi,alpha)
                        self.save();break
                    if any(p['classification']=='UNCERTIFIED' for p in latest):self.stop='UNCERTIFIED_PRICING';break
            if self.stop is None:self.stop='HEAVY_BUDGET'
        except Exception as error:
            self.stop='EXECUTION_OR_CERTIFICATE_AUDIT_ERROR:'+repr(error);write('DW_BOUND_EXECUTION_ERROR.json',dict(error=repr(error),iteration=self.iteration,call=self.call));raise
        finally:
            self.resource.close(self.materiality);self.finish();self.master.model.dispose()
            for b in self.blocks:b.model.dispose()
    def finish(self):
        best=next((b for b in reversed(self.brackets) if b['certified'] and b['L_corr']==self.bestL),None)
        write('DW_FINAL_BOUND_CERTIFICATE.json',dict(PASS=self.bestL is not None,materiality=self.materiality,best_certificate=best,interval=[self.bestL,self.bestU],DW_ROOT_OPTIMAL_CERTIFIED=self.converged,
          original_integer_UB_claimed=False,bound_authority='Exact dyadic-rational global weak duality plus receipt-audited full-domain native ObjBound; RMP upper uses registered native primal audit authority.'))
        result=dict(status=self.materiality,stop_reason=self.stop,base=BASE,checkpoint_columns=1048,new_RMP_solves=len(self.rmps),new_pricing_calls=len(self.prices),new_columns=len(self.column_records),retained_columns=1048+len(self.column_records),
          pricing_OPTIMAL=sum(p['classification'].startswith('OPTIMAL') for p in self.prices),pricing_TIME_LIMIT_WITH_VALID_BOUND=sum(p['classification']=='TIME_LIMIT_WITH_VALID_BOUND' for p in self.prices),pricing_UNCERTIFIED=sum(p['classification']=='UNCERTIFIED' for p in self.prices),
          first_RMP_objective=self.rmps[0]['objective'] if self.rmps else None,first_corrected_LB=self.brackets[0]['L_corr'] if self.brackets else None,first_interval=[self.brackets[0]['L_corr'],self.brackets[0]['U_RMP']] if self.brackets else [None,None],
          best_corrected_certified_LB=self.bestL,smallest_RMP_upper=self.bestU,final_interval=[self.bestL,self.bestU],arc_root_LB=BASE_LB,material_threshold=T_MATERIAL,certified_improvement_lower=None if self.bestL is None else self.bestL-BASE_LB,
          DW_ROOT_OPTIMAL_CERTIFIED=self.converged,DW_ROOT_LB=self.bestL if self.converged else None,
          total_heavy_wall_seconds=self.heavy,heavy_wall_until_decision=self.heavy if self.materiality!='INCONCLUSIVE' or self.converged else None,elapsed_including_build_audit_seconds=self.elapsed(),build_seconds=self.build_seconds,enclosure_audit_seconds=self.enclosure_seconds,wall_budget_PASS=self.heavy<=3600,
          first_negative_termination=False,full_domain=True,old_pricing_replayed=0,old_failed_dual_used=False,branch_and_price_run=False,production_M1=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,May_optimizer_Actual_Fresh_AC=[0,0,0])
        write('DW_FINAL_RESULT.json',result);self.save();print('BOUND_DONE',result,flush=True)
if __name__=='__main__':Experiment().run()
