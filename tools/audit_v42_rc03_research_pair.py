"""Read-only independent counts, original placement and legal selection audit.

Observed completions are read only after execution to recompute GPUh; they are
never controller inputs. No model, Native solve, AC solve or Actual is run.
"""
from pathlib import Path
import argparse
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC03'


def audit(pair):
    pair=Path(pair).resolve();records=[]
    def read(path):
        records.append(file_record(path));return json.loads(path.read_text(encoding='utf-8-sig'))
    common=read(pair/'COMMON_RUN_INPUTS.json')
    c0=read(pair/'C0/ACTUAL_RESULT.json');c1=read(pair/'C1/ACTUAL_RESULT.json')
    initial0=read(pair/'C0/INITIAL_PLACEMENT_LEDGER.json');initial1=read(pair/'C1/INITIAL_PLACEMENT_LEDGER.json')
    assert initial0==initial1
    assert all(r['sensitivity_used'] is False and r['GPU_registered'] is False
        and r['preplace_permission_required'] is False for r in initial1)
    assert len({r['uid'] for r in initial1})==len(initial1)==c1['Unknown_initial_placed_UIDs']
    assert c0['slots']==c1['slots']==16 and c0['MESS_plan_sha']==c1['MESS_plan_sha']==common['MESS_plan_sha']
    assert c0['research_environment_sha']==c1['research_environment_sha']==common['research_science_sha']
    assert c0['release_case_sha']==c1['release_case_sha']==common['release_case_sha']
    starts0=read(pair/'C0/ACTUAL_START_LEDGER.json');starts1=read(pair/'C1/ACTUAL_START_LEDGER.json')
    unknown0=[r for r in starts0 if r['origin_unknown']];unknown1=[r for r in starts1 if r['origin_unknown']]
    changed=[r for r in unknown1 if r['site']!=r['basic_site']]
    assert all(r['site']==r['basic_site'] for r in unknown0)
    assert len({r['uid'] for r in changed})==len(changed)==c1['PreSite_changed_UIDs']
    assert len(unknown0)==c0['Unknown_started_UIDs'] and len(unknown1)==c1['Unknown_started_UIDs']
    events=read(pair/'C1/JOB_EVENT_LEDGER.json')
    completions={r['uid']:r['time_seconds'] for r in events if r['event']=='COMPLETION_OBSERVED'}
    prefix=read(pair/'C1/PUBLIC_PREFIX_ORIGINAL_C1.json');end=prefix[-1]['end_seconds']
    decisions=read(pair/'C1/PENDING_PRE_SITE_LEDGER.json')
    by_event={(r['uid'],r['time_seconds']):r for r in decisions}
    assert all(any(c['kind']=='STAY' and c['site']==r['basic_site'] for c in r['candidates']) for r in decisions)
    selected=[];strict_better=0;stay_unavailable=0
    for start in changed:
        row=by_event[(start['uid'],start['time_seconds'])]
        candidate=next(c for c in row['candidates'] if c['site']==start['site'])
        stay=next(c for c in row['candidates'] if c['kind']=='STAY')
        data=candidate['research_data_contract'];score=candidate['sensitivity_score']
        assert row['chosen_site']==start['site'] and start['atomic_AC_rechecked'] is True
        assert candidate['feasible'] is True and candidate['physical']['PASS'] is True
        assert data['eligible'] is True and data['compatible'] is True and data['state']=='PENDING'
        assert data['provenance_class']=='ASSUMED' and data['customer_permission_claim'] is False
        assert data['measured_WAN_claim'] is False and data['ready_at_seconds']<=start['time_seconds']
        assert row['source_metadata_changed'] is False and row['future_private_reads']==0
        assert score['status']=='PASS' and math.isfinite(score['grid_peak'])
        legal=[c for c in row['candidates'] if c['feasible'] and isinstance(c.get('sensitivity_score'),dict)
            and c['sensitivity_score'].get('status')=='PASS']
        assert all(score['grid_peak']<=c['sensitivity_score']['grid_peak']+1e-10 for c in legal)
        baseline=None
        if stay['feasible']:
            assert stay['sensitivity_score']['status']=='PASS'
            baseline=stay['sensitivity_score']['grid_peak']
            assert score['grid_peak']<baseline-1e-10;strict_better+=1
        else:stay_unavailable+=1
        gpu_h=start['GPU']*(min(end,completions.get(start['uid'],end))-start['time_seconds'])/3600
        assert gpu_h>=0
        selected.append(dict(uid=start['uid'],basic_site=start['basic_site'],site=start['site'],
            start_seconds=start['time_seconds'],GPU=start['GPU'],changed_GPUh=gpu_h,
            STAY_feasible=stay['feasible'],STAY_predicted_maximum_phase_line_loading=baseline,
            selected_predicted_maximum_phase_line_loading=score['grid_peak'],
            candidate_AC_input_sha=candidate['candidate_AC_input_sha'],atomic_AC_rechecked=True,
            data_access_type=data['data_access_type'],provenance_class='ASSUMED'))
    gpu_h=sum(r['changed_GPUh'] for r in selected)
    assert abs(gpu_h-c1['changed_GPUh'])<1e-9
    result=dict(schema='RC03_INDEPENDENT_RESEARCH_PAIR_AUDIT_V1',status='PASS_RAW_EXECUTION_COUNTS_AND_SELECTION',
        scope=c1['scope'],scenario=c1['scenario'],slots=16,Source_strict_result_overwritten=False,
        release_case_sha=c1['release_case_sha'],research_science_sha=common['research_science_sha'],
        identical_initial_placement_ledger_sha=digest(initial1),initial_placed_UIDs=len(initial1),
        C0_Unknown_started_UIDs=len(unknown0),C1_Unknown_started_UIDs=len(unknown1),
        changed_UIDs=len(selected),changed_GPUh=gpu_h,
        selected_with_strictly_better_feasible_STAY=strict_better,
        selected_with_infeasible_STAY=stay_unavailable,STAY_always_included=True,
        chosen_is_minimum_among_legal_scored_candidates=True,actual_changed_UIDs=selected,
        GPUh_recomputed_from_observed_post_execution_completion=True,
        GPUh_is_not_C0_throughput_delta=True,grid_improvement_claim=False,
        Fresh_AC_certified_by_this_audit=False,current_D0_Full96_certified=False,
        continuous_time_voltage_safety_certified=False,Native_calls=0,AC_calls=0,Actual_runs=0,
        raw_records=records,tool=file_record(__file__))
    result['audit_sha']=digest(result);return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pair',type=Path,default=BASE/'ACTUAL_RESEARCH02/R1_SHARED_READY')
    parser.add_argument('--output',type=Path,default=BASE/'INDEPENDENT_RESEARCH_AUDIT/R1_RAW_SELECTION_AUDIT.json')
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('INDEPENDENT_AUDIT_MUST_NOT_OVERWRITE')
    result=audit(args.pair);_write(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('raw_records','actual_changed_UIDs')},indent=2))


if __name__=='__main__':main()
