"""Persistent isolated full-domain pricing worker; no RMP/pool mutations."""
from .common import *
def main(connection,units,stop_event):
    import numpy as np,gurobipy as gp,threading
    from fractions import Fraction as F
    from v42_dw_resume.audit import Block,corrected_rows,pure_binary_equalities
    from v42_dw_root.partition import axes
    from v42_dw_root.run import exact_rc
    from v42_degen.identity import inputs
    from v42_dw_root.models import subset
    blocks={};full={};active=[None];done=threading.Event();starts={}
    def watch():
        while not done.wait(.2):
            if (stop_event.is_set() or STOP.exists()) and active[0] is not None:active[0].terminate()
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    try:
        A,d,B,e,*_=inputs();owner,row_owner=axes()
        with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        rr={m:[] for m in units}
        for i in range(A.shape[0]):
            deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
            if len(deps)==1 and next(iter(deps)) in rr:rr[next(iter(deps))].append(i)
        for m in units:
            b=Block(B,e,owner,row_owner,native,m);blocks[m]=b
            rows=np.array(rr[m]);cols=b.columns;matrix=A[rows][:,cols]
            attrs=dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],lower=d['lower'][cols],upper=d['upper'][cols],types=d['types'][cols],objective=d['objective'][cols],constant=np.array(0.))
            full[m]=(matrix,attrs,pure_binary_equalities(matrix,attrs));starts[m]=None
            accepted=read(SCI/'DW_CHECKPOINT_LATEST.json')['pool'];seed=next(c for c in reversed(accepted) if c['MESS']==b.unit)
            with np.load(ROOT/seed['file']) as z:starts[m]=(z['x'] if 'x' in z else z['local_values']).copy()
            assert b.validate(starts[m],True)['PASS']
        del A,d,B,e,owner,row_owner,native,rr
        connection.send(dict(ready=True,pid=os.getpid(),census={m:b.census() for m,b in blocks.items()}))
        while True:
            job=connection.recv()
            if job is None:break
            m=job['unit'];b=blocks[m];model=b.model
            with np.load(OUT/job['dual_file']) as z:pi=z['pi'];alpha=z['alpha']
            key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest();assert key==job['dual_SHA']
            cost=b.price(pi,alpha[m]);assert model.ModelSense==1 and model.ObjCon==-float(alpha[m])
            for j in np.flatnonzero(np.diff(b.CSC.indptr)):
                k=b.CSC.indptr[j];assert F(float(cost[j]))==F(float(b.d['objective'][j]))-F(float(b.CSC.data[k]))*F(float(pi[b.CSC.indices[k]]))
            if starts[m] is not None:model.setAttr('Start',b.vars,starts[m].tolist())
            settings=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,MIPGap=0.,MIPGapAbs=0.,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,Seed=20260929,TimeLimit=job['cap'])
            for k,v in settings.items():model.setParam(k,v)
            model.Params.LogFile=(OUT.relative_to(ROOT)/job['log']).as_posix()
            from v42_dw_runtime.contracts import DiscoverySnapshot,RuntimeFlags
            from v42_dw_runtime.validation import DiscoveryController,OriginalBlockValidator
            with np.load(OUT/job['true_dual_file']) as z:tp=z['pi'];ta=z['alpha']
            snapshot=DiscoverySnapshot.create(job['round'],tp,pi,ta,alpha,job.get('smoothing_alpha',.1),job['RMP_objective'])
            assert snapshot.dual_SHA==job['true_dual_SHA']
            matrix,attrs,mask=full[m];validator=OriginalBlockValidator(m,b,matrix,attrs,mask)
            flags=RuntimeFlags(DW_DISCOVERY_EARLY_STOP=job['type']=='DISCOVERY')
            controller=DiscoveryController(job['type'],m,snapshot,validator,flags,job['retained_SHAs'])
            timing=dict(first_raw_incumbent=None,accepted_candidate_timestamps=[],quota_fill_time=None,terminate_request_time=None)
            captured=[];capture_seen=set();capture_errors=[]
            def capture(x,native_obj,source):
                digest=hashlib.sha256(x.tobytes()).hexdigest()
                if digest not in capture_seen:
                    capture_seen.add(digest);captured.append(dict(x=x,raw_SHA=digest,solver_objective=native_obj,source=source,arrival=len(captured)))
            def callback(native,where):
                if stop_event.is_set() or STOP.exists():native.terminate()
                if where==gp.GRB.Callback.MIPSOL and timing['first_raw_incumbent'] is None:timing['first_raw_incumbent']=time.perf_counter()
                if job['type']=='DISCOVERY' and where==gp.GRB.Callback.MIPSOL:
                    value=float(native.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    if value<=DISCOVERY_RC:
                        try:
                            observed=np.array(native.cbGetSolution(b.vars),dtype=np.float64);capture(observed,value,'MIPSOL')
                            class StopProxy:
                                def terminate(self):
                                    now=time.perf_counter();timing['terminate_request_time']=now
                                    if len(controller.accepted)==4:
                                        timing['quota_fill_time']=now;timing['accepted_candidate_timestamps'].append(dict(time=now,SHA=validator.trajectory_sha(observed)))
                                    native.terminate()
                            before=len(controller.accepted);controller.observe(observed,StopProxy(),value)
                            if len(controller.accepted)>before and (not timing['accepted_candidate_timestamps'] or timing['accepted_candidate_timestamps'][-1]['SHA']!=validator.trajectory_sha(observed)):timing['accepted_candidate_timestamps'].append(dict(time=time.perf_counter(),SHA=validator.trajectory_sha(observed)))
                            if controller.stop_reason=='DISCOVERY_QUOTA_FILLED' and timing['quota_fill_time'] is None:
                                timing['quota_fill_time']=time.perf_counter()
                            if controller.errors:capture_errors.extend(controller.errors)
                        except Exception as error:capture_errors.append(repr(error));native.terminate()
            start=time.perf_counter();active[0]=model
            if stop_event.is_set() or STOP.exists():model.Params.TimeLimit=.001
            model.optimize(callback);end=time.perf_counter();active[0]=None
            def attribute(name):
                try:v=float(getattr(model,name));return v if np.isfinite(v) and abs(v)<1e90 else None
                except (gp.GurobiError,AttributeError):return None
            obj=attribute('ObjVal') if model.SolCount else None;bound=attribute('ObjBound');rc=None;valid_point=False;physical=None;raw=None;point_file=None
            if model.SolCount:
                x=np.array(model.getAttr('X',b.vars));physical=b.validate(x,True);matrix,attrs,mask=full[m];raw=corrected_rows(matrix,attrs,x,True,mask)
                rc=float(exact_rc(b,x,pi,alpha[m]));valid_point=bool(physical['PASS'] and raw['PASS'] and obj is not None and abs(rc-obj)<=EPS)
                point_file=f"pricing_points/PRICE_{job['call']:04d}.npz";np.savez_compressed(OUT/point_file,x=x,axis=b.columns)
                if valid_point:starts[m]=x.copy()
            candidates=[]
            if job['type']=='DISCOVERY':
                if model.SolCount and obj is not None and obj<=DISCOVERY_RC:capture(x.copy(),obj,'FINAL_X')
                accepted=0;selected_SHAs=set();retained=set(job['retained_SHAs'])
                with np.load(OUT/job.get('true_dual_file',job['dual_file'])) as z:true_pi=z['pi'];true_alpha=z['alpha']
                true_key=hashlib.sha256(true_pi.tobytes()+true_alpha.tobytes()).hexdigest()
                assert true_key==job.get('true_dual_SHA',key)
                names=np.array([str(n) for n in b.d['names']]);route_ix=np.array([n.startswith('arc[') for n in names]);mode_ix=np.array([n.startswith('charge_mode[') for n in names]);pq_ix=np.array([n.startswith(('Pch[','Pdis[','Q[')) for n in names]);soc_ix=np.array([n.startswith(('E[','SOC[')) for n in names]);prior_profile=starts[m].copy() if starts[m] is not None else None
                for candidate in captured:
                    cx=candidate.pop('x');physical_c=b.validate(cx,True);matrix,attrs,mask=full[m];raw_c=corrected_rows(matrix,attrs,cx,True,mask)
                    search_rc=float(exact_rc(b,cx,pi,alpha[m]));true_rc=float(exact_rc(b,cx,true_pi,true_alpha[m]));a,c,column_key=b.column(cx)
                    valid=bool(physical_c['PASS'] and raw_c['PASS'] and abs(search_rc-candidate['solver_objective'])<=EPS and search_rc<=DISCOVERY_RC and true_rc<=DISCOVERY_RC)
                    chosen=valid and accepted<MAX_COLUMNS and column_key not in selected_SHAs and column_key not in retained
                    if chosen:selected_SHAs.add(column_key)
                    if chosen:accepted+=1
                    file=f"pricing_points/PRICE_{job['call']:04d}_CAPTURE_{candidate['arrival']:04d}.npz";np.savez_compressed(OUT/file,x=cx,axis=b.columns)
                    chosen_arcs=[int(n.rsplit(',',1)[1][:-1]) for n,v in zip(names[route_ix],cx[route_ix]) if v>.5];sequence=[dict(source=str(b.arcs[j][0]),depart=int(b.arcs[j][1]),destination=str(b.arcs[j][2]),connect=int(b.arcs[j][3]),travel=b.arcs[j][-1] is not None) for j in sorted(chosen_arcs,key=lambda j:b.arcs[j][1])]
                    profile=dict(route_SHA=hashlib.sha256(cx[route_ix].tobytes()).hexdigest(),mode_SHA=hashlib.sha256(cx[mode_ix].tobytes()).hexdigest(),site_sequence=sequence,PQ_profile_SHA=hashlib.sha256(cx[pq_ix].tobytes()).hexdigest(),SOC_profile_SHA=hashlib.sha256(cx[soc_ix].tobytes()).hexdigest(),PQ_profile_relative_L2=None if prior_profile is None else float(np.linalg.norm(cx[pq_ix]-prior_profile[pq_ix])/max(np.linalg.norm(prior_profile[pq_ix]),1e-12)),SOC_profile_relative_L2=None if prior_profile is None else float(np.linalg.norm(cx[soc_ix]-prior_profile[soc_ix])/max(np.linalg.norm(prior_profile[soc_ix]),1e-12)),similarity_diagnostic_only=True)
                    candidates.append(dict(candidate,point_file=file,point_SHA=sha(OUT/file),column_SHA=column_key,physical=physical_c,full_original_local=raw_c,manual_search_rc=search_rc,rc_inc=true_rc,valid_negative=valid,selected=chosen,true_dual_SHA=true_key,trajectory_profile=profile,label='VALID_NEGATIVE_DISCOVERY_COLUMNS' if valid else 'REJECTED_CAPTURE',pricing_optimum_claimed=False))
            valid_bound=bool(job['type']!='DISCOVERY' and model.Status in (2,9) and bound is not None and not stop_event.is_set() and not capture_errors and (obj is None or valid_point and bound<=rc+EPS))
            result=dict(call=job['call'],round=job['round'],type=job['type'],MESS=b.unit,unit=m,pid=os.getpid(),dual_SHA=key,dual_file=job['dual_file'],native_status=model.Status,ObjVal=obj,ObjBound=bound,ObjBoundC=attribute('ObjBoundC'),MIPGap=attribute('MIPGap'),runtime=model.Runtime,nodes=model.NodeCount,fingerprint=model.Fingerprint,settings=settings,interval=[start,end],wall_seconds=end-start,rc_inc=rc,valid_point=valid_point,valid_bound=valid_bound,physical=physical,full_original_local=raw,point_file=point_file,point_SHA=sha(OUT/point_file) if point_file else None,objective_SHA=hashlib.sha256(cost.tobytes()+np.array([-float(alpha[m])]).tobytes()).hexdigest(),full_original_domain=True,horizon=96,objective_transport_exact=True,callback_first_negative_stop=False,previous_feasible_MIP_start_only=True,no_fixing=True,pricing_optimality_claimed=model.Status==2 and valid_point,discovery_column_label=candidate_class(model.Status,valid_point,rc),global_bound_includes_ObjCon=True,ObjCon=model.ObjCon,receipt=job['receipt'])
            result.update(candidates=candidates,capture_errors=capture_errors,MIPSOL_distinct_captures=sum(c['source']=='MIPSOL' for c in candidates),true_dual_SHA=job.get('true_dual_SHA',key),true_dual_file=job.get('true_dual_file',job['dual_file']),stabilized_discovery=job.get('stabilized_discovery',False),basis_or_pool_restriction=False)
            if job['type']=='DISCOVERY':result['pricing_optimality_claimed']=False
            result.update(early_stop=controller.terminal_receipt(model.Status),timing=dict(start=start,native_terminal=end,**timing),pricing_saved_wall_estimate=max(0.,job['cap']-(end-start)),saved_wall_diagnostic_only=True)
            if model.Status==11:assert not result['valid_bound'] and not result['pricing_optimality_claimed']
            write(job['receipt'],result);connection.send(dict(result=job['receipt']))
    except BaseException as error:
        import traceback
        connection.send(dict(error=repr(error),traceback=traceback.format_exc(),pid=os.getpid()))
    finally:
        done.set();thread.join(timeout=1)
        for b in blocks.values():b.model.dispose()
        connection.close()
