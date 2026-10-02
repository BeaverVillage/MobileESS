"""Read-only consistency guard; never accept a contradictory bound interval."""
import math,sys
from .common import *

def interval(raw_bound,validated_upper):
    upper=min(UB,validated_upper) if validated_upper is not None else UB
    finite=raw_bound is not None and math.isfinite(raw_bound)
    compatible=not finite or raw_bound<=upper+1e-8
    lower=max(LB,raw_bound) if finite and compatible else LB
    return dict(PASS=compatible,raw_BestBd=raw_bound,validated_retained_UB=upper,valid_retained_LB=lower,
        valid_global_gap=max(0.,upper-lower)/abs(upper),solver_bound_used=bool(finite and compatible),
        note='Historical validated UB/LB retained; contradictory solver bound rejected, never turned into a negative-gap acceptance.')

def roots():
    r=read('ROOT_LP_EQUIVALENCE.json')
    a=read(r.get('selected_original_artifact','ROOT_LP_ORIGINAL.json'));b=read(r.get('selected_compact_artifact','ROOT_LP_COMPACT.json'))
    passed=bool(r['PASS'] and all(c.get('objective') is not None and -1e-8<=c['objective']<=UB+1e-8 for c in [a,b]))
    result=dict(PASS=passed,known_independently_validated_UB=UB,root_original=a.get('objective'),root_compact=b.get('objective'),
        condition='Both certified optima are nonnegative and no larger than a known physically feasible full-M1 point; full primal mappings/objective-equivalence gate also required.')
    dump('ROOT_CERTIFICATE_CONSISTENCY.json',result);assert passed,'ROOT_CERTIFICATE_INCONSISTENCY';return result

def canaries():
    a=read('CANARY_ORIGINAL_600S.json');b=read('CANARY_COMPACT_600S.json')
    if a.get('status')=='NOT_RUN' or b.get('status')=='NOT_RUN':return None
    ia=interval(a.get('BestBd'),a.get('validated_UB'));ib=interval(b.get('BestBd'),b.get('validated_UB'))
    certificate=bool(ia['PASS'] and ib['PASS']);start=bool(a.get('start_accepted') and b.get('start_accepted'))
    physical=bool(a.get('validated_UB') is not None and b.get('validated_UB') is not None)
    ratio=(ia['valid_global_gap']-ib['valid_global_gap'])/ia['valid_global_gap'] if ia['valid_global_gap']>0 else 0.
    delta=ib['valid_retained_LB']-ia['valid_retained_LB'];material=ratio>=.20 or delta>=.001
    result=dict(PASS=certificate,original=ia,compact=ib,same_MIP_start_accepted=start,physical_validation_PASS=physical,
        relative_gap_reduction=ratio,valid_LB_improvement=delta,material_computational_improvement=material,
        promising=bool(certificate and start and physical and material),P1_ACCEPTED=bool(certificate and any(c.get('validated_UB') is not None and i['valid_global_gap']<=.005 for c,i in [(a,ia),(b,ib)])),
        no_optimization=True,no_production=True)
    dump('CANARY_CERTIFICATE_AUDIT.json',result)
    # Complete a comparison even if a solver produced no feasible incumbent. Raw
    # worker receipts/solutions/logs remain immutable and are never repaired.
    comp=dict(PASS=certificate,same_MIP_start_accepted=start,physical_validation_PASS=physical,
        relative_gap_reduction=ratio,valid_LB_improvement=delta,material_computational_improvement=material,promising=result['promising'],
        original=dict(UB=ia['validated_retained_UB'],LB=ia['valid_retained_LB'],gap=ia['valid_global_gap'],nodes=a.get('nodes_processed')),
        compact=dict(UB=ib['validated_retained_UB'],LB=ib['valid_retained_LB'],gap=ib['valid_global_gap'],nodes=b.get('nodes_processed')),
        raw_original_solver_UB=a.get('validated_UB'),raw_compact_solver_UB=b.get('validated_UB'),
        certificate_audit_artifact='CANARY_CERTIFICATE_AUDIT.json',root_relaxation_equivalent=read('ROOT_LP_EQUIVALENCE.json')['PASS'],
        resource_comparison='Same hardware/settings and sequential lane; inspect resource receipts and disclosed read-only primary-root audits. No historical absolute speedup claim.',
        historical_speedup_claim=False,production_1800_run=False)
    if (OUT/'CANARY_COMPARISON.json').exists():dump('CANARY_COMPARISON_WORKER.json',read('CANARY_COMPARISON.json'))
    dump('CANARY_COMPARISON.json',comp);return result
if __name__=='__main__':
    if sys.argv[1]=='roots':print(roots(),flush=True)
    elif sys.argv[1]=='canaries':print(canaries(),flush=True)
    else:raise ValueError(sys.argv[1])
