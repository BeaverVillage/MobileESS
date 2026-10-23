"""Bounded resource guard for one identity-checked preparation child only."""
import sys,time
import psutil
from .stage_common import WORK,put

def watch(pid,expected):
    process=psutil.Process(pid);created=process.create_time();command=process.cmdline()
    if expected not in ' '.join(command) or '-m' not in command:raise PermissionError('OWN_PREPARATION_IDENTITY_REQUIRED')
    if command[command.index('-m')+1]!='v2_add_preflight.stage_aidc':raise PermissionError('ONLY_OWN_AIDC_NATIVE0_CHILD')
    started=time.monotonic();peak=0;terminated=False
    while time.monotonic()-started<7200:
        try:
            if process.create_time()!=created:raise PermissionError('PID_REUSE')
            rss=process.memory_info().rss;peak=max(peak,rss)
            # Leave allocation headroom below the user's hard 4GiB ceiling.
            if rss>3.6*1024**3 or psutil.virtual_memory().available<5.2*1024**3:
                if process.cmdline()!=command:raise PermissionError('OWN_COMMAND_CHANGED')
                receipt=dict(PASS=False,scope='OWN_MONOLITHIC_FULL_JOB_NATIVE0_ATTEMPT_ONLY',pid=pid,creation=created,command=command,
                    peak_RSS_bytes=peak,observed_RSS_bytes=rss,system_available_bytes=psutil.virtual_memory().available,
                    action='Terminate only this identity-checked preparation child before hard4GiB limit',
                    existing_V44_or_V1_workers_touched=False,official_campaign=False,Native_optimize_calls=0)
                put('A1_MONOLITHIC_RESOURCE_GUARD.json',receipt);process.terminate();terminated=True;break
        except psutil.NoSuchProcess:break
        time.sleep(.05)
    if not terminated:put('A1_MONOLITHIC_RESOURCE_GUARD.json',dict(PASS=True,process_closed_or_guard_deadline=True,
        pid=pid,peak_observed_RSS_bytes=peak,terminated=False,existing_workers_touched=False))

def watch_m_binding(pid,created):
    process=psutil.Process(pid);command=process.cmdline()
    if process.create_time()!=created or '-m' not in command:raise PermissionError('OWN_PREPARATION_IDENTITY_REQUIRED')
    if command[command.index('-m')+1:] not in (['v2_add_preflight.stage_m_binding','build'],['v2_add_preflight.stage_m_binding','joint_native0'],['v2_add_preflight.stage_m_binding','k48_build'],['v2_add_preflight.stage_m_binding','k48_native0'],['v2_add_preflight.stage_factory_fixture']):
        raise PermissionError('ONLY_NAMED_NATIVE0_INTERFACE_PREPARATION_CHILD')
    peak=0;start=time.monotonic();terminated=False
    while time.monotonic()-start<7200:
        try:
            if process.create_time()!=created or process.cmdline()!=command:raise PermissionError('OWN_PREPARATION_IDENTITY_DRIFT')
            rss=process.memory_info().rss;available=psutil.virtual_memory().available;peak=max(peak,rss)
            if rss>=3.85*1024**3 or available<5.1*1024**3:
                process.terminate();terminated=True;break
        except psutil.NoSuchProcess:break
        time.sleep(.05)
    put('STAGE_M_BINDING_NATIVE0_RESOURCE_GUARD.json',dict(PASS=not terminated,pid=pid,creation=created,command=command,
        phase='NATIVE0_PREPARATION',terminated=terminated,peak_RSS_bytes=peak,existing_workers_touched=False,
        official_campaign_memory_guard=False,Native_optimizer_calls=0))


if __name__=='__main__':
    if sys.argv[1]=='m_binding':watch_m_binding(int(sys.argv[2]),float(sys.argv[3]))
    else:watch(int(sys.argv[1]),sys.argv[2])
