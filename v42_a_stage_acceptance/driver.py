"""One new continuation, sequential native dates with immutable receipts."""
import sys,gzip,pickle,traceback,gc,threading
from time import time,perf_counter
from fractions import Fraction
from pathlib import Path
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock
from .policy import ROOT,OUT,STATIC,OLD,DAYS,BASE
from .budget import Budget
from .native import Native
from .execution import verify
from .physical import Physical
from v42_a_stage_compact_rowgen.resources import sample

def route(day):
    import v42_a_stage_canary.policy as p
    p.OUT=OUT;p.STATIC=STATIC;p.DAYS=DAYS[1:]
    import v42_a_stage_canary.prepare as prep
    import v42_a_stage_canary.phase as phase
    import v42_a_stage_canary.pricing as pricing
    import v42_a_stage_canary.targeted as targeted
    import v42_a_stage_canary.zero as zero
    for module in (prep,phase,pricing,zero):
        module.OUT=OUT
        if hasattr(module,'STATIC'):module.STATIC=STATIC
    prep.DAYS=DAYS[1:]
    # Cache relocation preserves every producer byte identity. The exact
    # historical physical domain is date-specific, not May19's job pool.
    import v42_a_stage_domain_v2.fast_census as census
    cache=OLD.parents[2]/'v42-a-stage-fast-active-static'
    r=read(cache/day/'PHYSICAL_DOMAIN_CACHE.json')
    for source in r['producer_sources']:
        rel=Path(source['path']).name
        current=next((q for q in (ROOT/'v42_a_stage_domain_v2/domain.py',ROOT/'v42_boundary/generator.py',ROOT/'v42_job_capability.py') if q.name==rel),None)
        if current is None or sha(current)!=source['sha256'] or record(source['path'])!=source:
            raise ValueError('DATE_PHYSICAL_DOMAIN_PRODUCER_BYTES_CHANGED')
    census._producer_sources=lambda:r['producer_sources'];prep.CACHE_STATIC=cache
    pricing.HISTORY=OUT/day;targeted.HISTORY=OUT/day
    return prep,phase

def may19(native):
    folder=OUT/DAYS[0];accepted=read(folder/'SHIFT_ACCEPTED_STATE.json')
    if not accepted['PASS']:raise PermissionError('INDEPENDENT_SHIFT_AUDIT_REQUIRED')
    for r in (accepted['point'],accepted['build'],accepted['gap_certificate']):
        if record(r['path'])!=r:raise ValueError('MAY19_ACCEPTED_AUDIT_BYTE_DRIFT')
    build=read(accepted['build']['path'])
    if record(build['state']['path'])!=build['state']:raise ValueError('FULL_DOMAIN_STATE_BYTES_CHANGED_AFTER_AUDIT')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    state,s=p['state'],p['snapshot'];cg=read(OLD/'WEIGHTED_CG_BUILD_VERIFICATION.json')
    if record(cg['snapshot']['path'])!=cg['snapshot']:raise ValueError('STRENGTHENED_MODEL_BYTES_CHANGED_AFTER_AUDIT')
    with gzip.open(cg['snapshot']['path'],'rb') as f:strong=pickle.load(f)
    audited=read(folder/'SHIFT_FULL_DOMAIN_BOUND_AUDIT.json')
    if s.fingerprint()!=audited['original_snapshot'] or strong.fingerprint()!=audited['strengthened_snapshot']:
        raise ValueError('PRESTART_MODEL_DIFFERS_FROM_INDEPENDENT_SHIFT_AUDIT')
    warm=np.load(accepted['point']['path'])['X'];physical=Physical(state,s)
    inc=read(OLD/'VALIDATED_INTEGER_INCUMBENT.json');mig=read(OLD/'P2_MIGRATION_PROBE_RESULT.json')
    locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OLD/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256']),
        LexLock('shift_magnitude',Fraction(950),True,accepted['gap_certificate']['sha256'])]
    from .stages import run
    stages,warm=run(native,strong,s,warm,physical,locks,folder,names=('prestart_relocation',))
    from .accepted import freeze
    certificates=[record(OLD/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),mig['certificate'],accepted['gap_certificate'],stages[0]['certificate']]
    result=freeze(DAYS[0],state,s,warm,physical,locks,certificates)
    result.update(historical_certificates_reused=True,fresh_end_to_end_runtime_measured=False,
        practical_runtime_accepted=False,practical_failure_reason='PR180_REUSABLE_CERTIFICATES_DO_NOT_PROVE_30_MINUTE_END_TO_END_RUNTIME')
    return result

def run(day,resume=False):
    verify()
    if day not in DAYS:raise PermissionError('ONLY_FOUR_REQUESTED_A_STAGE_DAYS')
    folder=OUT/day;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'STARTED.json').exists() and not resume:raise PermissionError('DAY_ALREADY_EXECUTED_USE_PRESERVED_CHECKPOINT')
    if resume and day!=DAYS[1]:raise PermissionError('ONLY_ACTUAL_MAY17_INTERFACE_FAILURE_CHECKPOINT')
    if day!=DAYS[0]:
        if not read(OUT/DAYS[0]/'A1_RESULT.json').get('A1_accepted'):raise PermissionError('MAY19_FINAL_A1_ACCEPTANCE_REQUIRED')
        for prior in DAYS[1:DAYS.index(day)]:
            if not (OUT/prior/'RESULT.json').exists():raise PermissionError('REQUESTED_EXECUTION_ORDER_REQUIRED')
    started=time();budget=Budget(day);native=Native(budget,day)
    previous=read(folder/'NATIVE_CALLS.json')['calls'] if resume else []
    if resume:
        atomic(folder/'ATTEMPT0_RESULT.json',read(folder/'RESULT.json'))
        atomic(folder/'ATTEMPT0_NATIVE_CALLS.json',dict(calls=previous))
    samples=[];stop=threading.Event()
    def resources():
        while not stop.is_set():
            samples.append(dict(unix=time(),**sample()))
            atomic(folder/'WHOLE_DAY_RESOURCES.json',dict(samples=samples))
            stop.wait(2)
    observer=threading.Thread(target=resources,daemon=True);observer.start()
    atomic(folder/('RESUME_1_STARTED.json' if resume else 'STARTED.json'),dict(PASS=True,day=day,actual_start_unix=started,budget=record(OUT/'CONTINUATION_BUDGET.json'),
        source=record(native.freeze_path),one_native_process=True,old_PR180_attempt_not_resumed=True,
        prior_native_seconds=budget.native_seconds,continuation_budget_not_reset=True))
    result=dict(day=day,A1_accepted=False,classification='INCONCLUSIVE',practical_runtime_accepted=False)
    try:
        if sample()['unsafe']:raise RuntimeError('SYSTEM_RAM_COMMIT_RESERVE_BEFORE_DAY_BUILD')
        if day==DAYS[0]:result.update(may19(native))
        else:
            prep,phase=route(day);seed=None
            if resume:
                b=read(folder/'INITIAL_VERIFICATION.json')
                if record(b['state']['path'])!=b['state']:raise ValueError('ORIGINAL_CHECKPOINT_STATE_DRIFT')
                with gzip.open(b['state']['path'],'rb') as stream:state=pickle.load(stream)
                nr=read(folder/'PHASE_I/S15/NATIVE_RESULT.json')
                if record(nr['raw_attributes']['path'])!=nr['raw_attributes']:raise ValueError('LAST_PHASE_I_RAW_POINT_DRIFT')
                seed=np.load(nr['raw_attributes']['path'])['X'][:state['compact'].matrix.shape[1]]
            else:state=prep.prepare(day)
            state,x,expanded,priced=phase.run(native,state,day,certified_zero_point=seed)
            from .integer import run as integer
            result.update(integer(native,state,expanded,priced,day))
            result.update(fresh_end_to_end_runtime_measured=True,historical_certificates_reused=False,
                practical_runtime_accepted=time()-started<=1800)
    except Exception as e:result.update(failure_reason=repr(e),traceback=traceback.format_exc())
    finally:
        stop.set();observer.join(timeout=3)
        calls=previous+native.calls
        result.update(native_seconds=sum(c.get('native_seconds') or 0 for c in calls),Work=sum(c.get('Work') or 0 for c in calls),
            native_calls=len(calls),wall_seconds=time()-read(folder/'STARTED.json')['actual_start_unix'],
            peak_RSS_bytes=max([c.get('peak_RSS_bytes') or 0 for c in native.calls]+[s['A_process_RSS_bytes'] for s in samples],default=0),
            per_day_native_limit=3600,practical_wall_target=1800,
            model_sizes=[dict(component=c['component'],identity=c['model_identity']) for c in native.calls],
            native_runtime_excludes_build_pricing_python_and_validation=True)
        if not result.get('A1_accepted'):result['practical_runtime_accepted']=False
        if result.get('A1_accepted') and result['practical_runtime_accepted']:result['classification']='PRACTICAL_RUNTIME_ACCEPTED'
        atomic(folder/'NATIVE_CALLS.json',dict(calls=calls));atomic(folder/'RESULT.json',result)
        print('FOURDAY_RESULT',day,result['classification'],result.get('failure_reason'),result['native_seconds'],result['wall_seconds'],flush=True)
    gc.collect();return result
if __name__=='__main__':run(sys.argv[1],resume='--resume' in sys.argv[2:])
