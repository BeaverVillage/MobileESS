"""May-04-only first-improvement source and acceptance evidence."""
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
from dayahead.v41.execution import science
from dayahead.v41.reserve import require,lexicographic_compare
from .first_replay import OUT
from .flex_diagnostic import A0,B0
from .early_stop import VERSION,TOLERANCES,IMPROVEMENT_EPS,IMPROVEMENT_NOISE
from .early_gate import model_sha

ALLOWED={'dayahead/v40g/optimizer.py','dayahead/v40h/feedback.py',
    'dayahead/v41r1/bounded_solver.py','dayahead/v41r1/early_stop.py'}

def source_gate():
    from .fo_release import test_gate
    before=read(OUT/'PRESERVATION.json');old={r['relative_path']:r for r in before['source']['files']}
    checks=[]
    for ref in science()['files']:
        rel=ref['relative_path'];changed=ref['sha256']!=old[rel]['sha256']
        require(not changed or rel in ALLOWED,'FIRST_IMPROVEMENT_UNAUTHORIZED_SOURCE_CHANGE:'+rel)
        checks.append(dict(path=rel,changed=changed))
    tests=test_gate(OUT/'V4_REGRESSIONS.xml',195)
    regression=read(OUT/'FULL_MODEL_REGRESSIONS.json');require(regression['status']=='PASS','KNOWN_IMPROVEMENT_NOT_RECOVERED')
    for case in regression['results'].values():
        require(read(case['production_engine_report']['path'])['compute_control_version']==VERSION,'FULL_MODEL_REGRESSION_SOURCE_VERSION')
    require(read(OUT/'OLD_FO_MISSED_IMPROVEMENT_REPLAY.json')['status']=='PASS','HISTORICAL_REPLAY_REQUIRED')
    baseline=read(B0/'dayahead/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    seed=read(A0/'POLICY_FEASIBLE_SEED_AUDIT.json')['seed_objective_vector']
    observed=[abs(a-b) for a,b in zip(seed[:2],baseline[:2])]
    require(max(observed)<=1e-10,'BASELINE_NOISE_EXCEEDS_REGISTERED_ENVELOPE')
    contract=dict(status='FROZEN',compute_control_version=VERSION,
        policy_day_optimization_hard_cap_seconds=1800,discovery='CONSTANT_OBJECTIVE_IMPROVEMENT_FEASIBILITY',
        SolutionLimit=1,MIPFocus=1,percentage_gap_on_P1_P5=False,neighborhood_optimality_proof_required=False,
        validated_independent_baseline_noise=observed,registered_absolute_noise_envelope=1e-10,
        deterministic_safety_multipliers=[100,1000],absolute_improvement_eps=list(IMPROVEMENT_EPS),
        independent_improvement_noise_tolerance=list(IMPROVEMENT_NOISE),
        physical_feasibility_tolerance=1e-9,integrality_tolerance=1e-9,higher_priority_lock_tolerances=list(TOLERANCES),
        calibration_uses_improved_B1_outcomes=False,raw_candidate_coverage='AUDIT_ONLY',
        complete_destination_sets=True,candidate_pruning=0,permanent_cross_region_constraints=0,
        coupled_max_free_discrete=25000,normal_max_free_discrete=10000,
        full_may_on_hold=True,source=science(),tests=record(OUT/'V4_REGRESSIONS.xml'),
        full_model_regressions=record(OUT/'FULL_MODEL_REGRESSIONS.json'),
        solver_documentation=['https://docs.gurobi.com/projects/optimizer/en/current/concepts/modeling/objectives.html',
            'https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#solutionlimit'])
    for name in ('FIRST_IMPROVEMENT_COMPUTE_CONTRACT.json','FIRST_IMPROVEMENT_SOURCE_GATE.json'):
        path=OUT/name;preserved=OUT/'first01_source'/name
        if path.exists() and not preserved.exists():
            import shutil
            shutil.copyfile(path,preserved)
    contract['higher_priority_guard']='CURRENT_ACCEPTED_INCUMBENT: search cuts and post-validation prevent giving back incidental higher-priority gains'
    write_json(OUT/'FIRST_IMPROVEMENT_COMPUTE_CONTRACT.json',contract)
    gate=dict(status='PASS',source=science(),checks=checks,regression_count=tests,
        contract=record(OUT/'FIRST_IMPROVEMENT_COMPUTE_CONTRACT.json'),
        scientific_equivalence='Authority/model-builder equations unchanged; complete MPS and candidate hashes must additionally match at acceptance.')
    write_json(OUT/'FIRST_IMPROVEMENT_SOURCE_GATE.json',gate)
    return gate

def acceptance_checks(root,seed,compute,solver,candidates,coverage):
    gate=read(OUT/'FIRST_IMPROVEMENT_SOURCE_GATE.json');require(gate['source']==science(),'FIRST_IMPROVEMENT_SOURCE_DRIFT')
    new=Path(root)/'2025-05-04/B1/dayahead/A0';stages=solver['stages']
    require(model_sha(A0/'PRIMARY_MODEL.mps.gz')==model_sha(new/'PRIMARY_MODEL.mps.gz'),'ORIGINAL_FULL_MODEL_CHANGED')
    original=read(A0/'V41R1_FULL_CANDIDATE_MANIFEST.json')
    require(original['candidate_set_SHA']==candidates['candidate_set_SHA'],'COMPLETE_CANDIDATE_UNIVERSE_CHANGED')
    require(compute['optimization_seconds']<=1800,'ABSOLUTE_HARD_CAP_EXCEEDED')
    require(seed['status']=='PASS' and len(stages)==5,'SEED_OR_STAGES_FAILED')
    require(solver['compute_control_version']==compute['compute_control_version']==VERSION,'SEARCH_CONTRACT_VERSION')
    baseline=read(B0/'dayahead/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    require(lexicographic_compare(stages[-1]['accepted_objective_vector'],baseline,TOLERANCES)<0,'KNOWN_COUNTEREXAMPLE_EXISTS_BUT_B1_NOT_BETTER')
    known=read(OUT/'KNOWN_P2_REGRESSION.json');require(known['status']=='PASS','KNOWN_P2_NOT_RECOVERED')
    history=[read(f) for f in sorted((new/'bounded_checkpoints').glob('ITERATION_*.json'),key=lambda f:int(f.stem.split('_')[1]))]
    p1=[h for h in history if h['objective_stage']=='PRIMARY_MIN_RHO']
    require(p1 and p1[0]['neighborhood']['family']=='ELECTRICAL_CRITICAL_WINDOW','P1_NOT_CURRENT_CRITICAL_FIRST')
    require(any(h['neighborhood']['coupled_capacity_release_active'] for h in p1),'COUPLED_CAPACITY_RELEASE_MISSING')
    structures=[read(f) for f in (new/'bounded_checkpoints').glob('STRUCTURE_P1_SWEEP_*.json')]
    for h in p1:
        if h['accepted']:
            require(any(s['incumbent']==h['incumbent_after'] for s in structures),'P1_BOTTLENECK_NOT_RECOMPUTED')
    for h in history:
        require(not h['percentage_gap_on_P1_P5'] and h['first_improvement_search'],'GAP_STILL_CONTROLS_SEARCH')
        require(h['neighborhood']['complete_job_domains_opened'] and not h['neighborhood']['permanent_cross_region_constraint'],'DESTINATION_OR_REGION_RESTRICTION')
        if h['accepted']:
            from .early_stop import STAGES
            priority=STAGES[h['objective_stage']]
            require(all(h['incumbent_after'][k]<=h['incumbent_before'][k]+TOLERANCES[k] for k in range(priority)),
                'CURRENT_INCUMBENT_HIGHER_PRIORITY_REGRESSION')
            semantic=h['semantic_validation'];require(semantic['status']==semantic['canonical_model_substitution']['status']=='PASS','ACCEPTED_UNVERIFIED_PROPOSAL')
            require(semantic.get('persisted_jobs') and semantic.get('persisted_power'),'ACCEPTED_PROPOSAL_NOT_PERSISTED')
            for field in ('persisted_jobs','persisted_power'):require(record(semantic[field]['path'])==semantic[field],'PROPOSAL_READBACK_HASH_DRIFT')
    for i,s in enumerate(stages):
        require(s['feasibility']['status']=='PASS' and not s['percentage_gap_controls_discovery'],'STAGE_FEASIBILITY_OR_SEARCH')
        require(not s['raw_candidate_coverage_required_for_stopping'],'RAW_COVERAGE_STOP_PRECONDITION')
        if i:require(all(s['accepted_objective_vector'][k]<=stages[i-1]['accepted_objective_vector'][k]+TOLERANCES[k] for k in range(i)),'HIGHER_PRIORITY_DEGRADATION')
    recovery=None
    if (new/'RECOVERED_SEED_AUDIT.json').exists():
        recovery=read(new/'RECOVERED_SEED_AUDIT.json');require(recovery['status']=='PASS','RECOVERY_SEED_AUDIT')
        plan=read(recovery['plan']['path'])
        require(plan['parent_recorded_optimization_seconds']+plan['conservative_stop_allowance_seconds']+compute['optimization_seconds']<=1800,'COMBINED_RECOVERY_HARD_CAP')
    return dict(status='PASS',checks_A_through_O='PASS',compute_control_version=VERSION,source_gate=record(OUT/'FIRST_IMPROVEMENT_SOURCE_GATE.json'),
        recovery=recovery,
        known_P2_regression=record(OUT/'KNOWN_P2_REGRESSION.json'),original_full_model_SHA=model_sha(new/'PRIMARY_MODEL.mps.gz'),
        authoritative_candidate_SHA=candidates['candidate_set_SHA'],current_critical_recomputed_after_every_P1_acceptance=True,
        optimization_seconds=compute['optimization_seconds'],accepted_by_stage={s['stage_priority']:s['material_improvements'] for s in stages},
        rejected_proposals=stages[-1]['rejected_proposals'],Full_May_started=False,
        Fresh_Actual='Verified by unchanged phase receipts and full acceptance runner')

def compare(acceptance):
    # The completed production report is assembled with diagnostic results in
    # first_report; this receipt makes the new formal run self-contained.
    write_json(OUT/'ACCEPTANCE_POINTER.json',record(acceptance))

if __name__=='__main__':source_gate()
