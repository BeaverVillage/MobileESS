"""One complete non-timing-sensitive native model census per candidate."""
import argparse,threading,psutil,gc
from time import perf_counter
from v42_root.common import *
from v42_root.data import prepare
from v42_root.native import build
import v42_root.profile as profile
from .census import measure,sparse_category
from .config import PRIMARY

def main():
    p=argparse.ArgumentParser();p.add_argument('kind');kind=p.parse_args().kind
    frozen();data=prepare();context=Context();context.folder=LOCAL/('STRUCTURAL_'+kind);context.folder.mkdir(parents=True,exist_ok=True)
    peak=[psutil.Process().memory_info().rss];stop=threading.Event()
    def sample():
        proc=psutil.Process()
        while not stop.wait(.25):peak[0]=max(peak[0],proc.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();start=perf_counter();profile.category=sparse_category
    try:
        with profile.Census() as census:m,units,levels,controls,bindings=build(context,data,kind)
        build_wall=perf_counter()-start
        print('complete model; measuring sparse families',kind,flush=True)
        stats=measure(m,units,levels,census,kind)
        stats.update(formulation=kind,model_build_seconds=build_wall,matrix_census_seconds=perf_counter()-start-build_wall,total_structural_seconds=perf_counter()-start,peak_RSS_bytes=peak[0],all_jobs=len(data[1]),all_native_electrical_slots=96,exactness='FORMULATION_EXACTNESS.json',time_scope='build and census measured separately; concurrent rollback I/O permitted; not a clean performance measurement')
        dump(kind+'_STRUCTURAL.json',stats);print('STRUCTURAL PASS',kind,stats['columns'],stats['rows'],stats['nonzeros'],flush=True)
        m.dispose();gc.collect()
    finally:stop.set();th.join(timeout=1)
    frozen()
if __name__=='__main__':main()
