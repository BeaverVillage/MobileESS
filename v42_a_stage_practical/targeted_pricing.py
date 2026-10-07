"""Migration-first exact native queries and independent concrete recovery."""
from pathlib import Path
from dataclasses import replace,asdict
from fractions import Fraction
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import read,atomic
from v42_a_stage_phase1.runner import load_cache,serial,projected_global_pi
from v42_a_stage_phase1.producer import price_snapshot
from v42_a_stage_phase1.oracle import corrected_certificate
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_early.candidate import physical_price,validate,migration_witnesses
from .policy import HISTORY,POLICY
from .native import Native,BudgetStop
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_residual.query import migration_query,select
from v42_a_stage_residual.recovery import migration_options
from .attribution import score

def worker(task):
    want,pi,cardinality,has_migration,folder=task
    native=Native(Budget());answer=dict(PASS=False,queries={})
    try:
        cache=load_cache(want)
        for kind in ('MIGRATION','STAY'):
            if kind=='MIGRATION' and not has_migration:
                answer['queries'][kind]=dict(PASS=True,status='NO_PHYSICAL_MIGRATION',native_call=False)
                continue
            query=migration_query(cache,cardinality,kind);priced=price_snapshot(query,cache['B'],pi)
            qfolder=Path(folder)/kind;qfolder.mkdir(parents=True,exist_ok=True)
            atomic(qfolder/'ORACLE_KIND.json',dict(class_id=want['class_id'],kind=kind,cardinality=cardinality,
                full_physical_kind_covered=True,temporary_query_only=True,permanent_domain_deletion=False))
            if query.matrix.shape[1]:
                rec,raw=native.solve(priced,qfolder,'LOCAL_PRICING')
                if rec['status']!=gp.GRB.OPTIMAL or not all(k in raw for k in ('X','Pi','RC')):
                    error=BudgetStop if rec['status'] in (9,11) else ValueError
                    raise error(kind+'_ORACLE_NOT_OPTIMAL')
                replay=primal_replay(priced,raw['X']);sign=verify_sign_convention(priced,raw['Pi'],raw['RC'])
                atomic(qfolder/'RAW_REPLAY.json',dict(PASS=replay['PASS'] and sign['PASS'],primal=replay,sign=sign))
                if not replay['PASS'] or not sign['PASS']:raise ValueError('QUERY_RAW_REPLAY_FAIL')
            else:raw=dict(X=np.zeros(0),Pi=np.zeros(query.matrix.shape[0]))
            cert=corrected_certificate(query,cache['B'],pi,raw['Pi'])
            if not cert['PASS']:raise ValueError('EXACT_QUERY_CERTIFICATE_FAIL')
            response=dict(PASS=True,status='COMPLETE_NATIVE_KIND_QUERY',certificate=cert,
                point=raw['X'],local_pi=raw['Pi'],native_call=bool(query.matrix.shape[1]))
            answer['queries'][kind]=response
            atomic(qfolder/'EXACT_QUERY.json',serial(dict(class_id=want['class_id'],kind=kind,certificate=cert,
                global_coupling_pi=tuple(map(float,pi)),local_raw_pi=tuple(map(float,raw['Pi'])),query_snapshot_sha256=query.fingerprint())))
        answer['PASS']=True
    except Exception as error:answer['error']=type(error).__name__+': '+str(error)
    answer.update(calls=native.calls,resources=native.resources)
    return answer

def targeted(native,executor,workers,original,master,raw,data,domains,ledger,axes,lrows,owned,targets,effect,baseline,folder):
    roster={r['class_id']:r for r in read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    pi=projected_global_pi(master,raw['Pi']);cp=np.asarray([pi[r] for r in axes.values()]);epsilon=Fraction(1,100000000)
    columns={key:[] for key in targets}
    for j,key in owned.items():
        if key in columns:columns[key].append(j)
    candidates=[];receipts=[]
    for first in range(0,len(targets),workers):
        native.remaining();keys=targets[first:first+workers]
        tasks=[]
        for key in keys:
            uid=data[7]['classes'][key][0]
            tasks.append((roster[key],cp,len(data[7]['classes'][key]),bool(domains[uid].blocks),str(folder/'B'/key[:12])))
        answers=list(executor.map(worker,tasks)) if executor else [worker(t) for t in tasks]
        for answer in answers:
            for call in answer['calls']:
                native.calls.append(call);native.native_seconds+=call['native_seconds'] or 0.;native.budget.charge(call['native_seconds'] or 0.)
            native.resources.extend(answer['resources'])
        for key,answer in zip(keys,answers):
            if not answer['PASS']:
                message=answer.get('error','TARGETED_QUERY_FAILED')
                error=BudgetStop if message.startswith('BudgetStop:') else ValueError
                raise error(message)
            native.remaining();cache=load_cache(roster[key]);cache['coupling_axes']=tuple(axes)
            uid=data[7]['classes'][key][0];job=data[1][uid];N=len(data[7]['classes'][key]);domain=domains[uid]
            cols=sorted(columns[key]);rows=list(lrows[key])
            active=replace(original,matrix=original.matrix[rows][:,cols].tocsr(),lower=original.lower[cols],upper=original.upper[cols],
                senses=original.senses[rows],rhs=original.rhs[rows],vtypes=np.full(len(cols),'C'),objectives=cache['snapshot'].objectives)
            current=corrected_certificate(active,original.matrix[list(axes.values())][:,cols],cp,pi[rows])
            if not current['PASS']:raise ValueError('ACTIVE_LOCAL_NORMALIZATION_CERTIFICATE_FAIL')
            potential=Fraction(current['exact_lower_bound']);class_candidates=[];seen=set()
            stats=dict(class_id=key,migration_attempted=True,migration_native_query=answer['queries']['MIGRATION']['native_call'],
                migration_physical_domain_paths=roster[key]['full_physical_migration'],
                migration_support_paths_examined=0,unmaterialized_negative_blocks=0,
                STAY_paths_examined=0,STAY_valid_negative=0,migration_valid_negative=0)
            def checked(option,expected=None):
                c=validate(cache,job,data[2][uid],data[3],domain,data[4][uid],data[0],{k:i for i,k in enumerate(axes)},cp,N,potential,option,key)
                if expected is not None and c['price']!=expected:raise ValueError('COMPACT_PREFIX_PHYSICAL_PRICE_MISMATCH')
                if c['price']>=-epsilon:return
                effect_key=c['coefficient_sha256']
                if effect_key in seen:return
                seen.add(effect_key);c['residual_score']=float(score(c,effect,baseline));class_candidates.append(c)
            def persist(complete=False):
                stats.update(STAY_valid_negative=sum(c['kind']=='STAY' for c in class_candidates),
                    migration_valid_negative=sum(c['kind']=='MIGRATION' for c in class_candidates))
                atomic(folder/'B'/key[:12]/'CONCRETE_RECOVERY.json',serial(dict(PASS=complete,**stats,
                    active_local_lower_bound=str(potential),global_coupling_pi=tuple(map(float,cp)),
                    candidates=[dict(c,option=asdict(c['option']),price=str(c['price'])) for c in class_candidates],
                    no_permanent_deletions=True,full_mixed_fractional_closure_claimed=False)))
            persist()
            # Recovery is explicitly migration-first even if STAY has easy negatives.
            migration=answer['queries']['MIGRATION']
            if migration['status']!='NO_PHYSICAL_MIGRATION':
                query=migration_query(cache,N,'MIGRATION')
                cert=corrected_certificate(query,cache['B'],cp,migration['local_pi'])
                if cert!=migration['certificate']:raise ValueError('INDEPENDENT_MIGRATION_QUERY_CERTIFICATE_FAIL')
                potential_negative=Fraction(cert['exact_lower_bound'])<potential-epsilon
                if potential_negative:
                    for option in migration_witnesses(cache,migration['point'],job,domain):
                        native.remaining();stats['migration_support_paths_examined']+=1
                        ident=(option.start,option.initial_site,option.checkpoint,option.physical_checkpoint_seconds,option.destination,option.transfer_start)
                        if ident in ledger['migration_pools'][key].active_keys:continue
                        price,_=physical_price(option,job,data[4][uid],data[0],{k:i for i,k in enumerate(axes)},cp,N,potential)
                        if price < -epsilon:checked(option,price)
                        if len(class_candidates)>=POLICY['migration_recovery_per_class']:break
                    if len(class_candidates)<POLICY['migration_recovery_per_class']:
                        compact={}
                        try:
                            for option,price in migration_options(job,data[4][uid],data[0],domain,{k:i for i,k in enumerate(axes)},cp,N,potential,
                                ledger['migration_pools'][key].active_keys,epsilon,native.budget,compact):
                                checked(option,price)
                                if len(class_candidates)>=POLICY['migration_recovery_per_class']:break
                        finally:stats['compact_migration_recovery']=compact;persist()
                    if not class_candidates:stats['unmaterialized_negative_blocks']=1
                stats.update(migration_query_certificate=cert,migration_query_lower_rc_bound=str(Fraction(cert['exact_lower_bound'])-potential),
                    migration_full_native_query_completed=True,all_physical_migration_paths_covered_by_query=roster[key]['full_physical_migration'])
            else:stats.update(migration_query_status='NO_PHYSICAL_MIGRATION',compact_migration_recovery=dict(blocks_examined=0,paths_evaluated=0,full_physical_scan=True))
            stay_query=migration_query(cache,N,'STAY');stay=answer['queries']['STAY']
            cert=corrected_certificate(stay_query,cache['B'],cp,stay['local_pi'])
            if cert!=stay['certificate']:raise ValueError('INDEPENDENT_STAY_QUERY_CERTIFICATE_FAIL')
            stats['STAY_query_certificate']=cert
            ranked=[]
            from v42_job_capability import Option
            axis_indices={k:i for i,k in enumerate(axes)}
            for start,site in ledger['stay_pools'][key].keys():
                stats['STAY_paths_examined']+=1
                if stats['STAY_paths_examined']%128==0:native.remaining()
                option=Option(start,site,((site,start,start+job.service_slots),))
                price,vector=physical_price(option,job,data[4][uid],data[0],axis_indices,cp,N,potential)
                if price < -epsilon:
                    residual=sum(float(v)*effect[r] for r,v in vector.items())-baseline[key]
                    ranked.append((-residual,price,site,start,repr(option),option))
            for item in sorted(ranked)[:POLICY['STAY_recovery_per_class']]:checked(item[-1],item[1])
            persist(complete=True);receipts.append(stats);candidates.extend(class_candidates)
            atomic(folder/'PRICING_PROGRESS.json',dict(fully_priced_classes=len(receipts),targeted_classes=len(targets),
                valid_negative_STAY=sum(c['kind']=='STAY' for c in candidates),valid_negative_migration=sum(c['kind']=='MIGRATION' for c in candidates)))
            print('RESIDUAL_PRICED',len(receipts),len(targets),key[:12],stats['STAY_valid_negative'],stats['migration_valid_negative'],flush=True)
    selected=select(candidates,True)
    result=dict(PASS=True,classes_priced=len(receipts),class_ids=targets,targeted_migration_search_completed=True,
        negative_STAY=sum(c['kind']=='STAY' for c in candidates),negative_migration=sum(c['kind']=='MIGRATION' for c in candidates),
        unmateralized_negative_blocks=sum(r['unmaterialized_negative_blocks'] for r in receipts),selected_batch_size=len(selected),
        selected_STAY=sum(c['kind']=='STAY' for c in selected),selected_migration=sum(c['kind']=='MIGRATION' for c in selected),
        selected_candidates=[dict(c,option=asdict(c['option']),price=str(c['price'])) for c in selected],receipts=receipts,
        full_150_closure=False,permanent_deletions=0)
    atomic(folder/'PRICING_RESULT.json',serial(result))
    return result,selected
