"""Read-only post-pilot optimization feedback and explicit backend rejection."""
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.adaptive_compact_joint.fresh_feedback import generate
from tools.global_local_multistart1800.joint import build_spec
from tools.adaptive_compact_joint.compact import integer_proof

def main():
    guard();state=read(DOCS/'FINAL_STATE.json');assert state['PASS']
    valid=[q for q in state['validations'] if q['FULL_PASS']];assert valid
    selected=min(valid,key=lambda q:q['UB'])
    case=v.load_native_case();point=v.load_point(selected['dense_lift']['path'])
    seen={read(c['model']['path'])['pool_signature'] for c in state['Native_calls']}
    pools,signature=generate(case,point,selected['replay']['path'],1,seen)
    spec,lo,hi,A,rhs=build_spec(case,point,selected['replay']['path'],pools,'POST_PILOT_FEEDBACK_PREVIEW',0)
    proof=integer_proof(case,point,spec,lo,hi,A,rhs);assert proof['PASS']
    write(DOCS/'POST_PILOT_FEEDBACK_SPEC.json',spec);write(DOCS/'POST_PILOT_FEEDBACK_INTEGER_EQUIVALENCE.json',proof)
    decision=read(DOCS/'PILOT_CONTINUATION_DECISION.json')
    write(DOCS/'FINAL_BACKEND_DECISION.json',dict(PASS=True,Optimize_calls=0,selected_baseline_backend='SOURCE_EXACT_JOINT_EXTENDED_FORMULATION',
        direct_substitution_adopted=False,source_physics_and_joint_route_decision_kept=True,
        reason='Exact direct model shrinks columns but same-pool Native Runtime worsens; no FULL UB improvement. Reject compute-disadvantaged formulation and do not consume remaining budget.',
        same_pool_comparison=decision,post_pilot_verified_feedback=record(DOCS/'OPTIMIZATION_FEEDBACK_01.json'),
        adapted_fixed_small_pool=record(DOCS/'FEEDBACK_POOL_01.json'),new_pool_signature=signature,
        duplicate_previous_pool=signature in seen,updated_pool_native0_proof=record(DOCS/'POST_PILOT_FEEDBACK_INTEGER_EQUIVALENCE.json'),
        new_native_dispatch=False,exact_pricing_or_column_generation_claim=False,
        improved_UB=False,physical_improvement_limit_proven=False))
    print(json.dumps(dict(PASS=True,Optimize_calls=0,new_pool_signature=signature,direct_adopted=False)))

if __name__=='__main__':main()
