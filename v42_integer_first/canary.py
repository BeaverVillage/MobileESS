"""One full-domain original-C3A 900-second integer-first campaign."""
from .common import *
from .certificates import certify_with_explicit_projection,known_witnesses,exact_value,solver_transport
from .benchmark import parameters,Monitor,log_phases
import re
def main():
    import gurobipy as gp
    from v42_redundancy.model import build
    prereg=REPORTS/'PREREGISTRATION.md';assert prereg.exists()
    general=json.loads((REPORTS/'GENERAL_EXACTNESS_GATE.json').read_text(encoding='utf-8-sig'));fixture=json.loads((REPORTS/'BOUNDED_FIXTURE_VERIFICATION.json').read_text(encoding='utf-8-sig'));speed=json.loads((REPORTS/'RECOURSE_NUMERICAL_AUDIT.json').read_text(encoding='utf-8-sig'))
    assert all(general[k] for k in ('integer_projection_PASS','continuous_recourse_equivalence_PASS','objective_epigraph_equivalence_PASS','weak_duality_exact_cuts_PASS')) and fixture['PASS'] and speed['performance_PASS']
    token=WORK/'checkpoints/CANARY_ONCE.json';assert not token.exists();write(token,dict(campaigns=1,native_and_wall_budget=900,Threads=1,recourse_Method=1,master_Method=2,scientific_objective='minimize original rho',master_objective='minimize theta',continuation_authorized=False))
    t0=time.perf_counter();runtime=0.;work=0.;lb=LB;ub=speed['new_valid_UB'];peak=0;rows=[];bounds=[];events=[];reason='BUDGET';cuts=[];seen=set();master_calls=recourse_calls=0
    A,d,_=hc.load();B=np.flatnonzero(d['types']=='B');reader=hc.physical_reader();prior.objective_identity(A,d);paths_audit('canary_build')
    pure=np.array([str(n).startswith(('route_flow[','node_activity[','charge_mode[')) for n in d['names']]);cols=np.flatnonzero(pure);pure_rows=np.flatnonzero(np.asarray(A[:,~pure].getnnz(axis=1)).ravel()==0);pos={int(j):i for i,j in enumerate(cols)}
    master=gp.Model('ORIGINAL_C3A_ROUTE_MODE_MASTER');master.Params.OutputFlag=0;mv=master.addMVar(len(cols),lb=d['lower'][cols],ub=d['upper'][cols],vtype=d['types'][cols]);theta=master.addVar(lb=lb,ub=float(d['upper'][239826]),obj=1,name='theta');master.addMConstr(A[pure_rows][:,cols],mv,d['sense'][pure_rows],d['rhs'][pure_rows]);master.update();mb=[mv[pos[int(j)]].item() for j in B]
    f=dict(d,types=np.full(A.shape[1],'C'));rec=build(A,f);variables=rec.getVars();bv=[variables[j] for j in B]
    assert (rec.getA()!=A).nnz==0 and np.array_equal(np.array(rec.getAttr('Obj')),d['objective']) and rec.ObjCon==float(d['constant'])
    assignments=sorted((WORK/'artifacts/assignments').glob('*.npz'));registry=json.loads((REPORTS/'BENDERS_CUT_CERTIFICATES.json').read_text(encoding='utf-8-sig'));transport=[]
    def insert(cc,label):
        beta,intercept,receipt=solver_transport(cc,d);assert receipt['PASS'];expression=gp.LinExpr(beta.tolist(),mb)+intercept
        if cc['kind']=='optimality':master.addConstr(theta>=expression,name=label)
        else:master.addConstr(expression<=0,name=label)
        transport.append(dict(label=label,**receipt));cuts.append(cc)
    for i,c in enumerate(registry['certificates']):
        accepted=c if c['PASS'] else c.get('optimize_zero_recovery')
        if accepted and accepted['PASS']:insert(accepted,f'benchmark_cut_{i:03d}')
    center=np.load(WORK/'artifacts/BEST_VALID_POINT.npz')['x'];assert prior.prior.full_replay(A,d,center,reader)['PASS'];mv.Start=center[cols];theta.Start=ub;master.update()
    write(REPORTS/'MASTER_MODEL_IDENTITY.json',dict(PASS=True,full_domain=True,route_flow_continuous=True,original_B_count=len(B),master_columns=master.NumVars,master_rows=master.NumConstrs,raw_graph_rows=len(pure_rows),domain_restricted=False,initial_valid_cuts=len(cuts),original_recourse_matrix_unchanged=True,all_pure_original_bounds_types_retained=True,theta_floor=lb,objective_epigraph_proof=str(REPORTS/'DECOMPOSITION_EQUIVALENCE_PROOF.md')))
    def remain():return min(900-runtime,900-(time.perf_counter()-t0))
    def snapshot():
        table(REPORTS/'MASTER_RECOURSE_TRACE.csv',rows);table(REPORTS/'GLOBAL_BOUND_TRAJECTORY.csv',bounds)
        write(WORK/'checkpoints/CANARY_STATE.json',dict(iterations=len(rows),LB=lb,UB=ub,native_Runtime=runtime,native_Work=work,wall_seconds=time.perf_counter()-t0,cut_count=len(cuts),reason=reason,scientific_hashes=json.loads((REPORTS/'SCIENTIFIC_IDENTITY.json').read_text(encoding='utf-8-sig'))['sources'],cut_registry=[{k:v for k,v in c.items() if k!='beta'} for c in cuts],restart_semantics='Fresh native masters with validated cuts and incumbent; no saved native search tree claim'))
        write(REPORTS/'CUT_SOLVER_TRANSPORT.json',dict(PASS=all(x['PASS'] for x in transport),cuts=transport))
    def callback(m,where):
        if where==gp.GRB.Callback.POLLING:return
        if time.perf_counter()-t0>=900:m.terminate()
    for it in range(10000):
        if remain()<15:reason='REGISTERED_BUDGET_CHECKPOINT_RESERVE';break
        label=f'master_{it:03d}';parameters(master,label,min(60,remain()-5));paths_audit(label,master)
        print('MASTER_START',it,'remaining',remain(),flush=True)
        with Monitor() as monitor:master.optimize(callback)
        master_calls+=1;runtime+=master.Runtime;work+=master.Work;peak=max(peak,monitor.peak)
        log=(WORK/'logs'/f'{label}.log').read_text(encoding='utf-8',errors='replace');severe=bool(re.search('numerical trouble|numeric error|numerical difficulties|unreliable|unstable',log,re.I))
        bd=float(master.ObjBound) if master.Status in (2,9,11) else None
        recrow=dict(iteration=it,master_status=master.Status,master_Runtime=master.Runtime,master_Work=master.Work,master_nodes=master.NodeCount,master_BestBd=bd,master_solution_count=master.SolCount,master_barrier_iterations=master.BarIterCount,master_bound_native_contract='Full original discrete domain and exact-valid cuts; inherited native MIP tolerance contract',**{f'master_{k}':v for k,v in log_phases(WORK/'logs'/f'{label}.log').items()})
        if bd is not None and np.isfinite(bd) and abs(bd)<1e90 and not severe:
            if bd>ub+1e-8:reason='NATIVE_BOUND_CONTRADICTS_VALID_UB';rows.append(recrow);break
            lb=max(lb,bd)
        bounds.append(dict(iteration=it,event='master',wall_seconds=time.perf_counter()-t0,native_Runtime=runtime,LB=lb,UB=ub,gap_percent=100*(ub-lb)/ub))
        if (ub-lb)/ub<=.005:reason='GLOBAL_GAP_LE_0P5';rows.append(recrow);break
        if severe or not master.SolCount:reason='MASTER_NO_VALID_INTEGER_CANDIDATE';rows.append(recrow);break
        mx=np.array(mv.X);z=np.rint([v.X for v in mb]);int_error=float(abs(np.array([v.X for v in mb])-z).max());flow_mask=np.array([str(d['names'][j]).startswith('route_flow[') for j in cols]);flow_error=float(abs(mx[flow_mask]-np.rint(mx[flow_mask])).max())
        candidate=hashlib.sha256(z.astype(np.uint8).tobytes()).hexdigest();recrow.update(candidate=candidate,master_integer_error=int_error,master_route_flow_error=flow_error,master_theta=theta.X)
        if int_error>1e-8 or flow_error>1e-8:reason='MASTER_INTEGER_OR_ROUTE_NUMERICAL_FAIL';rows.append(recrow);break
        if candidate in seen:reason='REPEATED_CANDIDATE_CUT_STRENGTH_DIAGNOSIS';rows.append(recrow);break
        seen.add(candidate);save(WORK/'artifacts'/f'candidate_{it:03d}.npz',z=z,B=B,master_cols=cols,master_x=mx)
        if remain()<15:reason='REGISTERED_BUDGET_BEFORE_RECOURSE';rows.append(recrow);break
        label=f'canary_recourse_{it:03d}';rec.reset();rec.setAttr('LB',bv,z);rec.setAttr('UB',bv,z);parameters(rec,label,min(120,remain()-5));rec.Params.Method=1;rec.update();paths_audit(label,rec)
        assert np.array_equal(np.array(rec.getAttr('Obj')),d['objective']) and rec.ObjCon==float(d['constant'])
        print('CANARY_RECOURSE_START',it,candidate,flush=True)
        with Monitor() as monitor:rec.optimize(callback)
        recourse_calls+=1;runtime+=rec.Runtime;work+=rec.Work;peak=max(peak,monitor.peak);recrow.update(recourse_status=rec.Status,recourse_Runtime=rec.Runtime,recourse_Work=rec.Work,peak_RSS=peak,replay_PASS=False)
        cc=None
        if rec.Status==gp.GRB.OPTIMAL and rec.SolCount:
            x=np.array(rec.getAttr('X'));pi=np.array(rec.getAttr('Pi'));rc=np.array(rec.getAttr('RC'));save(WORK/'artifacts'/f'{label}_RAW.npz',x=x,pi=pi,rc=rc,slack=np.array(rec.getAttr('Slack')),B=B,z=z)
            replay=prior.prior.full_replay(A,d,x,reader);write(WORK/'artifacts'/f'{label}_REPLAY.json',replay);recrow.update(replay_PASS=replay['PASS'],recourse_objective=float(d['objective']@x))
            if replay['PASS'] and recrow['recourse_objective']<ub:ub=recrow['recourse_objective'];save(WORK/'artifacts/BEST_VALID_POINT.npz',x=x);write(REPORTS/'BEST_FULL_REPLAY.json',replay)
            cc=certify_with_explicit_projection(A,d,B,pi,WORK/'artifacts'/f'canary_cut_{it:03d}')
        elif rec.Status==gp.GRB.INFEASIBLE:
            try:pi=-np.array(rec.getAttr('FarkasDual'))
            except gp.GurobiError:reason='NATIVE_FARKAS_UNAVAILABLE';rows.append(recrow);break
            save(WORK/'artifacts'/f'{label}_FARKAS.npz',pi=pi,B=B,z=z);cc=certify_with_explicit_projection(A,d,B,pi,WORK/'artifacts'/f'canary_cut_{it:03d}','feasibility')
        else:reason='RECOURSE_NUMERICALLY_UNRESOLVED';rows.append(recrow);break
        if cc and cc['PASS']:
            known=known_witnesses(cc,d,assignments);cc['known_witness_validation']=known;cc['source_exact_value']=float(exact_value(cc,z));cc['PASS']=known['PASS']
            if cc['kind']=='feasibility' and cc['source_exact_value']<=1e-8:cc['PASS']=False;cc['reason']='EXACT_SOURCE_SEPARATION_TOO_SMALL'
            if cc['kind']=='optimality':cc['source_certificate_loss']=recrow['recourse_objective']-cc['source_exact_value']
            cc.pop('beta',None)
        recrow.update(certificate_PASS=bool(cc and cc['PASS']),cut_kind=cc.get('kind') if cc else None);events.append(dict(iteration=it,candidate=candidate,certificate=cc))
        if not cc or not cc['PASS']:reason='CUT_CERTIFICATION_FAIL';rows.append(recrow);break
        beta,intercept,tr=solver_transport(cc,d);source_transport=intercept+float(beta@z);cc['delivered_source_value']=source_transport
        if cc['kind']=='feasibility' and source_transport<=1e-8:reason='TRANSPORT_SOURCE_SEPARATION_FAIL';rows.append(recrow);break
        insert(cc,f'canary_cut_{it:03d}');rows.append(recrow);bounds.append(dict(iteration=it,event='recourse',wall_seconds=time.perf_counter()-t0,native_Runtime=runtime,LB=lb,UB=ub,gap_percent=100*(ub-lb)/ub));snapshot()
        print('CANARY_ITERATION_DONE',it,'LB',lb,'UB',ub,'kind',cc['kind'],'native',runtime,'wall',time.perf_counter()-t0,flush=True)
    snapshot();write(REPORTS/'CANARY_CUT_CERTIFICATES.json',dict(events=events,accepted=sum(e['certificate']['PASS'] for e in events),rejected=sum(not e['certificate']['PASS'] for e in events)))
    result=dict(reason=reason,canary_executed=True,canary_campaigns=1,registered_budget=900,native_Runtime=runtime,native_Work=work,wall_seconds=time.perf_counter()-t0,peak_RSS=peak,master_calls=master_calls,recourse_calls=recourse_calls,complete_iterations=sum(bool(r.get('certificate_PASS')) for r in rows),old_LB=LB,new_LB=lb,old_UB=UB,new_UB=ub,gap_percent=100*(ub-lb)/ub,point5_percent_achieved=(ub-lb)/ub<=.005,benchmark_cuts_added=20,canary_cuts_added=len(cuts)-20,accepted_optimality_cuts=sum(c['kind']=='optimality' for c in cuts),accepted_feasibility_cuts=sum(c['kind']=='feasibility' for c in cuts),continuation_authorized=False,continuation_executed=False,no_restricted_bound_used=True,rows=rows)
    write(REPORTS/'CANARY_RESULT.json',result);master.dispose();rec.dispose();print('CANARY_FINISHED',json.dumps(clean({k:v for k,v in result.items() if k!='rows'})),flush=True)
if __name__=='__main__':main()
