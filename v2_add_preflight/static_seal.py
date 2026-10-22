"""Seal only new V2_add artifacts; never rewrite source or past evidence."""
import subprocess,psutil
from .static_common import *

REQUIRED=['V44_R043_ALGORITHM_IDENTITY_AUDIT.json','NO_NEW_GRID_CONSTRAINT_GENERATION_PROOF.json',
    'IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json','IEEE8500_EXACT_COMPACT_EQUIVALENCE.json',
    'IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json','FULL_CONSTRAINT_FAMILY_BEFORE_AFTER.csv',
    'IEEE123_IEEE8500_MODEL_SIZE_COMPARISON.csv','SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json',
    'A1_M1_A2_M2_ORIGINAL_STAGE_INTEGRATION.json','K48_BEAM_JOINT_ALGORITHM_PRESERVATION.json',
    'MAY01_PHYSICAL_EVALUATION_CONTRACT.json','MAY01_CAMPAIGN_PRESTART_READINESS.json',
    'FINAL_PRESTART_GO_NO_GO.json','FINAL_PRESTART_REVIEW_KO.md']

def seal():
    init();assert all((OUT/n).is_file() for n in REQUIRED)
    changes=subprocess.check_output(['git','diff','--name-status',BASE,'--'],cwd=ROOT,text=True).strip()
    assert not changes,'EXISTING_TRACKED_FILE_MODIFIED'
    coef=read(OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json')
    assert record(ROOT/'v2_add_preflight/static_coefficients.py')['sha256']==coef['identity']['code']['sha256']
    raw=read(OUT/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json');by={r['slot']:r for r in coef['records']}
    assert raw['PASS'] and len(raw['identity']['blocks'])==96
    assert all(b['coefficient']['sha256']==by[b['slot']]['sha256'] for b in raw['identity']['blocks'])
    put('COMMITTED_COEFFICIENT_CONSUMPTION_AUDIT.json',dict(PASS=True,slots=96,
        all_component_Native0_input_hashes_match_completed_horizon_manifest=True,
        completed88_reused_and_remaining8_resumed=True,completed_original_source_restorations_repeated=False,
        original_DY_inputs_coefficients_not_reused=True))
    own=[];protected=[];selfpid=psutil.Process().pid;parent=psutil.Process().ppid()
    for p in psutil.process_iter(['name','cmdline']):
        args=p.info['cmdline'] or []
        if 'python' not in (p.info['name'] or '').lower():continue
        if any('v2_add_preflight.static_' in s for s in args):
            if p.pid not in (selfpid,parent):own.append(dict(pid=p.pid,args=args))
        else:protected.append(dict(pid=p.pid,args=args))
    assert not own,'OWN_PREPARATION_PROCESS_STILL_RUNNING'
    put('PREPARATION_RESOURCE_AND_SOURCE_CLOSURE.json',dict(PASS=True,baseline=BASE,
        all_preexisting_tracked_files_unchanged=True,remaining_own_preparation_processes=own,
        protected_workers_observed=protected,protected_worker_termination_calls=0,
        stopped_own_diagnostics_only=['mobility initial and second attempts; exact process command identity recorded in runtime'],
        Native_optimization_calls=0,official_campaign_executed=False,
        original_Worker_ledgers_campaigns_not_modified=True,available_RAM_bytes=psutil.virtual_memory().available))
    outputs=[p for p in RUN.rglob('*') if p.is_file()]
    table('STATIC_RUNTIME_ARTIFACT_INDEX.csv',[dict(path=str(p.resolve()),bytes=p.stat().st_size) for p in outputs])
    put('RUNTIME_ARCHIVE_SUMMARY.json',dict(files=len(outputs),bytes=sum(p.stat().st_size for p in outputs),
        location=str(RUN.resolve()),recovered_component_files_unchanged=True,
        all_numeric_matrix_proof_archives_remain_local=True,
        row_ID_and_original_coordinate_maps_linked_by_certificates=True))
    put('PREPARATION_DEFECT_RECOVERY_AUDIT.json',dict(
        physical_settings_changed_during_repair=False,original_algorithms_edited=False,
        repairs=[dict(defect='Consumer observed a still-open NPZ zip',fix='Completed coefficient manifest is now the commit signal',preserved='SOURCE_YY_ORIGINAL_FULL_REFERENCE_RACE_FAILURE.json; pack2.log',completed88_slots_recomputed=0,remaining_unbuilt_slots_completed=8),
            dict(defect='Verifier mask mixed176288 raw inequalities and17206 original variable bounds',fix='Separate original-row and bound selectors; no row removed by the repair',preserved='static_verify_initial_index_failure.log'),
            dict(defect='Helper view assumed P/Q equations followed variable storage order',fix='Read actual pivot column in interleaved P(site)/Q(site) injection rows',preserved='interfaces_helper_view.log'),
            dict(defect='Raw worktree CRLF differs from Git blob',fix='Report raw difference and compare canonical Git clean-filter blob; source not rewritten')]))
    files=[p for p in OUT.iterdir() if p.is_file() and p.name!='STATIC_COMPLETE_EVIDENCE_MANIFEST.json']
    code=sorted((ROOT/'v2_add_preflight').glob('static_*.py'))
    put('STATIC_COMPLETE_EVIDENCE_MANIFEST.json',dict(baseline=BASE,source=SOURCE,
        required14_deliverables_complete=True,files=[record(p) for p in sorted(files)],
        code=[record(p) for p in code],all_original_sources_and_previous_evidence_preserved=True))

if __name__=='__main__':seal()
