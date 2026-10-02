"""Instrument PR116 primitives without changing representation or certificates."""
import gzip,json,os,threading,time
import numpy as np
import gurobipy as gp
import psutil
from v42_benders.engine import configure,relative_gap
from v42_benders.certificates import Uncertifiable
from v42_benders_v2.recourse import Recourse
from v42_benders_v2.engine import certified,add_validated_cut
from .candidates import persist,load
from .common import *

CUT_FIELDS=['CUT_ID','stage','iteration','type','source_x_hash','source_model_hash','recourse_status','recourse_seconds',
    'certificate_hash','coefficients_hash','cut_nnz','source_violation','residual','strict_margin','validator_result','master_insertion_result','artifact_sha256']
RECOURSE_FIELDS=['stage','iteration','source_x_hash','native_status','native_seconds','native_certificate','native_reason',
    'PhaseI_used','PhaseI_status','PhaseI_seconds','PhaseI_certificate','PhaseI_reason','unit_wall_seconds','threads','peak_RSS_bytes','final_result']

def snapshot():
    from v42_threshold.common import resource_snapshot
    return resource_snapshot()

def peak_monitor(stop,peak):
    p=psutil.Process()
    while not stop.is_set():
        peak[0]=max(peak[0],p.memory_info().rss);stop.wait(.5)

def scope_before_solve():
    require_scope()
    freeze=read('EXECUTION_FREEZE.json')
    for r in freeze['sources']:
        if sha(ROOT/r['path'])!=r['sha256']:raise ValueError('EXECUTED_SOURCE_CHANGED')

def write_cut(directory,index,cut,stage,row):
    cid=stage+'-CUT-'+cut['record']['cut_hash'][:20];name=f'CUT_{index:03d}'
    np.savez_compressed(directory/(name+'.npz'),coefficients=cut['coefficients'],intercept=np.array([cut['record']['intercept']]))
    payload=dict(CUT_ID=cid,record=cut['record'],independent_validation=cut['independent_validation'],
        coefficient_npz_sha256=sha(directory/(name+'.npz')),
        known_fixture_survival='PR116 exhaustive fixture replay preserved and preflight PASS. 7-bit fixture axes are not full-scale master points; global full-scale validity independently proven over the exact original x box.')
    with gzip.open(directory/(name+'.json.gz'),'wt',encoding='utf8') as f:json.dump(payload,f,ensure_ascii=False,allow_nan=False)
    return dict(CUT_ID=cid,stage=stage,iteration=index,type='PHASE1' if cut['record']['kind']=='phase1' else 'OPTIMALITY' if cut['record']['type']=='optimality' else 'NATIVE_FARKAS',
        source_x_hash=cut['record']['source_x_hash'],source_model_hash=cut['record']['source_hash'],
        recourse_status=row['native_status'],recourse_seconds=row['native_seconds'],certificate_hash=cut['record']['raw_vector_sha256'],
        coefficients_hash=cut['record']['cut_hash'],cut_nnz=int(np.count_nonzero(cut['coefficients'])),
        source_violation=cut['record']['strict_margin'],residual=cut['record']['bound_completed_stationarity'],
        strict_margin=cut['record']['strict_margin'],validator_result=True,master_insertion_result=False,
        artifact_sha256=sha(directory/(name+'.json.gz')))

def loop(n,*,env,directory,stage,validate,seconds=None,max_evaluations=None,warm=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    scope_before_solve();feasibility=stage in ['PILOT','FULL_B3'];master=gp.Model(stage+'_EXACT_MASTER',env=env)
    configure(master,1,60 if seconds is None else seconds,directory/'master.log')
    x=master.addMVar(len(n.xi),lb=n.xlower,ub=n.xupper,vtype='B',name='complete_master_x')
    dr=np.flatnonzero(np.diff(n.A.indptr)==0);master.addMConstr(n.B[dr],x,n.sense[dr],n.b[dr])
    theta=None if feasibility else master.addVar(lb=LB,name='certified_theta_rho')
    master.setObjective(0. if feasibility else theta);master.update()
    upper=None;lower=None if feasibility else LB;best=None
    if warm is not None:
        if feasibility:raise ValueError('NO_WARM_FOR_B3_CLEAN_RESTART')
        check=validate(warm)
        if not check.get('PASS') or n.residual(warm[n.xi],warm[n.yi])>1e-7:raise ValueError('INVALID_ORIGINAL_WARM')
        upper=float(n.c@warm[n.yi]+n.objective_constant);best=warm.copy()
        x.Start=warm[n.xi];theta.Start=upper
        dump('WARM_START_RECEIPT.json',dict(validated=True,upper=upper,Start_only=True,fixed_columns=0,
            original_binaries=len(n.xi),native_bounds_unchanged=True),directory)
    candidates=[];cuts=[];recourses=[];progress=[];hashes=set();native=None;phase=None;index=0;status='TIME_LIMIT';reason=None;witness=False;proof=False
    initial_upper=upper;initial_lower=lower
    def remaining():return float('inf') if seconds is None else seconds-(time.perf_counter()-start)
    def flush():
        table('FULLSCALE_CUT_LEDGER.csv',cuts,CUT_FIELDS,directory);table('FULLSCALE_RECOURSE_LEDGER.csv',recourses,RECOURSE_FIELDS,directory)
        dump('LIVE_PROGRESS.json',dict(stage=stage,status=status,reason=reason,candidates=candidates,
            recourse_calls=len(recourses),cuts=len(cuts),progress=progress,upper=upper,lower=lower,elapsed=time.perf_counter()-start),directory)
    try:
        while remaining()>0:
            scope_before_solve();master.Params.TimeLimit=max(.001,min(60.,remaining()));master.optimize()
            if master.Status==3:
                if upper is not None:raise Uncertifiable('MASTER_PROOF_CONTRADICTS_ORIGINAL_UB')
                proof=True;status='MASTER_INFEASIBLE';break
            if master.Status in [4,11,12]:raise Uncertifiable('UNSAFE_MASTER_STATUS')
            if not feasibility:
                if np.isfinite(master.ObjBound) and abs(master.ObjBound)<1e90:lower=max(lower,float(master.ObjBound))
                if upper is not None and relative_gap(upper,lower)<=.005:status='P1_GAP_TARGET';break
            if not master.SolCount:status='MASTER_NO_CANDIDATE';break
            values=np.asarray(x.X)
            if np.max(abs(values-np.rint(values)),initial=0)>1e-7:raise Uncertifiable('MASTER_NONINTEGER')
            values=np.rint(values);resources=snapshot()
            receipt=persist(directory,index,n,values,master,[c['CUT_ID'] for c in cuts],resources,stage)
            if receipt['vector_sha256'] in [c['vector_sha256'] for c in candidates]:raise Uncertifiable('MASTER_REPEATED_CANDIDATE_AFTER_CUT')
            candidates.append(dict(index=index,vector_sha256=receipt['vector_sha256'],axis_hash=receipt['axis_hash'],
                receipt_sha256=sha(directory/f'MASTER_X_{index:03d}_RECEIPT.json')))
            flush();print(stage,'PERSISTED X',index,receipt['vector_sha256'],flush=True)
            if max_evaluations is not None and len(recourses)>=max_evaluations:status='PILOT_MAX_EVALUATIONS';break
            if remaining()<=0:break
            values,checked=load(directory,index,n)
            threads=1 if resources['other_heavy_solve'] else 4
            unit_start=time.perf_counter();unit_budget=min(1800.,remaining());deadline=unit_start+unit_budget
            row=dict(stage=stage,iteration=index,source_x_hash=checked['vector_sha256'],native_status=None,native_seconds=None,
                native_certificate=False,native_reason=None,PhaseI_used=False,PhaseI_status=None,PhaseI_seconds=None,
                PhaseI_certificate=False,PhaseI_reason=None,unit_wall_seconds=None,threads=threads,peak_RSS_bytes=0,final_result='RUNNING')
            recourses.append(row);dump(f'RECOURSE_{index:03d}_STARTED.json',dict(stage=stage,source_x_hash=checked['vector_sha256'],
                persisted_receipt_sha256=candidates[-1]['receipt_sha256'],resources=resources,threads=threads,deadline_budget=unit_budget,
                started_UTC=stamp(),source_commit=git('rev-parse','HEAD'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json')),directory)
            flush();stop=threading.Event();peak=[psutil.Process().memory_info().rss];monitor=threading.Thread(target=peak_monitor,args=(stop,peak),daemon=True);monitor.start()
            cut=None
            try:
                if native is None:native=Recourse(n,env,directory/'native',threads,objective=not feasibility)
                native.model.Params.Threads=threads
                if time.perf_counter()>=deadline:status='BUILD_TIME_LIMIT';break
                raw=native.solve(values,max(.001,deadline-time.perf_counter()));row.update(native_status=raw['status'],native_seconds=raw['seconds'])
                # Keep a compact receipt pointing at the unchanged engine's durable full journal.
                dump(f'RECOURSE_{index:03d}_NATIVE_RAW_RECEIPT.json',dict(status=raw['status'],source_x_hash=checked['vector_sha256'],
                    persistence=raw['persistence'],axis_hash=raw['row_axis_hash'],raw_vector_sha256=raw.get('vector_sha256'),
                    warnings=raw['warnings'],Kappa=raw['Kappa'],FarkasProof=raw['farkas_proof'],seconds=raw['seconds']),directory)
                if raw['status']==2:
                    if not native.primal_valid(raw):raise Uncertifiable('NATIVE_PRIMAL')
                    point=n.assemble(values,np.asarray(raw['primal']));validation=validate(point)
                    dump(f'RECOURSE_{index:03d}_POINT_VALIDATION.json',validation,directory)
                    if not validation.get('PASS'):raise Uncertifiable('INDEPENDENT_PHYSICS_OR_THRESHOLD_WITNESS')
                    np.savez_compressed(directory/f'RECOURSE_{index:03d}_VALIDATED_POINT.npz',names=n.names,values=point)
                    best=point.copy()
                    if feasibility:witness=True;status='FEASIBLE_WITNESS';row['final_result']='VALIDATED_WITNESS';break
                    value=raw['objective'];upper=value if upper is None else min(upper,value)
                    cut=certified(n,raw,'optimality')
                elif raw['status']==3:
                    try:
                        cut=certified(n,raw,'native_farkas');row['native_certificate']=True
                    except (Uncertifiable,TypeError,KeyError) as e:
                        row['native_reason']=str(e);dump(f'RECOURSE_{index:03d}_NATIVE_REJECTION.json',dict(reason=str(e),
                            raw_persistence=raw['persistence'],no_native_cut=True),directory)
                        if time.perf_counter()>=deadline:status='NATIVE_REJECTED_NO_FALLBACK_BUDGET';break
                        row['PhaseI_used']=True;flush();print(stage,'NATIVE REJECTED',str(e),'PHASE-I FALLBACK',flush=True)
                        if phase is None:phase=Recourse(n,env,directory/'phase1',threads,phase=True)
                        phase.model.Params.Threads=threads
                        if time.perf_counter()>=deadline:status='PHASE1_BUILD_TIME_LIMIT';break
                        auxiliary=phase.solve(values,max(.001,deadline-time.perf_counter()))
                        row.update(PhaseI_status=auxiliary['status'],PhaseI_seconds=auxiliary['seconds'])
                        dump(f'RECOURSE_{index:03d}_PHASE1_RAW_RECEIPT.json',dict(status=auxiliary['status'],source_x_hash=checked['vector_sha256'],
                            persistence=auxiliary['persistence'],objective=auxiliary['objective'],warnings=auxiliary['warnings'],
                            raw_vector_sha256=auxiliary.get('vector_sha256'),seconds=auxiliary['seconds']),directory)
                        try:
                            if not phase.primal_valid(auxiliary):raise Uncertifiable('PHASE1_NONTERMINAL_OR_PRIMAL')
                            cut=certified(n,auxiliary,'phase1');row['PhaseI_certificate']=True
                        except (Uncertifiable,TypeError,KeyError) as e:
                            row['PhaseI_reason']=str(e);raise Uncertifiable('BOTH_PATHS_UNCERTIFIABLE: '+str(e)) from e
                else:status='RECOURSE_NONTERMINAL_NO_CUT';break
            finally:
                stop.set();monitor.join();row['peak_RSS_bytes']=peak[0];row['unit_wall_seconds']=time.perf_counter()-unit_start
                if row['final_result']=='RUNNING':row['final_result']='VALID_CUT_READY' if cut is not None else status
                flush()
            if cut is None:break
            if cut['record']['cut_hash'] in hashes:raise Uncertifiable('EXACT_DUPLICATE_CUT')
            ledger=write_cut(directory,len(cuts),cut,stage,row)
            if remaining()<=0 and seconds is not None:
                ledger['master_insertion_result']=False;cuts.append(ledger);status='VALIDATED_CUT_AFTER_TOTAL_WALL_LIMIT';break
            # Unchanged PR116 insertion function independently replays every payload.
            add_validated_cut(master,x,theta,n,cut);master.update();ledger['master_insertion_result']=True
            cuts.append(ledger);hashes.add(cut['record']['cut_hash'])
            progress.append(dict(iteration=index,source_x_hash=receipt['vector_sha256'],cut_ID=ledger['CUT_ID'],
                cut_hash=ledger['coefficients_hash'],upper=upper,lower=lower,elapsed=time.perf_counter()-start))
            flush();print(stage,'INSERTED CERTIFIED CUT',ledger['CUT_ID'],flush=True);index+=1
        result=dict(stage=stage,status=status,reason=reason,validated_witness=witness,global_master_infeasible=proof,
            numerical_contradiction=False,uncertified_cuts_inserted=0,valid_fullscale_cuts=len(cuts),
            inserted_valid_cuts=sum(c['master_insertion_result'] for c in cuts),distinct_persisted_candidates=len(candidates),
            candidates=candidates,recourse_calls=len(recourses),recourses=recourses,cuts=cuts,progress=progress,
            native_Farkas_cuts=sum(c['type']=='NATIVE_FARKAS' for c in cuts),PhaseI_cuts=sum(c['type']=='PHASE1' for c in cuts),
            optimality_cuts=sum(c['type']=='OPTIMALITY' for c in cuts),initial_upper=initial_upper,initial_lower=initial_lower,
            upper=upper,lower=lower,gap=None if feasibility else relative_gap(upper,lower),
            total_wall_seconds=time.perf_counter()-start,master_wall_seconds=sum(read(f'MASTER_X_{c["index"]:03d}_RECEIPT.json',directory)['master_wall_seconds'] for c in candidates),
            recourse_wall_seconds=sum((r['native_seconds'] or 0)+(r['PhaseI_seconds'] or 0) for r in recourses),
            warm_start_fixing=False,zero_objective_bound_used_as_rho_LB=False)
    except (Uncertifiable,ValueError,OSError,MemoryError) as e:
        status='STOP_UNCERTIFIABLE';reason=str(e)
        result=dict(stage=stage,status=status,reason=reason,validated_witness=False,global_master_infeasible=False,
            numerical_contradiction='CONTRADICTION' in reason,uncertified_cuts_inserted=0,valid_fullscale_cuts=len(cuts),
            inserted_valid_cuts=sum(c['master_insertion_result'] for c in cuts),distinct_persisted_candidates=len(candidates),
            candidates=candidates,recourse_calls=len(recourses),recourses=recourses,cuts=cuts,progress=progress,
            upper=upper,lower=None,gap=None,total_wall_seconds=time.perf_counter()-start)
    finally:
        flush()
        if native is not None:native.close()
        if phase is not None:phase.close()
        master.dispose()
    dump('RESULT.json',result,directory);return result,best
