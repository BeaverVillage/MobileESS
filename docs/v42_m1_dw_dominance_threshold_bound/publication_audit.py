"""Read-only native log observations and stopped-gate publication metadata."""
from v42_dw_dominance.common import *
from v42_dw_dominance.finalize import manifest
import re

def audit():
    diagnosis=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json')
    for row in diagnosis['per_MESS']:
        p=PR142/'logs'/f"PRICE_{row['call']:04d}_{row['MESS']}.log"
        lines=p.read_text(encoding='utf8',errors='replace').splitlines()
        root=next((x.strip() for x in reversed(lines) if x.strip().startswith('Root relaxation:')),None)
        match=re.search(r'([\d.]+) seconds',root or '')
        row.update(root_relaxation_native_duration_seconds=float(match[1]) if match else None,root_relaxation_literal=root,exact_elapsed_root_completion_time=None,root_time_scope='Literal native root relaxation phase duration; not exact wall time since pricing start and not root-processing completion. Rounded objective/cutoff message is not an exact global bound.')
    diagnosis['root_time_observation_scope']='Native phase duration recorded even for cutoff; exact completion timestamps and exact root LP bounds unavailable in historical receipts remain NULL.'
    write('DW_PRICING_BOUND_DIAGNOSIS.json',diagnosis);table('DW_PRICING_BOUND_WEAKNESS.csv',diagnosis['per_MESS'])
    write('PREOPT_INVOCATION_DIAGNOSTICS.json',dict(native_experiment_optimize_calls=0,initial_errors=['NameError: SOURCE not imported into new namespace','Wrong REF namespace for the A1 freeze file'],corrected=True,complete_matrix_and_1158_column_audit_rerun=True,scientific_base_modified=False,error_logs=['PREPARE.log','PREPARE_SECOND.log'],old_pricing_replayed=False))
    write('PREREGISTRATION_COMMITS.json',dict(base_head=BASE_HEAD,preregistration_commit='f38aacec9989536adabd6c847fb247a732abc27e',source_freeze_commit='95208030bffab15631d1083a9d20b4062c57a506',before_any_native_test_optimize=True,full_scale_experiment_optimize_calls=0,automatic_budget_extension=False))
    report=OUT/'FINAL_REVIEW_KO.md';text=report.read_text(encoding='utf8')
    text=text.replace('Root relaxation 완료 시간도 objective가 노출된 로그만 기재했다.', 'Root relaxation의 native phase duration은 cutoff 로그까지 별도 기재했다. 정확한 root 완료 wall timestamp는 NULL이다.')
    report.write_text(text,encoding='utf8')
    description='''The requested PR142 scalar floor is stored as the terminal global ObjBound of an interrupted integer MIP. The original arc-LP receipts store primal objectives and primal points, the root message is rounded, and exact root BestBd was not exposed. Numerical agreement does not prove that this scalar is a lower bound on the original arc LP. A global integer-MIP lower bound cannot automatically be transferred to the D-W root through local convexification.

Proves conv(X_m^I) subseteq P_m^arc and the full projected feasible-set inclusion on the frozen actual model. Independently audits all 1,158 retained columns, all 75,455 byte-identical duplicate rows, unchanged original axes/coupling/bounds/objective/global freedom, and seven exhaustive exact-rational fixtures. Stops before new CG and leaves the independent scalar floor NULL. The conditional [0.5687116103498322, 0.5836817975103938] calculation is explicitly not a certified interval; the retained certified interval is [0.5215744487783405, 0.5836817975103938].

PR142 pricing diagnosis is TRUE_NEGATIVE_RC_DOMINANT: all four final pricers OPTIMAL, zero native gap, summed genuine negative RC magnitude 0.07922906385001029 and proof-gap room about 1e-17. Incumbents are diagnostic only. Recover an original-axis arc-LP lower certificate first; after that gate, continue the registered fixed four-way smoothed threshold discovery policy. No pricing formulation strengthening or speed tuning is implemented.

Validation: semantic 361 / full pytest 1808 pass (one unchanged log1p warning), all native regression solves Threads=1 and nonoverlapping. Independent Fraction reconstruction of PR141 and PR142 pricing certificates passes; every previous tracked byte is preserved. New full-scale RMP/pricing/columns: 0/0/0. No B&P, May/Actual/Fresh AC, production M1/P2/A2/M2 calls. Worker policy 4/1/4/1, B2 inner1/B3 inner4 preserved. This draft records a failed lower-floor authority gate, not a completed threshold experiment.
'''
    (OUT/'PR_DESCRIPTION.md').write_text(description,encoding='utf8');manifest()

if __name__=='__main__':audit()
