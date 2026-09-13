"""Full frozen domain, rotating joint neighborhoods; exact AC incumbent acceptance."""
import time,math,json
from pathlib import Path
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import ac8500 as ac
from grid8500 import controls,GridRows,TAN
from run_support import Metrics,Oracle,Deadline,atomic,digest
from non_electrical_inputs import context
from dayahead.v40g.domain import Option,materialize,deviation,audit
from dayahead.v40g_segments.canonical import import_frozen,planning_power
from dayahead.v41r1.feasible_seed import job_audit
from dayahead.v41.temporal_restore import activate
from dayahead.v41.reserve import diagnostics,add_constraints

def options_metadata(ctx):
    out={};refs={r['job_uid']:r for r in ctx.reference}
    for uid,options in ctx.options.items():
        a=np.array([[ac.SITES.index(o[0]) if o[0] in ac.SITES else -1,*o[1:6],ac.SITES.index(o[6]) if o[6] else ac.SITES.index(refs[uid]['AIDC_site']) if refs[uid]['AIDC_site'] in ac.SITES else -1] for o in options],dtype=np.int32)
        out[uid]=a
    return out
def initial_indices(ctx):return {r['job_uid']:ctx.options[r['job_uid']].index([r['AIDC_site'],r['start_slot'],r['end_slot'],-1,-1,-1,'']) for r in ctx.reference}
def materialized(ctx,chosen):
    rows=[]
    for ref in ctx.reference:
        clean={k:v for k,v in ref.items() if k not in ('segment_schema','compute_segments','migration_events')}
        rows.append(materialize(clean,Option(*ctx.options[ref['job_uid']][chosen[ref['job_uid']]]),ctx.capacity,ctx.wan))
    with activate():
        result=import_frozen(rows);service=audit(ctx.reference,result,ctx.capacity,ctx.wan);physical,power=job_audit(result,ctx)
    cursor=26
    for row in sorted(result,key=lambda r:r['job_uid']):
        if row.get('migration_selected'):
            event=row['migration_events'][0];assert event['transfer_start']==max(cursor,event['checkpoint']),'UID_SERIAL_BINDING';cursor=event['transfer_end']
    assert service['status']==physical['status']=='PASS'
    return result,power,dict(service=service,physical=physical,UID_serial='PASS')
def vector(ctx,chosen,power,P1):
    return [float(P1),float(diagnostics(ctx.v41_ml_snapshot,ctx.capacity,power['gpu'])['mean_xi_GPUh']),sum(ctx.options[u][i][3]>=0 for u,i in chosen.items()),sum(deviation(r,Option(*ctx.options[r['job_uid']][chosen[r['job_uid']]])) for r in ctx.reference),sum((k+1)*(chosen[u]+1) for k,u in enumerate(sorted(chosen)))]
def better(left,right):
    for a,b,tol in zip(left,right,[1e-8,1e-8,0,0,0]):
        if a<b-tol:return True
        if a>b+tol:return False
    return False
def contributions(ref,opt):
    a=np.zeros((96,12),dtype=np.int16)
    for s,lo,hi in opt.segments(ref):
        lo=max(24,lo)-24;hi=min(120,hi)-24
        if lo<hi:a[lo:hi,ac.SITES.index(s)]+=int(ref['requested_GPU'])
    return a

def ranked_indices(meta,cost,ref,current,iteration,count=64):
    # Exact full-domain endpoint accumulation of current electrical marginal ranking cost.
    prefix=np.vstack([np.zeros(12),np.cumsum(cost,axis=0)]);site=meta[:,0];start=np.clip(meta[:,1]-24,0,96);end=np.clip(meta[:,2]-24,0,96);mig=meta[:,3]>=0;score=np.zeros(len(meta))
    valid=site>=0;score[valid]=prefix[end[valid],site[valid]]-prefix[start[valid],site[valid]]
    ix=np.flatnonzero(mig);src=meta[ix,6];cp=np.clip(meta[ix,3]-24,0,96);ready=np.clip(meta[ix,5]+1-24,0,96)
    score[ix]=prefix[cp,src]-prefix[start[ix],src]+prefix[end[ix],site[ix]]-prefix[ready,site[ix]]
    score*=ref['requested_GPU'];order=np.argsort(score,kind='stable');chosen=set(map(int,order[:count]));chosen.add(current)
    # Cover every transfer-start band, as UID serialization couples neighboring jobs.
    for ts in np.unique(meta[ix,4]):
        sub=ix[meta[ix,4]==ts]
        if len(sub):chosen.add(int(sub[np.argmin(score[sub])]))
    n=len(meta);chosen.update((iteration*17+j)%n for j in range(min(17,n)))
    return sorted(chosen),float(score[order[0]]),len(meta)

def neighborhood(ctx,grid,chosen,power,mp,mq,meta,iteration,folder,metrics,remaining,stage_best):
    started=time.perf_counter();xseed=controls(power['pcc'],mp,mq);cost,_=grid.cost_gradient(xseed)
    marginal=np.column_stack([np.gradient(ctx.tables[s],axis=1)[np.arange(96),power['gpu'][:,j]] for j,s in enumerate(ac.SITES)])
    cost*=marginal;refs={r['job_uid']:r for r in ctx.reference};eligible=[u for u in sorted(meta) if len(meta[u])>1]
    nfree=[8,12,16][(iteration//20)%3];start=(iteration*(nfree-2))%len(eligible);free={eligible[(start+j)%len(eligible)] for j in range(nfree-2)}
    impacts=[]
    for uid in eligible:
        contrib=contributions(refs[uid],Option(*ctx.options[uid][chosen[uid]]));impacts.append((float(np.sum(contrib*cost)),uid))
    ranked_jobs=[u for _,u in sorted(impacts,reverse=True)];free.update(ranked_jobs[(iteration*2)%len(eligible):((iteration*2)%len(eligible))+2])
    batches={}
    for uid in sorted(free):
        ix,_,evaluations=ranked_indices(meta[uid],cost,refs[uid],chosen[uid],iteration,[64,128,256][(iteration//20)%3]);batches[uid]=ix;metrics.candidate_evaluations+=evaluations
    metrics.candidate_seconds+=time.perf_counter()-started
    model=gp.Model('IEEE8500_AIDC_JOINT_NEIGHBORHOOD');model.Params.OutputFlag=0;model.Params.Threads=4;model.Params.Seed=20260911+iteration;model.Params.FeasibilityTol=1e-9;model.Params.IntFeasTol=1e-9;model.Params.OptimalityTol=1e-9;model.Params.MIPGap=0;model.Params.MIPGapAbs=0;model.Params.Method=1
    variables={};loads=[[gp.LinExpr(float(power['gpu'][t,s])) for s in range(12)] for t in range(96)];decode={}
    try:
        for uid,indices in batches.items():
            ref=refs[uid];old=contributions(ref,Option(*ctx.options[uid][chosen[uid]]));v=model.addVars(indices,vtype=GRB.BINARY,name='job_'+uid);variables[uid]=v;model.addConstr(v.sum()==1)
            for i in indices:
                v[i].Start=float(i==chosen[uid]);opt=Option(*ctx.options[uid][i]);decode[uid,i]=opt;delta=contributions(ref,opt)-old
                for t,s in zip(*np.nonzero(delta)):loads[t][s]+=int(delta[t,s])*v[i]
        # Preserve the original UID-serial, deterministic first-checkpoint WAN binder.
        cursor=26
        for uid in sorted(chosen):
            if uid not in variables:
                o=Option(*ctx.options[uid][chosen[uid]])
                if o.migrated:
                    if isinstance(cursor,int):model.addConstr(gp.LinExpr(max(cursor,o.checkpoint))==o.transfer_start)
                    else:
                        ready=model.addVar(lb=26,ub=119,vtype=GRB.INTEGER);model.addGenConstrMax(ready,[cursor],constant=o.checkpoint);model.addConstr(ready==o.transfer_start)
                    cursor=o.transfer_end
                continue
            vm=variables[uid];migrated=[i for i in vm if decode[uid,i].migrated]
            if not migrated:continue
            cp=decode[uid,migrated[0]].checkpoint;flag=model.addVar(vtype=GRB.BINARY);model.addConstr(flag==gp.quicksum(vm[i] for i in migrated));ready=model.addVar(lb=26,ub=119,vtype=GRB.INTEGER);after=model.addVar(lb=26,ub=119,vtype=GRB.INTEGER)
            if isinstance(cursor,int):model.addConstr(ready==max(cursor,cp))
            else:model.addGenConstrMax(ready,[cursor],constant=cp)
            ts=gp.quicksum(decode[uid,i].transfer_start*vm[i] for i in migrated);te=gp.quicksum(decode[uid,i].transfer_end*vm[i] for i in migrated)
            model.addGenConstrIndicator(flag,True,ts==ready);model.addGenConstrIndicator(flag,True,after==te);model.addGenConstrIndicator(flag,False,after==cursor);cursor=after
        gpu={};pcc=[]
        for t in range(96):
            pp=[]
            for s,site in enumerate(ac.SITES):
                cap=ctx.capacity.site_capacity[site];g=model.addVar(lb=0,ub=cap,vtype=GRB.INTEGER,name=f'GPU[{t},{site}]');p=model.addVar(lb=float(ctx.tables[site][t].min()),ub=float(ctx.tables[site][t].max()),name=f'PCC[{t},{site}]');model.addConstr(g==loads[t][s]);model.addGenConstrPWL(g,p,list(range(cap+1)),ctx.tables[site][t].tolist());g.Start=float(power['gpu'][t,s]);p.Start=float(power['pcc'][t,s]);gpu[t,site]=g;pp.append(p)
            pcc.append(pp)
        x=[[v for p in pcc[t] for v in (p,TAN*p)]+[float(v) for v in xseed[t,24:]] for t in range(96)]
        rho=model.addVar(lb=0,ub=1.,name='rho_max');rho.Start=grid.report(xseed)['P1'];rows=GridRows(grid,model,x,rho,xseed,2)
        reserve,_=add_constraints(model,ctx,gpu)
        # P1 remains primary. Every fifth neighborhood also searches the unchanged P2 under a P1 lock.
        if iteration%5==4:model.addConstr(rho<=grid.report(xseed)['P1']);model.setObjective(reserve)
        else:model.setObjective(rho)
        solves=[];answer=None
        for separation in range(4):
            seconds=min(20.,remaining())
            if seconds<2:break
            model.Params.TimeLimit=seconds;st=time.perf_counter();model.optimize();duration=time.perf_counter()-st;metrics.solve.append(duration);metrics.sample();solves.append(dict(seconds=duration,status=int(model.Status),solutions=int(model.SolCount),variables=model.NumVars,constraints=model.NumConstrs))
            if not model.SolCount:break
            proposed=dict(chosen)
            for uid,v in variables.items():proposed[uid]=max(v,key=lambda i:v[i].X)
            try:jobs,powr,check=materialized(ctx,proposed)
            except (AssertionError,ValueError):break
            nx=controls(powr['pcc'],mp,mq);added,report=rows.separate(nx,float(rho.X));metrics.candidate_evaluations+=1
            if added:continue
            if report['feasible']:answer=(proposed,jobs,powr,check,report)
            break
        atomic(folder/f'iteration_{iteration:05d}.json',dict(iteration=iteration,free_jobs=sorted(free),neighborhood_options=sum(map(len,batches.values())),full_domain_retained=True,solver_calls=solves,surrogate=answer[-1] if answer else None,proposal=answer[0] if answer else None))
        return answer
    finally:model.dispose()

def run(ctx,grid,folder,seed_indices=None,mp=None,mq=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);metrics=Metrics();oracle=Oracle(folder/'AC',metrics);start=time.perf_counter();chosen=initial_indices(ctx) if seed_indices is None else dict(seed_indices);jobs,power,audits=materialized(ctx,chosen);valid=oracle.validate(power['pcc'],mp,mq,'seed');assert valid['feasible']
    bestvec=vector(ctx,chosen,power,valid['P1']);initial=dict(indices=chosen,jobs=jobs,AC=valid,objective_vector=bestvec);meta=options_metadata(ctx);clock=Deadline(folder,metrics,initial);iteration=0
    while clock.remaining>0:
        try:answer=neighborhood(ctx,grid,chosen,power,mp,mq,meta,iteration,folder/'iterations',metrics,lambda:clock.remaining,bestvec)
        except (gp.GurobiError,ValueError,AssertionError) as ex:
            atomic(folder/'rejections'/f'{iteration:05d}.json',dict(error=type(ex).__name__,message=str(ex)));answer=None
        if answer is not None and answer[0]!=chosen and clock.remaining>60:
            candidate,cjobs,cpower,audit_result,surrogate=answer
            val=oracle.validate(cpower['pcc'],mp,mq,f'proposal_{iteration:05d}');vec=vector(ctx,candidate,cpower,val['P1'])
            if val['feasible'] and better(vec,bestvec) and clock.remaining>0:
                oldP1=bestvec[0];chosen,jobs,power,bestvec=candidate,cjobs,cpower,vec;clock.accept(dict(indices=chosen,jobs=jobs,AC=val,objective_vector=vec));atomic(folder/'accepted'/f'{metrics.incumbent_updates:05d}.json',dict(loop_elapsed_seconds=time.perf_counter()-clock.started,old_P1=oldP1,new_P1=vec[0],indices=chosen,AC=val,audits=audit_result,objective_vector=vec))
        iteration+=1
    timeline=clock.finish();final_started=time.perf_counter();final=ac.replay(folder/'FINAL_INDEPENDENT_AC',aidc_p=power['pcc'],aidc_q=power['qcc'],mess_p=mp,mess_q=mq,independent=True);metrics.ac.append(time.perf_counter()-final_started);assert final['feasible'];assert abs(final['max_phase_line_loading_pu']-clock.current['AC']['P1'])<1e-10
    result=dict(status='PASS',indices=chosen,jobs=jobs,objective_vector=bestvec,AC=final,timeline=timeline,metrics=metrics.summary(),total_runtime_seconds=time.perf_counter()-start,global_optimality_claimed=False,method='Full frozen candidate authority; rotating joint MILP neighborhoods; exact AC accepted incumbents; no floor or stagnation stop',iterations=iteration)
    atomic(folder/'FINAL_AIDC.json',result);np.savez_compressed(folder/'FINAL_POWER.npz',**power);return result,power
