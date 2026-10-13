"""Matched Native0 preparation benchmark; no solver creation or Optimize."""
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.cache import get,fast_save
from tools.adaptive_compact_joint.direct import save

def main():
    configure();full_guard();reference=read(DOCS/'CACHE_NATIVE0_EQUIVALENCE.json');spec=read(reference['old_spec']['path'])
    case=v.load_native_case();point=v.load_point(spec['center_raw']['path']);results={}
    for form in ('UNCHANGED_PREPARATION','CACHED_PREPARATION'):
        timer=Timing();folder=DOCS/'benchmark'/form
        if form=='UNCHANGED_PREPARATION':
            with timer.stage('unchanged_prepare_with_all_alias_proofs_and_packets'):model,proof=save(case,point,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],folder)
        else:
            cache=get(case,timer);model,proof=fast_save(case,point,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],folder,cache,timer)
        assert model['compact_matrix_SHA']==spec['compact_matrix_SHA'] and model['compact_domain_SHA']==spec['compact_domain_SHA'] and model['lift_SHA']==spec['lift_SHA']
        results[form]=dict(PASS=True,timing=timer.receipt(),spec=record(folder/'SPEC.json'),memory=r.memory())
        print(json.dumps(dict(form=form,timing=timer.receipt())),flush=True)
    write(DOCS/'MATCHED_PREPARATION_COMPARISON.json',dict(PASS=True,Optimize_calls=0,Source_Case_pool_Start_and_packets_equal=True,records=results,
        wall_reduction_seconds=results['UNCHANGED_PREPARATION']['timing']['total_wall']-results['CACHED_PREPARATION']['timing']['total_wall'],
        cache_creation_cost_separate=reference['timing']['parts']['static_cache_creation_alias_proof']))
if __name__=='__main__':main()
