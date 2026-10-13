"""Reference vs vectorized PCS scoring regression, all units and route depths."""
import argparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.scoring import LookaheadMinimax

def main(mode):
    configure();gate=read(DOCS/'NATIVE0_STATIC_GATE.json');spec=read(gate['models']['DIRECT']['path']);case=v.load_case(native=False);point=v.load_point(spec['center_raw']['path'])
    context=read(DOCS/'grid/epoch1001/CRITICAL_MINIMAX_CONTEXT.json');scorer=LookaheadMinimax(case,point,context);base=paths_of(case,point);rows=[];started=time.perf_counter()
    for u,pool in spec['pools'].items():
        for path in pool:
            peak,vector,risk=scorer.peak(dict(base,**{u:path}));rows.append(dict(unit=u,path=path,score=peak,vector=vector,risk=risk))
    report=dict(PASS=True,Optimize_calls=0,reference_raw=spec['center_raw'],source_code=record(DEVELOPMENT_ROOT/'tools/adaptive_perf_v3/scoring.py'),records=rows,wall_seconds=time.perf_counter()-started)
    if mode=='reference':
        write(DOCS/'SCORE_REFERENCE_BEFORE_VECTORIZE.json',report)
        (DOCS/'SCORING_BEFORE_VECTORIZE.py.txt').write_bytes((DEVELOPMENT_ROOT/'tools/adaptive_perf_v3/scoring.py').read_bytes())
    else:
        old=read(DOCS/'SCORE_REFERENCE_BEFORE_VECTORIZE.json');error=0.
        for a,b in zip(rows,old['records']):
            assert a['unit']==b['unit'] and a['path']==b['path'];error=max(error,abs(a['score']-b['score']),float(np.max(np.abs(np.asarray(a['vector'])-b['vector']))))
        assert error<1e-12;report['maximum_score_or_vector_error']=error;report['prior_wall_seconds']=old['wall_seconds'];write(DOCS/'SCORE_VECTORIZE_EQUIVALENCE.json',report)
    print(json.dumps(dict(PASS=True,mode=mode,wall=report['wall_seconds'])),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['reference','verify'],required=True);main(parser.parse_args().mode)
