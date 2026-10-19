from pathlib import Path
from v44.common import verify
from v44 import q250_m4_v2 as q
from .authorization import validate_request
from v44_recovery_r015.operations import PERMIT

def worker(request):
    from v44_recovery_r015.finite_bound import install
    from v44_recovery_r015.weather import install as weather_install
    from v44_recovery_r015.initial_running import install as running_install
    from v44_recovery_r015.actual_wall import install as wall_install
    from v44_recovery_r015.a2_cache import install as cache_install
    from v44_recovery_r015.current_ac_performance import install as performance_install
    from v44_recovery_r015.thread_policy import install as thread_install
    from v44_recovery_r015.native_cpu import install as native_cpu_install
    from v44_recovery_r015.source_io import install as source_io_install
    from v44_recovery_r015.snapshot_checks import install as snapshot_install
    from v44_recovery_r015.source_ports import install as source_ports_install
    from v44_recovery_r015.exact_clean import install as clean_install
    from v44_recovery_r015.stage_costs import install as costs_install
    from v44.campaign import run_case
    validate_request(request);verify(request['sources'])
    with source_io_install(request['sources'],Path(request['case_root'])/'R015_SOURCE_IO_PERFORMANCE.json') as source_io,source_ports_install(source_io),clean_install(),q.install(PERMIT),install(),weather_install(Path(request['case_root'])/'WEATHER_OBSERVATION_ADMISSION.json'),running_install(),wall_install(),cache_install(),snapshot_install(),native_cpu_install(),thread_install(),performance_install(),costs_install(request,source_io):
        from .resume import run
        return run(request)
