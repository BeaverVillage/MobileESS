"""900s union-of-optimize-wall canary, discovery5/certification1."""
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
        self.begin=time.perf_counter();self.carried_heavy=0.;self.carried_elapsed=0.;self.intervals=[];self.rmps=[];self.prices=[];self.columns=[];self.rounds=[];self.certs=[];self.canaries=[];self.current_round=0;self.call=0;self.column_id=0;self.bestL=read(POLICY/'DW_POLICY_CANARY_FINAL.json')['best_corrected_LB'];self.bestU=None;self.materiality='INCONCLUSIVE';self.converged=False;self.stop=None;self.workers=4;self.processes=[];self.pipes=[];self.pids=[];self.context=mp.get_context('spawn');self.cancel=self.context.Event();self.monitor=Monitor(self.pids,self.cancel)
        if recovery:
            for name in ('rmps','prices','columns','rounds','certs','canaries'):setattr(self,name,recovery[name])
            self.current_round=recovery['next_round_id'];self.call=recovery['next_call_id'];self.column_id=recovery['next_column_id'];self.carried_heavy=recovery['carried_heavy_seconds'];self.carried_elapsed=recovery['carried_elapsed_seconds'];self.bestL=recovery['best_L'];self.bestU=recovery['best_U'];self.workers=recovery['workers']
        start=time.perf_counter();self.A,self.d,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        assert signature(self.B,self.e)==read(PREVIOUS/'DW_BOUND_CHECKPOINT_AUDIT.json')['reference_signature']
        with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        self.blocks=prototypes(self.B,self.e,self.owner,self.row_owner,native);self.master=Master(self.B,self.e,self.owner,self.row_owner,native);self.seen=[set() for _ in range(4)]
        for directory,h in old_columns():
            m=UNITS.index(h['MESS'])
            with np.load(directory/h['file']) as z:
                new='x' in z;x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c']) if new else float(z['objective'])
            assert self.blocks[m].column(x)[2]==h['SHA256'];self.master.add(m,x,a,c,h['SHA256']);self.seen[m].add(h['SHA256'])
        assert len(self.master.lambdas)==1078
        if recovery:
            for column in self.columns:
                m=UNITS.index(column['MESS'])
                with np.load(OUT/column['file']) as z:x=z['x'];a=z['a'];c=float(z['c']);assert self.blocks[m].column(x)[2]==column['SHA256']
                self.master.add(m,x,a,c,column['SHA256']);self.seen[m].add(column['SHA256'])
        self.route_mask=pure_binary_equalities(self.A,self.d);self.basis=None;self.build_seconds=time.perf_counter()-start
        with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:self.lo=z['lower'];self.hi=z['upper']
        assert sha(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz')==read(PREVIOUS/'COORDINATE_ENCLOSURE_PROOF.json')['artifact_SHA']
        write('DW_THROUGHPUT_BUILD_RECEIPT.json',dict(PASS=True,scientific_base=BASE,retained=1078,cold_RMP=True,failed_dual_used=False,build_seconds=self.build_seconds,matrix_signature=signature(self.B,self.e),theorem_source_SHA=sha(ROOT/'v42_dw_bound/certificate.py')))
        self.warm_tested=False;self.warm_selected=False;self.warm_comparison=[];self.previous_pi=None;self.osc=[];self.stabilized=True;self.stabilization_tested=False;self.capture_ledger=[];self.previous_trajectories=set();self.smooth_pi=None;self.smooth_conv=None;self.smooth_weight=.30;self.smoothing_rows=[];self.zero_discovery_streak=0;self.smoothing_stagnation=False;self.force_certification=False;self.smooth_file=None;self.smooth_key=None
        if recovery:
            for name in ('warm_tested','warm_selected','warm_comparison','osc','stabilized','stabilization_tested','capture_ledger','smooth_weight','smoothing_rows','zero_discovery_streak','smoothing_stagnation','force_certification','smooth_file','smooth_key'):setattr(self,name,recovery.get(name,getattr(self,name)))
            if self.smooth_file:
                with np.load(OUT/self.smooth_file) as z:self.smooth_pi=z['pi'];self.smooth_conv=z['alpha']
            last=next((r for r in reversed(self.rmps) if r['status']==2),None)
            if last:
                with np.load(OUT/last['point_file']) as z:self.previous_pi=z['pi'].copy()
            self.previous_trajectories=set(recovery.get('previous_trajectories',[]))
        else:
            from .stabilization import proof
            self.monitor.phase='SMOOTHING_FIXTURE';value=proof(self.intervals,self.cancel);write('DW_STABILIZATION_FIXTURE_PROOF.json',value);assert value['PASS'];self.stabilization_tested=True
        self.launch_with_downgrade(self.workers);self.save()
    def spent(self):return self.carried_heavy+union_seconds(self.intervals)
    def remaining(self):return BUDGET-self.spent()
    def elapsed(self):return self.carried_elapsed+time.perf_counter()-self.begin
    def launch_with_downgrade(self,count):
        while True:
            try:self.start_workers(count);return
            except Exception as error:
                self.canaries.append(dict(round=self.current_round,workers=count,PASS=False,stage='WORKER_BUILD',error=repr(error)));write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=count,resource_PASS=False));self.cancel.set();self.close_workers()
                if count==1 or not any(token in str(error).lower() for token in ('memory','allocator','license')):raise
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
        self.monitor.sample()
    def close_workers(self):
        for pipe,p in zip(self.pipes,self.processes):
            if p.is_alive():
                try:pipe.send(None)
                except (EOFError,BrokenPipeError):pass
        for p in self.processes:p.join()
        for pipe in self.pipes:pipe.close()
        self.processes=[];self.pipes=[];self.pids.clear()
    def audit_copy(self,model):
        values=np.array(model.getAttr('X'));z=values[:len(self.master.z)];weights=values[len(self.master.z):];point=np.zeros(self.B.shape[1]);point[self.master.columns]=z
        residual=self.master.A@z-self.master.d['rhs'];conv=np.zeros(4)
        for weight,c in zip(weights,self.master.column_data):
            residual+=weight*c['a'];conv[c['unit']]+=weight;point[self.blocks[c['unit']].columns]+=weight*c['x']
        sense=self.master.d['sense'];vio=np.maximum(0,np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual)))
        bounds=max(float(np.maximum(self.master.d['lower']-z,0).max()),float(np.maximum(z-self.master.d['upper'],0).max()),float(np.maximum(-weights,0).max()))
        full=corrected_rows(self.A,self.d,point,False,self.route_mask)
        pi=np.array(model.getAttr('Pi')[:len(self.master.coupling)]);alpha=np.array(model.getAttr('Pi')[len(self.master.coupling):]);rc=np.array(model.getAttr('RC'))
        manual=np.array([c['c']-float(pi@c['a'])-alpha[c['unit']] for c in self.master.column_data]);global_rc=self.master.d['objective']-self.master.A.T@pi
        error=max(float(np.max(abs(manual-rc[len(z):]),initial=0)),float(np.max(abs(global_rc-rc[:len(z)]),initial=0)))
        sign=bool(np.all(pi[sense=='<']<=0) and np.all(pi[sense=='>']>=0))
        return dict(PASS=bool(full['PASS'] and vio.max(initial=0)<=EPS and abs(conv-1).max()<=EPS and bounds<=EPS and model.DualVio<=EPS and error<=EPS and sign),full_original=full,master_row_max_violation=float(vio.max(initial=0)),convexity_max_violation=float(abs(conv-1).max()),bounds_max_violation=float(bounds),DualVio=float(model.DualVio),manual_RC_error=error,sign_PASS=sign),point,pi,alpha,weights
    def warm_canary(self):
        self.warm_tested=True;self.monitor.phase='WARM_COLD_CANARY';self.master.model.update();vb,cb,keys=self.basis
        assert keys==[c['key'] for c in self.master.column_data[:len(keys)]]
        for i,path in enumerate(('cold','warm','warm','cold')):
            if self.remaining()<160:break
            model=self.master.model.copy();model.reset(1);model.update();assert model.Fingerprint==self.master.model.Fingerprint
            settings=dict(Threads=1,Method=2 if path=='cold' else 1,LPWarmStart=0 if path=='cold' else 2,Presolve=-1,Crossover=1,PreDual=0,BarConvTol=1e-11,Seed=20260929,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,TimeLimit=60)
            if path=='warm':
                model.setAttr('VBasis',model.getVars(),vb+[-1]*(model.NumVars-len(vb)));model.setAttr('CBasis',model.getConstrs(),cb);model.update()
            for k,v in settings.items():model.setParam(k,v)
            logfile=f'warm_cold/PAIR_{i:02d}_{path}.log';model.Params.LogFile=(OUT.relative_to(ROOT)/logfile).as_posix()
            write('DW_INFLIGHT.json',dict(kind='WARM_COLD_CANARY',spent_before=self.spent(),reserved_optimize_seconds=64,round=self.current_round))
            def control(m,where):
                if self.cancel.is_set() or STOP.exists():m.terminate()
            start=time.perf_counter();model.optimize(control);end=time.perf_counter();self.intervals.append((start,end))
            r=dict(index=i,path=path,settings=settings,interval=[start,end],wall_seconds=end-start,status=model.Status,objective=None,fingerprint=model.Fingerprint,basis_supplied=path=='warm',basis_accepted=False,iterations=float(model.IterCount),barrier_iterations=float(model.BarIterCount),native_runtime=float(model.Runtime),log_file=logfile,full_postsolve=None)
            if model.Status==2:
                audit,point,pi,alpha,weights=self.audit_copy(model);r['full_postsolve']=audit;r['objective']=float(model.ObjVal)
                file=f'warm_cold/PAIR_{i:02d}_{path}.npz';np.savez_compressed(OUT/file,point=point,pi=pi,alpha=alpha,lambda_values=weights);r.update(point_file=file,point_SHA=sha(OUT/file))
            model.dispose();text=(OUT/logfile).read_text(encoding='utf8',errors='replace')
            r['basis_accepted']=path=='warm' and 'discard basis' not in text and ('get start vectors from basis' in text or 'use basis' in text or 'crush' in text and 'warm-start' in text)
            self.warm_comparison.append(r);write('DW_RMP_WARM_COLD_COMPARISON.json',dict(tested=True,selected=False,records=self.warm_comparison,budget_charged=True))
            print('WARM_COLD',path,r['wall_seconds'],r['status'],r['objective'],r['basis_accepted'],flush=True)
            if self.cancel.is_set():break
        cold=[r for r in self.warm_comparison if r['path']=='cold'];warm=[r for r in self.warm_comparison if r['path']=='warm'];complete=len(cold)==len(warm)==2
        valid=complete and all(r['status']==2 and r['full_postsolve']['PASS'] for r in cold+warm) and max(r['objective'] for r in cold+warm)-min(r['objective'] for r in cold+warm)<=EPS
        cm=float(np.median([r['wall_seconds'] for r in cold])) if cold else None;wm=float(np.median([r['wall_seconds'] for r in warm])) if warm else None;reduction=1-wm/cm if cm and wm is not None else None
        self.warm_selected=bool(valid and all(r['basis_accepted'] for r in warm) and reduction>=.30)
        write('DW_RMP_WARM_COLD_COMPARISON.json',dict(tested=True,selected=self.warm_selected,same_RMP_fingerprint=self.master.model.Fingerprint,same_previous_basis=True,retained_column_keys=[c['key'] for c in self.master.column_data],previous_basis_file=self.rmps[-1]['basis_file'],pair_count=2,records=self.warm_comparison,cold_median_wall=cm,warm_median_wall=wm,median_wall_reduction=reduction,objective_agreement_PASS=valid,gate=.30,budget_charged=True,no_parameter_sweep=True))
    def observe_dual(self,pi,key):
        if self.previous_pi is not None:
            delta=pi-self.previous_pi;names=np.array(self.master.model.getAttr('ConstrName',self.master.coupling));critical=np.array([any(t in str(n).lower() for t in ('voltage','current','kva','grid','pcc')) for n in names])
            self.osc.append(dict(round=self.current_round,dual_SHA=key,L1=float(np.linalg.norm(delta,1)),L2=float(np.linalg.norm(delta)),Linf=float(np.linalg.norm(delta,np.inf)),normalized_L2=float(np.linalg.norm(delta)/max(np.linalg.norm(self.previous_pi),1e-12)),normalized_Linf=float(np.linalg.norm(delta,np.inf)/max(np.linalg.norm(self.previous_pi,np.inf),1e-12)),critical_grid_row_count=int(critical.sum()),critical_grid_L1=float(np.linalg.norm(delta[critical],1)),critical_grid_Linf=float(np.max(abs(delta[critical]),initial=0)),trajectory_turnover=0.,repeated_near_duplicates=0,rc_variance=None))
        self.last_true_pi=self.previous_pi.copy() if self.previous_pi is not None else None;self.previous_pi=pi.copy()
    def finish_osc(self,prices):
        if not self.osc or self.osc[-1]['round']!=self.current_round:return
        candidates=[c for p in prices for c in p['candidates'] if c['valid_negative']];now={c['column_SHA'] for c in candidates}
        turnover=1-len(now&self.previous_trajectories)/len(now|self.previous_trajectories) if now|self.previous_trajectories else 0.;near=0
        for p in prices:
            b=self.blocks[p['unit']];old=[c for c in self.master.column_data if c['unit']==p['unit'] and c['key'] in self.previous_trajectories]
            for c in p['candidates']:
                if not c['valid_negative'] or not old:continue
                with np.load(OUT/c['point_file']) as z:x=z['x'][b.mask]
                near+=int(min(float(np.mean(x!=o['x'][b.mask])) for o in old)<=.01)
        self.osc[-1].update(trajectory_turnover=turnover,repeated_near_duplicates=near,rc_variance=float(np.var([c['rc_inc'] for c in candidates])) if candidates else None)
        if now:self.previous_trajectories=now
        self.save()
    def smooth_snapshot(self,dual):
        pi,conv,true_key,file=dual;weight=self.smooth_weight;first=self.smooth_pi is None
        if first:self.smooth_pi=pi.copy();self.smooth_conv=conv.copy()
        else:self.smooth_pi=weight*pi+(1-weight)*self.smooth_pi;self.smooth_conv=weight*conv+(1-weight)*self.smooth_conv
        change=0. if self.last_true_pi is None else float(np.linalg.norm(pi-self.last_true_pi,np.inf)/max(1e-12,np.linalg.norm(self.last_true_pi,np.inf)))
        next_weight=weight if first else next_smoothing_weight(weight,change);key=hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest();file=f'SMOOTHED_DUAL_{self.current_round:04d}.npz';np.savez_compressed(OUT/file,pi=self.smooth_pi,alpha=self.smooth_conv)
        self.smooth_key=key;self.smooth_file=file;self.smooth_weight=next_weight
        self.smoothing_rows.append(dict(round=self.current_round,true_dual_SHA=true_key,smoothed_dual_SHA=key,smooth_file=file,alpha_used=weight,alpha_next=next_weight,first_no_distortion=first,normalized_true_change=change,smooth_true_Linf=float(np.max(abs(self.smooth_pi-pi),initial=0)),smooth_true_convexity_Linf=float(np.max(abs(self.smooth_conv-conv),initial=0)),accepted=0,rejected_after_true_RC=0,proposed=0,trajectory_turnover=0.))
        return file,key
    def true_four_pass(self):return any(c.get('PASS') and c.get('actual_four_overlap_seconds',0)>0 and c['workers']==4 for c in self.canaries)
    def solve_master(self,kind):
        if self.basis is not None and self.columns and not self.warm_tested:self.warm_canary()
        self.current_round+=1;model=self.master.model;warm=self.basis is not None
        if warm:
            vb,cb,keys=self.basis;assert keys==[c['key'] for c in self.master.column_data[:len(keys)]]
            model.setAttr('VBasis',self.master.z+self.master.lambdas,vb+[-1]*(model.NumVars-len(vb)));model.setAttr('CBasis',model.getConstrs(),cb);model.update()
        settings=dict(Threads=1,Method=2,Crossover=1,PreDual=0,BarConvTol=1e-11,Seed=20260929,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,LPWarmStart=2 if self.warm_selected else 1,TimeLimit=min(60,max(.001,self.remaining()-104)))
        if self.warm_selected:settings['Method']=1
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
        self.observe_dual(pi,key);self.bestU=model.ObjVal if self.bestU is None else min(self.bestU,model.ObjVal);self.save();print('POLICY_RMP',self.current_round,kind,model.ObjVal,self.spent(),flush=True)
        return pi,alpha,key,file
    def pricing_round(self,kind,dual,cap):
        pi,alpha,key,file=dual;results=[];self.monitor.phase=kind;sample_start=len(self.monitor.rows);batch_start=time.perf_counter();write('DW_INFLIGHT.json',dict(kind=kind,spent_before=self.spent(),reserved_optimize_seconds=min(self.remaining(),cap*math.ceil(4/self.workers)+4),round=self.current_round,dual_SHA=key))
        smooth_file,smooth_key=self.smooth_snapshot(dual);search_file=smooth_file if kind=='DISCOVERY' else file;search_key=smooth_key if kind=='DISCOVERY' else key
        for batch in range(math.ceil(4/self.workers)):
            pending=[]
            for k in range(self.workers):
                m=batch*self.workers+k
                if m>=4:break
                self.call+=1;job=dict(call=self.call,round=self.current_round,type=kind,unit=m,dual_SHA=search_key,dual_file=search_file,true_dual_SHA=key,true_dual_file=file,stabilized_discovery=search_key!=key,cap=cap,log=f'logs/PRICE_{self.call:04d}_{UNITS[m]}.log',receipt=f'pricing_receipts/PRICE_{self.call:04d}.json')
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
        self.monitor.sample();samples=[r for r in self.monitor.rows[sample_start:] if any(p['interval'][0]<=r['perf']<=p['interval'][1] for p in results)];stats=self.monitor.summary(samples)
        overlap=overlap_seconds([p['interval'] for p in results],4)
        safe=bool(len(results)==4 and not self.monitor.failed and all(r['native_status'] in (2,9) and not r['capture_errors'] and (r['ObjVal'] is None or r['valid_point']) for r in results) and stats['min_available_RAM'] is not None and stats['min_available_RAM']>=1024**3 and stats['max_commit_percent'] is not None and stats['max_commit_percent']<95 and (self.workers!=4 or overlap>0))
        canary=dict(round=self.current_round,workers=self.workers,PASS=safe,failures=list(set(self.monitor.failed)),solver_or_model_errors=len(results)!=4,all_same_dual=all(r['dual_SHA']==search_key and r['true_dual_SHA']==key for r in results),actual_four_overlap_seconds=overlap,native_calls=[r['call'] for r in results],batch_wall_seconds=time.perf_counter()-batch_start,**stats)
        self.canaries.append(canary);write('DW_PRICING_CONCURRENCY_CANARY.json',dict(attempts=self.canaries,selected_workers=self.workers,resource_PASS=safe,resource_safety_failure_observed=any(not c['PASS'] for c in self.canaries)))
        return sorted(results,key=lambda r:r['unit']),safe
    def add(self,r,pi,alpha):
        assert r['type']=='DISCOVERY' and r['valid_negative'] and r['rc_inc']<=DISCOVERY_RC
        m=r['unit'];b=self.blocks[m]
        with np.load(OUT/r['point_file']) as z:x=z['x'];assert np.array_equal(z['axis'],b.columns)
        assert b.validate(x,True)['PASS'] and r['full_original_local']['PASS'];rc=float(exact_rc(b,x,pi,alpha[m]));assert abs(rc-r['rc_inc'])<=EPS
        a,c,key=b.column(x)
        if key in self.seen[m]:return False
        exact,error=b.exact_coupling(x,a);assert error<=1e-12
        n=self.column_id;self.column_id+=1;file=f'columns/COLUMN_{n:06d}_{b.unit}.npz';ix=sorted(i for i,v in exact.items() if v)
        np.savez_compressed(OUT/file,x=x,axis=b.columns,a=a,c=np.array(c),exact_rows=ix,exact_numerators=np.array([str(exact[i].numerator) for i in ix]),exact_denominators=np.array([str(exact[i].denominator) for i in ix]))
        self.master.add(m,x,a,c,key);self.seen[m].add(key);self.columns.append(dict(number=n,round=self.current_round,MESS=b.unit,file=file,file_SHA=sha(OUT/file),SHA256=key,pricing_call=r['call'],rc_inc=rc,label='VALID_NEGATIVE_DISCOVERY_COLUMNS',pricing_optimum_claimed=False,native_status=r['native_status']))
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
        write('DW_THROUGHPUT_LIVE_STATUS.json',dict(round=self.current_round,RMP=len(self.rmps),pricing=len(self.prices),columns=len(self.columns),workers=self.workers,heavy_wall_union=self.spent(),remaining=self.remaining(),elapsed=self.elapsed(),best_L=self.bestL,best_U=self.bestU,materiality=self.materiality,stop=self.stop))
        table('DW_RMP_LEDGER.csv',[dict(round=r['round'],type=r['type'],status=r['status'],objective=r['objective'],dual_SHA=r['dual_SHA'],wall_seconds=r['wall_seconds'],receipt=f"RMP_RECEIPT_{r['round']:04d}.json") for r in self.rmps])
        for r in self.rmps:write(f"RMP_RECEIPT_{r['round']:04d}.json",r)
        table('DW_DISCOVERY_COLUMN_LEDGER.csv',self.columns)
        table('DW_MULTICOLUMN_DISCOVERY_LEDGER.csv',self.capture_ledger)
        table('DW_DUAL_OSCILLATION_AUDIT.csv',self.osc)
        table('DW_DUAL_SMOOTHING_LEDGER.csv',self.smoothing_rows)
        table('DW_THROUGHPUT_ITERATION_LEDGER.csv',self.rounds)
        table('DW_DISCOVERY_ITERATION_LEDGER.csv',[r for r in self.rounds if r['type']=='DISCOVERY'])
        table('DW_CERTIFICATION_ITERATION_LEDGER.csv',[r for r in self.rounds if r['type']!='DISCOVERY'])
        table('DW_CORRECTED_BOUND_LEDGER.csv',[dict(round=c['iteration'],type=c['type'],dual_SHA=c['dual_SHA'],certified=c['certified'],L_corr=c['L_corr'],U_RMP=c['U_RMP'],file=c['file']) for c in self.certs])
    def checkpoint(self,kind,prices,cert):
        poolrefs=read(OUT/'DW_THROUGHPUT_BASE_AUDIT.json')['checks']+[dict(file=(OUT/c['file']).relative_to(ROOT).as_posix(),file_SHA=c['file_SHA'],column_SHA=c['SHA256'],MESS=c['MESS']) for c in self.columns]
        state=dict(rmps=self.rmps,prices=self.prices,columns=self.columns,rounds=self.rounds,certs=self.certs,canaries=self.canaries,workers=self.workers,warm_tested=self.warm_tested,warm_selected=self.warm_selected,warm_comparison=self.warm_comparison,osc=self.osc,stabilized=self.stabilized,stabilization_tested=self.stabilization_tested,capture_ledger=self.capture_ledger,smooth_weight=self.smooth_weight,smoothing_rows=self.smoothing_rows,zero_discovery_streak=self.zero_discovery_streak,smoothing_stagnation=self.smoothing_stagnation,force_certification=self.force_certification,smooth_file=self.smooth_file,smooth_key=self.smooth_key,previous_trajectories=sorted(self.previous_trajectories))
        r=self.rmps[-1];write('DW_THROUGHPUT_CHECKPOINT_LATEST.json',dict(round=self.current_round,type=kind,pool=poolrefs,total_retained_columns=len(poolrefs),RMP=r,true_dual_SHA=r['dual_SHA'],smoothed_dual_SHA=self.smooth_key,alpha=self.smoothing_rows[-1]['alpha_used'] if self.smoothing_rows else None,smoothing_stagnation=self.smoothing_stagnation,pricing_receipts=[p['receipt'] for p in prices],new_columns=self.columns,beta_values=[p['ObjBound'] if p['valid_bound'] and kind!='DISCOVERY' else None for p in prices],corrected_LB=cert['L_corr'] if cert else None,certificate=cert,upper=r['objective'],best_interval=[self.bestL,self.bestU],materiality=self.materiality,elapsed_budget=self.spent(),optimize_intervals=self.intervals,elapsed_total=self.elapsed(),source_commit=self.commit,resource_canary=self.canaries[-1] if self.canaries else None,restart_state=state))
        (OUT/'DW_INFLIGHT.json').unlink(missing_ok=True)
    def run(self):
        schedule=['DISCOVERY']*5+['CERTIFICATION'];position=len([r for r in self.rounds if r['type']!='FINAL_CERTIFICATION'])%6
        try:
            while not self.stop and self.remaining()>35 and len(self.rounds)<30:
                if STOP.exists():self.stop='USER_STOP';break
                last=self.rmps[-1]['wall_seconds'] if self.rmps else 20.;reserve=max(30.,last);waves=math.ceil(4/self.workers);cycle=5*(last+20*waves)+(last+60*waves)+8
                final=bool(self.current_round and position==0 and 100<=self.remaining()<cycle+100)
                kind='FINAL_CERTIFICATION' if final else 'CERTIFICATION' if self.force_certification else schedule[position]
                if not final and self.remaining()<reserve+(20 if kind=='DISCOVERY' else 60)*waves+104:
                    if self.remaining()>=100:kind='FINAL_CERTIFICATION';final=True
                    else:self.stop='POLICY_CANARY_BUDGET';break
                round_start=time.perf_counter();before=len(self.columns);dual=self.solve_master(kind)
                if dual is None:
                    if self.cancel.is_set() and self.monitor.failed and not STOP.exists() and self.workers>1:
                        self.checkpoint(kind,[],None);old=self.workers;self.close_workers();self.stop=None;self.launch_with_downgrade(old//2);continue
                    break
                if self.bestU<=T_MATERIAL:self.materiality='PROVEN_NONMATERIAL';self.stop='RMP_UPPER_PROVES_NONMATERIAL';self.checkpoint(kind,[],None);break
                cap=min(60,(self.remaining()-4)/waves) if final else 20 if kind=='DISCOVERY' else 60
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
                        for c in p['candidates']:
                            if c['selected']:
                                merged=dict(p,**c);merged['valid_negative']=True;self.add(merged,dual[0],dual[1])
                            self.capture_ledger.append(dict(call=p['call'],round=p['round'],MESS=p['MESS'],arrival=c['arrival'],source=c['source'],raw_SHA=c['raw_SHA'],column_SHA=c['column_SHA'],point_file=c['point_file'],point_SHA=c['point_SHA'],rc_smooth=c['manual_search_rc'],rc_inc=c['rc_inc'],valid_negative=c['valid_negative'],selected=c['selected'],label=c['label'],pricing_optimum_claimed=False))
                else:
                    cert=self.certify(dual,prices,kind)
                    if self.force_certification and not all(p['valid_bound'] and p['ObjBound']>=-EPS for p in prices):self.smoothing_stagnation=True
                    self.force_certification=False;self.zero_discovery_streak=0
                if kind=='DISCOVERY':
                    self.zero_discovery_streak=self.zero_discovery_streak+1 if len(self.columns)==before else 0
                    if self.zero_discovery_streak>=3:self.force_certification=True
                smooth=self.smoothing_rows[-1];smooth['accepted']=len(self.columns)-before;smooth['proposed']=sum(len(p['candidates']) for p in prices);smooth['rejected_after_true_RC']=sum(c['manual_search_rc']<=DISCOVERY_RC and c['rc_inc']>DISCOVERY_RC for p in prices for c in p['candidates'])
                self.rounds.append(dict(round=self.current_round,type=kind,workers=self.workers,round_wall_seconds=time.perf_counter()-round_start,RMP_wall_seconds=self.rmps[-1]['wall_seconds'],pricing_optimize_union=union_seconds([p['interval'] for p in prices]),columns_added=len(self.columns)-before,dual_SHA=dual[2],corrected_LB=cert['L_corr'] if cert else None,RMP_upper=self.rmps[-1]['objective'],materiality=self.materiality,cumulative_heavy_wall=self.spent(),elapsed_total=self.elapsed()))
                self.checkpoint(kind,prices,cert);self.rounds[-1]['round_wall_seconds']=time.perf_counter()-round_start;self.rounds[-1]['elapsed_total']=self.elapsed();self.checkpoint(kind,prices,cert)
                self.save();print('POLICY_ROUND',self.current_round,kind,len(self.columns)-before,self.bestL,self.bestU,self.spent(),flush=True)
                self.finish_osc(prices);self.smoothing_rows[-1]['trajectory_turnover']=self.osc[-1]['trajectory_turnover'] if self.osc and self.osc[-1]['round']==self.current_round else 0.;self.checkpoint(kind,prices,cert);self.save()
                if final:self.stop=self.stop or 'THROUGHPUT_FINAL_CERTIFICATION_COMPLETE';break
                position=0 if kind!='DISCOVERY' else (position+1)%6
            self.stop=self.stop or 'POLICY_CANARY_BUDGET'
        except BaseException as error:
            self.stop='EXECUTION_ERROR:'+repr(error);self.cancel.set();write('EXECUTION_ERROR.json',dict(error=repr(error)));raise
        finally:
            self.close_workers();self.monitor.close();self.finish();self.master.model.dispose()
    def finish(self):
        assert self.spent()<=BUDGET,'PREREGISTERED900S_BUDGET_OVERRUN'
        old=read(POLICY/'DW_POLICY_CANARY_FINAL.json');oldrate=.80998069224726;newrate=len(self.columns)/(self.elapsed()/60);ds=[r['round_wall_seconds'] for r in self.rounds if r['type']=='DISCOVERY'];cs=[r['round_wall_seconds'] for r in self.rounds if r['type']!='DISCOVERY'];resource=bool(self.canaries and self.canaries[-1]['PASS']);failure=any(not c['PASS'] for c in self.canaries);median=float(np.median(ds)) if ds else None
        quality='PROMISING' if resource and not failure and median is not None and median<=35 and newrate>=2 and self.true_four_pass() else 'NOT_SUPPORTED'
        if not ds or self.stop.startswith('EXECUTION_ERROR'):quality='INCONCLUSIVE'
        first=next((r for r in self.rounds if r['corrected_LB'] is not None),None)
        value=dict(scientific_base=BASE,PR141_head=BASE_HEAD,preopt_commit=self.commit,status='POLICY_CANARY_INCONCLUSIVE' if self.materiality=='INCONCLUSIVE' else 'POLICY_CANARY_DECIDED',materiality=self.materiality,policy_canary=quality,stop_reason=self.stop,workers=self.workers,resource_PASS=resource,resource_safety_failure_observed=failure,initial_retained_columns=1078,new_RMP_solves=len(self.rmps),new_pricing_calls=len(self.prices),new_discovery_columns=len(self.columns),retained_columns=1078+len(self.columns),discovery_rounds=len(ds),certification_rounds=len(cs),median_discovery_round_wall=median,median_certification_round_wall=float(np.median(cs)) if cs else None,old_columns_per_minute=oldrate,new_columns_per_minute=newrate,RMP_warmstart_tested=self.warm_tested,RMP_warmstart_selected=self.warm_selected,dual_stabilization_tested=self.stabilization_tested,dual_stabilization_selected=self.stabilized,actual_4way_pricing_calls=sum(len(c.get('native_calls',[])) for c in self.canaries if c['workers']==4 and c.get('actual_four_overlap_seconds',0)>0),true_4way_resource_PASS=self.true_four_pass(),time_to_first_new_certified_LB=None if first is None else first['elapsed_total'],heavy_to_first_new_certified_LB=None if first is None else first['cumulative_heavy_wall'],best_corrected_LB=self.bestL,smallest_RMP_upper=self.bestU,final_interval=[self.bestL,self.bestU],material_threshold=T_MATERIAL,DW_ROOT_OPTIMAL_CERTIFIED=self.converged,DW_ROOT_LB=self.bestL if self.converged else None,total_optimize_wall_union=self.spent(),sum_native_optimize_wall=sum(b-a for a,b in self.intervals),total_elapsed_including_build_audit=self.elapsed(),heavy_wall_to_materiality_decision=self.spent() if self.materiality!='INCONCLUSIVE' else None,build_seconds=self.build_seconds,May_production=[0,0,0],no_branch_and_price=True,old_TIME_LIMIT_retroactively_added=False)
        if not self.warm_tested:write('DW_RMP_WARM_COLD_COMPARISON.json',dict(tested=False,selected=False,reason='No accepted discovery append reached before stop',records=[]))
        write('DW_TRUE_4WAY_RESOURCE_SUMMARY.json',dict(actual_4way_attempted=any(c['workers']==4 and c.get('native_calls') for c in self.canaries),actual_4way_pricing_calls=value['actual_4way_pricing_calls'],PASS=self.true_four_pass(),selected_workers=self.workers,attempts=self.canaries,all_native_pricing_overlap_four_seconds=sum(c.get('actual_four_overlap_seconds',0) for c in self.canaries),RAM_GATE_GIB=1,peak_scope='Observed samples inside native pricing intervals; exact unsampled peaks not claimed'))
        value.update(smoothing_enabled=True,smoothing_mode='adaptive_exponential',smoothing_alpha_initial=.30,smoothing_alpha_final=self.smooth_weight,SMOOTHING_STAGNATION=self.smoothing_stagnation,smoothing_proposed=sum(row['proposed'] for row in self.smoothing_rows),smoothing_true_negative=sum(c['valid_negative'] for c in self.capture_ledger),smoothing_rejected_after_true_RC=sum(row['rejected_after_true_RC'] for row in self.smoothing_rows),smoothing_accepted=len(self.columns),box_proximal_trust_region_run=False)
        write('DW_THROUGHPUT_FINAL.json',value);write('DW_OPTIMIZE_INTERVALS.json',dict(intervals=self.intervals,carried_budget_seconds=self.carried_heavy,union_seconds=self.spent(),budget=900));self.save();print('THROUGHPUT_DONE',value,flush=True)
if __name__=='__main__':Experiment().run()
