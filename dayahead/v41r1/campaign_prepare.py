"""Current-code release evidence under the explicit separate-pilot waiver."""
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.reserve import require
from dayahead.v41.execution import science,commit


def p0_gate():
    from dayahead.v41.legacy_p0 import ITEMS
    from dayahead.v41.scientific_archive import verify_manifest
    from dayahead.v41.persistence import verify_table
    from dayahead.v41.electrical import verify_generation_proof
    xml=OUT/'V41_TEST_RESULTS.xml';tree=ET.parse(xml);cases=list(tree.iter('testcase'))
    require(len(cases)>=221 and not any(list(tree.iter(t)) for t in ('failure','error','skipped')),'FULL_REGRESSION_GATE')
    unit=RUNTIME/'pilot/2025-05-01/B0';verify_manifest(unit/'UNIT_SCIENTIFIC_MANIFEST.json')
    from dayahead.v41r1.migration_retention import validate
    for phase in ('dayahead','actual'):validate(read(unit/phase/(phase.upper()+'_RECEIPT.json')),science())
    electric=RUNTIME/'e/20250501/V41_ELECTRICAL_CERTIFICATE.json';verify_generation_proof(read(electric))
    mapper=[]
    for path in (electric.parent/'mapper_audit/MAPPER_AUDIT.json',
                 unit/'dayahead/audit/mapper/MAPPER_AUDIT.json',unit/'actual/audit/mapper/MAPPER_AUDIT.json'):
        value=read(path);frame=verify_table(value['rows'])
        require(value['status']=='PASS' and value['slots']==96 and value['duplicated_group_slots']==0
            and max(value['P_max_error_kW'],value['Q_max_error_kvar'])<=value['tolerance']
            and not frame.duplication_detected.any(),'CORRECTED_MAPPER_GATE')
        mapper.append(dict(artifact=record(path),status='PASS',group_slots=len(frame),
            P_max_error_kW=value['P_max_error_kW'],Q_max_error_kvar=value['Q_max_error_kvar']))
    rows=[]
    for key,spec in ITEMS.items():
        tests=[]
        for name in spec['tests']:
            matching=[c for c in cases if c.attrib['name'].split('[',1)[0]==name]
            require(bool(matching),'LEGACY_P0_TEST_MISSING:'+name)
            tests.append(dict(test=name,status='PASS',cases=len(matching),junit=record(xml)))
        rows.append(dict(item=key,original_defect=spec['original_defect'],
            current_implementation_path=spec['paths'],exact_fix=spec['exact_fix'],regression_test=tests,
            artifact_hash_evidence=[record(ROOT/p) for p in spec['paths']]+[record(electric),record(unit/'UNIT_SCIENTIFIC_MANIFEST.json')],
            status='PASS',affected_policy_stage=spec['scope']))
    path=OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json'
    if path.exists():
        prior=OUT/'LEGACY_P0_HISTORY'/f'{record(path)["sha256"]}.json';prior.parent.mkdir(exist_ok=True)
        if not prior.exists():shutil.copyfile(path,prior)
    result=dict(status='PASS',PASS=7,FAIL=0,items=rows,source_manifest=science(),
        scope='PRE_EXECUTION_CURRENT_CODE_AND_REGRESSION_CLOSURE',historical_status_not_assumed_as_closure=True,
        background_duplication=dict(status='PASS',evidence=mapper,
            Planning_Fresh_Actual_96_slot_readback=True,old_mapper_unreachable_regression='test_corrected_mapper_never_forwards_native_loads_to_duplicated_branch'),
        May1_B0_B1_boundary_revalidated=False,separate_May1_pilot='WAIVED_BY_LATEST_USER',
        B1_scientific_outcome='NOT_YET_COMPUTED; full campaign must satisfy the normal phase gates',
        waiver=record(OUT/'USER_SKIP_PILOT_REMOVE_MEMORY_CAP.json'))
    write_json(path,result);return result


def prepare():
    from dayahead.v41r1.migration_factor import verify_gate
    from dayahead.v41.release import plan
    verify_gate();p0_gate();plan()
    runtime_tests=ET.parse(OUT/'CAMPAIGN_RUNTIME_TESTS.xml')
    require(len(list(runtime_tests.iter('testcase')))==5 and not any(list(runtime_tests.iter(t)) for t in ('failure','error','skipped')),'CAMPAIGN_RUNTIME_REGRESSION_GATE')
    stress=read(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json')
    from .campaign_revision import verify_stress_reuse
    verify_stress_reuse(stress,science())
    require(stress['paging_counters_available'],'PAGING_MEASUREMENT_MISSING')
    baseline=read(OUT/'Q90_BASELINE_31_DAY_AUDIT.json')
    require(baseline['status']=='PASS' and baseline['verified_days']==31 and baseline['failed_days']==0,'Q90_BASELINE_31_DAY_GATE')
    from .coefficient_prepare import verify_manifest as verify_coefficients
    verify_coefficients()
    operations=[record(Path(__file__)),record(ROOT/'dayahead/v41r1/campaign_run.py'),
                record(ROOT/'dayahead/v41r1/campaign_resources.py'),record(ROOT/'dayahead/v41r1/campaign_revision.py'),
                record(ROOT/'dayahead/v41r1/gap03_revision.py'),record(ROOT/'dayahead/v41r1/watchdog.py'),
                record(ROOT/'dayahead/v41r1/baseline_audit.py'),record(ROOT/'dayahead/v41r1/coefficient_prepare.py')]
    config=dict(PARALLEL_DAY_WORKERS=4,SOLVER_THREADS_PER_DAY=4,adaptive_parallelism=False,
        A0_Method=1,MemLimit='UNLIMITED',SoftMemLimit='UNLIMITED',NodefileStart_GB=.5,
        NodefileDir='Per worker under the local SSD campaign workspace',
        B1_A0_MIPGap={'P1':.03,'P2':.03,'P3':0.,'P4':0.,'P5':0.},
        B3_A1_MIPGap={'P1':.03,'P2':.03,'P4':0.,'P5':0.},
        A0_MIPGapAbs=0,A0_FeasibilityTol=1e-9,A0_IntFeasTol=1e-9,A0_OptimalityTol=1e-9,
        all_other_stage_objective_and_optimality_requirements='UNCHANGED',
        one_model_for_P1_P5=True,work_limit_exhaustion='B1/B3 P1/P2 CONTINUE_IDENTICAL_MODEL_UNTIL_REGISTERED_GAP_CERTIFICATE',
        candidate_pruning=False,Actual_optimization=False,independent_days=True,
        policy_order=['B0','B1','B2','B3'],target_days=31,policy_days=124,
        separate_May1_pilot='CANCELLED_BY_USER',completed_May1_B0='RETAINED_BYTE_IDENTICAL')
    write_json(OUT/'FIXED_FOUR_WORKER_SOLVER_CONFIGURATION.json',config)
    value=dict(status='READY',source=science(),operations=operations,
        test_results=record(OUT/'V41_TEST_RESULTS.xml'),exact_equivalence=record(OUT/'EXACT_COMPRESSION_GATE.json'),
        legacy_P0=record(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json'),
        stress=record(OUT/'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json'),
        stress_reuse=record(OUT/'Q90_REVISION_STRESS_REUSE.json'),
        baseline=record(OUT/'Q90_BASELINE_31_DAY_AUDIT.json'),baseline_retention=record(OUT/'Q90_BASELINE_RETAINED_B0_GATE.json'),
        gap_authorization=record(OUT/'USER_APPROVED_B1_B3_GAP_3PCT.json'),
        electrical_coefficients=record(OUT/'V41R1_31_DAY_PLANNING_COEFFICIENT_MANIFEST.json'),
        configuration=record(OUT/'FIXED_FOUR_WORKER_SOLVER_CONFIGURATION.json'),
        runtime_tests=record(OUT/'CAMPAIGN_RUNTIME_TESTS.xml'),
        input_plan=record(OUT/'V41_MAY_CAMPAIGN_PLAN.csv'),
        separate_pilot_waiver=record(OUT/'USER_SKIP_PILOT_REMOVE_MEMORY_CAP.json'),
        monitor_path=str(RUNTIME/'campaign_progress.json'),heartbeat_path=str(RUNTIME/'campaign_heartbeat.json'),
        detached_runner=str(ROOT/'dayahead/v41r1/campaign_run.py'),
        free_SSD_bytes=shutil.disk_usage(ROOT).free,May1_B1_scientific_result_available=False)
    write_json(OUT/'FULL_MAY_PREPARATION.json',value)
    print('FULL_MAY_PREPARATION_READY',flush=True);return value


def freeze():
    prep=read(OUT/'FULL_MAY_PREPARATION.json');require(prep['status']=='READY' and prep['source']==science(),'PREPARATION_SOURCE_CHANGED')
    for path in prep['operations']:require(record(path['path'])==path,'OPERATIONAL_SOURCE_CHANGED')
    result=dict(scientific_commit=commit(),science=science(),preparation=record(OUT/'FULL_MAY_PREPARATION.json'),
        operations=prep['operations'],separate_May1_pilot='CANCELLED_BY_USER')
    write_json(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json',result);return result


def verify_release():
    release=read(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json')
    require(release['scientific_commit']==commit() and release['science']==science(),'CAMPAIGN_SOURCE_NOT_FROZEN')
    require(record(release['preparation']['path'])==release['preparation'],'PREPARATION_DRIFT')
    prep=read(release['preparation']['path'])
    for name in ('test_results','exact_equivalence','legacy_P0','stress','stress_reuse','baseline','baseline_retention','gap_authorization','electrical_coefficients','configuration','input_plan','separate_pilot_waiver','runtime_tests'):
        require(record(prep[name]['path'])==prep[name],'CAMPAIGN_GATE_DRIFT:'+name)
    for ref in release['operations']:require(record(ref['path'])==ref,'CAMPAIGN_OPERATION_DRIFT')
    return release


def verify_launch_authority():
    release=verify_release()
    from .coefficient_prepare import verify_manifest
    verify_manifest()  # Rehash all 31 days before the supervisor can start optimization.
    return release


if __name__=='__main__':
    import sys
    {'prepare':prepare,'freeze':freeze,'verify':verify_release}[sys.argv[1]]()
