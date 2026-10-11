"""All-terminal independent aggregation. Original RESULT/ledger bytes are read-only."""
from pathlib import Path
import sys,json,statistics,traceback
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from tools import b1_only_v4 as b

def run():
    root=b.DEFAULT_ROOT;m=b.verify_only(root)
    contract=root/'FINALIZER_CONTRACT.json'
    if contract.exists():assert b.record(__file__)==b.read(contract)['source']
    if (root/'FINAL_REPORT.json').exists():return
    if not (root/'CAMPAIGN_COMPLETION.json').exists():return
    ledger=b.read(root/'CAMPAIGN_LEDGER.json');rows=list(ledger['dates'].values())
    if len(rows)!=31 or any(r['status'] not in ('PASS','FAIL') for r in rows):return
    with b.singleton(root/'FINAL_REPORT.lock'):
        if (root/'FINAL_REPORT.json').exists():return
        values=[];all_calls=[];days=[]
        for row in rows:
            result=b.read(row['result']);ref=b.record(row['result'])
            assert ref['sha256']==row['result_SHA']
            assert result['arm']=='B1' and result['day']==row['day']
            science=result.get('scientific',{});inc= science.get('incumbent',{})
            physical_ref=inc.get('physical');physical=b.read(physical_ref['path']) if physical_ref else {}
            if physical_ref:assert b.record(physical_ref['path'])==physical_ref
            environments=result.get('metrics',{}).get('environments',{})
            actual=environments.get('ACTUAL',{});day_calls=[]
            if result.get('FULL_feasible_certified'):
                assert physical.get('PASS') is True and physical.get('scientific_primal_replay',{}).get('PASS') is True
            if result.get('AC_status')=='AC PASS':
                assert actual.get('slots')==96 and actual.get('Full_AC_Physical_PASS') is True
                assert actual.get('AC_converged') is True and actual.get('control_complete') is True
                assert actual.get('SVR11_finite_rating_and_taps') is True
            for native in result.get('native_ledgers',[]):
                r=native['receipt'];assert b.record(r['path'])==r
                content=b.read(r['path']);day_calls.append(dict(receipt=r,contents=content))
            all_calls.extend(day_calls)
            if actual.get('maximum_line_loading') is not None:values.append(actual['maximum_line_loading'])
            svr_audits=[]
            for receipt in result.get('metrics',{}).get('evidence',[]):
                assert b.record(receipt['path'])==receipt
                audit=b.read(receipt['path']);slots=b.read(audit['slots_receipt']['path'])
                svr_audits.append(dict(namespace=audit['namespace'],
                    SVR_failed_slots=sum(not s['svr']['hardware_PASS'] for s in slots),
                    control_incomplete_slots=sum(not s['control_actions_done_as_of_current_time'] for s in slots),
                    receipt=receipt))
            days.append(dict(day=row['day'],status=row['status'],reason=result.get('reason'),result=ref,
                FULL_feasible_certified=result.get('FULL_feasible_certified'),
                Global_Gap_0_5_percent_certified=result.get('global_gap_certified'),
                Global_LB=result.get('certified_LB'),Global_Gap=result.get('certified_Gap'),
                Planning_freeze_allowed=science.get('accepted',False),Planning_rho_max=result.get('Planning_objective'),
                Planning_AC_status='NOT_EXECUTED_BY_APPROVED_SOURCE18R_CONTRACT',
                Actual_fresh_AC_PASS=result.get('AC_status')=='AC PASS',
                Native_Runtime=result.get('Native_Runtime'),known_completed_Native_Runtime=result.get('known_completed_Native_Runtime'),
                Wall_seconds=result.get('wall_seconds'),native_ledgers=day_calls,
                original_job_population_verified=physical.get('original_job_population_verified'),
                original_integer_types_restored=physical.get('original_integer_types_restored'),
                original_jobs=physical.get('original_jobs'),
                original_primal_rows_PASS=physical.get('scientific_primal_replay',{}).get('PASS'),
                QoS_job_scheduler_WAN_original_FULL_validation_PASS=physical.get('PASS'),
                QoS_job_scheduler_WAN_certificate=physical_ref,
                scheduler_metrics=physical.get('schedule_metrics'),scheduler_objective_residuals=physical.get('schedule_objective_residuals'),
                physical_metrics=environments,SVR_and_controls=svr_audits,
                planning_input_SHA=m['input_receipts'][row['day']],
                Actual_reoptimization=result.get('Actual_reoptimization'),Actual_PQ_repair=result.get('Actual_PQ_repair')))
        previous=b.read(b.ORIGIN/'CAMPAIGN_LEDGER.json');hardware=b.read(m['hardware']['path'])
        old_manifest=b.read(b.ORIGIN/'CAMPAIGN_MANIFEST.json');old_hardware=b.read(old_manifest['hardware']['path'])
        historical=[]
        for row in rows:
            d=row['day'];base=previous['dates'].get('B0/'+d,{})
            old_b1=old_manifest['origins'][d]['historical_B1_result']
            baseline=base.get('metrics',{}).get('environments',{}).get('ACTUAL',{})
            historical.append(dict(day=d,historical_B0_status=base.get('status'),historical_B0_result=base.get('result'),
                historical_B0_execution_SHA=base.get('original_execution_source_SHA',base.get('source_SHA')),
                historical_B0_Actual_physics=baseline,historical_PR189_B1_result=old_b1,
                historical_PR189_B1_physics='Original result linked; different equipment must not be treated as the current B1 measurement',
                current_B0_is_not_executed=True,current_B1_historical_PASS_promotion=False,
                origin_frozen_equipment_equivalent=hardware['equipment_SHA']==old_hardware['equipment_SHA'] and m['scenario']['sha256']==old_manifest['scenario']['sha256']))
        runtime=sum(d.get('known_completed_Native_Runtime') or 0 for d in days)
        report=dict(schema='V42_B1_ONLY_FINAL_INDEPENDENT_REPORT_V1',campaign_id=m['run_id'],all31_terminal=True,
            PASS=sum(d['status']=='PASS' for d in days),FAIL=sum(d['status']=='FAIL' for d in days),
            all31_PASS=all(d['status']=='PASS' for d in days),days=days,
            maximum_Actual_line_loading=max(values) if values else None,
            mean_Actual_maximum_line_loading=statistics.mean(values) if values else None,
            metric_population='All measured Actual dates including FAIL; absent Actual stays unavailable',
            total_known_Native_Runtime=runtime,total_Native_Runtime=None if any(d['Native_Runtime'] is None for d in days) else runtime,
            total_Wall_seconds=b.read(root/'REPORT.json')['wall_seconds'],
            source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA'],hardware=m['hardware'],scenario=m['scenario'],thermal=m['thermal'],
            Source18r_commit=m['source_commit'],forecast_31_audit=b.record(root/'ALL31_CAUSAL_INPUT_AUDIT.json'),
            Native_ledgers=all_calls,error_and_restart_history=[dict(day=r['day'],attempts=r['attempts'],terminal_history=r.get('terminal_history',[])) for r in rows],
            historical_physical_comparison_provenance=historical,UTC=b.now())
        b.atomic(root/'FINAL_REPORT.json',report)
        lines=['# B1-only May 2025 final report',f"31/31 terminal; {report['PASS']} PASS; {report['FAIL']} FAIL.",
            '31/31 PASS' if report['all31_PASS'] else 'All dates reached terminal state; 31/31 PASS is not certified.',
            f"Total known Native Runtime: {runtime} s; Wall: {report['total_Wall_seconds']} s.",
            f"Maximum measured Actual line loading: {report['maximum_Actual_line_loading']} pu.",
            '| Date | Status | FULL | Gap<=0.5% | Freeze | Actual AC | Native s | Reason |','|---|---|---|---|---|---|---|---|']
        for d in days:lines.append('| '+' | '.join(str(x) for x in (d['day'],d['status'],d['FULL_feasible_certified'],d['Global_Gap_0_5_percent_certified'],d['Planning_freeze_allowed'],d['Actual_fresh_AC_PASS'],d['Native_Runtime'],d['reason']))+' |')
        (root/'FINAL_REPORT.md').write_text('\n\n'.join(lines)+'\n',encoding='utf8')

if __name__=='__main__':
    try:run()
    except Exception as error:
        b.atomic(b.DEFAULT_ROOT/'FINAL_REPORT_ERROR.json',dict(error=repr(error),traceback=traceback.format_exc(),UTC=b.now()));raise
