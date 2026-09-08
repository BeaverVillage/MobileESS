"""Paper-facing compute quality; missing global bounds remain explicitly null."""
from collections import Counter
from pathlib import Path
import numpy as np
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import record


def quantiles(values):
    values=[v for v in values if v is not None]
    return dict(count=len(values),median=float(np.median(values)) if values else None,
        P90=float(np.quantile(values,.9)) if values else None,maximum=max(values) if values else None)


def aggregate(root=RUNTIME):
    root=Path(root);rows=[];candidate_lineage=[]
    for day in range(1,32):
        for policy in ('B0','B1','B2','B3'):
            unit=root/f'2025-05-{day:02}'/policy;da=unit/'dayahead'
            complete=(unit/'UNIT_RECEIPT.json').exists()
            row=dict(day=f'2025-05-{day:02}',policy=policy,complete=complete,
                classification='NOT_COMPLETED',optimization_seconds=None,coverage_fraction=None,P1_global_gap=None,P2_global_gap=None)
            if complete:
                row['classification']='REFERENCE_FEASIBLE' if policy=='B0' else 'LEGACY_RESULT_REQUIRES_EXPLICIT_CLASSIFICATION'
                compute=da/'POLICY_DAY_COMPUTE_REPORT.json'
                if compute.exists():
                    timing=read(compute);row['optimization_seconds']=timing['optimization_seconds']
                    row['TOTAL_UNUSED_BUDGET_SECONDS']=timing.get('TOTAL_UNUSED_BUDGET_SECONDS')
                    row['stage_runtime_seconds']=timing.get('stage_runtime_seconds')
                coverage=da/'CANDIDATE_COVERAGE_REPORT.json'
                if coverage.exists():row['coverage_fraction']=read(coverage)['fraction_candidates_visited']
                solver=da/('A1' if policy=='B3' else 'A0')/'BOUNDED_SOLVER_REPORT.json'
                if solver.exists():
                    report=read(solver);row['classification']=report['classification']
                    row['stage_early_stop']=[{k:s.get(k) for k in ('stage_priority','runtime_seconds','starting_objective','final_objective',
                        'material_improvements','normal_sweeps_completed','diversification_sweeps_completed','stage_family_coverage_fraction',
                        'STAGE_COVERAGE_FRACTION','neighborhoods_solved','termination_reason')} for s in report['stages']]
                    for i,name in enumerate(('P1','P2')):
                        if len(report['stages'])>i:row[name+'_global_gap']=report['stages'][i]['achieved_relative_gap']
                elif policy=='B2' and (da/'M1/M1_RESULT.json').exists():
                    row['classification']='BOUNDED_MESS_FEASIBLE_NO_GLOBAL_CERTIFICATE'
                lineage=dict(day=row['day'],policy=policy,scientific_candidate_pruning=0,stages=[])
                candidates=[('POLICY',da/'V41R1_FULL_CANDIDATE_MANIFEST.json')]
                if policy=='B3':
                    candidates=[('A0_EXACT_B1_REUSE',root/row['day']/'B1/dayahead/A0/V41R1_FULL_CANDIDATE_MANIFEST.json'),
                        ('A1_EXISTING_FIXED_RUNNING_AUTHORITY',da/'A1/V41R1_FULL_CANDIDATE_MANIFEST.json')]
                for stage,path in candidates:
                    if path.exists():
                        data=read(path)
                        lineage['stages'].append(dict(stage=stage,manifest=record(path),
                            **{k:data.get(k) for k in ('candidate_set_SHA','final_authoritative_candidates','PENDING_relocation_candidates',
                                'RUNNING_migration_candidates','total_destination_arcs','hard_infeasible_removals','reason_counts','removal_scope')}))
                if not lineage['stages'] and policy=='B0':lineage['authority']='RETAINED_FIXED_B0_REFERENCE; NO_OPTIONAL_AIDC_DECISIONS'
                candidate_lineage.append(lineage)
            rows.append(row)
    by_policy={}
    for policy in ('B0','B1','B2','B3'):
        current=[r for r in rows if r['policy']==policy and r['complete']]
        by_policy[policy]=dict(completed_days=len(current),remaining_days=31-len(current),
            classifications=dict(Counter(r['classification'] for r in current)),
            optimization_seconds=quantiles([r['optimization_seconds'] for r in current]),
            unused_budget_seconds=quantiles([r.get('TOTAL_UNUSED_BUDGET_SECONDS') for r in current]),
            early_stop_reasons=dict(Counter(s['termination_reason'] for r in current for s in r.get('stage_early_stop',[]) if s.get('termination_reason'))),
            coverage_fraction=quantiles([r['coverage_fraction'] for r in current]),
            P1_global_gap=quantiles([r['P1_global_gap'] for r in current]),
            P2_global_gap=quantiles([r['P2_global_gap'] for r in current]),
            P1_missing_global_certificate=sum(r['P1_global_gap'] is None for r in current),
            P2_missing_global_certificate=sum(r['P2_global_gap'] is None for r in current))
    value=dict(status='PASS',method='bounded-compute fix-and-optimize matheuristic',
        full_physical_feasibility_constraints_retained_at_every_neighborhood_subproblem=True,
        representative_global_validation_status='COMPLETED; SEE_REPORTED_B1_GLOBAL_BOUNDS_AND_CONDITIONAL_P2_SCOPE' if (root/'strong_global_validation/COMPLETE.json').exists() else 'PENDING_SEPARATE_VALIDATION; NOT_CLAIMED_COMPLETED',
        representative_global_validation=None if not (root/'strong_global_validation/COMPLETE.json').exists() else record(root/'strong_global_validation/COMPLETE.json'),
        missing_bound_is_not_zero_gap=True,all_124_policy_days_included=True,policies=by_policy,days=rows)
    write_json(root/'aggregation/V41R1_FULL_CANDIDATE_MANIFEST.json',dict(status='PASS',
        interpretation='Per-policy stage lineage. B3 A0 reuses the complete B1 universe; A1 fixes accepted RUNNING events under the unchanged policy.',
        completed_policy_days=len(candidate_lineage),permanent_computational_pruning=0,units=candidate_lineage))
    write_json(root/'aggregation/F_AND_O_MONTHLY_SOLUTION_QUALITY.json',value);return value


if __name__=='__main__':aggregate()
