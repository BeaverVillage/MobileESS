import cProfile
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

root=Path(__file__).parents[2];sys.path.insert(0,str(root))
from v42_integration.q90_recourse import evaluate_q90_recourse
spec=importlib.util.spec_from_file_location('v42_integration._frozen_reference',root/'audit/reference_source.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
s=mod.load_conditional_source();n=json.loads((Path(__file__).parent/'FROZEN_A2_NOMINAL_SERVICE.json').read_text(encoding='utf-8'))
p=json.loads((Path(__file__).parent/'A2_SERVICE_TIMING_SOURCE_PACKET.json').read_text(encoding='utf-8'))
def run():return evaluate_q90_recourse(s['packet'],n,p['q90_hourly_GPUh'],p['TRAIN_CDF_lower'],p['TRAIN_CDF_upper'])
run()
pr=cProfile.Profile();pr.enable();start=perf_counter();r=run();elapsed=perf_counter()-start;pr.disable()
pr.dump_stats(str(Path(__file__).parent/'recourse.prof'))
import pstats
pstats.Stats(pr).sort_stats('cumulative').print_stats(22)
print('warm_seconds',elapsed,'branches',len(s['packet'].branch_names),'ratings',sum(v is not None for v in s['packet'].coefficients[0].transformer_ratings))
