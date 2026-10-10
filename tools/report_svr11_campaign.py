"""Read-only same-date performance comparisons, separate from own PASS cohorts."""
from pathlib import Path
import sys,itertools,statistics,csv
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic,read,now,record
from v42_svr11 import DAYS,ORDER
from v42_svr11.authority import verify

METRICS=('Vmin','Vmax','maximum_line_loading','losses_kWh','losses_kvarh','Planning_objective','Native_Runtime','wall_seconds')

def value(row,name):
    return row.get(name) if name in ('Planning_objective','Native_Runtime','wall_seconds') else row.get('metrics',{}).get('environments',{}).get('ACTUAL',{}).get(name)

def summary(rows):
    out={}
    for name in METRICS:
        values=[value(r,name) for r in rows];values=[v for v in values if isinstance(v,(int,float))]
        out[name]=dict(n=len(values),mean=statistics.mean(values) if values else None,
            minimum=min(values) if values else None,maximum=max(values) if values else None)
    return out

def run(root):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json');rows=list(ledger['dates'].values())
    cohorts=[];paired=[];date_table=[]
    for arm in ORDER:
        axis=[r for r in rows if r['arm']==arm];good=[r for r in axis if r['status']=='PASS']
        cohorts.append(dict(arm=arm,PASS_dates=[r['day'] for r in good],FAIL_dates=[r['day'] for r in axis if r['status']=='FAIL'],
            population='This policy own PASS dates only; do not compare unequal cohorts as causal policy improvement',performance=summary(good)))
    for a,b in itertools.combinations(ORDER,2):
        days=[d for d in DAYS if ledger['dates'][a+'/'+d]['status']==ledger['dates'][b+'/'+d]['status']=='PASS']
        comparison={}
        for name in METRICS:
            delta=[]
            for day in days:
                x,y=value(ledger['dates'][a+'/'+day],name),value(ledger['dates'][b+'/'+day],name)
                if isinstance(x,(int,float)) and isinstance(y,(int,float)):delta.append(dict(day=day,a=x,b=y,b_minus_a=y-x))
            comparison[name]=dict(n=len(delta),mean_b_minus_a=statistics.mean(v['b_minus_a'] for v in delta) if delta else None,dates=delta)
        paired.append(dict(policies=[a,b],same_PASS_dates=days,n=len(days),metrics=comparison))
    for r in rows:
        attempts=[]
        for request in r['attempts']:
            rp=Path(read(request)['result'])
            if rp.exists():
                v=read(rp);attempts.append(dict(result=record(rp),status=v['status'],Native_Runtime=v.get('Native_Runtime'),
                    known_completed_Native_Runtime=v.get('known_completed_Native_Runtime'),Native_Runtime_uncertain=v.get('Native_Runtime_uncertain'),reason=v.get('reason')))
        date_table.append(dict(arm=r['arm'],day=r['day'],status=r['status'],reason=r.get('reason'),
            latest_performance={k:value(r,k) for k in METRICS},FULL_feasible_certified=r.get('FULL_feasible_certified'),
            global_gap_certified=r.get('global_gap_certified'),optimization_status=r.get('optimization_status'),AC_status=r.get('AC_status'),attempts=attempts,
            controls_and_physical_evidence={ns:{k:metrics.get(k) for k in (
                'slots','voltage_violations','line_current_violations','transformer_current_violations',
                'transformer_nameplate_current_violations','transformer_kVA_violations','AC_converged','control_complete',
                'SVR_bank_count','original_RegControl_count','SVR_tap_ranges','original_RegControl_tap_ranges','phase_tap_operation_evidence')}
                for ns,metrics in r.get('metrics',{}).get('environments',{}).items()}))
    terminal=sum(r['status'] in ('PASS','FAIL') for r in rows)
    out=dict(status='COMPLETE' if terminal==124 and not any(r.get('retry_pending') for r in rows) else 'IN_PROGRESS',completed=terminal,total=124,
        source_SHA=m['execution_SHA'],equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],campaign_root=str(root),
        policy_own_PASS_cohorts=cohorts,paired_same_date_comparisons=paired,dates=date_table,retrospective_design=True,
        independent_holdout_claim=False,Native_limit_basis='Measured cumulative per stage within each explicitly fresh attempt; previous attempts retained',
        tap_interaction_assessment=dict(
            serial_banks=['BUS82','BUS83'],added_downstream_banks=['BUS86','BUS62'],
            assessment='All eleven banks and original seven RegControls operate jointly in each independent chronological Planning/Actual context. Per-phase tap ranges/change counts and full slot evidence are retained for joint response assessment. Series BUS82/BUS83 and upstream RegControl interaction remain possible; voltage PASS alone does not prove absence of interference. No comparative siting or isolated-control AC experiment was performed.',
            evidence='dates[].controls_and_physical_evidence: all SVR phases and original RegControl tap ranges, physical limits, exact full-slot receipt SHA'),
        B0_Planning_objective_note='B0 FCFS has no MILP objective; null is not a zero objective',verifier=record(Path(__file__)),UTC=now())
    atomic(root/'PERFORMANCE_COMPARISON.json',out)
    lines=['# SVR11 campaign performance comparison',f"{out['status']}: {terminal}/124 dates terminal.",
        f"Scientific Source SHA: `{m['execution_SHA']}`",'Policy own PASS cohorts and paired same-date populations are separate. B0 has no MILP objective.',
        '| Policy | Own PASS | Current FAIL | Actual peak line loading mean | Actual losses kWh mean |','|---|---:|---:|---:|---:|']
    for c in cohorts:
        perf=c['performance'];lines.append(f"| {c['arm']} | {len(c['PASS_dates'])} | {len(c['FAIL_dates'])} | {perf['maximum_line_loading']['mean']} | {perf['losses_kWh']['mean']} |")
    lines += ['','Pairwise deltas use only dates where both policies PASS. A lower failure rate and a smaller mean on a different PASS population are not an unbiased policy comparison.','']
    for p in paired:lines.append(f"- {p['policies'][0]} / {p['policies'][1]}: {p['n']} common PASS dates; exact dates and numerical deltas in PERFORMANCE_COMPARISON.json.")
    lines += ['','All failed attempts and measured/unknown Native Runtime remain linked, even when the final date attempt PASSes. May2025 is retrospective and is not an independent holdout.']
    lines += ['',out['tap_interaction_assessment']['assessment']]
    (root/'PERFORMANCE_COMPARISON.md').write_bytes(('\n\n'.join(lines)+'\n').encode())
    return out

if __name__=='__main__':
    r=run(sys.argv[1]);print(r['status'],r['completed'],'/124')
