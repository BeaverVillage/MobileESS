"""Frozen four-way root continuation within one newly authorized grant."""
from .common import *
from .policy import convergence_certificate
from .cg_reuse import Mechanics
from .resources import Monitor
from v42_dw_resume.audit import Master,prototypes,corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_degen.identity import inputs,signature,digest
from v42_dw_root.run import exact_rc
from v42_dw_bound.certificate import global_dual,receipt
import numpy as np,multiprocessing as mp,gurobipy as gp,threading,gc

class Experiment(Mechanics):
    def __init__(self,resume=False):
        gc.collect();self.commit=verify_freeze();preserve_old();arc=read(ARC/'ARC_LP_CERTIFIED_RESULT.json');assert arc['ARC_LP_CERTIFIED'];assert not STOP.exists()
        basecp=read(SCI/'DW_CHECKPOINT_LATEST.json');self.initial_rmp=dict(basecp['RMP']);self.initial_rmp['point_file']='../'+SCI.name+'/'+self.initial_rmp['point_file'];self.historical_optimize=basecp['cumulative_optimize']
        self.resume_checkpoint=read(OUT/'DW_CHECKPOINT_LATEST.json') if (OUT/'DW_CHECKPOINT_LATEST.json').exists() else None
        if self.resume_checkpoint:assert self.resume_checkpoint['type']!='TERMINAL','ONE_CONTINUATION_GRANT_ALREADY_FINISHED'
        if not (OUT/'CG_STARTED.json').exists():write('CG_STARTED.json',dict(preopt_commit=self.commit,new_grant=1800,historical_PR149=self.historical_optimize,explicit_user_authorized_new_task=True))
        for directory in ('logs','columns','pricing_points','pricing_receipts','bound_certificates'):(OUT/directory).mkdir(parents=True,exist_ok=True)
        self.RMP_cap=300.;self.force_final_after_incomplete=False;self.wait_events=[];self.runtime_suspended=False
        self.begin=time.perf_counter();self.budget_carried=0.;self.wall_carried=0.;self.intervals=[];self.rmps=[];self.prices=[];self.columns=[];self.rounds=[];self.certs=[];self.canaries=[];self.capture_ledger=[];self.smoothing_rows=[];self.current_round=basecp['RMP']['round'];self.call=max(p['call'] for p in basecp['restart_state']['prices']);self.column_id=1604;self.workers=4;self.context=mp.get_context('spawn');self.cancel=self.context.Event();self.processes=[];self.pipes=[];self.pids=[];self.monitor=Monitor(self.pids,self.cancel)
        self.floor=arc['L_arc_cert'];self.authority=read(ARC/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');old=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json');self.best_corr=old['best_corrected_LB'];self.bestU=old['smallest_RMP_upper'];self.bestL=max(self.floor,self.best_corr);self.materiality=decision(self.bestL,self.bestU,self.authority);self.converged=False;self.stop=None;self.accepted=[];self.uppers=[self.bestU]
        self.smooth_weight=basecp['alpha_next'];self.active_start=None;self.resource_gate('INITIAL_POOL_RESTORE')
        start=time.perf_counter();self.A,self.d,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        assert signature(self.B,self.e)==read(PREVIOUS/'DW_BOUND_CHECKPOINT_AUDIT.json')['reference_signature']
        with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:self.native=z['names']
        self.blocks=prototypes(self.B,self.e,self.owner,self.row_owner,self.native);self.master=Master(self.B,self.e,self.owner,self.row_owner,self.native);self.seen=[set() for _ in UNITS]
        for directory,h in old_columns():
            m=UNITS.index(h['MESS'])
            with np.load(directory/h['file']) as z:
                new='x' in z;x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c'] if new else z['objective'])
            assert self.blocks[m].column(x)[2]==h['SHA256'];self.master.add(m,x,a,c,h['SHA256']);self.seen[m].add(h['SHA256'])
        assert len(self.master.lambdas)==START_COLUMNS
        with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:self.lo=z['lower'];self.hi=z['upper']
        assert sha(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz')==read(PREVIOUS/'COORDINATE_ENCLOSURE_PROOF.json')['artifact_SHA']
        self.route_mask=pure_binary_equalities(self.A,self.d);self.build_seconds=time.perf_counter()-start;self.previous_pi=None;self.last_true_pi=None;self.smooth_pi=None;self.smooth_conv=None;self.smooth_weight=.125;self.smooth_file=None;self.smooth_key=None
        self.restore_smoothing();self.setup_audits();self.persistent_selected=False;self.restore_run();from v42_dw_accelerated.persistent import FullScalePersistentRMP;self.persistent_adapter=FullScalePersistentRMP(self.master)
        self.watch_done=threading.Event();self.active=[None];self.active_start=None;self.active_spent=0
        def watch():
            while not self.watch_done.wait(.2):
                over=self.active_start is not None and self.active_spent+time.perf_counter()-self.active_start>=BUDGET-1
                if STOP.exists() or over:
                    self.cancel.set()
                if self.cancel.is_set() and self.active[0] is not None:self.active[0].terminate()
        self.watch_thread=threading.Thread(target=watch,daemon=True);self.watch_thread.start()
        self.start_workers(4)
        self.save()
        if not self.resume_checkpoint:self.checkpoint('RESTORED_TRUE_RMP')

    def restore_smoothing(self):
        cp=read(SCI/'DW_CHECKPOINT_LATEST.json');base=read(OUT/'DW_CONTINUATION_BASE_AUDIT.json')
        matches=cp['pool_SHA']==base['pool_SHA'] and cp['dual_axis_SHA']==digest(np.flatnonzero(self.row_owner<0)) and cp['row_axis_SHA']==digest(self.e['row_names'][self.row_owner<0])
        self.smooth_weight=cp['alpha_next'];self.smooth_file='../'+SCI.name+'/'+cp['smooth_file'];self.smooth_key=cp['smooth_key']
        with np.load(SCI/cp['RMP']['point_file']) as z:self.previous_pi=z['pi'].copy();current_pi=z['pi'].copy();current_alpha=z['alpha'].copy()
        with np.load(SCI/cp['RMP']['point_file']) as z:self.last_true_pi=z['pi'].copy()
        if matches:
            with np.load(OUT/self.smooth_file) as z:self.smooth_pi=z['pi'].copy();self.smooth_conv=z['alpha'].copy()
            assert hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest()==self.smooth_key
        else:
            self.smooth_pi=current_pi;self.smooth_conv=current_alpha;self.smooth_file='SMOOTHING_FALLBACK.npz';np.savez_compressed(OUT/self.smooth_file,pi=self.smooth_pi,alpha=self.smooth_conv);self.smooth_key=hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest()
        self.uppers=[r['objective'] for r in cp['restart_state']['rmps'] if r['status']==2][-6:]
        write('DW_SMOOTHING_RESTORE_RECEIPT.json',dict(PASS=True,restored_exact=matches,alpha=self.smooth_weight,smooth_file=self.smooth_file,smooth_key=self.smooth_key,pool_SHA=cp['pool_SHA'],native_optimize_calls=0))

    def spent(self):return self.budget_carried+union_seconds(self.intervals)
    def remaining(self):return BUDGET-self.spent()
    def elapsed(self):return self.wall_carried+time.perf_counter()-self.begin

    def smooth_snapshot(self,dual):
        pi,conv,true_key,file=dual;weight=self.smooth_weight;first=self.smooth_pi is None
        if first:self.smooth_pi=pi.copy();self.smooth_conv=conv.copy()
        else:self.smooth_pi=weight*pi+(1-weight)*self.smooth_pi;self.smooth_conv=weight*conv+(1-weight)*self.smooth_conv
        change=0. if self.last_true_pi is None else float(np.linalg.norm(pi-self.last_true_pi,np.inf)/max(1e-12,np.linalg.norm(self.last_true_pi,np.inf)))
        next_weight=weight if first else next_smoothing_weight(weight,change);key=hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest();file=f'SMOOTHED_DUAL_{self.current_round:04d}.npz';np.savez_compressed(OUT/file,pi=self.smooth_pi,alpha=self.smooth_conv)
        self.smooth_key=key;self.smooth_file=file;self.smooth_weight=next_weight
        self.smoothing_rows.append(dict(round=self.current_round,true_dual_SHA=true_key,smoothed_dual_SHA=key,smooth_file=file,alpha_used=weight,alpha_next=next_weight,first_no_distortion=first,normalized_true_change=change,accepted=0,proposed=0,rejected_after_true_RC=0))
        return file,key

    def solve_master(self,kind):
        self.close_workers()  # Idle pricing native heaps are unnecessary for RMP.
        self.current_round+=1;self.resource_gate('RMP');rmp_begin=time.perf_counter();model=self.master.model;model.reset(0 if self.persistent_selected else 1)
        settings=dict(Threads=1,Method=2,Crossover=1,LPWarmStart=0,PreDual=0,BarConvTol=1e-11,Seed=20260929,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,TimeLimit=min(self.RMP_cap,max(.001,self.remaining()-124)))
        for k,v in settings.items():model.setParam(k,v)
        model.Params.LogFile=(OUT.relative_to(ROOT)/f'logs/RMP_{self.current_round:04d}.log').as_posix()
        self.monitor.phase='RMP';self.active_spent=self.spent();self.active_start=time.perf_counter();self.active[0]=model
        write('DW_INFLIGHT.json',dict(kind='RMP',spent_before=self.spent(),reserved_optimize_seconds=settings['TimeLimit']+1,round=self.current_round))
        start=time.perf_counter();(self.persistent_adapter.solve(lambda m,w:m.terminate() if self.cancel.is_set() or STOP.exists() else None) if self.persistent_selected else model.optimize(lambda m,w:m.terminate() if self.cancel.is_set() or STOP.exists() else None));end=time.perf_counter();self.active[0]=None;self.active_start=None;self.intervals.append([start,end]);self.debit_done()
        row=dict(round=self.current_round,type=kind,status=model.Status,objective=None,dual_SHA=None,wall_seconds=end-start,interval=[start,end],warm_basis_supplied=False,settings=settings,point_file=None)
        self.rmps.append(row)
        if model.Status!=2:self.stop='RMP_NOT_OPTIMAL';self.save();return None
        checked=self.master.raw_audit();point=np.zeros(self.B.shape[1]);point[self.master.columns]=model.getAttr('X',self.master.z)
        for v,c in zip(self.master.lambdas,self.master.column_data):point[self.blocks[c['unit']].columns]+=float(v.X)*c['x']
        full=corrected_rows(self.A,self.d,point,False,self.route_mask);assert checked['PASS'] and full['PASS'] and model.DualVio<=EPS
        pi=np.array(model.getAttr('Pi',self.master.coupling));alpha=np.array(model.getAttr('Pi',self.master.conv));key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest();sense=self.master.d['sense']
        assert np.all(pi[sense=='<']<=0) and np.all(pi[sense=='>']>=0)
        manual=np.array([c['c']-float(pi@c['a'])-alpha[c['unit']] for c in self.master.column_data]);global_rc=self.master.d['objective']-self.master.A.T@pi
        error=max(float(np.max(abs(manual-np.array(model.getAttr('RC',self.master.lambdas))),initial=0)),float(np.max(abs(global_rc-np.array(model.getAttr('RC',self.master.z))),initial=0)));assert error<=EPS
        file=f'RMP_POINT_{self.current_round:04d}.npz';np.savez_compressed(OUT/file,point=point,pi=pi,alpha=alpha,lambda_values=np.array(model.getAttr('X',self.master.lambdas)))
        row.update(objective=model.ObjVal,dual_SHA=key,point_file=file,point_SHA=sha(OUT/file),primal_SHA=hashlib.sha256(point.tobytes()).hexdigest(),full_original=full,master=checked,manual_RC_error=error,L_corr_at_solve=self.best_corr,L_cert_at_solve=self.bestL,total_RMP_wall=time.perf_counter()-rmp_begin)
        self.last_true_pi=self.previous_pi.copy() if self.previous_pi is not None else None;self.previous_pi=pi.copy();self.bestU=min(self.bestU,model.ObjVal);self.materiality=decision(self.bestL,self.bestU,self.authority)
        # Materiality is diagnostic; it never stops root CG.
        self.tier_audit('DISCOVERY',pi,alpha,key);self.save();print('THRESHOLD_RMP',self.current_round,model.ObjVal,self.spent(),self.materiality,flush=True);return pi,alpha,key,file

    def certify(self,dual,prices):
        pi,alpha,key,file=dual;value,proof=global_dual(self.master.A,self.master.d,pi,self.lo[self.master.columns],self.hi[self.master.columns])
        c=receipt(self.current_round,1,pi,alpha,key,value,proof,prices,self.authority_rmp()['objective'],self.master,self.blocks);c['true_dual_origin_RMP']=self.authority_rmp()['round'];c['latest_RMP_optimal']=self.authority_rmp()['status']==2;c['type']='FINAL_CERTIFICATION';c['file']=f'bound_certificates/ROUND_{self.current_round:04d}.json'
        if c['certified']:self.best_corr=max(self.best_corr,c['L_corr'])
        self.bestL=max(self.floor,self.best_corr);self.materiality=decision(self.bestL,self.bestU,self.authority);self.converged=convergence_certificate(c,prices,key)
        c['materiality']=self.materiality;c['aggregated_lower']=self.bestL;c['threshold']=self.authority['T_cert'];write(c['file'],c);self.certs.append(c);return c

    def save(self):
        for r in self.rmps:write(f"RMP_RECEIPT_{r['round']:04d}.json",r)
        table('DW_RMP_LEDGER.csv',[dict(round=r['round'],type=r['type'],status=r['status'],objective=r['objective'],dual_SHA=r['dual_SHA'],wall_seconds=r['wall_seconds']) for r in self.rmps]);table('DW_DISCOVERY_COLUMN_LEDGER.csv',self.columns);table('DW_MULTICOLUMN_DISCOVERY_LEDGER.csv',self.capture_ledger);table('DW_DUAL_SMOOTHING_LEDGER.csv',self.smoothing_rows);table('DW_ACCELERATED_CG_ITERATION_LEDGER.csv',self.rounds)
        distance=[dict(point='PRE_CG',U_RMP=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['smallest_RMP_upper'],L_arc_cert=self.floor,L_corr=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['best_corrected_LB'],L_final=max(self.floor,read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['best_corrected_LB']),T_cert=self.authority['T_cert'],D_U=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['smallest_RMP_upper']-self.authority['T_cert'],D_L=self.authority['T_cert']-max(self.floor,read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['best_corrected_LB']))]+[dict(point=f"RMP_{r['round']}",U_RMP=r['objective'],L_arc_cert=self.floor,L_corr=r['L_corr_at_solve'],L_final=r['L_cert_at_solve'],T_cert=self.authority['T_cert'],D_U=r['objective']-self.authority['T_cert'],D_L=self.authority['T_cert']-r['L_cert_at_solve']) for r in self.rmps if r['status']==2]
        if self.certs:distance.append(dict(point='FINAL_CERTIFICATION',U_RMP=self.bestU,L_arc_cert=self.floor,L_corr=self.best_corr,L_final=self.bestL,T_cert=self.authority['T_cert'],D_U=self.bestU-self.authority['T_cert'],D_L=self.authority['T_cert']-self.bestL))
        table('DW_ACCELERATED_CG_THRESHOLD_DISTANCE.csv',distance)
        write('DW_LIVE_STATUS.json',dict(round=self.current_round,discovery_rounds=len(self.accepted),RMP=len(self.rmps),pricing=len(self.prices),columns=len(self.columns),heavy_wall_union=self.spent(),remaining=self.remaining(),best_corr=self.best_corr,floor=self.floor,best_L=self.bestL,best_U=self.bestU,threshold=self.authority['T_cert'],materiality=self.materiality,stop=self.stop))

    def checkpoint(self,kind,prices=(),cert=None):
        checkpoint_start=time.perf_counter()
        poolrefs=read(SCI/'DW_CHECKPOINT_LATEST.json')['pool']+[dict(file=(OUT/c['file']).relative_to(ROOT).as_posix(),file_SHA=c['file_SHA'],column_SHA=c['SHA256'],MESS=c['MESS']) for c in self.columns]
        poolSHA=hashlib.sha256(json.dumps([(x['MESS'],x['column_SHA']) for x in poolrefs],separators=(',',':')).encode()).hexdigest()
        write('DW_CHECKPOINT_LATEST.json',dict(type=kind,pool=poolrefs,total_retained_columns=len(poolrefs),pool_SHA=poolSHA,dual_axis_SHA=digest(np.flatnonzero(self.row_owner<0)),row_axis_SHA=digest(self.e['row_names'][self.row_owner<0]),RMP=self.rmps[-1] if self.rmps else self.initial_rmp,pricing_receipts=[p['receipt'] for p in prices],new_columns=self.columns,certificate=cert,best_interval=[self.bestL,self.bestU],best_corrected_LB=self.best_corr,arc_floor=self.floor,threshold_authority=self.authority,alpha_next=self.smooth_weight,smooth_file=self.smooth_file,smooth_key=self.smooth_key,optimize_intervals=self.intervals,elapsed_budget=self.spent(),elapsed_wall=self.elapsed(),authority_key=self.audit_authority.key,audit_cache_SHA=sha(OUT/'PHYSICAL_AUDIT_CACHE.json'),feature_selection_SHA=sha(OUT/'DW_RUNTIME_FEATURE_SELECTION.json'),early_stop_statistics=[p.get('early_stop') for p in prices],resource_usage=self.monitor.summary(self.monitor.rows),audit_receipts=self.audit_rows,source_commit=self.commit,historical_PR149_optimize=self.historical_optimize,cumulative_optimize=self.historical_optimize+self.spent(),restart_state=dict(rmps=self.rmps,prices=self.prices,rounds=self.rounds,columns=self.columns,certs=self.certs,canaries=self.canaries,capture_ledger=self.capture_ledger,smoothing_rows=self.smoothing_rows,accepted=self.accepted,uppers=self.uppers,audit_rows=self.audit_rows,validation_rows=self.validation_rows,checkpoint_timings=getattr(self,'checkpoint_timings',[]))))
        write('DW_CONTINUATION_LATEST_CHECKPOINT.json',read(OUT/'DW_CHECKPOINT_LATEST.json'));self.debit_done()
        if (OUT/'DW_PHASE_STATE.json').exists() and (prices or kind=='TERMINAL'):
            phase=read(OUT/'DW_PHASE_STATE.json');phase['committed']=True;write('DW_PHASE_STATE.json',phase)
        checkpoint_rows=getattr(self,'checkpoint_timings',[]);checkpoint_rows.append(dict(round=self.current_round,kind=kind,wall=time.perf_counter()-checkpoint_start));self.checkpoint_timings=checkpoint_rows;table('DW_CHECKPOINT_TIMING.csv',checkpoint_rows)
        # Keep inflight reservation until the associated phase/point is durable.
        if prices or kind not in ('INITIAL_TRUE_RMP',):(OUT/'DW_INFLIGHT.json').unlink(missing_ok=True)

    def run(self):
        try:
            dual=self.resume_dual() if self.resume_checkpoint else self.last_completed_dual();self.checkpoint('RESTORED_TRUE_RMP')
            while not self.stop and not self.converged:
                if STOP.exists():self.stop='USER_STOP';break
                if self.remaining()<144:
                    self.run_certification(dual,'BUDGET_RESERVE');self.stop=self.stop or 'NEW_BUDGET_BLOCK_RESERVE_EXHAUSTED';break
                before=len(self.columns);round_start=time.perf_counter();prices,safe=self.pricing_round('DISCOVERY',dual,20)
                if not safe:self.stop='RESOURCE_OR_PRICING_FAILURE';self.checkpoint('DISCOVERY_FAILED',prices);break
                self.parallel_validation(prices,dual)
                for p in prices:
                    for c in p['candidates']:
                        if c['selected']:self.add(dict(p,**c),dual[0],dual[1])
                        self.capture_ledger.append(dict(call=p['call'],round=p['round'],MESS=p['MESS'],arrival=c['arrival'],point_file=c['point_file'],point_SHA=c['point_SHA'],column_SHA=c['column_SHA'],rc_smooth=c['manual_search_rc'],rc_true=c['rc_inc'],valid_negative=c['valid_negative'],selected=c['selected'],pricing_optimum_claimed=False))
                count=len(self.columns)-before;self.accepted.append(count);smooth=self.smoothing_rows[-1];smooth.update(accepted=count,proposed=sum(len(p['candidates']) for p in prices),rejected_after_true_RC=sum(c['manual_search_rc']<=DISCOVERY_RC and c['rc_inc']>DISCOVERY_RC for p in prices for c in p['candidates']))
                prior=self.bestU;self.checkpoint('DISCOVERY_ADDED',prices);newdual=self.solve_master('POST_DISCOVERY_TRUE_RMP')
                if newdual is not None:dual=newdual;self.uppers.append(self.bestU)
                trigger=early_trigger(self.accepted,self.uppers,self.authority['T_cert'])
                self.rounds.append(dict(discovery_round=len(self.accepted),block=(len(self.accepted)-1)//8+1,pricing_round=prices[0]['round'],post_RMP_round=self.current_round,workers=4,columns_added=count,round_wall_seconds=time.perf_counter()-round_start,pricing_optimize_union=union_seconds([p['interval'] for p in prices]),pricing_batch_wall=self.canaries[-1]['batch_wall_seconds'],validation_wall=self.validation_rows[-1]['total_wall'],audit_wall=self.audit_rows[-1]['wall'],RMP_wall=self.rmps[-1].get('total_RMP_wall'),U_before=prior,U_after=self.bestU,delta_U_round=prior-self.bestU,cumulative_delta_U=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['smallest_RMP_upper']-self.bestU,D_U=self.bestU-self.authority['T_cert'],L_cert=self.bestL,D_L=self.authority['T_cert']-self.bestL,early_certification_trigger=trigger))
                self.checkpoint('BLOCK_COMPLETE' if len(self.accepted)%8==0 else 'POST_DISCOVERY',prices);self.save();print('CONTINUATION_DISCOVERY',len(self.accepted),count,self.bestU,self.spent(),trigger,flush=True)
                if newdual is None:
                    self.run_certification(self.last_completed_dual(),'INCOMPLETE_RMP');self.stop='RMP_NOT_OPTIMAL';break
                # Continue even after a materiality decision.
                if trigger:self.run_certification(dual,trigger)
            self.stop=self.stop or ('CERTIFIED_ROOT_CONVERGENCE' if self.converged else 'ROOT_GRANT_STOP')
        except BaseException as error:
            self.stop='EXECUTION_ERROR:'+repr(error);self.cancel.set();write('CG_EXECUTION_ERROR.json',dict(error=repr(error)));raise
        finally:
            self.close_workers();self.full_pool_final();self.watch_done.set();self.watch_thread.join();self.monitor.close();self.finish();self.master.model.dispose()

    def run_certification(self,dual,reason):
        if self.converged:return
        if self.remaining()<2:return
        if any(c['dual_SHA']==dual[2] for c in self.certs):return
        self.tier_audit('FINAL_CERTIFICATION',dual[0],dual[1],dual[2])
        cap=max(.001,self.remaining()-2) if reason=='BUDGET_RESERVE' else min(120.,max(.001,self.remaining()-2))
        prices,safe=self.pricing_round('FINAL_CERTIFICATION',dual,cap)
        if safe:
            c=self.certify(dual,prices);c['trigger']=reason;write(c['file'],c);write('DW_ACCELERATED_FINAL_CERTIFICATION.json',dict(status='COMPLETED',certificate=c,pricing_receipts=[p['receipt'] for p in prices],same_true_dual=dual[2],cap=cap,trigger=reason));self.checkpoint('FINAL_CERTIFICATION',prices,c)
        else:self.stop='RESOURCE_OR_PRICING_FAILURE'
        if self.converged:self.stop='CERTIFIED_ROOT_CONVERGENCE'
        # Materiality is diagnostic; it never stops root CG.

    def finish(self):
        assert self.spent()<=1800
        if not (OUT/'DW_ACCELERATED_FINAL_CERTIFICATION.json').exists():write('DW_ACCELERATED_FINAL_CERTIFICATION.json',dict(status='NOT_RUN',reason=self.stop,exact_threshold_decision=self.materiality))
        self.materiality=decision(self.bestL,self.bestU,self.authority);ds=[r['round_wall_seconds'] for r in self.rounds];elapsed=self.elapsed()
        write('DW_ACCELERATED_FINAL_RESULT.json',dict(status='THRESHOLD_EXPERIMENT_INCONCLUSIVE' if self.materiality=='INCONCLUSIVE' else 'EXACT_THRESHOLD_DECISION',materiality=self.materiality,stop_reason=self.stop,initial_retained_columns=START_COLUMNS,retained_columns=START_COLUMNS+len(self.columns),new_RMP_solves=len(self.rmps),new_pricing_calls=len(self.prices),new_discovery_columns=len(self.columns),discovery_rounds=len(self.accepted),certification_rounds=len(self.certs),best_corrected_LB=self.best_corr,new_corrected_LB=self.certs[-1]['L_corr'] if self.certs and self.certs[-1]['certified'] else None,arc_floor=self.floor,best_certified_LB=self.bestL,smallest_RMP_upper=self.bestU,final_interval=[self.bestL,self.bestU],material_threshold=self.authority['T_cert'],threshold_authority=self.authority,DW_ROOT_OPTIMAL_CERTIFIED=self.converged,total_optimize_wall_union=self.spent(),sum_native_optimize_wall=sum(b-a for a,b in self.intervals),elapsed_including_build_audit=elapsed,build_seconds=self.build_seconds,columns_per_min=len(self.columns)/(elapsed/60),discovery_median=float(np.median(ds)) if ds else None,RMP_upper_decrease_per_min=(read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['smallest_RMP_upper']-self.bestU)/(elapsed/60),warm_RMP_selected=False,workers=4,Threads=1,RAM_floor_GiB=1,actual_four_overlap_seconds=sum(c.get('actual_four_overlap_seconds',0) for c in self.canaries),adaptive_smoothing=True,smoothing_alpha_final=self.smooth_weight,no_domain_restriction=True,pricing_redesign=False,May_production=[0,0,0],Branch_and_Price=False))
        write('DW_OPTIMIZE_INTERVALS.json',dict(intervals=self.intervals,union_seconds=self.spent(),budget_carried=self.budget_carried,current_segment_union=union_seconds(self.intervals),previous_intervals_file='PRE_RESUME_DW_OPTIMIZE_INTERVALS.json' if self.budget_carried else None,budget=1800,arc_budget_carried=0,historical_PR149_optimize=self.historical_optimize,cumulative_optimize=self.historical_optimize+self.spent()));self.checkpoint('TERMINAL');self.save();self.runtime_receipts();self.continuation_receipts();print('CONTINUATION_CG_DONE',self.materiality,self.bestL,self.bestU,len(self.columns),self.spent(),flush=True)

from .integration import Integration
# Runtime methods override only adapters; frozen science imports remain original.
for _name in Integration.METHODS:setattr(Experiment,_name,getattr(Integration,_name))
if __name__=="__main__":
 import sys
 Experiment(resume='--resume' in sys.argv).run()
