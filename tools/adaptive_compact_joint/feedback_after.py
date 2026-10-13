"""Return verified new joint incumbent to beam, without another Optimize."""
from tools.adaptive_compact_joint.adapter import *
from tools.adaptive_compact_joint.beam import generate
from tools.adaptive_compact_joint.compact import integer_proof
from tools.global_local_multistart1800.joint import build_spec
from tools.minimax_beam1800 import grid

def main():
    guard();result=read(DOCS/'PILOT_RESULT.json');valid=[a for a in result['validations'] if a['FULL_PASS']]
    assert valid;selected=min(valid,key=lambda a:(a['UB'],a['label']!='ADAPTIVE'))
    case=v.load_native_case();point=v.load_point(selected['raw']['path']);grid.DOCS=DOCS
    context,_=grid.refresh(case,point,1)
    pools,beam=generate(case,point,context,selected['replay']['path'],size=8,epoch=1)
    spec,lo,hi,A,rhs=build_spec(case,point,selected['replay']['path'],pools,'FEEDBACK_PREVIEW_ONLY',0)
    proof=integer_proof(case,point,spec,lo,hi,A,rhs);assert proof['PASS']
    write(DOCS/'FEEDBACK_PREVIEW_SPEC.json',spec);write(DOCS/'FEEDBACK_PREVIEW_INTEGER_EQUIVALENCE.json',proof)
    previous=read(DOCS/'ADAPTIVE_BEAM_EPOCH_00.json')
    write(DOCS/'POST_PILOT_FEEDBACK_CYCLE.json',dict(PASS=True,Optimize_calls=0,
        full_incumbent=selected,feedback=record(DOCS/'OPTIMIZATION_FEEDBACK_01.json'),
        updated_beam=record(DOCS/'ADAPTIVE_BEAM_EPOCH_01.json'),
        previous_signature=previous['pool_signature'],new_signature=beam['pool_signature'],
        per_unit_new_paths={u:sum(p not in previous['pools'][u] for p in pools[u]) for u in pools},
        next_pool_native0_exact_proof=record(DOCS/'FEEDBACK_PREVIEW_INTEGER_EQUIVALENCE.json'),
        same_fixed_small_size=True,new_solver_dispatch=False,
        reason='Feedback cycle demonstrated using FULL verified pilot Raw. No established gain warrants spending remaining Native budget.'))
    print(json.dumps(dict(PASS=True,Optimize_calls=0,new_pool_signature=beam['pool_signature'])))

if __name__=='__main__':main()
