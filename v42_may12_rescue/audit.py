"""Read-only historical recovery. No native optimization or old-tree writes."""
import csv,json,hashlib,subprocess
from fractions import Fraction
from pathlib import Path
from .policy import ROOT,OUT,STATIC,TEMP,OLD,OLDOUT,OLDSTATIC,DAY,BASE
from v42_pr134_b1.common import read,atomic,record

def file_digest(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p),sha256=h,bytes=p.stat().st_size)

def processes():
    import psutil
    found=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            d=p.info
            if (d['name'] or '').lower() in ('python.exe','pythonw.exe'):
                found.append(dict(pid=d['pid'],creation=d['create_time'],cwd=p.cwd(),argv=d['cmdline'],rss=p.memory_info().rss))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return found

def run():
    for p in (OUT,STATIC,TEMP):p.mkdir(parents=True,exist_ok=True)
    freeze=read(OLDOUT/'SOURCE_FREEZE_EPOCH_5.json')
    head=subprocess.check_output(['git','-C',str(OLD),'rev-parse','HEAD'],text=True).strip()
    if head!=BASE or freeze['git_head']!=BASE:raise ValueError('ACTUAL_MAY12_SOURCE_HEAD_DRIFT')
    source=[];copied=[]
    for path,h in freeze['execution_sources'].items():
        p=Path(path);rec=file_digest(p)
        if rec['sha256']!=h:raise ValueError('OLD_EXECUTED_SOURCE_DRIFT:'+path)
        q=ROOT/p.relative_to(OLD)
        if q.read_bytes()!=p.read_bytes():
            # New checkout line endings can differ. Restore executed bytes only
            # in the NEW independent tree, before writing any experiment code.
            if q.read_bytes().replace(b'\r\n',b'\n')!=p.read_bytes().replace(b'\r\n',b'\n'):
                raise ValueError('CHECKOUT_NOT_ACTUAL_EXECUTED_SOURCE:'+str(q))
            q.write_bytes(p.read_bytes());copied.append(str(q))
        source.append(rec)
    historical=[file_digest(p) for p in sorted((OLDOUT/DAY).rglob('*')) if p.is_file()]
    cache=[file_digest(p) for p in sorted((OLDSTATIC/DAY).rglob('*')) if p.is_file()]
    atomic(OUT/'HISTORICAL_BYTE_MANIFEST.json',dict(PASS=True,old_evidence=historical,old_cache=cache,old_sources=source,checkout_executed_byte_restorations=copied))
    f=OLDOUT/DAY;r=read(f/'RESULT.json');calls=read(f/'NATIVE_CALLS.json')['calls']
    trajectory=read(f/'PHASE_I_TRACE.json');zero=read(f/'PHASE_I_ZERO_CERTIFICATE.json');p1=read(f/'P1_TRACE.json')
    price=read(f/'P1/S0/PRICE/FULL_PRICING_RESULT.json')
    rounds=[]
    for i in (19,20,21):
        q=read(f/f'PHASE_I/S{i}/PRICE/PRICING_RESULT.json')
        rounds.append(dict(solve=i,STAY=q['selected_STAY'],migration=q['selected_migration'],classes=q['classes_priced'],selected=q['selected_batch_size']))
    audit=dict(PASS=True,scope='HISTORICAL_RECOVERY_ONLY_NOT_NEW_ACCEPTANCE',actual_source_HEAD=head,source_freeze=record(OLDOUT/'SOURCE_FREEZE_EPOCH_5.json'),
        old_result=record(f/'RESULT.json'),old_traceback=r['traceback'],solver_failure=False,python_verifier_failure=True,
        failed_function='v42_a_stage_early.progress.inclusion_witness',failed_line=19,caller='v42_a_stage_canary.phase.activate:33',
        historical_native_calls=len(calls),historical_native_seconds=sum(c['native_seconds'] or 0 for c in calls),historical_Work=sum(c['Work'] or 0 for c in calls),historical_wall_seconds=r['wall_seconds'],
        last_native_solve=calls[-1],last_master_solve=next(c for c in reversed(calls) if c['component']=='ORIGINAL_P1'),
        last_validated_original_primal_phase1=zero,last_restricted_P1_primal=p1,last_certified_Phi=zero['zero']['replayed_phi'],
        original_point_integer_feasibility_not_yet_proven=True,P1_was_started=True,P2_was_not_started=True,
        phase1_activation_rounds=trajectory['activation_rounds'],phase1_activations=rounds,
        complete_pricing_classes=price['classes'],negative_blocks_verified=price['negative_blocks'],negative_blocks_not_yet_activated=price['negative_blocks'],
        previous_full_domain_LB=price['full_domain_phase1_lower_bound'],previous_full_domain_LB_float=float(Fraction(price['full_domain_phase1_lower_bound'])),
        previous_restricted_LP_value=float(Fraction(price['active_objective_upper'])),closure=False,
        protected_processes_observed=processes(),other_processes_signalled_or_modified=False)
    atomic(OUT/'MAY12_RECOVERY_AUDIT.json',audit)
    with (OUT/'PHASE1_ACTIVATION_TRAJECTORY.csv').open('w',encoding='utf8',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(trajectory['trajectory'][0]));w.writeheader();w.writerows(trajectory['trajectory'])
    print('MAY12_RECOVERY_AUDIT',head,len(calls),r['native_seconds'],zero['zero']['replayed_phi'],rounds,flush=True)
if __name__=='__main__':run()
