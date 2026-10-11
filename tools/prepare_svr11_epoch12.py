"""Release the numerically validated Planning repair; all124 results start fresh."""
from pathlib import Path
import sys,os,shutil,json,re,subprocess
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files
from v42_svr11 import DAYS
ROOT=Path(r'D:\v42_svr11_may_20261011_12')
OLD=Path(r'D:\v42_svr11_may_20261011_10')
DIAG=Path(r'D:\v42_svr11_planning_diagnostics_20261011')
DEV=Path(r'D:\v42_svr11_ldc_development_20261011')

def prepare():
    assert not (ROOT/'CAMPAIGN_MANIFEST.json').exists(),'IMMUTABLE_EPOCH_ALREADY_RELEASED'
    ROOT.mkdir(exist_ok=True)
    old=read(OLD/'CAMPAIGN_MANIFEST.json')
    equipment_origin=read(old['hardware']['path'])['equipment_change_contract']
    assert record(equipment_origin['path'])==equipment_origin
    shutil.copyfile(equipment_origin['path'],ROOT/'EQUIPMENT_CHANGE_CONTRACT.json')
    # Only byte-identical unchanged raw files get physical storage sharing.
    # Templates/current producers/progress/policy results are never hardlinked.
    from v42_svr11.prepare import RAW,raw,release
    links=[]
    for day in DAYS:
        folder=ROOT/'raw'/day;folder.mkdir(parents=True,exist_ok=True)
        for name in RAW:
            origin=OLD/'raw'/day/name;target=folder/name
            if origin.exists() and not target.exists():os.link(origin,target)
            if origin.exists():
                assert record(origin)['sha256']==record(target)['sha256'] and os.path.samefile(origin,target)
                links.append(dict(original=record(origin),shared=record(target),hardlink=True))
    raw(ROOT)
    atomic(ROOT/'SELECTIVE_REUSE_LEDGER.json',dict(PASS=True,raw_shared=links,
        previous_epoch_sensitivity_coefficients_reused=0,previous_epoch_AC_results_promoted=0,
        previous_epoch_optimized_plans_promoted=0,
        regenerated=['All date-specific final LDC interval coefficients and their dependent model caches',
            'All124 Planning decisions, Actual materialization and Fresh96 physical verdicts'],
        diagnostic_only_original_response_kernel_use='Development projection and independent slot51 regeneration proof; not admitted to campaign models',UTC=now()))
    from v42_svr11.freeze import prepare as hardware
    h=hardware(ROOT/'hardware')
    assert h['equipment_SHA']==read(old['hardware']['path'])['equipment_SHA']
    from v42_svr11.regression import run as regression
    implementation=regression(ROOT)
    assert implementation['FAIL_CONTINUE']['PASS'] and implementation['control_independence']['PASS']
    log=DIAG/'FINAL_IMPLEMENTATION_REGRESSION.log';text=log.read_text(encoding='utf8')
    count=int(re.findall(r'(\d+) passed',text)[-1]);assert count==75
    atomic(ROOT/'REGRESSION_VALIDATION.json',dict(PASS=True,synthetic_fixture_only=False,
        pytest_passed=count,pytest_exit_code=0,pytest_stdout=record(log),
        native_compile_and_single_timestamp=True,implementation=record(ROOT/'IMPLEMENTATION_REGRESSIONS.json'),
        actual_B3_solver_parallel_execution_certified=False,
        scope='Scheduler/DTO/retry mechanics and actual independent-controller smoke; not a full-month voltage certificate'))
    projection=read(DIAG/'2025-05-18_CAP_AWARE_LDC_INTERVAL_FROZEN_PLAN_DIAGNOSTIC.json')
    target=projection['target']
    atomic(ROOT/'FROZEN_PLAN_MODEL_IMPROVEMENT.json',dict(PASS=True,synthetic_fixture_only=False,
        Actual_inputs_used_for_model=0,old_prediction_pu=target['old_prediction_pu'],
        new_prediction_pu=target['new_upper_pu'],new_lower_pu=target['new_lower_pu'],
        Forecast_AC_pu=target['Forecast_AC_pu'],prediction_kind='Physical LDC interval upper endpoint, not an exact point prediction',
        original_diagnostic=record(DIAG/'2025-05-18_CAP_AWARE_LDC_INTERVAL_FROZEN_PLAN_DIAGNOSTIC.json'),
        known_frozen_plan_interval_miss_cells=projection['affected_interval_miss_cells'],
        global_nonlinear_envelope_certified=False,
        validity='Settled unsaturated original LDC deadband; local relative-voltage and delivered-power approximation. Remaining residuals are retained, no empirical voltage offset.',
        independent_Holdout_claim=False))
    actual=DEV/'dates/B2/2025-05-18/attempts/development_03/ACTUAL_DIAGNOSTIC_01/INDEPENDENT_ACTUAL_VALIDATION.json'
    assert read(actual)['PASS']
    generation=DIAG/'FINAL_GENERATOR_CONNECTION/GENERATOR_CONNECTION_VALIDATION.json'
    gen=read(generation);assert gen['PASS'] and gen['independent_compiles']==121 and all(v['bitwise_equal'] for v in gen['fields'].values())
    assert gen['model_source']==record(SOURCE/'v42_svr11/model.py') and gen['LDC_source']==record(SOURCE/'v42_svr11/ldc_interval.py')
    validation=ROOT/'MODEL_VALIDATION_RELEASE_CONTRACT.json';sources=source_files()
    from v42_svr11.model import VERSION
    atomic(validation,dict(source_SHA=digest(sources),model_code_SHA=sources['v42_svr11/model.py'],model_version=VERSION,
        Actual_inputs_used_in_Planning=0,tap_optimization_variables=0,independent_Holdout_claim=False,
        development_execution_Source_SHA=read(actual)['source_SHA'],
        generator_verification_execution_Source_SHA=gen['source_SHA'],
        distinct_execution_and_release_SHA_preserved=True,
        generator_connection=record(generation),global_nonlinear_envelope_certified=False,
        validation_scope='Two independently reoptimized Forecast96 dates and one direct Actual96; actual controller deadbands unchanged; local approximation retains documented limitations',
        all_previous_results_and_native_ledgers_preserved=True,old_optimized_results_promoted=0,
        evidence=dict(root_cause=record(DIAG/'MAY18_QUANTITATIVE_CAUSE_DECOMPOSITION.json'),
            frozen_plan_prediction=record(ROOT/'FROZEN_PLAN_MODEL_IMPROVEMENT.json'),
            May18_reoptimization=record(DEV/'dates/B2/2025-05-18/attempts/development_03/INDEPENDENT_FORECAST_VALIDATION.json'),
            normal_date_validation=record(DEV/'dates/B2/2025-05-16/attempts/development_03/INDEPENDENT_FORECAST_VALIDATION.json'),
            May18_Actual=record(actual),regression_validation=record(ROOT/'REGRESSION_VALIDATION.json')),UTC=now()))
    atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),source_SHA=old['execution_SHA'],
        dispatch_quiescence=record(OLD/'DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'),
        scientific_model_change=True,physical_equipment_change=False,qualified_completed_dates_reused=False,
        all_old_results_preserved=True,naturally_ended_worker_observation=record(DIAG/'EPOCH10_DRAIN_PRESERVATION.json'),
        reason='Validated native LDC interval repair and direct Planning-to-Actual execution; all124 new policy/date runs required',UTC=now()))
    m=release(ROOT)
    from v42_svr11.controller import initial
    atomic(ROOT/'CAMPAIGN_LEDGER.json',initial())
    assert m['worker_counts']==dict(B0=3,B2=3,B1=1,B3=1)
    assert not m['postoptimization_DayAhead_Fresh_AC']
    print(json.dumps(dict(PASS=True,source_SHA=m['execution_SHA'],source_commit=m['source_commit'],root=str(ROOT),
        equipment_SHA=h['equipment_SHA'],old_results_promoted=0,worker_counts=m['worker_counts'])),flush=True)

if __name__=='__main__':prepare()
