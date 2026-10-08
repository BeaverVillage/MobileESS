"""One cumulative sequential recovery experiment; never optimize P2."""
import gzip,pickle,gc,traceback,os,itertools
from fractions import Fraction
from time import perf_counter
from dataclasses import replace
import numpy as np
from .policy import ROOT,OUT,STATIC,DAY,OLDOUT
from .native import create
from .execution import active_freeze
from .contract import decide
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_compact_rowgen.assembly import partition
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_canary.pricing import full_pricing
from v42_a_stage_canary.phase import activate
from v42_a_stage_practical.integer_model import restore_types
from v42_a_stage_lexfull.runner import objective_value

def checkpoint(name,state,raw=None):
    p=STATIC/(name+'.pkl.gz')
    if p.exists() and 'compact' in state:
        with gzip.open(p,'rb') as f:old=pickle.load(f)
        if (old['state']['compact'].fingerprint()!=state['compact'].fingerprint()
            or old['state']['reference'].fingerprint()!=state['reference'].fingerprint()
            or set(old['raw'])!=set(raw) or any(not np.array_equal(old['raw'][k],raw[k]) for k in raw)):
            raise ValueError('COMPLETED_P1_STATE_CHECKPOINT_DRIFT')
        return record(p)
    with gzip.open(p,'xb',compresslevel=1) as f:pickle.dump(dict(state=state,raw=raw),f,protocol=5)
    return record(p)

def run(resume_pre_native_gate=False,resume_incomplete_pricing=False,resume_verified_batch=False):
    started=perf_counter();native=None;timings={};decision=dict(PASS=False,classification='MAY12_PHASE1_RECOVERED_P1_INCONCLUSIVE')
    if (OUT/'NEW_RUN_STARTED.json').exists():
        if resume_verified_batch:
            pointer=OUT/'LATEST_BATCH_PRICING_CHECKPOINT.json'
            if pointer.exists():
                receipt=read(pointer)['decision']
                if record(receipt['path'])!=receipt:raise ValueError('BATCH_PRICING_RESUME_DECISION_DRIFT')
                previous=read(receipt['path'])
                permitted=previous['classification']=='MAY12_RESOURCE_PENDING'
            else:
                previous=read(OUT/'PRE_IMPLEMENTATION_BOUNDARY1/FINAL_DECISION.json')
                permitted=previous.get('error')=="PermissionError('MAY12_FROZEN_SOURCE_REQUIRED')"
            calls=read(OUT/'NEW_NATIVE_CALLS.json')
            marker=read(OUT/'PRE_IMPLEMENTATION_BOUNDARY1/IMPLEMENTATION_BOUNDARY_REQUEST.json')
            if (not permitted
                or marker['reason']!='INTENTIONAL_BETWEEN_SOLVE_IMPLEMENTATION_BOUNDARY'
                or previous['new_native_seconds']!=calls['actual_Runtime'] or previous['new_native_calls']!=len(calls['calls'])):
                raise PermissionError('ONLY_PRESERVED_IMPLEMENTATION_BOUNDARY_RESUME')
            atomic(OUT/'RESUME_VERIFIED_STAY_BATCH.json',dict(PID=os.getpid(),source=record(active_freeze()),
                prior_Runtime=previous['new_native_seconds'],prior_calls=previous['new_native_calls'],no_budget_reset=True,
                completed_pricing_and_master_reused=True,scientific_parameters_unchanged=True))
        elif resume_incomplete_pricing:
            pointer=OUT/'LATEST_PARTIAL_PRICING_CHECKPOINT.json'
            previous_receipt=read(pointer)['decision'] if pointer.exists() else record(OUT/'PRE_PRICING_START_GATE_FAILURE2/FINAL_DECISION.json')
            if record(previous_receipt['path'])!=previous_receipt:raise ValueError('PARTIAL_PRICING_DECISION_DRIFT')
            previous=read(previous_receipt['path']);accounted=read(OUT/'NEW_NATIVE_CALLS.json')
            if (previous['classification']!='MAY12_RESOURCE_PENDING' or previous['new_native_calls']!=len(accounted['calls'])
                or previous['new_native_seconds']!=accounted['actual_Runtime'] or (OUT/'P1_TRAJECTORY.json').exists()):
                raise PermissionError('ONLY_PRESERVED_PARTIAL_PRICING_CHECKPOINT_RESUME')
            atomic(OUT/'RESUME_PARTIAL_PRICING.json',dict(PID=os.getpid(),source=record(active_freeze()),
                prior_Runtime=previous['new_native_seconds'],prior_calls=previous['new_native_calls'],
                previous_decision=previous_receipt,no_budget_reset=True))
        else:
            old=read(OUT/'PRE_NATIVE_START_GATE_FAILURE1/FINAL_DECISION.json')
            if not resume_pre_native_gate or old['new_native_calls']!=0 or old['new_native_seconds']!=0:
                raise PermissionError('ONE_NEW_MAY12_EXPERIMENT_ONLY')
            if (OUT/'NEW_NATIVE_CALLS.json').exists() and read(OUT/'NEW_NATIVE_CALLS.json')['calls']:
                raise PermissionError('CANNOT_RESET_ACTUAL_NATIVE_BUDGET')
            atomic(OUT/'RESUME_PRE_NATIVE_GATE.json',dict(PID=os.getpid(),source=record(active_freeze()),
                no_previous_native_call=True,native_budget_not_reset=True,previous_gate_failure=record(OUT/'PRE_NATIVE_START_GATE_FAILURE1/FINAL_DECISION.json')))
    else:atomic(OUT/'NEW_RUN_STARTED.json',dict(PID=os.getpid(),source=record(active_freeze()),native_budget=3600,automatic_followup=False))
    try:
        from .prepare import route
        route()
        native=create()
        r=read(OUT/'WITNESS_FAILURE_REPRODUCTION.json')['payload']
        if record(r['path'])!=r:raise ValueError('FAILURE_PAYLOAD_BYTE_DRIFT')
        with gzip.open(r['path'],'rb') as f:p=pickle.load(f)
        state=p['old'];negative=p['negative'];raw=p['raw']
        # Admit all independently verified current negative supports in one
        # preregistered batch; keep the historical failed 64-column attempt.
        before=perf_counter();cache=OUT/'RECOVERED_ACTIVATED_STATE.json'
        if (resume_incomplete_pricing or resume_verified_batch) and cache.exists():
            saved=read(cache)
            if saved['failure_payload']!=r or record(saved['state']['path'])!=saved['state']:
                raise ValueError('RECOVERED_ACTIVATED_STATE_BYTE_DRIFT')
            with gzip.open(saved['state']['path'],'rb') as f:stored=pickle.load(f)
            state=stored['state'];warm=stored['warm']
            if (state['compact'].fingerprint()!=saved['compact_sha256'] or state['reference'].fingerprint()!=saved['reference_sha256']
                or record(saved['inclusion']['path'])!=saved['inclusion']):raise ValueError('RECOVERED_ACTIVATED_STATE_MATRIX_OR_WITNESS_DRIFT')
        else:
            state,warm=activate(state,negative,raw['X'],OUT/'P1/RECOVERED_ACTIVATION',max_batch=130)
            path=STATIC/'RECOVERED_ACTIVATED_STATE.pkl.gz'
            with gzip.open(path,'xb',compresslevel=1) as f:pickle.dump(dict(state=state,warm=warm),f,protocol=5)
            atomic(cache,dict(PASS=True,state=record(path),failure_payload=r,compact_sha256=state['compact'].fingerprint(),
                reference_sha256=state['reference'].fingerprint(),inclusion=record(OUT/'P1/RECOVERED_ACTIVATION/ACTIVATION.json'),
                no_native_call=True,source=record(active_freeze())))
        timings['recovered_activation_build_seconds']=perf_counter()-before
        del p;gc.collect();trajectory=[]
        for round_no in itertools.count():
            native.remaining();s=state['compact'];folder=OUT/('P1_BATCH' if resume_verified_batch and round_no>=2 else 'P1')/f'S{round_no}'
            before=perf_counter()
            calls_before=len(native.calls)
            if resume_incomplete_pricing and round_no==0:
                rec=read(folder/'NATIVE_RESULT.json');identity=read(rec['model_identity']['path'])
                if identity['original_snapshot_sha256']!=s.fingerprint() or record(rec['raw_attributes']['path'])!=rec['raw_attributes']:
                    raise ValueError('P1_MASTER_CHECKPOINT_MATRIX_OR_RAW_DRIFT')
                raw=dict(np.load(rec['raw_attributes']['path']))
                atomic(folder/'CACHED_MASTER_REUSE.json',dict(PASS=True,original=record(folder/'NATIVE_RESULT.json'),new_native_calls=0,budget_not_reset=True))
            else:rec,raw=native.solve(s,folder,'ORIGINAL_P1')
            master_reused=len(native.calls)==calls_before
            if rec['status']!=2 or not all(k in raw for k in ('X','Pi','RC')):raise RuntimeError('P1_LP_NOT_OPTIMAL')
            replay=primal_replay(s,raw['X']);sign=verify_sign_convention(s,raw['Pi'],raw['RC'])
            ex=expanded_point(state,raw['X']);original=primal_replay(state['reference'],ex)
            if not replay['PASS'] or not sign['PASS'] or not original['PASS']:raise ValueError('ORIGINAL_P1_PRIMAL_DUAL_REPLAY_FAILED')
            from .exact import replay as exact_replay
            dyadic=exact_replay(state['reference'],ex)
            if not dyadic['PASS']:raise ValueError('ORIGINAL_P1_EXACT_DYADIC_ROW_REPLAY_FAILED')
            atomic(folder/'ORIGINAL_PRIMAL_DUAL_REPLAY.json',dict(PASS=True,compact=replay,original=original,sign=sign))
            atomic(folder/'EXACT_ORIGINAL_ROW_REPLAY.json',dyadic)
            local,owned=partition(s,state['metas'],state['grows'])
            beforeprice=perf_counter()
            if resume_verified_batch and round_no==0:
                from .completed_pricing import restore
                priced,negative=restore(state,folder/'PRICE',raw)
                atomic(folder/'COMPLETE_PRICING_REUSE.json',dict(PASS=True,exact_bounds_reverified=True,
                    original_native_raw_replayed=True,completed_native_calls_recharged=False,
                    original_full_pricing=record(folder/'PRICE/FULL_PRICING_RESULT.json')))
            else:
                priced,negative=full_pricing(native,s,None,raw,None,state['data'],state['domains'],state['ledger'],state['axes'],state['n'],state['grows'],local,owned,folder/'PRICE')
            trajectory.append(dict(round=round_no,LP_objective=rec['objective'],native_Runtime=rec['native_seconds'],Work=rec['Work'],
                master_solve_reused=master_reused,actual_new_master_Runtime=0 if master_reused else rec['native_seconds'],
                full_domain_LB=None if priced['full_domain_phase1_lower_bound'] is None else float(Fraction(priced['full_domain_phase1_lower_bound'])),
                pricing_classes=priced['classes'],negative_blocks=priced['negative_blocks'],closed=priced['no_negative_omitted_block_certified'],
                pricing_wall_seconds=perf_counter()-beforeprice,round_wall_seconds=perf_counter()-before))
            atomic(OUT/'P1_TRAJECTORY.json',dict(trajectory=trajectory))
            checkpoint(f'P1_S{round_no}',state,raw)
            if priced['no_negative_omitted_block_certified']:
                L=priced['full_domain_phase1_lower_bound']
                if L is None:raise ValueError('FULL_DOMAIN_PRICING_CLOSURE_WITHOUT_LB')
                closure=dict(PASS=True,classes=priced['classes'],complete_STAY_and_migration_coverage=True,
                    no_negative_omitted_block_certified=True,full_original_global_rows=True,all_original_local_rows=True,
                    full_STAY=priced['complete_STAY'],full_migration=priced['complete_migration'],
                    exact_certificate=record(folder/'PRICE/FULL_PRICING_RESULT.json'),candidate_deletions=0)
                atomic(OUT/'COMPLETE_PRICING_CLOSURE.json',closure)
                bound=dict(PASS=True,exact_LB=L,LB=float(Fraction(L)),scope='FULL_ORIGINAL_MAY12_P1_LP_RELAXATION',
                    original_objective_identity=str(s.objective('rho')),ObjCon=str(s.objective('rho').constant),full_130_class_certificates=closure,
                    finite_original_bound_support_and_exact_dual_sign=True,roundoff_transport_correction=True,
                    restricted_master_ObjBound_not_used=True,source=record(active_freeze()))
                atomic(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',bound)
                break
            if not negative:raise RuntimeError('UNRESOLVED_EXACT_PRICING_INTERVAL_WITHOUT_VERIFIED_NEGATIVE_SUPPORT')
            if resume_verified_batch and round_no>=1:
                from .stay_batch import augment
                negative,batch=augment(state,negative,folder/'PRICE',folder)
                trajectory[-1]['additional_exact_negative_STAY_columns']=batch['additional_negative_concrete_STAY_columns']
                trajectory[-1]['batch_STAY_verification_wall_seconds']=batch['wall_seconds']
                atomic(OUT/'P1_TRAJECTORY.json',dict(trajectory=trajectory))
            native.remaining();prior_fingerprint=s.fingerprint();transition=folder/'ACTIVATED_NEXT_STATE.json'
            if transition.exists():
                saved=read(transition)
                if (saved['from_compact_sha256']!=prior_fingerprint or saved['prior_raw']!=rec['raw_attributes']
                    or record(saved['state']['path'])!=saved['state'] or record(saved['witness']['path'])!=saved['witness']):
                    raise ValueError('ACTIVATED_TRANSITION_CHECKPOINT_INPUT_OR_BYTES_DRIFT')
                with gzip.open(saved['state']['path'],'rb') as f:stored=pickle.load(f)
                state,warm=stored['state'],stored['warm']
                if state['compact'].fingerprint()!=saved['to_compact_sha256'] or state['reference'].fingerprint()!=saved['to_reference_sha256']:
                    raise ValueError('ACTIVATED_TRANSITION_CHECKPOINT_MATRIX_DRIFT')
            else:
                state,warm=activate(state,negative,raw['X'],folder,max_batch=130)
                path=STATIC/(folder.parent.name+'_NEXT_'+folder.name+'.pkl.gz')
                with gzip.open(path,'xb',compresslevel=1) as f:pickle.dump(dict(state=state,warm=warm),f,protocol=5)
                atomic(transition,dict(PASS=True,from_compact_sha256=prior_fingerprint,to_compact_sha256=state['compact'].fingerprint(),
                    to_reference_sha256=state['reference'].fingerprint(),prior_raw=rec['raw_attributes'],state=record(path),
                    witness=record(folder/'ACTIVATION.json'),source=record(active_freeze()),no_budget_reset=True))
            if state['compact'].fingerprint()==prior_fingerprint:raise ValueError('UNRESOLVED_EXACT_NEGATIVE_DIRECTION_ALREADY_IN_ACTIVE_MATRIX')
            inclusion=exact_replay(state['reference'],expanded_point(state,warm))
            atomic(folder/'EXACT_ACTIVATED_INCLUSION_ROW_REPLAY.json',inclusion)
            if not inclusion['PASS']:raise ValueError('EXACT_PRIOR_POINT_INCLUSION_ROW_REPLAY_FAILED')
        before=perf_counter();typed,typeproof=restore_types(state,state['global_types'])
        atomic(OUT/'ORIGINAL_INTEGER_TYPE_RESTORATION.json',typeproof);timings['integer_model_restore_seconds']=perf_counter()-before
        import v42_a_stage_acceptance.physical as physical_module
        physical_module.STATIC=STATIC/'PHYSICAL';physical_module.ROOT=ROOT
        physical=physical_module.Physical(state,typed)
        native.warm_point=None  # No fractional LP point is asserted to be an integer incumbent.
        verified=[]
        def validate(x,objective):
            rows=primal_replay(typed,x);iv=typed.vtypes!='C';integral=float(np.max(abs(x[iv]-np.rint(x[iv])),initial=0))
            if not rows['PASS'] or integral>1e-5:return
            v=physical.verify(x)
            if not v['PASS']:return
            U=objective_value(typed,x,'rho');values={o.name:str(objective_value(typed,x,o.name)) for o in typed.objectives}
            from v42_a_stage_acceptance.schedule_audit import original_schedule_metrics
            metrics,residuals=original_schedule_metrics(state['data'][1],v['selected_jobs'],values)
            v.update(original_job_population_verified=True,original_jobs=len(state['data'][1]),original_integer_types_restored=True,
                integral_max_residual=integral,scientific_primal_replay=rows,objective_values=values,schedule_metrics=metrics,
                original_P1_objective_consistency=abs(float(U)-objective)<=1e-6,no_future_information=True,
                frozen_input=record(OLDOUT/DAY/'INITIAL_VERIFICATION.json'))
            if not v['original_P1_objective_consistency']:raise ValueError('P1_NATIVE_OBJECTIVE_IDENTITY_FAIL')
            if verified and U>=Fraction(verified[-1]['exact_UB']):return
            point=STATIC/'VALIDATED_INTEGER_POINT.npz';np.savez_compressed(point,X=x)
            atomic(OUT/'ORIGINAL_PHYSICAL_REPLAY.json',v)
            candidate=dict(PASS=True,exact_UB=str(U),UB=float(U),original_integer_types_restored=True,
                physical=record(OUT/'ORIGINAL_PHYSICAL_REPLAY.json'),point=record(point),exact_objective_values=values,
                evaluated_P2_metrics_only=metrics,actual_full_original_integer_rows=typed.matrix.shape[0],columns=typed.matrix.shape[1],nnz=typed.matrix.nnz)
            verified.append(candidate);atomic(OUT/'VALIDATED_INTEGER_INCUMBENTS.json',dict(trajectory=verified))
            print('MAY12_ORIGINAL_INTEGER_INCUMBENT_VERIFIED',float(U),flush=True)
            L=Fraction(bound['exact_LB'])
            if U>=L and ((U-L)/abs(U) if U else Fraction(0) if L==0 else Fraction(1))<=Fraction(1,200):
                atomic(OUT/'INDEPENDENT_CERTIFIED_TARGET_STOP.json',dict(PASS=True,reason='CERTIFIED_P1_ONLY_GLOBAL_GAP_TARGET_MET',
                    exact_LB=str(L),exact_UB=str(U),memory_triggered=False))
                if getattr(native,'live_model',None) is not None:native.live_model.terminate()
        native.incumbent_callback=validate
        rec,raw=native.solve(typed,OUT/'P1/INTEGER_CONTROL','INTEGER_CONTROL')
        if 'X' in raw:validate(raw['X'],rec['objective'])
        integer=(dict(verified[-1],native_status=rec['status'],native_active_bound_not_used=True,native_result=record(OUT/'P1/INTEGER_CONTROL/NATIVE_RESULT.json'))
            if verified else dict(PASS=False,native_status=rec['status'],reason='NO_VALIDATED_ORIGINAL_INTEGER_INCUMBENT'))
        atomic(OUT/'P1_INTEGER_RESULT.json',integer)
        v=read(OUT/'ORIGINAL_PHYSICAL_REPLAY.json') if verified else dict(PASS=False)
        acceptance=decide(read(OUT/'PHASE1_ZERO_CERTIFICATE.json'),closure,bound,integer,v)
        atomic(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json',acceptance)
        if acceptance['PASS']:
            freeze=dict(PASS=True,state='A1_P1_ONLY_ACCEPTED',A1_ACCEPTED=False,day=DAY,
                validated_original_integer_point=integer['point'],integer_model_checkpoint=checkpoint('ACCEPTED_INTEGER_MODEL',dict(state=state,typed=typed)),
                exact_objective_values=integer['exact_objective_values'],metrics_only=integer['evaluated_P2_metrics_only'],
                selected_jobs=v['selected_jobs'],controls=v['controls'],globals=v['globals'],
                physical=record(OUT/'ORIGINAL_PHYSICAL_REPLAY.json'),global_bound=record(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json'),
                acceptance=record(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json'),scientific_input=record(OLDOUT/DAY/'INITIAL_VERIFICATION.json'),
                source=record(active_freeze()),downstream_executed=False)
            atomic(OUT/'P1_ONLY_FREEZE.json',freeze)
            decision.update(PASS=True,classification='MAY12_P1_ONLY_ACCEPTED',P1=acceptance)
        else:decision.update(P1=acceptance,reason='GLOBAL_INTEGER_GAP_NOT_ACCEPTED')
    except Exception as e:
        decision.update(PASS=False,error=repr(e),traceback=traceback.format_exc())
        if 'RESOURCE_PENDING' in str(e):decision['classification']='MAY12_RESOURCE_PENDING'
        elif 'PRICING' in str(e):decision['classification']='MAY12_PHASE1_PRICING_INCOMPLETE'
        elif 'INCLUSION' in str(e) or 'WITNESS' in str(e):decision['classification']='MAY12_WITNESS_VALIDATION_FAIL'
    finally:
        decision.update(new_wall_seconds=perf_counter()-started,new_native_seconds=0 if native is None else native.native_seconds,
            new_Work=0 if native is None else sum(c.get('Work') or 0 for c in native.calls),new_native_calls=0 if native is None else len(native.calls),
            timings=timings,old_native_seconds=233.89299654960632,P2_executed=False,automatic_followup=False)
        atomic(OUT/'FINAL_DECISION.json',decision)
        print('MAY12_FINAL_DECISION',decision['classification'],decision['new_native_seconds'],decision.get('error'),flush=True)
if __name__=='__main__':
    import sys
    run('--resume-pre-native-gate' in sys.argv,'--resume-incomplete-pricing' in sys.argv,'--resume-verified-batch' in sys.argv)
