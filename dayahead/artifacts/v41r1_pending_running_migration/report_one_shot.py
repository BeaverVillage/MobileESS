"""Read-only outcome comparison after all four frozen May-1 phases."""
from pathlib import Path
import sys,importlib.util,subprocess,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.scientific_archive import document,verify_manifest
from dayahead.v41.persistence import verify_table
from dayahead.v41.execution import science

spec=importlib.util.spec_from_file_location('observational_helpers',ROOT/'dayahead/artifacts/v41r1_terminal_residual/report_runner.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
DAY='2025-05-01';OLD=helpers.OLD


def policy(root,name,new):
    unit=root/'pilot'/DAY/name;da=unit/'dayahead';ac=unit/'actual'
    vector=read(da/'optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    grids={stage:helpers.electrical(folder,stage=='DayAhead') for stage,folder in (
        ('DayAhead',da/'optimization/stages/JOINT_FREEZE'),('Fresh',da/'grid'),('Actual',ac/'grid'))}
    actual=read(ac/'ACTUAL_RESULT.json');h4=pd.read_parquet(ac/'H4_OPTIMIZER_WINDOWS.parquet')
    with np.load(da/'FROZEN_AIDC_POWER.npz',allow_pickle=False) as p:
        occupancy=dict(critical_18h_GPU=int(p['gpu'][72].sum()),critical_18h_PCC_kW=float(p['pcc'][72].sum()),
            critical_18h_GPU_by_site=p['gpu'][72].tolist(),critical_18h_PCC_by_site=p['pcc'][72].tolist(),
            maximum_GPU=int(p['gpu'].sum(axis=1).max()),daily_GPUh=float(p['gpu'].sum()/4),daily_PCC_kWh=float(p['pcc'].sum()/4))
    result=dict(DayAhead_objective_vector=vector,
        Actual_evaluated_objective_vector=[grids['Actual']['rho_max'],float(h4.reserve_shortfall_xi_GPUh.mean()),*vector[2:]],
        Actual_vector_authority='P1/P2 are realized arithmetic evaluation; P3-P5 remain frozen DayAhead decisions. No Actual optimization.',
        electrical=grids,occupancy=occupancy,Actual_execution_delay_KPIs=actual['execution_delay_KPIs'],
        Actual_execution_rate=actual['execution_rate'],Actual_GPU_feasibility=actual['final_execution_feasibility'],
        Actual_optimizer_calls=actual['Actual_optimizer_calls'],Actual_physical_violation=actual['summary']['physical_violation'],
        H4_raw_vs_actionable_coverage=actual['H4_raw_vs_actionable_coverage'])
    if new:
        candidates=read(da/'aidc/migration/MIGRATION_ELIGIBILITY_SUMMARY.json')
        for ref in candidates['files'].values():verify_table(ref)
        result['migration']=candidates
        replay=ac/'aidc/ACTUAL_MIGRATION_REPLAY_AUDIT.json'
        result['Actual_migration']=read(replay) if replay.exists() else {'applicability':'NO_FROZEN_MIGRATIONS'}
    return result


def run():
    frozen=read(RUNTIME/'V41R1_SCIENTIFIC_REVISION_FREEZE.json');assert frozen['science']==science()
    results={label:{p:policy(root,p,label=='NEW') for p in ('B0','B1')} for label,root in [('OLD',OLD),('NEW',RUNTIME)]}
    receipts=[];manifests={}
    for p in ('B0','B1'):
        unit=RUNTIME/'pilot'/DAY/p
        manifests[p]=verify_manifest(unit/'UNIT_SCIENTIFIC_MANIFEST.json')
        for phase in ('dayahead','actual'):
            path=unit/phase/(phase.upper()+'_RECEIPT.json');r=read(path)
            assert r['science']==frozen['science'] and r['scientific_commit']==frozen['scientific_commit']
            receipts.append(record(path))
    prep=read(RUNTIME/'inputs'/DAY/'PRE_SOLVE_PERSISTENCE_AUDIT.json')
    for entry in prep['tables'].values():verify_table(entry)
    assert prep['snapshot_count']==1 and prep['tables']['runtime_predictions']['rows']==1395 and prep['tables']['h4_windows']['rows']==81
    from dayahead.v41.scalars import project
    assert project(read(OLD/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json')).sha256==project(read(prep['snapshot']['path'])).sha256
    p0=read(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json');assert p0['PASS']==7 and p0['FAIL']==0
    nesting=read(OUT/'V41_MAY01_B0_IN_B1_FEASIBILITY.json');assert nesting['status']=='PASS'
    gains={}
    for label,policies in results.items():
        gains[label]={}
        for stage,key in [('DayAhead','DayAhead_objective_vector'),('Actual','Actual_evaluated_objective_vector')]:
            a=policies['B0'][key][0];b=policies['B1'][key][0]
            gains[label][stage]=dict(B0=a,B1=b,B0_minus_B1=a-b,B1_reduction_percent=100*(a-b)/a)
    blockers=[]
    for p,value in results['NEW'].items():
        assert value['Actual_optimizer_calls']==0
        if value['Actual_physical_violation']:blockers.append(p+'_ACTUAL_PHYSICAL_VIOLATION')
        for stage,g in value['electrical'].items():
            if g['raw_voltage_violation_count'] or g['line_current_violation_count']:blockers.append(p+'_'+stage+'_RAW_ELECTRICAL_VIOLATION')
    model=read(RUNTIME/'pilot'/DAY/'B1/dayahead/A0/PRIMARY_STRUCTURE.json')
    pre=read(OUT/'PRE_MAY01_ONE_SHOT_AUDIT/MODEL/PRIMARY_STRUCTURE.json')
    for key in ('domain_counts','model_variables','model_constraints','integer_variables_including_binary','general_constraints'):
        assert model[key]==pre[key],key
    gate=read(OUT/'EXACT_COMPRESSION_GATE.json')
    report=dict(status='COMPLETE_RAW_OUTCOMES_REPORTED',scientific_commit=frozen['scientific_commit'],
        contract=gate['contract'],results=results,primary_gains=gains,model_structure=model,
        compression_gate=record(OUT/'EXACT_COMPRESSION_GATE.json'),regression_test_count=len(list(ET.parse(OUT/'V41_TEST_RESULTS.xml').iter('testcase'))),
        P0=record(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json'),B0_in_B1=record(OUT/'V41_MAY01_B0_IN_B1_FEASIBILITY.json'),
        all_four_phases_same_scientific_commit=True,receipts=receipts,
        full_May_readiness='FAIL' if blockers else 'PASS',full_May_blocking_reasons=blockers,
        full_May_launched=False,full_May_requires_user_review=True,new_voltage_margin=None,
        Actual_voltage_retuning=False,optimizer_scalar_outputs_unchanged=True,
        attribution='Only fixed-start initial placement and one-shot first-checkpoint migration are flexible. No time shifting, extra checkpoint, terminal cap or Actual optimization.',
        generator=record(__file__))
    document(OUT/'V41R1_MAY01_FINAL_ONE_SHOT_RESULTS.json',report)
    document(OUT/'V41R1_COMPLETE_PERSISTENCE_AUDIT.json',dict(status='PASS',manifests=manifests,
        receipts=receipts,ML_persistence=prep,all_manifest_leaves_reopened=True,all_four_phases_same_scientific_commit=True))
    flat=[]
    for label,policies in results.items():
        for p,v in policies.items():
            for stage,g in v['electrical'].items():
                flat.append(dict(revision=label,policy=p,stage=stage,**{k:g[k] for k in ('rho_max','Vmin','Vmax','raw_voltage_violation_count')},
                    critical_line=str(g['critical_line_location']),maximum_voltage=str(g['maximum_voltage_location'])))
    pd.DataFrame(flat).to_csv(OUT/'V41R1_MAY01_RAW_ELECTRICAL_RESULTS.csv',index=False)
    print(dict(primary_gains=gains,full_May_readiness=report['full_May_readiness'],blocking_reasons=blockers),flush=True)


if __name__=='__main__':run()
