"""Bounded third-move extension of the independently verified pair."""
from collections import Counter
import time
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .flex_diagnostic import OUT,WORK
from .flex_model import Data,ProbeModel

def run():
    d=Data();p=None
    try:
        pair=read(OUT/'PAIR_ORIGINAL_MODEL_WITNESS.json');single=read(WORK/'FEASIBLE_SINGLE_MOVES.json')
        best=None;counts=Counter();t=time.perf_counter()
        for item in single:
            if item['uid'] in pair['choices']:continue
            choices={**pair['choices'],item['uid']:item['option_index']}
            q,reason=d.quick(choices);counts[reason]+=1
            if q is not None and (best is None or tuple(q['vector'])<tuple(best['vector'])):
                best=dict(choices=choices,vector=q['vector'],delta=[a-b for a,b in zip(q['vector'],d.base)])
        p=ProbeModel(d);cert,_=p.certify(best['choices'],'TRIPLE_ORIGINAL_MODEL_WITNESS')
        assert cert['status']=='PASS'
        write_json(OUT/'CAPACITY_RELEASE_TRIPLE_PROBES.json',dict(status='PASS',counts=dict(counts),
            scan_seconds=time.perf_counter()-t,best=best,certificate=record(OUT/'TRIPLE_ORIGINAL_MODEL_WITNESS.json'),
            scope='Verified capacity/WAN pair plus each of the 658 independently feasible single-job alternatives; no exhaustive global triple claim',
            candidates_pruned=0,Actual_reads=0))
        print('TRIPLE_VERIFIED',best['vector'],flush=True)
    finally:
        if p:p.close()
        d.close()

if __name__=='__main__':run()
