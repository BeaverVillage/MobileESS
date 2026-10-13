"""All-reservoir scoring wall measurement; no Optimize or model creation."""
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.scoring import LookaheadMinimax

def main():
    configure();guard();static=read(DOCS/'NATIVE0_STATIC_GATE.json');spec=read(static['models']['DIRECT']['path'])
    case=v.load_case(native=False);point=v.load_point(spec['center_raw']['path']);context=read(DOCS/'grid/epoch1001/CRITICAL_MINIMAX_CONTEXT.json')
    scorer=LookaheadMinimax(case,point,context);base=paths_of(case,point);reservoir=read(DOCS/'BEAM_RESERVOIR.json')['units'];started=time.perf_counter();counts={}
    for u,paths in reservoir.items():
        counts[u]=0
        for path in paths.values():
            score,vec,risk=scorer.peak(dict(base,**{u:path}));assert np.isfinite(score);counts[u]+=1
    wall=time.perf_counter()-started
    write(DOCS/'ALL_RESERVOIR_VECTORIZE_TIMING.json',dict(PASS=True,Optimize_calls=0,units=counts,score_wall=wall,actual_reference_UB=spec['center_replay'],
        source_code=record(DEVELOPMENT_ROOT/'tools/adaptive_perf_v3/scoring.py'),baseline_score=scorer.peak(base)[0],
        same_reservoir_and_context_as_development=True,prior_score_admission_wall=static['timing']['parts']['Score_admission_and_candidate_IO'],
        prior_stage_includes_admission_and_IO_not_only_scoring=True))
    print(json.dumps(dict(PASS=True,score_wall=wall,counts=counts)),flush=True)
if __name__=='__main__':main()
