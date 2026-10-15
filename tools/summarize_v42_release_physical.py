"""UID rejection funnel and exact all-substep failure summary; no AC rerun."""
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def main():
    target=OUT/'PHYSICAL_GATE_AND_REJECTION_SUMMARY.json'
    if target.exists():raise FileExistsError('PHYSICAL_SUMMARY_MUST_NOT_OVERWRITE')
    diag=read(OUT/'ASOF_SUBSTEP_PHYSICAL_DIAGNOSIS.json')
    rows=read(OUT/'ASOF_PREFIX_ALL_SUBSTEP_RAW.json')
    bad=[r for r in rows if not r['PASS']]
    lines=[dict(r,slot=x['slot'],native_seconds=x['native_seconds']) for x in rows for r in x['physical']['currents'] if r['element'].lower().startswith('line.')]
    worst=max(lines,key=lambda r:r['loading_pu'])
    first=bad[0] if bad else None
    control=None
    if first:
        i=rows.index(first)
        control=dict(current=first['SVR'],previous=None if not i else rows[i-1]['SVR'],
            queued_event=first['event'],inputs_held_during_slot=True,
            no_unknown_yet_submitted=first['native_seconds']<966.,
            first_native_seconds=first['native_seconds'],highest_node=first['highest_node'])
    funnels={}
    for c in ('C0','C1'):
        events=read(OUT/c/'PENDING_PRE_SITE_LEDGER.json');reasons={};counts=Counter()
        for e in events:
            stay=e['candidates'][0];reason=stay['reason']
            if reason:reasons.setdefault(reason,set()).add(e['uid']);counts[reason]+=1
        jobs=read(OUT/c/'JOB_EVENT_LEDGER.json')
        rejected=[r for r in jobs if 'CURRENT_CANDIDATE_AC' in str(r.get('reason',''))]
        funnels[c]=dict(STAY_rejection_events=dict(counts),STAY_rejected_UIDs={k:sorted(v) for k,v in reasons.items()},
            STAY_rejected_unique_UID_counts={k:len(v) for k,v in reasons.items()},
            current_AC_rejected_job_event_UIDs=sorted({r['uid'] for r in rejected}),
            current_AC_rejected_job_event_count=len(rejected))
    summary=dict(status='PHYSICAL_FAIL_ASOF_SUBSTEPS',Gate2='FAIL_PHYSICAL_SUBSTEP_TRAJECTORY',
        all_actual_start_instant_AC_proofs='PASS_SEPARATE_INDEPENDENT_ACTUAL_CERTIFICATE',
        current_same_input_3_start_crosscheck='PASS',retrospective_offline_Fresh_settled_first16='PASS',
        asof_all_substeps=diag['physical_substeps'],asof_violating_substeps=len(bad),
        violating_event_kinds=dict(Counter(r['event']['kind'] for r in bad)),
        asof_voltage_min_pu=diag['min_voltage_pu'],asof_voltage_max_pu=diag['max_voltage_pu'],
        asof_max_phase_line_loading=worst['loading_pu'],worst_line=worst,
        violation_cells={k:sum(r['physical'][k] for r in rows) for k in rows[0]['physical'] if k.endswith('violation_cells')},
        asof_last_solve_all_slots_PASS=diag['settled_last_solve_all_PASS'],
        first_violation_control_comparison=control,Unknown_rejection_funnels=funnels,
        attribution='FIRST_VIOLATION_DURING_ORIGINAL_NATIVE_QUEUED_AUTO_ACTION_WITH_FIXED_SLOT_INPUTS;EXACT_PT_LDC_SVR_CAUSE_NOT_CHANGED_OR_CLAIMED_RESOLVED',
        voltage_limits=[.95,1.05],control_parameters_changed=False,unsafe_running_jobs_dropped=False,
        source=file_record(__file__),Native_calls=0,AC_calls=0)
    _write(target,summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('first_violation_control_comparison','Unknown_rejection_funnels')},indent=2))

if __name__=='__main__':main()
