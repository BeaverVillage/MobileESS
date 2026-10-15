"""Independent metrics from saved Actual/Fresh ledgers; no simulation or solve."""
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
import csv
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def local_time(seconds):
    return datetime.fromtimestamp(seconds,timezone(timedelta(hours=10))).isoformat()


def write_csv(path,rows):
    with path.open('w',encoding='utf8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    target=OUT/'INDEPENDENT_MEASURED_COMPARISON.json'
    if target.exists():raise FileExistsError('MEASURED_COMPARISON_MUST_NOT_OVERWRITE')
    common=read(OUT/'C0_C1_COMMON_INPUT_CERTIFICATE.json');assert common['status']=='PASS'
    completed=read(OUT/'COMPARISON_COMPLETE.json');assert completed['status']=='EXECUTED'
    fresh_status=read(OUT/'C0_C1_FRESH_AC_STATUS.json')
    variants={};fresh_rows=[];physical_vectors={}
    for label in ('C0','C1'):
        base=OUT/label;actual=read(base/'ACTUAL_GRID_METRICS.json');receipt=actual['receipt']
        queue=read(base/'QUEUE_LEDGER.json');qos=read(base/'QOS_ACTUAL_LEDGER.json')
        events=read(base/'UNKNOWN_CANDIDATE_LEDGER.json')
        known=read(base/'KNOWN_REFERENCE_AND_CORRECTIVE_LEDGER.json')
        corrective=known['corrective_audit'];conflicts={r['uid'] for r in corrective if r.get('GPU_capacity_conflict')}
        unknown=[r for r in queue if r['origin_unknown']]
        reason_uids=defaultdict(set);reason_candidates=Counter()
        for e in events:
            for c in e['candidates']:
                if c['reason']:
                    reason_uids[c['reason']].add(e['uid']);reason_candidates[c['reason']]+=1
        conflict_reasons=Counter(c['reason'] for e in corrective for c in e.get('rejected_candidates',[]))
        with np.load(base/'ACTUAL_GPU_PQ.npz',allow_pickle=False) as packet:
            a={k:packet[k].copy() for k in packet.files}
        known_queue=sum(not r['origin_unknown'] and r['admitted_time'] is None for r in queue)
        known_started=sum(not r['origin_unknown'] and r['admitted_time'] is not None for r in queue)
        summary=dict(actual_receipt=receipt,initial_running=324,additional_Known_started=known_started-324,
            all_started_including_initial=known_started+sum(r['admitted_time'] is not None for r in unknown),
            Unknown_submitted=len(unknown),Unknown_started=sum(r['admitted_time'] is not None for r in unknown),
            Unknown_queued=sum(r['admitted_time'] is None for r in unknown),Known_pending=known_queue,
            Known_running=sum(not r['origin_unknown'] and r['latest_state']=='RUNNING' for r in queue),
            completed_jobs=receipt['completed_jobs'],carryout_jobs=receipt['carryout_jobs'],
            Known_actual_GPU_conflict_UIDs=len(conflicts),Known_conflict_event_attempts=len(corrective),
            Known_corrective_commands=len(known['actual_corrective_commands']),
            Known_corrective_actual_starts=sum(r.get('actual_start_seconds') is not None for r in known['actual_corrective_commands'].values()),
            Known_corrective_rejection_candidate_evaluations=dict(conflict_reasons),
            Unknown_rejection_UIDs_by_reason={k:len(v) for k,v in sorted(reason_uids.items())},
            Unknown_rejection_candidate_evaluations=dict(sorted(reason_candidates.items())),
            rejection_UID_sets_overlap=True,Unknown_candidate_event_count=len(events),
            Unknown_unique_start_eligible_UIDs=len({e['uid'] for e in events if e['start_eligible']}),
            Unknown_legal_feasible_site_ge1_UIDs=len({e['uid'] for e in events if any(c['feasible'] for c in e['candidates'])}),
            occupation_GPUh=float(a['GPU'].sum()/4),compute_GPUh=float(a['compute_GPU'].sum()/4),
            completed_jobs_in_window_compute_GPUh=actual['completed_jobs_in_window_compute_GPUh'],
            IT_kWh=float(a['IT_kw'].sum()/4),PCC_kWh=float(a['PCC_P_kw'].sum()/4),
            PCC_kvarh=float(a['PCC_Q_kvar'].sum()/4),
            controller_P50_seconds=actual['controller_P50_seconds'],controller_P95_seconds=actual['controller_P95_seconds'],
            controller_max_seconds=actual['controller_max_seconds'],controller_scope=actual['controller_latency_scope'],
            controller_tick_count=actual['controller_tick_count'],
            QoS_latest_start_excess_UIDs=sum(r['latest_start_excess_seconds']>0 for r in qos),
            QoS_max_latest_start_excess_seconds=max(r['latest_start_excess_seconds'] for r in qos),
            QoS_unfinished_UIDs=sum(r['unfinished'] for r in qos),
            QoS_window_status_counts=dict(Counter(r['window_status'] for r in qos)),
            source_QoS_metadata_unconfirmed_is_SLA_guarantee=False,
            affine={k:v for k,v in actual.items() if k.startswith('affine_')})
        physical_path=base/'FRESH_16/FRESH_PHYSICAL_SLOTS.json'
        if physical_path.exists():
            slots=read(physical_path);assert len(slots)==16
            peaks=[];all_currents=[];slot_critical=[]
            for row in slots:
                physical=row['physical'];lines=[r for r in physical['currents'] if r['element'].startswith('line.')]
                critical=max(lines,key=lambda r:r['loading_pu']);peaks.append(critical['loading_pu']);slot_critical.append(critical)
                all_currents.extend(r['loading_pu'] for r in lines)
                fresh_rows.append(dict(policy=label,slot=row['slot'],start_seconds=actual['begin_seconds']+900*row['slot'],
                    start_fixed_AEST=local_time(actual['begin_seconds']+900*row['slot']),
                    max_phase_line_loading=critical['loading_pu'],critical_line=critical['element'],
                    critical_phase=critical['phase'],critical_terminal=critical['terminal'],
                    voltage_min_pu=physical['voltage_min_pu'],voltage_max_pu=physical['voltage_max_pu'],
                    voltage_violation_cells=physical['voltage_violation_cells'],
                    line_current_violation_cells=physical['line_current_violation_cells'],
                    transformer_current_violation_cells=physical['transformer_current_violation_cells'],
                    transformer_kVA_violation_cells=physical['transformer_kva_violation_cells'],
                    physical_PASS=row['PASS']))
            index=int(np.argmax(peaks));critical=slot_critical[index]
            f=read(base/'FRESH_16/FRESH_PHYSICAL_RESULT.json')
            summary['Fresh']=dict(status=f['status'],max_phase_line_loading=max(peaks),critical_slot=index,
                critical_interval_start_fixed_AEST=local_time(actual['begin_seconds']+index*900),
                critical_interval_end_fixed_AEST=local_time(actual['begin_seconds']+(index+1)*900),
                critical_line=critical['element'],critical_phase=critical['phase'],critical_terminal=critical['terminal'],
                time_mean_of_16_slot_max_phase_line_loading=float(np.mean(peaks)),
                mean_all_phase_line_terminal_cells=float(np.mean(all_currents)),
                voltage_min_pu=min(r['physical']['voltage_min_pu'] for r in slots),
                voltage_max_pu=max(r['physical']['voltage_max_pu'] for r in slots),
                voltage_violation_cells=f['voltage_violation_cells'],line_current_violation_cells=f['line_current_violation_cells'],
                transformer_current_violation_cells=f['transformer_current_violation_cells'],
                transformer_kVA_violation_cells=f['transformer_kVA_violation_cells'],
                AC_wall_seconds=f['AC_wall_seconds'],physical_SolveSnap_count=f['physical_SolveSnap_count'],
                hardware_11_SVR_original_7_RegControl=True,full96=False)
            physical_vectors[label]=np.array([v for r in slots for v in
                [*(n['voltage_pu'] for n in r['physical']['nodes']),*(n['loading_pu'] for n in r['physical']['currents'])]])
            assert all(r['MESS_plan_sha']==common['common_inputs']['fixed_MESS_plan_sha'] for r in slots)
            for t,r in enumerate(slots):
                assert np.array_equal(r['PCC_P_kw'],a['PCC_P_kw'][t]) and np.array_equal(r['PCC_Q_kvar'],a['PCC_Q_kvar'][t])
        else:summary['Fresh']=dict(status=fresh_status['variants'][label]['status'],actual_evaluation='NOT_CERTIFIED')
        variants[label]=summary
    keys=('Unknown_submitted','Unknown_started','Known_actual_GPU_conflict_UIDs','Known_corrective_commands',
        'occupation_GPUh','compute_GPUh','completed_jobs_in_window_compute_GPUh','PCC_kWh','PCC_kvarh','Known_pending','carryout_jobs')
    delta={k:variants['C1'][k]-variants['C0'][k] for k in keys}
    if len(physical_vectors)==2:
        delta['Fresh_max_absolute_voltage_or_current_array_difference']=float(np.max(np.abs(physical_vectors['C1']-physical_vectors['C0'])))
        for key in ('max_phase_line_loading','time_mean_of_16_slot_max_phase_line_loading','voltage_min_pu','voltage_max_pu'):
            delta['Fresh_'+key]=variants['C1']['Fresh'][key]-variants['C0']['Fresh'][key]
    report=dict(status='MEASURED',scope='FIXED_PR223_M2_FIRST16_DIAGNOSTIC',diagnostic_case_sha=common['diagnostic_case_sha'],
        variants=variants,C1_minus_C0=delta,changed_site_UIDs=completed['changed_site_UIDs'],changed_compute_GPUh=0. if not completed['changed_site_UIDs'] else 'SEE_FUNNEL',
        performance_improvement='NOT_DEMONSTRATED' if completed['changed_site_UIDs']==0 else 'REQUIRES_METRIC_REVIEW',
        common_input_certificate=file_record(OUT/'C0_C1_COMMON_INPUT_CERTIFICATE.json'),
        Fresh_status=file_record(OUT/'C0_C1_FRESH_AC_STATUS.json'),Gurobi_Native_calls=0)
    report['analysis_sha']=digest(report);_write(target,report)
    if fresh_rows:write_csv(OUT/'C0_C1_FRESH_GRID_LOADING_COMPARISON.csv',fresh_rows)
    print(json.dumps(dict(variants=variants,C1_minus_C0=delta),indent=2))


if __name__=='__main__':main()
