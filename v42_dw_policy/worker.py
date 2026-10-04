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
            accepted=read(OUT/'DW_POLICY_RESUME_CHECKPOINT_AUDIT.json')['checks'];seed=next(c for c in reversed(accepted) if c['MESS']==b.unit)
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
            start=time.perf_counter();active[0]=model
            if stop_event.is_set() or STOP.exists():model.Params.TimeLimit=.001
            model.optimize();end=time.perf_counter();active[0]=None
            def attribute(name):
                try:v=float(getattr(model,name));return v if np.isfinite(v) and abs(v)<1e90 else None
                except (gp.GurobiError,AttributeError):return None
            obj=attribute('ObjVal') if model.SolCount else None;bound=attribute('ObjBound');rc=None;valid_point=False;physical=None;raw=None;point_file=None
            if model.SolCount:
                x=np.array(model.getAttr('X',b.vars));physical=b.validate(x,True);matrix,attrs,mask=full[m];raw=corrected_rows(matrix,attrs,x,True,mask)
                rc=float(exact_rc(b,x,pi,alpha[m]));valid_point=bool(physical['PASS'] and raw['PASS'] and obj is not None and abs(rc-obj)<=EPS)
                point_file=f"pricing_points/PRICE_{job['call']:04d}.npz";np.savez_compressed(OUT/point_file,x=x,axis=b.columns)
                if valid_point:starts[m]=x.copy()
            valid_bound=bool(model.Status in (2,9) and bound is not None and not stop_event.is_set() and (obj is None or valid_point and bound<=rc+EPS))
            result=dict(call=job['call'],round=job['round'],type=job['type'],MESS=b.unit,unit=m,pid=os.getpid(),dual_SHA=key,dual_file=job['dual_file'],native_status=model.Status,ObjVal=obj,ObjBound=bound,ObjBoundC=attribute('ObjBoundC'),MIPGap=attribute('MIPGap'),runtime=model.Runtime,nodes=model.NodeCount,fingerprint=model.Fingerprint,settings=settings,interval=[start,end],wall_seconds=end-start,rc_inc=rc,valid_point=valid_point,valid_bound=valid_bound,physical=physical,full_original_local=raw,point_file=point_file,point_SHA=sha(OUT/point_file) if point_file else None,objective_SHA=hashlib.sha256(cost.tobytes()+np.array([-float(alpha[m])]).tobytes()).hexdigest(),full_original_domain=True,horizon=96,objective_transport_exact=True,callback_first_negative_stop=False,previous_feasible_MIP_start_only=True,no_fixing=True,pricing_optimality_claimed=model.Status==2 and valid_point,discovery_column_label=candidate_class(model.Status,valid_point,rc),global_bound_includes_ObjCon=True,ObjCon=model.ObjCon,receipt=job['receipt'])
            if job['type']=='DISCOVERY':result['pricing_optimality_claimed']=False
            write(job['receipt'],result);connection.send(dict(result=job['receipt']))
    except BaseException as error:
        import traceback
        connection.send(dict(error=repr(error),traceback=traceback.format_exc(),pid=os.getpid()))
    finally:
        done.set();thread.join(timeout=1)
        for b in blocks.values():b.model.dispose()
        connection.close()
