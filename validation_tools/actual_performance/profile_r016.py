"""Profile isolated real AC prefixes without changing the running campaign."""
import cProfile
import pstats
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path('D:/v44_may01_07_prepare_20261016')
sys.path.insert(0, str(ROOT))
from v44.common import atomic, read, record, digest
from v44_recovery_r015.operations import sources, schema_backend_sources
from v44_recovery_r015.source_io import install as source_install
from v44_recovery_r015.source_ports import install as ports_install
from v44_recovery_r015.exact_clean import install as clean_install
from v44_recovery_r015.current_ac_performance import live_read_scope, ExactAuditEncoding
from v44_recovery_r015.thread_policy import numerical_threads
from v44_recovery_r015.cpu_placement import actual_cpu_scope

out = Path(sys.argv[1])
out.mkdir(exist_ok=False)
helper = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/validate_r009_final_repeated.py')
setup = helper.read_text(encoding='utf8').split('import v44_recovery_r009.current_ac_performance as performance')[0]
setup = setup.replace("out=Path(sys.argv[1]);out.mkdir(exist_ok=False)", "out=Path(sys.argv[1])")
exec(compile(setup, str(helper), 'exec'))
# The historical fixture imports its old adapter; restore the current adapter.
from v44_recovery_r015.current_ac_performance import live_read_scope, ExactAuditEncoding
request = read(helper.parent/'requests/2025-05-01_B3_attempt003.json')
pins = list({r['path']:r for r in request['sources']+sources()+schema_backend_sources()}.values())
with native_zero() as denied, source_install(pins) as pool, ports_install(pool), clean_install(), numerical_threads(1), actual_cpu_scope() as placement:
    engine = oracle('B3')
    encoding = ExactAuditEncoding()
    with scope(), patch('v44.svr11_ac.RUNTIME', out/'AC_AUDIT'), live_read_scope(encoding,engine):
        engine._probe(rows)
        candidate = list(rows)
        candidate[-1] = dict(candidate[-1],P=candidate[-1]['P'].copy())
        candidate[-1]['P'][0] += .5
        profiler = cProfile.Profile()
        start = time.perf_counter()
        value = profiler.runcall(engine._probe,candidate)
        wall = time.perf_counter()-start
        profiler.dump_stats(str(out/'profile.pstats'))
        with (out/'profile.txt').open('w',encoding='utf8') as stream:
            pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(65)
        audit = read(value['physical_audit']['path'])
        atomic(out/'RESULT.json',dict(wall_seconds=wall,verdict=value['PASS'],physical_steps_sha=digest(value['physical_steps']),raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'],source_IO=pool.report(),Native_optimizer_calls=len(denied),placement=placement))
        print((out/'profile.txt').read_text(encoding='utf8'),flush=True)
