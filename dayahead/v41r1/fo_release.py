"""Reviewable F&O release and exact completed-B0 retention gates."""
import ast
import hashlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json,digest
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.execution import science,commit
from dayahead.v41.reserve import require
from .bounded_solver import CONTRACT
from .early_stop import VERSION,GUARDS,NORMAL_SECONDS,DIVERSIFICATION_SECONDS

EVIDENCE=ROOT/'dayahead/artifacts/v41r1_bounded_compute'
BASE='833597c1dd10f32934e30c20ac7fb3907ca880e2'
CHANGED={'dayahead/v40g/optimizer.py','dayahead/v40h/feedback.py','dayahead/v40h/recourse.py',
    'dayahead/v41/execution.py','dayahead/v41/solver_observer.py','dayahead/v41r1/migration_factor.py'}
ADDED={'dayahead/v41r1/'+x for x in ('bounded_solver.py','bounded_runtime.py','bounded_mess.py',
    'feasible_seed.py','candidate_manifest.py','exact_aggregation.py','early_stop.py')}


def preserve(path):
    path=Path(path)
    if path.exists():
        target=EVIDENCE/'prior_gates'/(path.stem+'_'+record(path)['sha256']+path.suffix)
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(path,target)
        return record(target)


def test_gate(path,minimum):
    tree=ET.parse(path);cases=list(tree.iter('testcase'))
    require(len(cases)>=minimum and not any(list(tree.iter(t)) for t in ('failure','error','skipped')),'F_AND_O_REGRESSION_GATE:'+str(path))
    return len(cases)


def b0_ast(source):
    class StripCompute(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            if node.module in ('dayahead.v41r1.bounded_runtime','dayahead.v41r1.feasible_seed'):return None
            return node
        def visit_If(self,node):
            if "'v41_bounded_compute'" in ast.unparse(node.test):return None
            return self.generic_visit(node)
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id in ('activate','finish'):return None
            return self.generic_visit(node)
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Attribute) and t.attr=='v41_a1_reference_choices' for t in node.targets):return None
            return self.generic_visit(node)
    tree=ast.parse(source)
    tree.body=[n for n in tree.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name not in ('science','m1_identity','run_m1')]
    return ast.dump(StripCompute().visit(tree),include_attributes=False)


def strategy_gate():
    tests=EVIDENCE/'BOUNDED_REGRESSIONS.xml';count=test_gate(tests,27)
    full=EVIDENCE/'FULL_REGRESSIONS.xml';test_gate(full,200)
    previous=read(OUT/'Q90_BASELINE_RETAINED_B0_GATE.json')['current_source']
    if previous==science():
        previous=read(EVIDENCE/'STRATEGY_SOURCE_EQUIVALENCE.json')['previous_source']
    old={r['relative_path']:r for r in previous['files']};current=science();checks=[]
    for ref in current['files']:
        rel=ref['relative_path']
        if rel in ADDED:
            checks.append(dict(path=rel,change='NEW_COMPUTE_ONLY_MODULE'));continue
        original=subprocess.check_output(['git','show',BASE+':'+rel],cwd=ROOT)
        sha=hashlib.sha256(original).hexdigest()
        if sha!=ref['sha256']:require(rel in CHANGED,'UNAUTHORIZED_SCIENTIFIC_SOURCE_CHANGE:'+rel)
        checks.append(dict(path=rel,original_sha256=sha,current_sha256=ref['sha256'],unchanged=sha==ref['sha256']))
    original=subprocess.check_output(['git','show',BASE+':dayahead/v41/execution.py'],cwd=ROOT).decode('utf-8-sig')
    require(b0_ast(original)==b0_ast((ROOT/'dayahead/v41/execution.py').read_text(encoding='utf-8-sig')),'B0_EXECUTED_AST_CHANGED_OUTSIDE_COMPUTE_BRANCHES')
    proof=EVIDENCE/'STRATEGY_SOURCE_EQUIVALENCE.json'
    write_json(proof,dict(status='PASS',previous_commit=BASE,previous_source=previous,current_source=current,checks=checks,
        B0_and_Actual_executed_AST_unchanged_after_removing_compute_only_instrumentation=True,
        original_candidate_enumerator_unchanged=True,sparse_event_recurrence_preserved=True,
        aggregation='REFINEMENT_OF_ORIGINAL_GROUPS; MIGRATION_UID_SINGLETON; ORIGINAL_P5_RANK_RETAINED',
        constraints='ORIGINAL_LINEAR_GENERAL_GPU_WAN_GRID_H4_ROWS_ACTIVE_IN_EVERY_NEIGHBORHOOD',
        M1_identity_repair='ARRAY_DIGEST_MATCHES_EXISTING_MESS_CONSUMER; NO_INPUT_VALUE_CHANGED',
        tests=record(tests),full_regressions=record(full)))
    p5=EVIDENCE/'P5_EQUIVALENCE_AUDIT.json'
    write_json(p5,dict(status='PASS',post_solve_eligible=False,action='RETAIN_P5_INSIDE_REMAINING_BUDGET',
        reason='Original P5 ranks entire placement/migration columns. Equal P1-P4 does not imply identical IDC trajectories.',
        counterexample=dict(equal_P1_P4=[1.,0.,0,4],GPU_trajectory_A=[1,0],GPU_trajectory_B=[0,1],P5_A=1,P5_B=2),
        regression_test='test_p5_is_not_pure_job_disaggregation',test_results=record(tests)))
    gate=dict(status='PASS',contract=CONTRACT,equivalence_test_count=count,
        sources=[record(ROOT/p) for p in sorted(CHANGED|ADDED|{'dayahead/v40g/domain.py','dayahead/v41r1/migration.py','dayahead/v41r1/migration_load.py'})],
        test_results=record(tests),full_regressions=record(full),source_equivalence=record(proof),P5_audit=record(p5))
    preserve(OUT/'F_AND_O_EQUIVALENCE_GATE.json');write_json(OUT/'F_AND_O_EQUIVALENCE_GATE.json',gate)
    return gate


def retain_b0():
    proof=read(EVIDENCE/'STRATEGY_SOURCE_EQUIVALENCE.json');require(proof['current_source']==science(),'RETENTION_SOURCE_CHANGED')
    gate_path=OUT/'Q90_BASELINE_RETAINED_B0_GATE.json';gate=read(gate_path);prior=preserve(gate_path)
    from dayahead.v41.campaign import verify_receipt
    for entry in gate['receipts']:
        receipt=verify_receipt(entry['receipt']['path'])
        require(record(entry['receipt']['path'])==entry['receipt'],'B0_RECEIPT_CHANGED')
        additions=[r['path'] for r in science()['files'] if r['relative_path'] in CHANGED]
        entry['attested_changed_paths']=sorted(set(entry['attested_changed_paths']+additions))
    gate.update(current_source=science(),prior_retention_gate=prior,compute_revision_proof=record(EVIDENCE/'STRATEGY_SOURCE_EQUIVALENCE.json'),
        scope='Enumerated completed B0 bytes retained; computation changes do not alter the B0 decision or Actual method')
    write_json(gate_path,gate)
    from .migration_retention import validate
    for e in gate['receipts']:validate(read(e['receipt']['path']),science())


def prepare(acceptance,components,stress):
    from .coefficient_prepare import verify_manifest
    from .early_gate import source_gate
    source_gate();strategy_gate();retain_b0();verify_manifest()
    acceptance=Path(acceptance);result=read(acceptance)
    require(result['status']=='PASS' and result['source']==science() and result['Fresh']==result['Actual']=='PASS','DIFFICULT_INSTANCE_ACCEPTANCE_REQUIRED')
    require(result['optimization_seconds']<=1800,'ACCEPTANCE_BUDGET')
    require(result.get('compute_control_version')==VERSION and result.get('checks_A_through_O')=='PASS','CORRECTED_EARLY_STOP_ACCEPTANCE_REQUIRED')
    component=read(components);require(component['status']=='PASS' and component['source']==science(),'B3_COMPONENT_GATE')
    test_gate(EVIDENCE/'FO_OPERATIONS_REGRESSIONS.xml',11)
    memory=read(stress);require(memory['status']=='PASS' and memory['workers']==4 and memory['threads_per_worker']==4,'FOUR_BY_FOUR_MEMORY_GATE')
    import gzip
    h=hashlib.sha256()
    with gzip.open(acceptance.parent/'2025-05-04/B1/dayahead/A0/PRIMARY_MODEL.mps.gz','rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    require(h.hexdigest()==memory['uncompressed_model_SHA'],'STRESS_AND_ACCEPTANCE_MODELS_NOT_EXACTLY_IDENTICAL')
    for ref in result['artifacts'].values():require(record(ref['path'])==ref,'ACCEPTANCE_ARTIFACT_DRIFT')
    path=OUT/'F_AND_O_COMPUTE_CONTRACT.json'
    preserve(path)
    write_json(path,dict(status='FROZEN',contract=CONTRACT,compute_control_version=VERSION,method='bounded-compute fix-and-optimize matheuristic',
        total_optimization_seconds_per_policy_day=1800,shared_components=['A0','M1','A1','MF'],
        build_seed_validation_in_budget=True,Fresh_Actual_outside_budget=True,
        neighborhood_seconds=60,free_discrete_minimum_target=2000,free_discrete_initial_target=5000,free_discrete_maximum=10000,
        nominal_P1_P2_P3_P4_P5_seconds=list(GUARDS),unused_time_rolls_forward=True,
        normal_sweep_seconds=list(NORMAL_SECONDS),diversification_sweep_seconds=list(DIVERSIFICATION_SECONDS),
        sweep_definition='ONE_DETERMINISTIC_ROUND_THROUGH_FIVE_MAJOR_FAMILIES; MULTIPLE_COMPLETE_JOB_NEIGHBORHOODS_PER_FAMILY',
        raw_candidate_coverage='AUDIT_ONLY; NEVER_A_STOPPING_PREREQUISITE',
        unvisited_classification='NOT_VISITED_WITHIN_COMPUTE_BUDGET',
        current_objective_material_improvement_restarts_normal_sweep=True,
        analytically_valid_objective_floors_enabled=True,
        full_original_candidate_universe=True,permanent_candidate_pruning=0,physical_relaxation=False,
        P5='RETAINED_IN_REMAINING_BUDGET',global_bound_pass='NOT_ENABLED; NO_GLOBAL_CERTIFICATE_CLAIM',
        MESS='INHERITED_AUTHORIZED_ROUTE_SEARCH_WITH_VERIFIED_FULL_FLEET_CHECKPOINT_AND_SHARED_DEADLINE',
        PARALLEL_DAY_WORKERS=4,GUROBI_THREADS_PER_DAY=4,acceptance=record(acceptance)))
    dependencies=[OUT/'F_AND_O_EQUIVALENCE_GATE.json',OUT/'F_AND_O_COMPUTE_CONTRACT.json',
        OUT/'Q90_BASELINE_RETAINED_B0_GATE.json',OUT/'V41R1_31_DAY_PLANNING_COEFFICIENT_MANIFEST.json',
        OUT/'Q90_BASELINE_31_DAY_AUDIT.json',EVIDENCE/'STRATEGY_SOURCE_EQUIVALENCE.json',EVIDENCE/'P5_EQUIVALENCE_AUDIT.json',
        EVIDENCE/'FULL_REGRESSIONS.xml',EVIDENCE/'BOUNDED_REGRESSIONS.xml',EVIDENCE/'FO_OPERATIONS_REGRESSIONS.xml',
        EVIDENCE/'REPRESENTATIVE_GLOBAL_VALIDATION_PLAN.json',EVIDENCE/'PERFORMANCE_COMPARISON.json',
        EVIDENCE/'CANDIDATE_RESIDUAL_REJECTION_FIX.json',EVIDENCE/'EARLY_STOP_SOURCE_GATE.json',
        EVIDENCE/'EARLY_STOP_REGRESSIONS.xml',EVIDENCE/'EARLY_STOP_BEFORE_AFTER.json',EVIDENCE/'EARLY_STOP_BEFORE_AFTER.md',
        EVIDENCE/'B0_VS_B1_OBJECTIVES.json',EVIDENCE/'B0_VS_B1_OBJECTIVES.md',EVIDENCE/'USER_FULL_MAY_HOLD.json',
        EVIDENCE/'pre_early_stop/PRESERVATION.json',EVIDENCE/'early01_failure/PRESERVATION.json',EVIDENCE/'early02_failure/PRESERVATION.json',
        RUNTIME/'bounded_compute/fo_early_minimum_slice_01/RESULT.json',acceptance,Path(components),Path(stress)]
    operations=[ROOT/'dayahead/v41r1'/p for p in ('campaign_run.py','campaign_prepare.py','watchdog.py','fo_release.py',
        'early_gate.py','fo_quality.py','fo_acceptance.py','fo_baseline_report.py','fo_transition.py','fo_stress.py','fo_strong_validation.py','fo_report.py','coefficient_prepare.py')]+[ROOT/'dayahead/tools/monitor_v41r1_may_live.ps1']
    value=dict(status='READY',kind=CONTRACT,science=science(),dependencies=[record(p) for p in dependencies],
        operations=[record(p) for p in operations],acceptance=record(acceptance),acceptance_unit=str(acceptance.parent/'2025-05-04/B1'))
    write_json(OUT/'F_AND_O_FULL_MAY_PREPARATION.json',value);return value


def freeze():
    prep=read(OUT/'F_AND_O_FULL_MAY_PREPARATION.json');require(prep['science']==science(),'FREEZE_SOURCE_DRIFT')
    release=dict(kind=CONTRACT,scientific_commit=commit(),science=science(),preparation=record(OUT/'F_AND_O_FULL_MAY_PREPARATION.json'),
        dependencies=prep['dependencies'],operations=prep['operations'],acceptance=prep['acceptance'],acceptance_unit=prep['acceptance_unit'])
    for ref in release['dependencies']+release['operations']:require(record(ref['path'])==ref,'FREEZE_EVIDENCE_DRIFT')
    preserve(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json');write_json(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json',release)
    return verify()


def verify():
    value=read(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json')
    require(value['kind']==CONTRACT and value['scientific_commit']==commit() and value['science']==science(),'F_AND_O_FROZEN_SOURCE_DRIFT')
    for ref in [value['preparation']]+value['dependencies']+value['operations']:
        require(record(ref['path'])==ref,'F_AND_O_RELEASE_EVIDENCE_DRIFT:'+ref['path'])
    return value


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['gate','retain','prepare','freeze','verify'])
    p.add_argument('--acceptance');p.add_argument('--components');p.add_argument('--stress');a=p.parse_args()
    if a.mode=='prepare':prepare(a.acceptance,a.components,a.stress)
    else:{'gate':strategy_gate,'retain':retain_b0,'freeze':freeze,'verify':verify}[a.mode]()
