"""Source-bound whole-job repair for new B1 and B3; old producers stay valid."""
import sys
from fast_prepare import ROOT, read, record
from v41r4_loop_budget import adapted
import v41r4_loop_runtime as runtime
import v41r4_loop_worker as worker
from mission_loop_archive import install as install_archive
from mission_loop_large_block import install as install_blocks

HELPERS=(*runtime.HELPERS,'mission_loop_large_block.py','mission_loop_large_worker.py')
def ranking_cache(day):
    current=runtime.MAY_OUT/day
    if (current/'V41R3_RANKING_PHYSICS.npz').exists() and (current/'V41R3_FO_PHYSICS_RANKING_AUDIT.json').exists():
        return current
    return runtime.ranking_cache(day)

configure_repaired=adapted(runtime.configure, [], dict(HELPERS=HELPERS,ranking_cache=ranking_cache))
prepare_repaired=adapted(runtime.prepare_ranking, [], dict(ranking_cache=ranking_cache))

def main(day,phase):
    release=read(runtime.MAY_OUT/'mission/LARGE_BLOCK_REPAIR_RELEASE.json')
    assert release['status']=='PASS'
    assert all(record(r['path'])==r for r in release['helpers'])
    install_archive()
    policy=phase.split('_')[0]
    repaired=policy in ('B1','B3') and phase.endswith('_DA')
    producer=runtime.MAY_OUT/day/f'PRODUCER_{policy}.json'
    if phase.endswith('_AC') and producer.exists():
        repaired=any(r['path']==str(ROOT/'mission_loop_large_block.py') for r in read(producer)['science']['files'])
    if repaired:
        install_blocks()
        worker.configure=configure_repaired
        worker.prepare_ranking=prepare_repaired
    worker.main(day,phase)

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
