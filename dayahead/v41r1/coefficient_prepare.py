"""Certify each day's current Planning coefficients before any May optimization."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import Counter
import argparse,os,subprocess,sys,threading,time,uuid
from dayahead.paper_analysis.storage import read,write_json,digest
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.reserve import require

DAYS=tuple(f'2025-05-{d:02}' for d in range(1,32))
PASS_CLASSES={'CURRENT_V41R1_GENERATED_AND_CERTIFIED','REUSED_BY_EXACT_INPUT_AND_METHOD_EQUIVALENCE'}


def certify(day,generate_missing=True):
    from dayahead.v41.electrical import load,generate,identity
    from dayahead.v41.persistence import verify_table
    require(day in DAYS,'COEFFICIENT_DAY_OUTSIDE_MAY')
    root=RUNTIME/'e'/day.replace('-','');certificate=root/'V41_ELECTRICAL_CERTIFICATE.json'
    context=None;regenerated=False;previous_error=None;archive=None
    try:
        try:context=load(day)
        except Exception as error:
            previous_error=repr(error)
            if not generate_missing:raise
            if root.exists():
                archive=RUNTIME/'e_old'/(day.replace('-','')+'_'+uuid.uuid4().hex[:6])
                root.resolve().relative_to(RUNTIME.resolve());archive.resolve().relative_to(RUNTIME.resolve())
                archive.parent.mkdir(parents=True,exist_ok=True);root.rename(archive)
                write_json(archive/'INVALIDATION.json',dict(day=day,reason=previous_error,
                    bytes_preserved=True,classification='MISSING/INVALID'))
            context=generate(day);regenerated=True
        value=read(certificate);current=identity(day);inputs=current['identity']['inputs']
        require(value['input_identity']==current and inputs['day']==context.day==day,'COEFFICIENT_TARGET_DAY_MISMATCH')
        mapper=read(value['mapper_audit']['path']);frame=verify_table(mapper['rows'])
        require(mapper['target_day']==day and mapper['stage']=='Planning_GENERATION'
            and mapper['status']=='PASS' and mapper['slots']==96 and mapper['duplicated_group_slots']==0
            and not frame.duplication_detected.any(),'COEFFICIENT_BACKGROUND_DUPLICATION')
        require(max(mapper['P_max_error_kW'],mapper['Q_max_error_kvar'])<=mapper['tolerance'],'COEFFICIENT_MAPPER_PQ_CONSERVATION')
        require(inputs['native_mapper']['sha256']==record(ROOT/'dayahead/v40e/mapping.py')['sha256'],'COEFFICIENT_CURRENT_MAPPER_METHOD_MISMATCH')
        categories={
            'topology':('feeder_manifest','OpenDSS_master','PCC_mapping','service_PCC_mapping'),
            'background_load_mapper':('background_mapping','native_mapper','native_allocation_authority'),
            'demand_PV_DayAhead':('demand','PV','weather'),
            'ratings':('line_ratings','transformer_ratings'),
            'AC_anchor_input':('AC_anchor_input',),
            'generation_method':('V41_generation_entrypoint','V41_generation_source','voltage_generation','current_generation','transformer_generation')}
        identities={name:dict(SHA=digest({k:inputs[k] for k in keys}),inputs={k:inputs[k] for k in keys}) for name,keys in categories.items()}
        result=dict(day=day,status='PASS',classification=('CURRENT_V41R1_GENERATED_AND_CERTIFIED' if regenerated else
            'REUSED_BY_EXACT_INPUT_AND_METHOD_EQUIVALENCE'),certificate=record(certificate),
            Planning_electrical_coefficients=value['outputs']['planning_coefficients'],
            AC_anchor_voltage_sensitivity=value['outputs']['voltage'],current_sensitivity=value['outputs']['current'],
            transformer_coefficients=value['outputs']['transformer_coefficients'],
            authority_identities=identities,generation_source_SHA=inputs['V41_generation_source']['manifest_SHA'],
            generation_input_SHA=current['identity_SHA'],output_SHA={k:r['sha256'] for k,r in value['outputs'].items()},
            readback_validation=dict(status='PASS',method='v41.electrical.load: SHA256 plus exact coefficient-array equality',
                all_96_slots=True,current_day_bound=True),mapper_audit=value['mapper_audit'],
            mapper_zero_duplicate_group_slots=True,mapper_PQ_conservation='PASS',
            generated_this_audit=regenerated,prior_invalid_reason=previous_error,prior_preservation=str(archive) if archive else None,
            generation_attestation=value['generation_attestation'],Actual_used=False,Fresh_is_not_Planning_authority=True)
        write_json(RUNTIME/'coefficient_audit'/(day+'.json'),result)
        require(read(RUNTIME/'coefficient_audit'/(day+'.json'))==result,'COEFFICIENT_AUDIT_READBACK')
        return result
    finally:
        if context is not None:context.electrical.voltage.close();context.electrical.current.close()


def manifest():
    rows=[]
    for day in DAYS:
        path=RUNTIME/'coefficient_audit'/(day+'.json')
        if path.exists():
            value=read(path);rows.append(dict(day=day,status=value['status'],classification=value['classification'],audit=record(path)))
        else:rows.append(dict(day=day,status='FAIL',classification='MISSING/INVALID'))
    passed=sum(r['status']=='PASS' for r in rows)
    value=dict(status='PASS' if passed==31 else 'FAIL',PASS=passed,TOTAL=31,FAIL=31-passed,days=rows,
        classification_counts=dict(Counter(r['classification'] for r in rows)),
        historical_ready_not_assumed=True,Full_May_optimization_requires_31_of_31_PASS=True)
    write_json(OUT/'V41R1_31_DAY_PLANNING_COEFFICIENT_MANIFEST.json',value)
    return value


def verify_manifest():
    from dayahead.v41.electrical import identity,verify_generation_proof
    from dayahead.v41.persistence import verify_table
    path=OUT/'V41R1_31_DAY_PLANNING_COEFFICIENT_MANIFEST.json';value=read(path)
    require(value['status']=='PASS' and value['PASS']==value['TOTAL']==31 and value['FAIL']==0,'PLANNING_COEFFICIENTS_NOT_31_OF_31')
    require([r['day'] for r in value['days']]==list(DAYS),'COEFFICIENT_MANIFEST_DAY_SET')
    for row in value['days']:
        require(row['status']=='PASS' and row['classification'] in PASS_CLASSES,'COEFFICIENT_DAY_NOT_CERTIFIED')
        require(record(row['audit']['path'])==row['audit'],'COEFFICIENT_DAY_AUDIT_DRIFT')
        audit=read(row['audit']['path']);require(audit['day']==row['day'],'COEFFICIENT_AUDIT_WRONG_DAY')
        require(audit['status']=='PASS' and audit['classification']==row['classification'],'COEFFICIENT_AUDIT_STATUS_DRIFT')
        require(record(audit['certificate']['path'])==audit['certificate'],'COEFFICIENT_CERTIFICATE_DRIFT')
        cert=read(audit['certificate']['path']);verify_generation_proof(cert)
        current=identity(row['day'])
        require(cert['input_identity']==current,'COEFFICIENT_CURRENT_INPUT_METHOD_DRIFT')
        require(current['identity']['inputs']['day']==row['day'],'COEFFICIENT_CERTIFICATE_WRONG_DAY')
        require(audit['generation_input_SHA']==current['identity_SHA'] and audit['generation_source_SHA']==
            current['identity']['inputs']['V41_generation_source']['manifest_SHA'],'COEFFICIENT_GENERATION_IDENTITY_DRIFT')
        for ref in cert['outputs'].values():require(record(ref['path'])==ref,'COEFFICIENT_OUTPUT_HASH_DRIFT')
        require(audit['output_SHA']=={k:r['sha256'] for k,r in cert['outputs'].items()},'COEFFICIENT_OUTPUT_SET_DRIFT')
        require(audit['readback_validation']['status']=='PASS' and audit['readback_validation']['current_day_bound']
            and audit['readback_validation']['all_96_slots'],'COEFFICIENT_READBACK_NOT_CERTIFIED')
        require(audit['mapper_audit']==cert['mapper_audit']==record(cert['mapper_audit']['path']),'COEFFICIENT_MAPPER_AUDIT_DRIFT')
        mapper=read(cert['mapper_audit']['path']);frame=verify_table(mapper['rows'])
        require(mapper['target_day']==row['day'] and mapper['stage']=='Planning_GENERATION'
            and mapper['status']=='PASS' and mapper['slots']==96 and mapper['duplicated_group_slots']==0
            and not frame.duplication_detected.any() and max(mapper['P_max_error_kW'],mapper['Q_max_error_kvar'])<=mapper['tolerance'],
            'COEFFICIENT_MAPPER_NOT_VALID')
    return value


def batch(git,wait_for_ml=False):
    from dayahead.tools.v41_detached_launcher import provision_git
    provision_git(git)
    if wait_for_ml:
        while True:
            prep=read(RUNTIME/'BASELINE_PREPARATION_PROGRESS.json')
            if prep['status']=='PASS':break
            require(prep['status']=='RUNNING','CAUSAL_PREPARATION_FAILED_BEFORE_ELECTRICAL_GATE')
            time.sleep(5)
    state=dict(status='RUNNING',stage='PLANNING_ELECTRICAL_COEFFICIENTS',workers=4,days={},pid=os.getpid());lock=threading.RLock()
    def save():
        state['updated_at']=time.time();write_json(RUNTIME/'COEFFICIENT_PREPARATION_PROGRESS.json',state)
    def run(day):
        log=ROOT/'logs/v41r1_migration/coefficient_prepare'/(day+'.log');log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a',encoding='utf-8') as stream:
            proc=subprocess.Popen([sys.executable,'-u','-m','dayahead.v41r1.coefficient_prepare','--day',day],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)
            with lock:state['days'][day]=dict(status='RUNNING',pid=proc.pid,log=str(log));save()
            result=proc.wait()
        if result:
            audit_path=RUNTIME/'coefficient_audit'/(day+'.json')
            previous=read(audit_path) if audit_path.exists() else None
            write_json(audit_path,dict(day=day,status='FAIL',classification='MISSING/INVALID',
                failure_log=record(log),returncode=result,previous_audit=previous))
        with lock:state['days'][day].update(status='PASS' if result==0 else 'FAIL',returncode=result);save()
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,DAYS))
    value=manifest()
    with lock:state['status']='PASS' if not any(results) and value['status']=='PASS' else 'FAIL';save()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--day');p.add_argument('--git');p.add_argument('--wait-for-ml',action='store_true');a=p.parse_args()
    if a.day:print(certify(a.day)['classification'],flush=True)
    else:batch(a.git,a.wait_for_ml)
