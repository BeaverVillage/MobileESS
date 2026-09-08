from fast_prepare import *
from v41r4_readback_v2 import validate
from v41r4_runtime import MAY_RUN,MAY_OUT
from dayahead.paper_analysis.storage import write_json
from copy import deepcopy

def main():
    out=MAY_OUT/'readback_regression';out.mkdir(parents=True,exist_ok=True)
    results={d:validate(MAY_RUN/d/'B1/dayahead/A0/bounded_checkpoints') for d in ('2025-05-02','2025-05-03','2025-05-04')}
    evidence=results['2025-05-04']['real_consumption'][0]
    ranking=read(evidence['ranking']['path']);iteration=read(evidence['receipt']['path'])
    rejected=[]
    for label in ('wrong_consumed_order','wrong_net_score','false_compound_flag'):
        folder=out/label;folder.mkdir(exist_ok=True);e=deepcopy(ranking);r=deepcopy(iteration)
        if label=='wrong_consumed_order':r['neighborhood']['consumed_anchor_unit_order']=list(reversed(r['neighborhood']['consumed_anchor_unit_order']))
        elif label=='wrong_net_score':next(u for u in e['ordered_existing_anchor_units'] if u['kind']=='EXISTING_COMPOUND_2')['search_key'][0]+=0.1
        else:r['neighborhood']['compound_net_effect_used_in_ordering']=False
        write_json(folder/'PHYSICS_RANKING_probe.json',e);write_json(folder/'ITERATION_probe.json',r)
        try:validate(folder)
        except AssertionError:rejected.append(label)
        else:raise AssertionError('CORRUPTION_ACCEPTED:'+label)
    save(out/'READBACK_REGRESSION.json',dict(status='PASS',real_days=results,corruptions_rejected=rejected,
        empty_anchor_iterations_remain_NOT_APPLICABLE=True,optimizer_changes=0,optimizer_calls=0,
        source=record(ROOT/'v41r4_readback_v2.py')))
    print('READBACK_REGRESSION_PASS',flush=True)

if __name__=='__main__':main()
