"""900s union-of-optimize-wall canary, discovery3/certification1."""
from .common import *
import numpy as np,multiprocessing as mp,gurobipy as gp,math
from fractions import Fraction as F
from v42_dw_resume.audit import Master,prototypes,corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_degen.identity import inputs,signature
from v42_dw_root.run import exact_rc
from v42_dw_bound.certificate import global_dual,receipt,decide
from .worker import main as worker_main
from .resources import Monitor
class Experiment:
    def __init__(self):
        import sys
        self.commit=verify_freeze();preserve_old();assert not STOP.exists();recovery=None
        if '--resume' in sys.argv:
            from .resume import recover
            recovery=recover()
        else:
            with (OUT/'STARTED.json').open('x',encoding='utf8') as f:json.dump(dict(preopt_commit=self.commit),f)
        self.begin=time.perf_counter();self.carried_heavy=0.;self.carried_elapsed=0.;self.intervals=[];self.rmps=[];self.prices=[];self.columns=[];self.rounds=[];self.certs=[];self.canaries=[];self.current_round=0;self.call=0;self.column_id=0;self.bestL=read(PREVIOUS/'DW_FINAL_RESULT.json')['best_corrected_certified_LB'];self.bestU=None;self.materiality='INCONCLUSIVE';self.converged=False;self.stop=None;self.workers=4;self.processes=[];self.pipes=[];self.pids=[];self.context=mp.get_context('spawn');self.cancel=self.context.Event();self.monitor=Monitor(self.pids,self.cancel)
        if recovery:
            for name in ('rmps','prices','columns','rounds','certs','canaries'):setattr(self,name,recovery[name])
            self.current_round=recovery['next_round_id'];self.call=recovery['next_call_id'];self.column_id=recovery['next_column_id'];self.carried_heavy=recovery['carried_heavy_seconds'];self.carried_elapsed=recovery['carried_elapsed_seconds'];self.bestL=recovery['best_L'];self.bestU=recovery['best_U'];self.workers=recovery['workers']
        start=time.perf_counter();self.A,self.d,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        assert signature(self.B,self.e)==read(PREVIOUS/'DW_BOUND_CHECKPOINT_AUDIT.json')['reference_signature']
        with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        self.blocks=prototypes(self.B,self.e,self.owner,self.row_owner,native);self.master=Master(self.B,self.e,self.owner,self.row_owner,native);self.seen=[set() for _ in range(4)]
        for directory,h in old_columns():
            m=UNITS.index(h['MESS']);new=h.get('format')=='policy_optimal'
            with np.load(directory/h['file']) as z:x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c']) if new else float(z['objective'])
            assert self.blocks[m].column(x)[2]==h['SHA256'];self.master.add(m,x,a,c,h['SHA256']);self.seen[m].add(h['SHA256'])
        assert len(self.master.lambdas)==1066
        if recovery:
            for column in self.columns:
                m=UNITS.index(column['MESS'])
                with np.load(OUT/column['file']) as z:x=z['x'];a=z['a'];c=float(z['c']);assert self.blocks[m].column(x)[2]==column['SHA256']
                self.master.add(m,x,a,c,column['SHA256']);self.seen[m].add(column['SHA256'])
        self.route_mask=pure_binary_equalities(self.A,self.d);self.basis=None;self.build_seconds=time.perf_counter()-start
        with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:self.lo=z['lower'];self.hi=z['upper']
        assert sha(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz')==read(PREVIOUS/'COORDINATE_ENCLOSURE_PROOF.json')['artifact_SHA']
        write('DW_POLICY_BUILD_RECEIPT.json',dict(PASS=True,scientific_base=BASE,retained=1066,cold_RMP=True,failed_dual_used=False,build_seconds=self.build_seconds,matrix_signature=signature(self.B,self.e),theorem_source_SHA=sha(ROOT/'v42_dw_bound/certificate.py')))
        self.launch_with_downgrade(self.workers);self.save()
    def spent(self):return self.carried_heavy+union_seconds(self.intervals)
    def remaining(self):return BUDGET-self.spent()
    def elapsed(self):return self.carried_elapsed+time.perf_counter()-self.begin
    def launch_with_downgrade(self,count):
        while True:
            try:self.start_workers(count);return
            except Exception as error:
                self.canaries.append(dict(round=self.current_round,workers=count,PASS=False,stage='WORKER_BUILD',error=repr(error)));write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=count,resource_PASS=False));self.cancel.set();self.close_workers()
                if count==1:raise
                count//=2
    def start_workers(self,count):
        self.workers=count;self.cancel.clear();self.processes=[];self.pipes=[];self.pids.clear();self.monitor.failed.clear();self.monitor.baseline=__import__('psutil').swap_memory().used
        for k in range(count):
            parent,child=self.context.Pipe();p=self.context.Process(target=worker_main,args=(child,list(range(k,4,count)),self.cancel));p.start();child.close();self.processes.append(p);self.pipes.append(parent);self.pids.append(p.pid)
        errors=[]
        for pipe in self.pipes:
            while not pipe.poll(.5):
                if STOP.exists():self.cancel.set()
                if any(not p.is_alive() for p in self.processes):raise RuntimeError('WORKER_EXIT_DURING_BUILD')
            value=pipe.recv()
            if 'error' in value:errors.append(value)
            else:
                old=read(PREVIOUS/'DW_BOUND_BUILD_RECEIPT.json')['pricing_census']
                for m,c in value['census'].items():assert c['signature']==old[m]['signature']
        if errors:raise RuntimeError('WORKER_BUILD_ERROR:'+repr(errors))
    def close_workers(self):
        for pipe,p in zip(self.pipes,self.processes):
            if p.is_alive():
                try:pipe.send(None)
                except (EOFError,BrokenPipeError):pass
        for p in self.processes:p.join()
        for pipe in self.pipes:pipe.close()
        self.processes=[];self.pipes=[];self.pids.clear()
    def solve_master(self,kind):
        self.current_round+=1;model=self.master.model;warm=self.basis is not None
        if warm:
            vb,cb,keys=self.basis;assert keys==[c['key'] for c in self.master.column_data[:len(keys)]]
            model.setAttr('VBasis',self.master.z+self.master.lambdas,vb+[-1]*(model.NumVars-len(vb)));model.setAttr('CBasis',model.getConstrs(),cb);model.update()
        settings=dict(Threads=1,Method=2,Crossover=1,PreDual=0,BarConvTol=1e-11,Seed=20260929,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,TimeLimit=min(300,max(.001,self.remaining()-4)))
        for k,v in settings.items():model.setParam(k,v)
        model.Params.LogFile=(OUT.relative_to(ROOT)/f'logs/RMP_{self.current_round:04d}.log').as_posix()
        def control(m,where):
            if STOP.exists() or self.cancel.is_set():m.terminate()
        self.monitor.phase='RMP';write('DW_INFLIGHT.json',dict(kind='RMP',spent_before=self.spent(),reserved_optimize_seconds=min(self.remaining(),settings['TimeLimit']+4),round=self.current_round));start=time.perf_counter();model.optimize(control);end=time.perf_counter();self.intervals.append((start,end))
        row=dict(round=self.current_round,type=kind,status=model.Status,wall_seconds=end-start,interval=[start,end],objective=None,dual_SHA=None,point_file=None,warm_basis_supplied=warm,settings=settings)
        self.rmps.append(row)
        if model.Status!=2:self.stop='RMP_NOT_OPTIMAL';return None
        checked=self.master.raw_audit();point=np.zeros(self.B.shape[1]);point[self.master.columns]=model.getAttr('X',self.master.z)
        for v,c in zip(self.master.lambdas,self.master.column_data):point[self.blocks[c['unit']].columns]+=float(v.X)*c['x']
        full=corrected_rows(self.A,self.d,point,False,self.route_mask);assert checked['PASS'] and full['PASS'] and model.DualVio<=EPS
        pi=np.array(model.getAttr('Pi',self.master.coupling));alpha=np.array(model.getAttr('Pi',self.master.conv));key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()
        assert np.all(pi[self.master.d['sense']=='<']<=0) and np.all(pi[self.master.d['sense']=='>']>=0)
        manual=np.array([c['c']-float(pi@c['a'])-alpha[c['unit']] for c in self.master.column_data]);rc=np.array(model.getAttr('RC',self.master.lambdas));global_rc=self.master.d['objective']-self.master.A.T@pi
        error=max(float(np.max(abs(manual-rc),initial=0.)),float(np.max(abs(global_rc-np.array(model.getAttr('RC',self.master.z))),initial=0.)));assert error<=EPS
        file=f'RMP_POINT_{self.current_round:04d}.npz';np.savez_compressed(OUT/file,point=point,pi=pi,alpha=alpha,lambda_values=np.array(model.getAttr('X',self.master.lambdas)))
        vb=list(model.getAttr('VBasis'));cb=list(model.getAttr('CBasis'));self.basis=(vb,cb,[c['key'] for c in self.master.column_data]);basisfile=f'RMP_BASIS_{self.current_round:04d}.npz';np.savez_compressed(OUT/basisfile,VBasis=vb,CBasis=cb,row_names=np.array(model.getAttr('ConstrName')),column_names=np.array(model.getAttr('VarName')))
        row.update(objective=model.ObjVal,dual_SHA=key,primal_SHA=hashlib.sha256(point.tobytes()).hexdigest(),point_file=file,point_SHA=sha(OUT/file),basis_file=basisfile,full_original=full,master=checked,manual_RC_error=error)
        self.bestU=model.ObjVal if self.bestU is None else min(self.bestU,model.ObjVal);self.save();print('POLICY_RMP',self.current_round,kind,model.ObjVal,self.spent(),flush=True)
        return pi,alpha,key,file
    def pricing_round(self,kind,dual,cap):
        pi,alpha,key,file=dual;results=[];self.monitor.phase=kind;sample_start=len(self.monitor.rows);batch_start=time.perf_counter();write('DW_INFLIGHT.json',dict(kind=kind,spent_before=self.spent(),reserved_optimize_seconds=min(self.remaining(),cap*math.ceil(4/self.workers)+4),round=self.current_round,dual_SHA=key))
        for batch in range(math.ceil(4/self.workers)):
            pending=[]
            for k in range(self.workers):
                m=batch*self.workers+k
                if m>=4:break
                self.call+=1;job=dict(call=self.call,round=self.current_round,type=kind,unit=m,dual_SHA=key,dual_file=file,cap=cap,log=f'logs/PRICE_{self.call:04d}_{UNITS[m]}.log',receipt=f'pricing_receipts/PRICE_{self.call:04d}.json')
                self.pipes[k].send(job);pending.append(k)
            while pending:
                for k in pending[:]:
                    if self.pipes[k].poll(.2):
                        value=self.pipes[k].recv();pending.remove(k)
                        if 'error' in value:self.cancel.set();write(f'WORKER_ERROR_{self.current_round:04d}_{k}.json',value)
                        else:r=read(OUT/value['result']);self.intervals.append(r['interval']);self.prices.append(r);results.append(r)
                if STOP.exists():self.cancel.set()
                for k in pending:
                    if not self.processes[k].is_alive():raise RuntimeError('WORKER_EXIT_DURING_NATIVE_SOLVE')
            if self.cancel.is_set():break
        self.monitor.sample();samples=self.monitor.rows[sample_start:];stats=self.monitor.summary(samples)
        safe=bool(len(results)==4 and not self.monitor.failed and all(r['native_status'] in (2,9) and (r['ObjVal'] is None or r['valid_point']) for r in results))
        canary=dict(round=self.current_round,workers=self.workers,PASS=safe,failures=list(set(self.monitor.failed)),solver_or_model_errors=len(results)!=4,all_same_dual=all(r['dual_SHA']==key for r in results),batch_wall_seconds=time.perf_counter()-batch_start,**stats)
        self.canaries.append(canary);write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=self.workers,resource_PASS=safe,resource_safety_failure_observed=any(not c['PASS'] for c in self.canaries)))
        return sorted(results,key=lambda r:r['unit']),safe
    def add(self,r,pi,alpha):
        assert r['type']=='DISCOVERY' and r['valid_point'] and r['rc_inc']<=DISCOVERY_RC
        m=r['unit'];b=self.blocks[m]
        with np.load(OUT/r['point_file']) as z:x=z['x'];assert np.array_equal(z['axis'],b.columns)
        assert b.validate(x,True)['PASS'] and r['full_original_local']['PASS'];rc=float(exact_rc(b,x,pi,alpha[m]));assert abs(rc-r['rc_inc'])<=EPS
        a,c,key=b.column(x)
        if key in self.seen[m]:return False
        exact,error=b.exact_coupling(x,a);assert error<=1e-12
        n=self.column_id;self.column_id+=1;file=f'columns/COLUMN_{n:06d}_{b.unit}.npz';ix=sorted(i for i,v in exact.items() if v)
        np.savez_compressed(OUT/file,x=x,axis=b.columns,a=a,c=np.array(c),exact_rows=ix,exact_numerators=np.array([str(exact[i].numerator) for i in ix]),exact_denominators=np.array([str(exact[i].denominator) for i in ix]))
        self.master.add(m,x,a,c,key);self.seen[m].add(key);self.columns.append(dict(number=n,round=self.current_round,MESS=b.unit,file=file,file_SHA=sha(OUT/file),SHA256=key,pricing_call=r['call'],rc_inc=rc,label='VALID_NEGATIVE_DISCOVERY_COLUMN',pricing_optimum_claimed=False,native_status=r['native_status']))
        return True
    def certify(self,dual,prices,kind):
        pi,alpha,key,file=dual
        if len(prices)!=4:return None
        value,proof=global_dual(self.master.A,self.master.d,pi,self.lo[self.master.columns],self.hi[self.master.columns])
        c=receipt(self.current_round,1,pi,alpha,key,value,proof,prices,self.rmps[-1]['objective'],self.master,self.blocks);c['type']=kind
        file=f'bound_certificates/ROUND_{self.current_round:04d}.json';write(file,c);c['file']=file;self.certs.append(c)
        if c['certified']:self.bestL=max(self.bestL,c['L_corr']) if self.bestL is not None else c['L_corr']
        self.materiality=decide(self.bestL,self.bestU);self.converged=bool(c['certified'] and all(p['native_status']==2 and p['valid_point'] and p['rc_inc']>=-EPS for p in prices) and c['U_RMP']-c['L_corr']<=POST)
        if self.materiality!='INCONCLUSIVE':self.stop='CERTIFIED_MATERIALITY_DECISION'
        elif self.converged:self.stop='EXACT_CG_CONVERGENCE'
        return c
    def save(self):
        write('DW_POLICY_LIVE_STATUS.json',dict(round=self.current_round,RMP=len(self.rmps),pricing=len(self.prices),columns=len(self.columns),workers=self.workers,heavy_wall_union=self.spent(),remaining=self.remaining(),elapsed=self.elapsed(),best_L=self.bestL,best_U=self.bestU,materiality=self.materiality,stop=self.stop))
        table('DW_RMP_LEDGER.csv',[dict(round=r['round'],type=r['type'],status=r['status'],objective=r['objective'],dual_SHA=r['dual_SHA'],wall_seconds=r['wall_seconds'],receipt=f"RMP_RECEIPT_{r['round']:04d}.json") for r in self.rmps])
        for r in self.rmps:write(f"RMP_RECEIPT_{r['round']:04d}.json",r)
        table('DW_DISCOVERY_COLUMN_LEDGER.csv',self.columns)
        table('DW_DISCOVERY_ITERATION_LEDGER.csv',[r for r in self.rounds if r['type']=='DISCOVERY'])
        table('DW_CERTIFICATION_ITERATION_LEDGER.csv',[r for r in self.rounds if r['type']!='DISCOVERY'])
        table('DW_CORRECTED_BOUND_LEDGER.csv',[dict(round=c['iteration'],type=c['type'],dual_SHA=c['dual_SHA'],certified=c['certified'],L_corr=c['L_corr'],U_RMP=c['U_RMP'],file=c['file']) for c in self.certs])
    def checkpoint(self,kind,prices,cert):
        poolrefs=read(OUT/'DW_POLICY_RESUME_CHECKPOINT_AUDIT.json')['checks']+[dict(file=(OUT/c['file']).relative_to(ROOT).as_posix(),file_SHA=c['file_SHA'],column_SHA=c['SHA256'],MESS=c['MESS']) for c in self.columns]
        state=dict(rmps=self.rmps,prices=self.prices,columns=self.columns,rounds=self.rounds,certs=self.certs,canaries=self.canaries,workers=self.workers)
        r=self.rmps[-1];write('DW_POLICY_CHECKPOINT_LATEST.json',dict(round=self.current_round,type=kind,pool=poolrefs,total_retained_columns=len(poolrefs),RMP=r,pricing_receipts=[p['receipt'] for p in prices],new_columns=self.columns,beta_values=[p['ObjBound'] if p['valid_bound'] else None for p in prices],corrected_LB=cert['L_corr'] if cert else None,certificate=cert,upper=r['objective'],best_interval=[self.bestL,self.bestU],materiality=self.materiality,elapsed_budget=self.spent(),optimize_intervals=self.intervals,elapsed_total=self.elapsed(),source_commit=self.commit,resource_canary=self.canaries[-1] if self.canaries else None,restart_state=state))
        (OUT/'DW_INFLIGHT.json').unlink(missing_ok=True)
    def run(self):
        schedule=['DISCOVERY']*3+['CERTIFICATION'];position=len([r for r in self.rounds if r['type']!='FINAL_CERTIFICATION'])%4
        try:
            while not self.stop and self.remaining()>35:
                if STOP.exists():self.stop='USER_STOP';break
                last=self.rmps[-1]['wall_seconds'] if self.rmps else 20.;reserve=max(30.,last);waves=math.ceil(4/self.workers);cycle=3*(last+20*waves)+(last+60*waves)+8
                final=bool(self.current_round and position==0 and 120<=self.remaining()<cycle+120)
                kind='FINAL_CERTIFICATION' if final else schedule[position]
                if not final and self.remaining()<reserve+(20 if kind=='DISCOVERY' else 60)*waves+124:
                    if self.remaining()>=120:kind='FINAL_CERTIFICATION';final=True
                    else:self.stop='POLICY_CANARY_BUDGET';break
                round_start=time.perf_counter();before=len(self.columns);dual=self.solve_master(kind)
                if dual is None:break
                if self.bestU<=T_MATERIAL:self.materiality='PROVEN_NONMATERIAL';self.stop='RMP_UPPER_PROVES_NONMATERIAL';self.checkpoint(kind,[],None);break
                cap=min(120,(self.remaining()-4)/waves) if final else 20 if kind=='DISCOVERY' else 60
                prices,safe=self.pricing_round(kind,dual,cap)
                if not safe:
                    self.checkpoint(kind,prices,None);self.save()
                    if STOP.exists():self.stop='USER_STOP';break
                    old=self.workers;self.close_workers()
                    if old==1:self.stop='RESOURCE_OR_PRICING_CANARY_FAILURE';break
                    self.launch_with_downgrade(old//2);continue
                cert=None
                if kind=='DISCOVERY':
                    for p in prices:
                        if p['valid_point'] and p['rc_inc']<=DISCOVERY_RC:self.add(p,dual[0],dual[1])
                else:cert=self.certify(dual,prices,kind)
                self.rounds.append(dict(round=self.current_round,type=kind,workers=self.workers,round_wall_seconds=time.perf_counter()-round_start,RMP_wall_seconds=self.rmps[-1]['wall_seconds'],pricing_optimize_union=union_seconds([p['interval'] for p in prices]),columns_added=len(self.columns)-before,dual_SHA=dual[2],corrected_LB=cert['L_corr'] if cert else None,RMP_upper=self.rmps[-1]['objective'],materiality=self.materiality,cumulative_heavy_wall=self.spent(),elapsed_total=self.elapsed()))
                self.checkpoint(kind,prices,cert);self.rounds[-1]['round_wall_seconds']=time.perf_counter()-round_start;self.rounds[-1]['elapsed_total']=self.elapsed();self.checkpoint(kind,prices,cert)
                self.save();print('POLICY_ROUND',self.current_round,kind,len(self.columns)-before,self.bestL,self.bestU,self.spent(),flush=True)
                if final:self.stop=self.stop or 'POLICY_CANARY_FINAL_CERTIFICATION_COMPLETE';break
                position=(position+1)%4
            self.stop=self.stop or 'POLICY_CANARY_BUDGET'
        except BaseException as error:
            self.stop='EXECUTION_ERROR:'+repr(error);self.cancel.set();write('EXECUTION_ERROR.json',dict(error=repr(error)));raise
        finally:
            self.close_workers();self.monitor.close();self.finish();self.master.model.dispose()
    def finish(self):
        assert self.spent()<=BUDGET,'PREREGISTERED900S_BUDGET_OVERRUN'
        old=read(PREVIOUS/'DW_FINAL_RESULT.json');oldrate=old['new_columns']/(old['elapsed_including_build_audit_seconds']/60);newrate=len(self.columns)/(self.elapsed()/60);ds=[r['round_wall_seconds'] for r in self.rounds if r['type']=='DISCOVERY'];cs=[r['round_wall_seconds'] for r in self.rounds if r['type']!='DISCOVERY'];resource=bool(self.canaries and self.canaries[-1]['PASS']);failure=any(not c['PASS'] for c in self.canaries);median=float(np.median(ds)) if ds else None
        quality='PROMISING' if resource and not failure and median is not None and median<=(60 if self.workers==4 else 120) and newrate>oldrate else 'NOT_SUPPORTED'
        if not ds or self.stop.startswith('EXECUTION_ERROR'):quality='INCONCLUSIVE'
        first=next((r for r in self.rounds if r['corrected_LB'] is not None),None)
        value=dict(scientific_base=BASE,old_policy_stop_commit=read(OUT/'DW_POLICY_RESUME_CHECKPOINT_AUDIT.json')['old_policy_stop_commit'],preopt_commit=self.commit,status='POLICY_CANARY_INCONCLUSIVE' if self.materiality=='INCONCLUSIVE' else 'POLICY_CANARY_DECIDED',materiality=self.materiality,policy_canary=quality,stop_reason=self.stop,workers=self.workers,resource_PASS=resource,resource_safety_failure_observed=failure,initial_retained_columns=1066,new_RMP_solves=len(self.rmps),new_pricing_calls=len(self.prices),new_discovery_columns=len(self.columns),retained_columns=1066+len(self.columns),discovery_rounds=len(ds),certification_rounds=len(cs),median_discovery_round_wall=median,median_certification_round_wall=float(np.median(cs)) if cs else None,old_columns_per_minute=oldrate,new_columns_per_minute=newrate,time_to_first_new_certified_LB=None if first is None else first['elapsed_total'],heavy_to_first_new_certified_LB=None if first is None else first['cumulative_heavy_wall'],best_corrected_LB=self.bestL,smallest_RMP_upper=self.bestU,final_interval=[self.bestL,self.bestU],material_threshold=T_MATERIAL,DW_ROOT_OPTIMAL_CERTIFIED=self.converged,DW_ROOT_LB=self.bestL if self.converged else None,total_optimize_wall_union=self.spent(),sum_native_optimize_wall=sum(b-a for a,b in self.intervals),total_elapsed_including_build_audit=self.elapsed(),heavy_wall_to_materiality_decision=self.spent() if self.materiality!='INCONCLUSIVE' else None,build_seconds=self.build_seconds,May_production=[0,0,0],no_branch_and_price=True,old_TIME_LIMIT_retroactively_added=False)
        write('DW_POLICY_CANARY_FINAL.json',value);write('DW_OPTIMIZE_INTERVALS.json',dict(intervals=self.intervals,carried_budget_seconds=self.carried_heavy,union_seconds=self.spent(),budget=900));self.save();print('POLICY_DONE',value,flush=True)
if __name__=='__main__':Experiment().run()
