"""Freeze the unchanged law and input period before reading holdout outcomes."""
from datetime import datetime, timezone
from .common import *
from v42_regcontrol.authority import common_contract, source, compile_verified

PRODUCERS=('v42_capacity/planning.py','v42_capacity/replay.py','v42_capacity/truth_audit.py',
 'v42_capacity/reference.py','v42_capacity/queue.py','v42_capacity/actual.py',
 'v42_modelable/power.py','v42_modelable/population.py','v42_april_port/builder.py',
 'v42_regcontrol/session.py','v42_regcontrol/authority.py','v42_regcontrol/runner.py',
 'v42_final/runtime.py','v42_final/reserve.py','v42_final/workload.py')

def main():
    if (OUT/'PREREGISTRATION.json').exists(): raise ValueError('ALREADY_FROZEN')
    OUT.mkdir(parents=True)
    (OUT/'.gitattributes').write_text('* -text whitespace=cr-at-eol\n*.log -text whitespace=-blank-at-eol,cr-at-eol\n',encoding='utf-8')
    a=read(EXO/'V40D_AEMO_COMPLETENESS.json'); w=read(EXO/'V40D_WEATHER_COMPLETENESS.json')
    if [x['day'] for x in a['demand']['days']]!=list(DAYS) or [x['day'] for x in w['days']]!=list(DAYS):
        raise ValueError('EXISTING_FROZEN_MAY_PERIOD_MISMATCH')
    frozen=[record(ROOT/p) for p in PRODUCERS]
    frozen += [record(ROOT/'v42_final/runtime_bundle'/x['relative']) for x in read(ROOT/'v42_final/runtime_bundle/INTEGRITY.json')['files']]
    frozen += [record(ROOT/'v42_final/inference'/Path(x['path']).name) for x in read(ROOT/'v42_final/runtime_bundle/INTEGRITY.json')['inference_source_extraction']]
    frozen += [record(ROOT/'docs/v42_final_integration'/p) for p in ('CC4_EXECUTION_LAG_KERNEL.csv','RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv')]
    interface=read(ROOT.parent/'v42_integrated_pr/docs/v42_final/AGGREGATE_BINDING.json')['interface']
    frozen += [record(resolve(interface[k])) for k in ('prediction','ledger','selection')]
    sources=[]
    for day in DAYS:
        manifest=read(RAW/day/'source_day_manifest.json')
        for r in manifest['files'].values(): resolve(r)
        snap=SNAPS/day/'V37_R4A_D1_SNAPSHOT.parquet'
        sources.append(dict(day=day,snapshot=record(snap),snapshot_manifest=record(snap.with_name('V37_R4A_DAY_MANIFEST.json')),
            forecast=record(RAW/day/'aemo_forecast.json'),weather=record(RAW/day/'gfs_d1_weather.parquet'),manifest=record(RAW/day/'source_day_manifest.json'),
            gfs_vintage_manifest=record(RAW/day/'gfs_source_manifest.json')))
        frozen.extend([sources[-1][k] for k in ('snapshot','snapshot_manifest','forecast','weather','manifest','gfs_vintage_manifest')])
    exo={k:a[k]['source'] for k in ('demand','pv')}; exo['weather']=w['derived']
    frozen += [record(resolve(r)) for r in exo.values()]
    archive=read(ROOT/'docs/v42_april_modelable_population_b0/BUNDLE/DAY_20250401/SOURCE_PROVENANCE.json')['archive']
    frozen.append(record(resolve(archive)))
    # Source authority alone is inspected here. No May voltage outcomes exist yet.
    control=common_contract('B0'); m=source()
    frozen += m['audit']['static_source_graph']['files']+m['audit']['code_read']
    frozen += read(ROOT/'docs/v42_april_b0_capacity_queue_voltage_calibration/ELECTRICAL_SOURCE_AUTHORITY.json')['static_sources']
    power=read(ROOT/'docs/v42_april_modelable_population_b0/BUNDLE/DAY_20250401/POWER_AUTHORITY.json')
    frozen += [power[k] for k in ('C1','C1_implementation')]
    write(OUT,'PREREGISTRATION.json',dict(exact_base=BASE,frozen_at=datetime.now(timezone.utc).isoformat(),days=DAYS,
        existing_period_authority=[record(EXO/'V40D_AEMO_COMPLETENESS.json'),record(EXO/'V40D_WEATHER_COMPLETENESS.json')],
        margin_pu=0,Planning_voltage_band=[.95,1.05],Actual_voltage_band=[.95,1.05],
        parameter_tuning_calls=0,Runtime_fit_calls=0,CC4_fit_calls=0,holdout_outcomes_observed_before_freeze=False,
        control=control,archive=archive,day_sources=sources,exogenous_sources=exo,power=power,
        frozen_sources=frozen,capacity_total_GPU=780,
        modelability_rule=record(ROOT/'docs/v42_april_modelable_population_b0/POPULATION/V42_PHYSICAL_MODELABILITY_RULE.md'),
        population_policy='unchanged J_PHYSICAL rule; raw unmodelable events retained in ledger; no result-driven exclusion',
        planning_producer='unchanged PR125 B0 affine anchor and sensitivity; current reference controls equal anchor',
        grid_alignment='96 quarter-hour END labels; demand quarter-hour sampling; PV repeat half-hour observations twice',
        weather_alignment='inherited quarter-hour START time interpolation; no forecast weather in Actual',
        read_order='planning inputs -> physical Planning -> V_PLAN -> freeze ALL 31 days -> private Actual truth/PQ -> Fresh AC',
        historical_requested_walltime_service=False,requested_walltime_runtime_feature_only=True,
        Actual_tap_replay=False,Actual_PQ_repair=0,Actual_reoptimization=0,MESS=0,AIDC_grid_flexibility=False,
        pass_rule='0 Actual voltage cells -> margin=0 holdout PASS candidate; any cell -> FAIL',
        reference_005_coverage_not_acceptance_gate=True,post_result_margin_retuning_forbidden=True,
        B1='NOT_RUN',B2='NOT_RUN',B3='NOT_RUN',M1='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',
        FINAL_MARGIN_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,
        previously_untouched_by_April_calibration=True,
        prior_May01_development_canary_exists=True,pristine_never_seen_dataset_claim=False,
        statistical_scope='untuned evaluation relative to April; inherited development canary is disclosed'))
    print('PREREGISTRATION SEALED: May 1–31, margin=0, no tuning',flush=True)

if __name__=='__main__': main()
