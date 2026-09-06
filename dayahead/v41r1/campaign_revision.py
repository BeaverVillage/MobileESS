"""Evidence-bound transition preserving completed B0 across the Q90 baseline repair."""
import ast,hashlib,subprocess,types
import xml.etree.ElementTree as ET
import numpy as np
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.reserve import require
from dayahead.v41.execution import science,commit

PREVIOUS='e7fc82cce415d36f524cf5db80e31d244c8e7698'
ALLOWED_CHANGED={'dayahead/v40g/optimizer.py','dayahead/v41/common.py','dayahead/v41/execution.py',
    'dayahead/v41/retention.py','dayahead/v41/solver_observer.py','dayahead/v40a/feedback.py',
    'dayahead/v40h/feedback.py','dayahead/v41r1/migration_factor.py','dayahead/v41r1/migration_retention.py',
    'dayahead/v40g/domain.py','dayahead/v40g_segments/canonical.py','dayahead/v41r1/migration.py'}


def old_blob(producer,relative):
    return subprocess.check_output(['git','show',producer+':'+relative],cwd=ROOT)


def model_build_parts(source):
    text=source.decode('utf-8-sig').replace('\r\n','\n')
    prefix=text[text.index('def solve('):text.index('    def optimize(label):')]
    builder=text[text.index('    try:\n        variables='):text.index("        pstage=optimize('PRIMARY_MIN_RHO')")]
    return dict(initialization_SHA=hashlib.sha256(prefix.encode()).hexdigest(),
        model_builder_SHA=hashlib.sha256(builder.encode()).hexdigest())


def refresh_exact_gate():
    path=OUT/'EXACT_COMPRESSION_GATE.json';previous=read(path)
    tree=ET.parse(OUT/'V41_TEST_RESULTS.xml');cases=list(tree.iter('testcase'))
    require(len(cases)>=253 and not any(list(tree.iter(t)) for t in ('failure','error','skipped')),'REVISION_REGRESSION_NOT_PASS')
    selected=[c for c in cases if c.attrib['classname']=='tests.dayahead.test_v41r1_compression'
        or c.attrib['name']=='test_explicit_recurrence_and_feedback_keep_backlog_out_of_physical_model']
    require(len(selected)==12,'REVISION_EXACT_EQUIVALENCE_CASES_MISSING')
    stress=read(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json')
    require(stress['status']=='PASS' and stress['source']==science(),'CURRENT_FULL_MODEL_MEASUREMENT_MISSING')
    structure=stress['workers'][0]['model'];model=read(structure['path'])
    require(model['domain_counts']['options']==previous['full_explicit_candidate_combinations']==4251141,
        'REPRESENTATIVE_EXPLICIT_DOMAIN_CHANGED')
    require(model['matrix_nonzeros']==previous['matrix_nonzeros']==6838619,'REPRESENTATIVE_MATRIX_CHANGED')
    write_json(RUNTIME/'rev/gap01/EXACT_GATE_BEFORE_REFRESH.json',previous)
    paths={r['path'] for r in previous['sources']}|{r['path'] for r in science()['files']}
    paths|={str(ROOT/'tests/dayahead'/f'test_v41r1_{n}.py') for n in ('admission','baseline','gap_and_b3','preparation')}
    result={**previous,'status':'PASS','sources':[record(p) for p in sorted(paths)],
        'test_results':record(OUT/'V41_TEST_RESULTS.xml'),'tests':[c.attrib['name'] for c in selected],
        'equivalence_test_count':len(selected),'model_structure':structure,
        'current_four_worker_measurement':record(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json'),
        'full_regression_case_count':len(cases),'frozen_unadmitted_jobs':'Full service backlog; no physical segments, placement or migration',
        'P1_P2_termination_gap':.001,'P3_P5_termination_gap':0.,
        'baseline_31_day_audit':record(OUT/'Q90_BASELINE_31_DAY_AUDIT.json')}
    write_json(path,result)
    from dayahead.v41r1.migration_factor import verify_gate
    verify_gate()
    return result


def canonical_reuse_check(producer,jobs,sites):
    from dayahead.v40g_segments import canonical
    from dayahead.v41.retention import unchanged_nodes
    from dayahead.v41r1.migration_admission import overlapping_backlog,unadmitted
    old=old_blob(producer,'dayahead/v40g_segments/canonical.py').decode('utf-8-sig')
    current=(ROOT/'dayahead/v40g_segments/canonical.py').read_text(encoding='utf-8-sig')
    require(unchanged_nodes(old,{'occupancy','terminal'})==unchanged_nodes(current,{'occupancy','terminal'}),
        'B0_CANONICAL_UNATTESTED_FUNCTION_CHANGE')
    require(not any(overlapping_backlog(r) for r in jobs),'RETAINED_B0_NEW_BACKLOG_BRANCH_ACTIVE')
    module=types.ModuleType('old_canonical');exec(compile(old,'<original canonical>','exec'),module.__dict__)
    before=module.import_frozen(jobs);after=canonical.import_frozen(jobs)
    require(before==after and module.identities(before)==canonical.identities(after),'B0_CANONICAL_DECISION_CHANGED')
    left=module.occupancy(before,sites);right=canonical.occupancy(after,sites)
    require(np.array_equal(left[0],right[0]) and left[1]==right[1],'B0_CANONICAL_OCCUPANCY_CHANGED')
    require([module.terminal(r) for r in before]==[canonical.terminal(r) for r in after],'B0_CANONICAL_TERMINAL_CHANGED')
    return dict(status='PASS',job_count=len(jobs),new_backlog_branch_active=False,
        unadmitted_jobs_outside_Day_D=sum(unadmitted(r) for r in jobs),
        original_and_current_canonical_decisions_equal=True,all_96_slot_occupancy_equal=True,
        terminal_ledger_equal=True,unchanged_other_canonical_function_AST=True)


def create_evidence():
    from dayahead.v41.campaign import verify_receipt
    from dayahead.v41.retention import unchanged_nodes
    from dayahead.v41.snapshot import capacity_authority
    sites=capacity_authority()[0].aidc_ids
    current=science();audit_path=OUT/'Q90_BASELINE_31_DAY_AUDIT.json';audit=read(audit_path)
    require(audit['status']=='PASS' and audit['verified_days']==31,'BASELINE_AUDIT_NOT_COMPLETE')
    checks=[];entries=[]
    sources=[RUNTIME/'pilot/2025-05-01/B0/dayahead/DAYAHEAD_RECEIPT.json',
        RUNTIME/'pilot/2025-05-01/B0/actual/ACTUAL_RECEIPT.json',
        RUNTIME/'2025-05-02/B0/dayahead/DAYAHEAD_RECEIPT.json',
        RUNTIME/'2025-05-04/B0/dayahead/DAYAHEAD_RECEIPT.json']
    for path in sources:
        receipt=verify_receipt(path,None);day=receipt['day'];changed=[]
        for ref in receipt['science']['files']:
            rel=ref['relative_path'];original=old_blob(receipt['scientific_commit'],rel)
            require(hashlib.sha256(original).hexdigest()==ref['sha256'],'B0_SOURCE_GIT_PROVENANCE')
            if record(ref['path'])['sha256']==ref['sha256']:continue
            require(rel in ALLOWED_CHANGED,'B0_EXECUTED_METHOD_CHANGED:'+rel)
            if rel=='dayahead/v41/execution.py':
                updated=Path(ref['path']).read_text(encoding='utf-8-sig')
                branch='from .persistence import optimizer_rows\n    from dayahead.v41r1.migration_persistence import pre_solve'
                require(updated.count(branch)==1,'B0_PERSISTENCE_ENTRYPOINT_SHAPE_CHANGED')
                updated=updated.replace(branch,'from .persistence import pre_solve, optimizer_rows')
                require(unchanged_nodes(original.decode('utf-8-sig'),{'science'})==
                    unchanged_nodes(updated,{'science'}),'B0_EXECUTION_BODY_CHANGED')
            changed.append(str(Path(ref['path']).resolve()))
        folder=RUNTIME/'inputs'/day
        old=record(folder/'common/COMMON_B0_REFERENCE_JOBS.json');new=record(folder/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')
        require(old['sha256']==new['sha256'] and old['bytes']==new['bytes'],'COMPLETED_B0_REFERENCE_CHANGED:'+day)
        old_common=read(folder/'common/COMMON_INPUT_RECEIPT.json');new_common=read(folder/'common_q90_v3/COMMON_INPUT_RECEIPT.json')
        require(old_common['snapshot']==new_common['snapshot'] and old_common['COMMON_DA_DURATION_SHA']==new_common['COMMON_DA_DURATION_SHA'],
            'COMPLETED_B0_SERVICE_OR_ML_CHANGED')
        require(bool(read(new_common['snapshot']['path'])['PENDING_JOB_Q90_SECONDS']),
            'RETAINED_B0_EMPTY_RUNTIME_BRANCH_ACTIVE')
        proof=next(r for r in audit['days'] if r['day']==day)
        require(proof['status']=='PASS' and proof['changed_start_jobs']==0,'B0_RETENTION_CHANGED_START')
        canonical_check=canonical_reuse_check(receipt['scientific_commit'],read(new['path']),sites)
        entries.append(dict(day=day,phase=path.parent.name,receipt=record(path),old_reference=old,new_reference=new,
            attested_changed_paths=changed,input_equality_evidence=[record(folder/'common/COMMON_INPUT_RECEIPT.json'),
                record(folder/'common_q90_v3/COMMON_INPUT_RECEIPT.json')]))
        checks.append(dict(receipt=record(path),day=day,unchanged_reference_bytes=True,unchanged_ML=True,
            unchanged_B0_execution_body=True,original_git_blobs_verified=True,artifact_manifest_verified=True,
            canonical_readback_equivalence=canonical_check))
    builder=model_build_parts((ROOT/'dayahead/v40g/optimizer.py').read_bytes())
    stress=read(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json')
    require(stress['status']=='PASS' and stress['source']==current,'CURRENT_SOURCE_FOUR_WORKER_STRESS_REQUIRED')
    proof_path=OUT/'Q90_REVISION_SOURCE_EQUIVALENCE.json'
    write_json(proof_path,dict(status='PASS',current_source=current,checks=checks,model_build=builder,
        old_commit=PREVIOUS,baseline_change_scope='Prospective common first-fit queue; byte-identical completed B0 inputs proven per receipt',
        B1_B3_change_scope='P1/P2 0.1% bound; current A1 candidate guard; existing frozen non-admission remains full backlog',
        Actual_electrical_and_dispatch_methods_changed=False,
        canonical_change_scope='Skip physical occupancy for frozen UNASSIGNED; full backlog for Q90 ledger overlap; inactive on retained B0'))
    write_json(OUT/'Q90_BASELINE_RETAINED_B0_GATE.json',dict(status='PASS',current_source=current,receipts=entries,
        audit=record(audit_path),proof=record(proof_path),no_recertification_of_old_generation=True,
        original_producer_commits_preserved=True,scope='Only enumerated byte-identical B0 phases'))
    write_json(OUT/'Q90_REVISION_STRESS_REUSE.json',dict(status='PASS',current_source=current,
        measurement=record(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json'),proof=record(proof_path),
        measured_source=stress['source'],fresh_measurement=True,
        exact_same_representative_reference=entries[0]['new_reference'],model_build=builder,
        reason='New four-worker measurement of the final scientific source; previous measurement preserved separately'))


def verify_stress_reuse(stress,current_source):
    require(stress['status']=='PASS','FOUR_WORKER_STRESS_NOT_PASS')
    proof=read(OUT/'Q90_REVISION_STRESS_REUSE.json')
    require(proof['status']=='PASS' and proof['current_source']==current_source,'STRESS_REUSE_SOURCE_DRIFT')
    for key in ('measurement','proof','exact_same_representative_reference'):
        require(record(proof[key]['path'])==proof[key],'STRESS_REUSE_EVIDENCE_DRIFT')
    require(proof['measured_source']==stress['source'],'STRESS_ORIGINAL_MEASUREMENT_DRIFT')
    require(proof['model_build']==model_build_parts((ROOT/'dayahead/v40g/optimizer.py').read_bytes()),'STRESS_MODEL_BUILDER_DRIFT')


def transition_state():
    from .campaign_prepare import verify_release
    from .campaign_run import verify_phase
    frozen=verify_release();path=RUNTIME/'campaign_state.json';state=read(path)
    require(state['scientific_commit']==PREVIOUS,'UNEXPECTED_PRIOR_CAMPAIGN_COMMIT')
    require(state['status']=='PAUSED_FOR_AUTHORIZED_REVISION','CAMPAIGN_NOT_PAUSED_FOR_REVISION')
    write_json(RUNTIME/'rev/gap01/STATE_BEFORE_FINAL_TRANSITION.json',state)
    for row in state['units'].values():
        for key in ('dayahead_receipt','actual_receipt'):
            if row.get(key):verify_phase(row[key]['path'],frozen)
        if row['status']=='FAILED':
            require(row['day']=='2025-05-03' and row['policy']=='B0','UNREVIEWED_FAILED_UNIT')
            row['superseded_failure']=dict(error=row.pop('error'),classification='OLD_B0_REFERENCE_INCOMPATIBLE_WITH_FINAL_Q90_RUNTIME',
                audit=record(OUT/'Q90_BASELINE_31_DAY_AUDIT.json'))
            row.update(status='PENDING',worker_pid=None,phase=None)
    state.update(scientific_commit=frozen['scientific_commit'],status='READY_AFTER_AUTHORIZED_REVISION',
        prior_scientific_commit=PREVIOUS,revision_proof=record(OUT/'Q90_REVISION_SOURCE_EQUIVALENCE.json'))
    write_json(path,state)


if __name__=='__main__':
    import sys
    {'exact-gate':refresh_exact_gate,'evidence':create_evidence,'transition':transition_state}[sys.argv[1]]()
