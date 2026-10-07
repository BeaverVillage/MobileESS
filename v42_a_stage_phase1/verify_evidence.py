"""Postsolve audit of completed certificates only; no new pool search/solve."""
from pathlib import Path
from fractions import Fraction
import csv,subprocess
import numpy as np
from v42_pr134_b1.common import read,record,atomic,table
from .setup import OUT,STATIC,POLICY
from .oracle import validate_coverage


def verify_partial():
    result=read(OUT/'MAY19/PHASE1_RESULT.json');ledger=read(OUT/'MAY19/NATIVE_CALLS.json')
    calls=ledger['calls'];used=sum(c['native_seconds'] or 0 for c in calls)
    if abs(used-result['native_seconds'])>1e-8 or abs(used-ledger['cumulative_native_seconds'])>1e-8:
        raise ValueError('FINAL_NATIVE_LEDGER_MISMATCH')
    ids=[c['folder'] for c in calls]
    if len(ids)!=len(set(ids)):raise ValueError('DUPLICATED_NATIVE_CALL_LEDGER')
    master=next(c for c in calls if c['component']=='PHASE_I');identity=read(master['model_identity']['path'])
    with np.load(master['raw_attributes']['path']) as archive:pi=archive['Pi'].copy()
    with np.load(identity['attributes']['path']) as archive:senses=archive['senses']
    construction=read(OUT/'PHASE1_CONSTRUCTION_VERIFICATION.json')
    if record(construction['weights']['path'])!=construction['weights']:raise ValueError('FROZEN_WEIGHT_DRIFT')
    with np.load(construction['weights']['path']) as archive:weights={k:archive[k] for k in archive.files}
    for row,w in zip(weights['rows'],weights['weights']):
        sense=senses[row]
        pi[row]=min(w,max(-w,pi[row])) if sense=='=' else min(0.,max(-w,pi[row])) if sense=='<' else max(0.,min(w,pi[row]))
    expected=pi[read(OUT/'INITIAL_COUPLING_AXES.json')['rows']]
    qualified={r['class_id']:r for r in read(OUT/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    paths=sorted((OUT/'MAY19/C1/R0/B').glob('*/EXACT_COMPLETE_BLOCK_CERTIFICATE.json'))
    receipts=[read(p) for p in paths]
    complete_ids={r['class_id'] for r in receipts}
    validate_coverage({key:qualified[key] for key in complete_ids},receipts,expected)
    epsilon=Fraction(POLICY['epsilon_price'])
    coverage=dict(PASS=True,scope='INDEPENDENT_RECHECK_OF_ALREADY_COMPLETED_CERTIFICATES_ONLY',
        complete_pool_pricing_PASS=False,total_classes=len(qualified),certified_classes=len(receipts),
        missing_classes=sorted(set(qualified)-complete_ids),
        certified_physical_STAY=sum(r['physical_STAY'] for r in receipts),
        certified_physical_migration=sum(r['physical_migration'] for r in receipts),
        certified_compact_blocks=sum(r['complete_compact_blocks'] for r in receipts),
        unexamined_physical_STAY=sum(r['full_physical_STAY'] for key,r in qualified.items() if key not in complete_ids),
        unexamined_physical_migration=sum(r['full_physical_migration'] for key,r in qualified.items() if key not in complete_ids),
        negative_block_directions=sum(Fraction(r['oracle_point_price']) < -epsilon for r in receipts),
        exact_negative_physical_STAY_count=None,exact_negative_physical_migration_count=None,
        minimum_completed_block_rc_lower_bound=str(min(Fraction(r['minimum_rc_lower_bound']) for r in receipts)),
        minimum_omitted_rc_over_full_domain=None,full_domain_LP_infeasibility_proven=False,
        closure_not_inferred_from_partial_scan=True,bounds_recomputed_from_frozen_native_blocks=True,
        actual_master_Pi_reprojected_independently=True,native_seconds=used,pricing_wall_seconds=result['pricing_wall_seconds'],
        conservative_charged_total=used+result['pricing_wall_seconds'],
        charged_total_soft_stop_overshoot=max(0.,used+result['pricing_wall_seconds']-POLICY['native_plus_pricing_wall_seconds']),
        actual_master_extra_optimize_calls=0,actual_reused_first_block_extra_optimize_calls=0,
        new_native_optimize_calls=0,no_unexamined_block_priced_by_this_audit=True)
    atomic(OUT/'MAY19/PRICING_PARTIAL_COVERAGE.json',coverage)
    rows=[dict(class_id=r['class_id'],physical_STAY=r['physical_STAY'],physical_migration=r['physical_migration'],
        compact_blocks=r['complete_compact_blocks'],minimum_rc_lower_bound=r['minimum_rc_lower_bound'],
        point_price=r['oracle_point_price'],exact_native_lower_bound=r['certificate']['exact_lower_bound']) for r in receipts]
    table(OUT/'MAY19/COMPLETED_BLOCK_PRICING_TRACE.csv',rows,list(rows[0]))
    atomic(OUT/'MAY19/ENGINEERING_STOP.json',dict(PASS=True,primary_classification=result['classification'],
        stop_reason=result['error'],unused_native_seconds=POLICY['cumulative_native_seconds']-used,
        additional_native_calls_authorized=False,native_plus_pricing_wall_exhausted=True,
        accepted_dates=[],May17_calls=0,May12_calls=0,May10_calls=0,Planning_calls=0,Actual_calls=0,Fresh_calls=0))
    return coverage


def supplement():
    coverage=verify_partial()
    verification=read(OUT/'VERIFICATION.json')
    verification['partial_pricing_independent_verification']=record(OUT/'MAY19/PRICING_PARTIAL_COVERAGE.json')
    verification['postsolve_auditor_source']=record(__file__)
    atomic(OUT/'VERIFICATION.json',verification)
    path=OUT/'FINAL_REVIEW_KO.md';text=path.read_text(encoding='utf8')
    statement=(f"실제 complete-block pricing은 {coverage['certified_classes']}/{coverage['total_classes']} class에서 완료했습니다. "
        f"이 범위의 physical STAY={coverage['certified_physical_STAY']:,}, migration={coverage['certified_physical_migration']:,}, "
        f"compact blocks={coverage['certified_compact_blocks']:,}이며 음의 block direction={coverage['negative_block_directions']}개를 발견했습니다. "
        "남은 class를 가격 계산하지 않았으므로 complete STAY/migration closure=False이며 전체 omitted minimum rc와 physical negative candidate count는 미측정입니다. "
        "저장된 모든 완료 certificate의 bound를 원본 frozen cache와 실제 master Pi에서 독립 재계산했습니다.")
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if line.startswith('15. '):lines[i]=line+' '+statement
        if line.startswith('16. '):lines[i]=line+' 실제 누락 class='+str(len(coverage['missing_classes']))+'; full pricing PASS=False.'
        if line.startswith('17. '):lines[i]=line+' 완료 subset block lower bound minimum='+coverage['minimum_completed_block_rc_lower_bound']+'; full-domain minimum과 다릅니다.'
        if line.startswith('26. '):lines[i]=line+f" 보수적으로 charge한 native+pricing={coverage['conservative_charged_total']:.6f}s, 600s soft-stop overshoot={coverage['charged_total_soft_stop_overshoot']:.6f}s."
    lines.extend(['',statement])
    path.write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
    # Preserve raw/canonical trace. This is an explicitly labelled derivative.
    with (OUT/'MAY19/PHASE1_ITERATION_TRACE.csv').open(encoding='utf8') as f:rows=list(csv.DictReader(f))
    for row in rows:
        row['pricing_classes_completed']=coverage['certified_classes'];row['pricing_classes_required']=coverage['total_classes']
        row['pricing_wall_seconds']=coverage['pricing_wall_seconds'];row['full_domain_minimum_rc']='UNMEASURED_PARTIAL_SCAN'
        row['closure_status']='INCOMPLETE_PRICING_ENGINEERING_STOP'
        row['notes']+='; partial pricing coverage is in PRICING_PARTIAL_COVERAGE.json; original raw trace preserved'
    table(OUT/'MAY19/PHASE1_ITERATION_TRACE_REVIEWED.csv',rows,list(rows[0]))
    print('COMPLETED_CERTIFICATES_INDEPENDENTLY_VERIFIED',coverage['certified_classes'],coverage['negative_block_directions'],flush=True)


if __name__=='__main__':supplement()
