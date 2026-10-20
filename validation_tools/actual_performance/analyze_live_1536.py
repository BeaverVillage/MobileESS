"""Summarize a nonblocking live sample; no live worker/source changes."""
import sys,json,collections
from pathlib import Path
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
import psutil
from v44.common import read,record,atomic,now
path=Path('D:/MobileESS_V44/development/actual_live_20261017_1536.speedscope.json')
data=read(path);frames=data['shared']['frames']
inclusive=collections.Counter();leaf=collections.Counter();groups=collections.Counter();total=0
for profile in data['profiles']:
    samples=profile.get('samples',[]);weights=profile.get('weights',[1]*len(samples))
    for sample,weight in zip(samples,weights):
        if not sample:continue
        stack=[frames[i] for i in sample];total+=weight
        keys=[(str(f.get('file','')),f['name']) for f in stack]
        leaf[keys[-1]]+=weight
        for key in set(keys):inclusive[key]+=weight
        names={f['name'] for f in stack}
        if any(Path(f.get('file','')).name=='copy.py' for f in stack):group='Python deepcopy'
        elif names & {'inventory','_ratings','_equipment','_controls','live_properties','_physical_inputs','_properties'}:group='Live equipment/property reads and guards'
        elif names & {'persist','canonical_list','encoded','iterencode','dumps'}:group='Serialization and Raw persistence'
        elif 'SolveSnap' in names:group='Native SolveSnap frame'
        else:group='Other'
        groups[group]+=weight
def rows(counter):
    return [dict(file=k[0],function=k[1],sample_percent=100*v/total) for k,v in counter.most_common(12)]
root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
heartbeat=read(root/'2025-05-01/B3/attempt003/ACTUAL/HEARTBEAT.json')
process=psutil.Process(35968)
result=dict(UTC=now(),sampling=record(path),valid_samples=687,sampling_errors=44,
    sampling_limit='15-second nonblocking sample; failed reads can bias percentages; not a whole-run CPU breakdown.',
    groups={k:round(100*v/total,2) for k,v in groups.most_common()},top_inclusive=rows(inclusive),top_leaf=rows(leaf),
    actual_heartbeat=heartbeat,CPU_wall_ratio=heartbeat['CPU_seconds']/heartbeat['wall_seconds'],
    affinity=process.cpu_affinity(),available_RAM_GiB=psutil.virtual_memory().available/2**30,
    active_revision=read(root/'AUTONOMOUS_RECOVERY/CURRENT_HANDOFF.json')['active_revision'],
    source_or_running_policy_modified=False)
atomic(path.with_name('ACTUAL_LIVE_BOTTLENECK_1536.json'),result)
print(json.dumps(dict(groups=result['groups'],top_inclusive=result['top_inclusive'][:7],CPU_wall_ratio=result['CPU_wall_ratio'],latest=heartbeat['latest']),ensure_ascii=False,indent=2))
