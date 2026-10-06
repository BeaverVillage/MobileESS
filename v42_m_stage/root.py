from .common import *
import subprocess
import threading
from v42_m1_accel_vnext.native_state import inspect_live

def freeze():
    assert read(OUT/'HYBRID_PRICING_SELECTION.json')['PRICING_BACKEND']=='ORIGINAL_GUROBI_EXACT'
    folders=('v42_m_stage','v42_m_stage_root','v42_dw_root','v42_dw_resume','v42_dw_bound',
        'v42_dw_runtime','v42_dw_accelerated','v42_degen','v42_native','v42_bootstrap')
    paths=[p for folder in folders for p in (ROOT/folder).rglob('*.py')]
    write('ROOT_EXECUTION_FREEZE.json',dict(sources={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
        authorities={p:sha(OUT/p) for p in ('HYBRID_PRICING_SELECTION.json','PREREGISTRATION_AUTHORITY.json',
            'PR152_BYTE_FREEZE.json','ROOT1604_RESUME_AUTHORITY.json','DW_CONTINUATION_BASE_AUDIT.json',
            'M_STAGE_REMAINING_WORK_PREREGISTRATION.md')},
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()))

def run():
    assert not (OUT/'CG_STARTED.json').exists(),'One new grant only; use explicit resume within that grant'
    freeze()
    from v42_m_stage_root.cg import Experiment
    experiment=Experiment()
    done=threading.Event();foreign=[]
    def watch():
        while not done.wait(2):
            observed,blocked=inspect_live(experiment.pids)
            if blocked:
                foreign.append(dict(observed=observed,blocked=blocked));experiment.cancel.set()
                experiment.monitor.failed.append('CONFIRMED_FOREIGN_NATIVE_OVERLAP')
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    try:experiment.run()
    finally:
        done.set();thread.join()
        write('ROOT_FOREIGN_NATIVE_OBSERVATION.json',dict(overlap=foreign,foreign_control_calls=0))

if __name__=='__main__':run()
