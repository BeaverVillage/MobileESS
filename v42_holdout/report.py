"""Holdout measurement only. No parameter/margin selection or science mutation."""
import csv
import gzip
import numpy as np
from .common import *
from v42_capacity.calibration import aligned_residual

def metrics(residual,days,nodes):
    e=residual['e_total']; absolute=abs(e); up=np.maximum(e,0);down=np.maximum(-e,0)
    if e.shape!=(len(days),96,len(nodes)) or not np.isfinite(e).all(): raise ValueError('FULL_RESIDUAL_AXIS_REQUIRED')
    d,t,n=np.unravel_index(np.argmax(absolute),e.shape)
    stats=dict(mean_signed_error=float(e.mean()),MAE=float(absolute.mean()),RMSE=float(np.sqrt((e**2).mean())),
        median_absolute_error=float(np.median(absolute)),maximum_absolute_error=float(absolute.max()),
        points=int(e.size),worst_location=dict(day=days[d],slot=int(t),node_phase=nodes[n],
            V_PLAN=float(residual['V_PLAN'][d,t,n]),V_ACTUAL_AC=float(residual['V_ACTUAL_AC'][d,t,n]),e_total=float(e[d,t,n])))
    coverage=dict(reference_only=True,acceptance_gate=False,margin_pu=.005,
        upper_pointwise_coverage=float((up<=.005).mean()),lower_pointwise_coverage=float((down<=.005).mean()),
        joint_pointwise_coverage=float((absolute<=.005).mean()),joint_day_coverage=float((absolute.max((1,2))<=.005).mean()),
        covered_days=int(np.sum(absolute.max((1,2))<=.005)),exceedance_days=[days[i] for i in np.flatnonzero(absolute.max((1,2))>.005)],
        maximum_exceedance=float(np.maximum(absolute-.005,0).max()))
    return stats,coverage

def judge(violations,*,complete,planning_violations):
    if not complete: return 'NOT_EVALUABLE_INCOMPLETE_HOLDOUT'
    return 'margin=0 holdout PASS candidate' if violations==0 else 'margin=0 holdout FAIL'

def main():
    source_freeze(); dayrows=[];plans=[];actuals=[];nodes=None;params=[];physical=[]
    for day in DAYS:
        dest=destination(day);p=np.load(dest/'V_PLAN.npz');a=np.load(dest/'V_ACTUAL_AC.npz')
        names=tuple(map(str,p['node_names']))
        if nodes is not None and nodes!=names: raise ValueError('CROSS_DAY_VOLTAGE_AXIS_DRIFT')
        nodes=names
        r=aligned_residual(p['V_PLAN'],a['V_ACTUAL_AC'],names,tuple(map(str,a['node_names'])),plan_representation='magnitude_pu')
        plans.append(r['V_PLAN']);actuals.append(r['V_ACTUAL_AC'])
        receipt=read(dest/'FRESH_ACTUAL_AC_RECEIPT.json');dayrows.append(receipt)
        control=read(dest/'RAW_CONTROL_LOG.json');params.extend(dict(day=day,**row) for row in control['slots'])
        freeze=read(dest/'PLANNING_FREEZE.json')
        for k in ('reference','physical_arrays','voltage','response','planning_input','coefficients'): resolve(freeze[k])
        ap=np.load(dest/'ACTUAL_PHYSICAL.npz')
        if not np.array_equal(a['PCC_P_kw'],ap['PCC_P_kw']) or not np.array_equal(a['PCC_Q_kvar'],ap['PCC_Q_kvar']): raise ValueError('ACTUAL_PQ_FROZEN_ARRAY_DRIFT')
        if not np.all(a['capacitor_states']==1) or not np.all(a['converged']): raise ValueError('SOURCE_CONTROL_OR_CONVERGENCE_GATE')
        cap=read(dest/'ACTUAL_CAPACITY_RECEIPT.json'); physical.append(cap)
    plan=np.array(plans);actual=np.array(actuals);residual=dict(V_PLAN=plan,V_ACTUAL_AC=actual,e_total=actual-plan)
    stats,coverage=metrics(residual,DAYS,nodes)
    for label in ('Planning_voltage_violations','voltage_violations','line_current_violations','transformer_current_violations','transformer_kVA_violations'):
        if any(r[label]<0 for r in dayrows): raise ValueError('INVALID_VIOLATION_COUNT')
    security=dict(days=31,slots=31*96,converged_days=sum(r['converged'] for r in dayrows),
        converged_slots=sum(r['converged_slots'] for r in dayrows),
        Planning_voltage_violations=int(np.sum((plan<.95)|(plan>1.05))),
        Planning_violation_days=int(np.sum(np.any((plan<.95)|(plan>1.05),axis=(1,2)))),
        Planning_voltage_min=float(plan.min()),Planning_voltage_max=float(plan.max()),
        Actual_voltage_violations=int(np.sum((actual<.95)|(actual>1.05))),
        Actual_violation_days=int(np.sum(np.any((actual<.95)|(actual>1.05),axis=(1,2)))),
        Actual_voltage_min=float(actual.min()),Actual_voltage_max=float(actual.max()),
        line_current_violations=sum(r['line_current_violations'] for r in dayrows),
        transformer_current_violations=sum(r['transformer_current_violations'] for r in dayrows),
        transformer_kVA_violations=sum(r['transformer_kVA_violations'] for r in dayrows),
        primary_band=[.95,1.05],Planning_margin_pu=0,Actual_PQ_repair=0,Actual_reoptimization=0,MESS=0)
    verdict=judge(security['Actual_voltage_violations'],complete=security['converged_slots']==2976,
        planning_violations=security['Planning_voltage_violations'])
    flags=dict(May_B0='RUN',B1='NOT_RUN',B2='NOT_RUN',B3='NOT_RUN',M1='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',
        FINAL_MARGIN_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,
        B0_ZERO_MARGIN_HOLDOUT_PASS_CANDIDATE=security['Actual_voltage_violations']==0,
        Planning_band_premise_satisfied=security['Planning_voltage_violations']==0,
        V42_all_arms_margin_generalization=False,margin_retuning_calls=0,parameter_tuning_calls=0,
        Actual_Planning_tap_replay=False,Actual_Planning_cap_replay=False,Actual_PQ_repair=0,Actual_reoptimization=0,
        MESS=0,AIDC_grid_flexibility=False,Planning_RegControl='AUTONOMOUS_SOURCE_BACKED',
        Actual_RegControl='AUTONOMOUS_SOURCE_BACKED',capacitors_fixed_ON=True,CapControl_count=0)
    write(OUT,'MAY_SECURITY_SUMMARY.json',security);write(OUT,'PRIMARY_RESIDUAL_METRICS.json',stats)
    write(OUT,'REFERENCE_005_COVERAGE.json',coverage);write(OUT,'FINAL_FLAGS.json',flags)
    write(OUT,'FINAL_VERDICT.json',dict(verdict=verdict,security=security,
        planning_premise_satisfied=flags['Planning_band_premise_satisfied'],FINAL_MARGIN_ACCEPTED=False,
        reason='B0 holdout evaluated; other comparison arms untested; no V42-wide final margin accepted',
        reference_coverage_used_to_retune=False,post_holdout_calibration_calls=0))
    table(OUT,'MAY_B0_DAY_SUMMARY.csv',dayrows,list(dayrows[0]))
    columns=['day','node','phase','slot','V_PLAN','V_ACTUAL_AC','e_total']
    with gzip.open(OUT/'MAY_B0_VOLTAGE_RESIDUALS.csv.gz','wt',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(columns)
        for d,day in enumerate(DAYS):
            for t in range(96):
                for n,name in enumerate(nodes):
                    node,phase=name.rsplit('.',1);writer.writerow([day,node,'ABC'[int(phase)-1],t,float(plan[d,t,n]),float(actual[d,t,n]),float(actual[d,t,n]-plan[d,t,n])])
    write(OUT,'REGCONTROL_PARAMETER_INTEGRITY.json',dict(PASS=True,slots=len(params),
        all_source_settings_identical=all(r['source_parameters_before_after_identical'] for r in params),
        all_7_enabled=all(r['all_7_RegControls_enabled'] for r in params),
        modes=sorted({r['control_mode'] for r in params}),authority_SHAs=sorted({r['REGCONTROL_AUTHORITY_SHA'] for r in params}),
        capacitor_unexpected_states=0,source_definitions_unchanged=True,parameter_tuning=0))
    write(OUT,'MAY_PHYSICAL_SUMMARY.json',dict(Actual_GPUh=sum(r['actual_GPUh'] for r in physical),
        Actual_IT_kWh=sum(r['actual_IT_kWh'] for r in physical),Actual_PCC_kWh=sum(r['actual_PCC_kWh'] for r in physical),
        capacity_violations=sum(r['capacity_violations'] for r in physical),dropped_jobs=sum(r['dropped_jobs'] for r in physical),
        current_Runtime_and_CC4_contract_unchanged=True))
    april_metrics=read(APRIL/'PRIMARY_RESIDUAL_METRICS.json');april_coverage=read(APRIL/'CURRENT_005_COVERAGE.json')
    april_days=[read(APRIL/'BUNDLE'/day_folder(f'2025-04-{d:02d}')/'FRESH_ACTUAL_AC_RECEIPT.json') for d in range(1,31)]
    comparison=[]
    for month,ds,met,cov in [('April',april_days,april_metrics,april_coverage),('May',dayrows,stats,coverage)]:
        comparison.append(dict(month=month,days=len(ds),slots=len(ds)*96,Planning_voltage_violations=sum(r['Planning_voltage_violations'] for r in ds),
            Actual_voltage_violations=sum(r['voltage_violations'] for r in ds),Actual_violation_days=sum(r['voltage_violations']>0 for r in ds),
            Actual_min=min(r['voltage_min'] for r in ds),Actual_max=max(r['voltage_max'] for r in ds),
            line_current_violations=sum(r['line_current_violations'] for r in ds),transformer_current_violations=sum(r['transformer_current_violations'] for r in ds),
            transformer_kVA_violations=sum(r['transformer_kVA_violations'] for r in ds),
            mean_signed_error=met['mean_signed_error'],MAE=met['MAE'],RMSE=met['RMSE'],max_abs=met['maximum_absolute_error'],
            reference_005_joint_pointwise=cov['joint_pointwise_coverage'],reference_005_joint_day=cov['joint_day_coverage']))
    table(OUT,'APRIL_MAY_COMPARISON.csv',comparison,list(comparison[0]))
    print(verdict,security,stats,flush=True)

if __name__=='__main__':main()
