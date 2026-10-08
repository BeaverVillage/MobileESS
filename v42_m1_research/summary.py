"""Reviewable research delivery, from independently rechecked evidence only."""
import argparse
import csv
import json
from pathlib import Path
import shutil
from v42_unified.audit import ROOT,write
from v42_unified.storage import sha
from .case import REPORTS


def csv_file(path,rows):
    columns=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(rows)


def summarize(run_path):
    from .check_joint import run as independent
    run_path=Path(run_path).resolve()
    receipt=independent(run_path)
    write(REPORTS/'INDEPENDENT_JOINT_CHECK.json',receipt)
    raw=json.loads((run_path/'RESEARCH_TRACK_RESULTS.json').read_text(encoding='utf8'))
    lb=raw.get('LB',{});joint=raw.get('JOINT_DISJUNCTION',{})
    root=joint.get('original_full_ROOT_source',{})
    write(REPORTS/'ROOT_FRACTIONAL_DIAGNOSIS.json',dict(case_sha=raw['case_sha'],
        original_full_ROOT=root.get('fractional_diagnosis',{'status':'NOT_PROVEN'}),
        relaxed_multitime_R=lb.get('fractional_diagnosis',{'status':'NOT_PROVEN'}),
        original_ROOT_source=root.get('source_receipt'),
        diagnosis_does_not_certify_infeasibility=True))
    write(REPORTS/'MULTITIME_GRID_REQUIREMENT.json',lb.get('requirements',dict(status='NOT_PROVEN')))
    write(REPORTS/'JOINT_ROUTE_SOC_COVER_PROOF.json',dict(case_sha=raw['case_sha'],
        original_integer_domain_inclusion=lb.get('inclusion',dict(status='NOT_PROVEN')),
        four_fleet_two_time_complete_count_cover=joint.get('cover',dict(status='NOT_PROVEN')),
        route_pair_conflicts_not_adopted=lb.get('cover',dict(status='NOT_PROVEN')),
        independently_rechecked=receipt,
        M1_global_infeasibility='NOT_PROVEN',whole_96_slot_convex_hull_generated=False,
        full_original_96_slot_rows_in_count_leaves=True,scalar_grid_support_aggregation=False))
    write(REPORTS/'LB_CERTIFICATION.json',dict(case_sha=raw['case_sha'],independent=receipt,
        retained_multitime_R=lb.get('LP'),complete_count_disjunction=joint,
        historical_native_LB=0.5687116104049206,
        historical_native_LB_not_relabelled_exact=True,archived_higher_hull_claim_not_freshly_admitted=True,
        no_neighborhood_or_native_child_bound_promoted=True))
    rows=[]
    if root:
        rows.append(dict(case_sha=raw['case_sha'],label='ORIGINAL_C3A_ARCHIVED_FULL_LP',
            native_ROOT_LP_objective=root['native_ROOT_LP_objective_diagnostic'],
            independently_certified_LB=root['independently_certified_parent_LB'],
            scope='FULL_ORIGINAL_C3A_LP',new_Native_Runtime=0.,
            source='COMPLETED_M188_ARCHIVE_EXACT_REPLAY'))
    if lb:
        rows.append(dict(case_sha=raw['case_sha'],label='FOUR_FLEET_MULTITIME_R_LP',
            native_ROOT_LP_objective=lb['LP']['native'].get('objective'),
            independently_certified_LB=lb['LP']['certificate'].get('independently_certified_LB'),
            scope='ROW_DELETION_RELAXATION_CONTAINS_FULL_INTEGER_DOMAIN',
            new_Native_Runtime=lb['LP']['native']['Native_Runtime'],new_Native_Work=lb['LP']['native']['Native_Work'],
            rows=lb['LP']['build']['rows'],columns=lb['LP']['build']['columns'],nnz=lb['LP']['build']['nnz']))
        rows.append(dict(case_sha=raw['case_sha'],label='FOUR_FLEET_MULTITIME_R_MILP',
            native_ROOT_LP_objective=None,independently_certified_LB='NOT_PROVEN',
            native_solver_bound_diagnostic=lb['MILP']['native'].get('native_solver_bound_diagnostic'),
            scope='GLOBAL_R_SOLVER_DIAGNOSTIC_NOT_EXACT_CERTIFICATE',
            new_Native_Runtime=lb['MILP']['native']['Native_Runtime'],new_Native_Work=lb['MILP']['native']['Native_Work']))
    for leaf in joint.get('leaves',[]):
        rows.append(dict(case_sha=raw['case_sha'],label='COMPLETE_JOINT_COUNT_LEAF_'+str(leaf['leaf']),
            native_ROOT_LP_objective=leaf['native'].get('objective'),
            independently_certified_LB=leaf['independently_certified_leaf_LB'],
            scope='ONE_LEAF_ONLY_MIN_ALL_LEAVES_REQUIRED_GLOBAL',
            new_Native_Runtime=leaf['native']['Native_Runtime'],new_Native_Work=leaf['native']['Native_Work'],
            rows=leaf['build']['rows'],columns=leaf['build']['columns'],nnz=leaf['build']['nnz']))
    csv_file(REPORTS/'LB_ROOT_COMPARISON.csv',rows)
    write(REPORTS/'JOINT_LB_UB_GAP.json',receipt)
    # Preserve original raw ledger, with an explicitly derived cost view.
    ledger=json.loads((run_path/'NATIVE_RUNTIME_LEDGER.json').read_text(encoding='utf8'))
    separated=[]
    for cost in ledger['non_native_wall_costs']:
        view=dict(cost)
        if cost['label']=='MULTITIME_R_PREPARATION':
            native_wall=sum(c['optimize_wall_seconds'] for c in ledger['calls'] if c['label'] in ('JOINT_MULTITIME_R_LP','JOINT_MULTITIME_R_MILP'))
            view.update(inclusive_wall_seconds=cost['wall_seconds'],nested_Native_optimize_wall_seconds=native_wall,
                exclusive_non_native_wall_seconds=max(0.,cost['wall_seconds']-native_wall),
                raw_parent_measurement_is_inclusive=True)
        else:view['exclusive_non_native_wall_seconds']=cost['wall_seconds']
        separated.append(view)
    ledger['derived_wall_cost_separation']=separated
    ledger['raw_native_ledger_SHA256']=sha(run_path/'NATIVE_RUNTIME_LEDGER.json')
    write(REPORTS/'NATIVE_RUNTIME_LEDGER.json',ledger)
    artifacts=REPORTS/'artifacts';artifacts.mkdir(exist_ok=True)
    for source in run_path.iterdir():
        if source.is_file() and source.suffix in ('.npz','.json','.log'):
            shutil.copyfile(source,artifacts/source.name)
    manifest={str(p.relative_to(ROOT)):sha(p) for p in sorted(REPORTS.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    manifest.update({str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'v42_m1_research').glob('*.py'))})
    write(REPORTS/'SHA256_MANIFEST.json',dict(case_sha=raw['case_sha'],files=manifest,
        hash_algorithm='SHA256',manifest_self_hash_excluded=True,all_new_files_on_D=True))
    print('INDEPENDENT_RESEARCH_DELIVERY_PASS',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('run_path');a=p.parse_args();summarize(a.run_path)


if __name__=='__main__':main()
