"""Native0 full worker bootstrap in disposable DEV cases; no production writes."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import argparse,sys,subprocess,os,inspect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r040 import operations as op,batch
from v44.common import read,record,atomic,digest,now

def child(pointer,out):
    from v44_recovery_r040 import actual
    from v44.execution import case_scope
    from v44.locks import process_identity
    from v42_may_campaign_native90.preflight import native_zero
    from v44_recovery_r038.phases import load_handoff
    seen={}
    def probe(request):
        root=Path(request['case_root'])
        assert root.is_relative_to(out.parent)
        with case_scope(request,request['lease'],dict(**process_identity(),worker_slot=1)):
            op.require();h=load_handoff(request)
            import v43_actual.compare as shared
            text=inspect.getsource(shared.run)
            assert "and v['latency_within_900_seconds']" not in text
            assert "v['Actual96_execution_PASS']" in text and "v['Fresh96_physical_PASS']" in text
            seen.update(day=request['day'],arm=request['arm'],same_frozen_AIDC=h['aidc_folder'],MESS_plan_sha=None if h['MESS_plan'] is None else h['MESS_plan'].get('plan_sha'),
                inherited_full_worker_scopes_entered=True,latency_guard_removed=True,physical_gates_retained=True)
            return dict(PASS=True)
    with native_zero() as denied,patch.object(actual,'actual_case',probe):
        result=op.worker(pointer)
        assert result['PASS'] and not denied and seen
    atomic(out,dict(UTC=now(),PASS=True,Native_optimizer_calls=0,production_case_written=False,full_Actual120_run_claimed=False,bootstrap=seen))

def parent(out):
    op.authority();out.mkdir(exist_ok=False)
    state=read(op.STATE);lease=read(op.CAMPAIGN/'COORDINATOR_LEASE.json');jobs=deepcopy(state['jobs']);ready=[]
    for job in jobs:
        if job['status']=='PREPARED':
            batch.check_ready(job);case=read(job['prepare_request']);folder=out/(job['day']+'_'+job['arm']);folder.mkdir()
            handoff=read(job['handoff']['path']);handoff['case_root']=str(folder);handoff['handoff_sha']=digest({k:v for k,v in handoff.items() if k!='handoff_sha'})
            target=folder/'PRE_ACTUAL_READY.json';atomic(target,handoff);atomic(folder/'START.json',dict(pid=2147483647,process_created=0))
            case=op.attach(case);case.update(case_root=str(folder),lease=lease,r038_phase='ACTUAL_PARALLEL',parallel_actual_slot=len(ready)+1,R038_pre_actual_handoff=record(target))
            ready.append((case,folder))
    assert len(ready)>=2
    ready_keys={op.key(case) for case,_ in ready}
    manifest=dict(UTC=now(),authorization=record(op.AMENDMENT),lease=lease,all_preparations_resolved=True,
        ready=[dict(day=r['day'],arm=r['arm'],case_root=r['case_root'],handoff=r['R038_pre_actual_handoff'],slot=i) for i,(r,_) in enumerate(ready,1)],
        excluded=[dict(day=j['day'],arm=j['arm'],reason='NATIVE0_VALIDATION_ONLY_NOT_PREPARED_YET') for j in jobs if op.key(j) not in ready_keys],already_complete=[],
        cpu_placement=op.cpu.placement(op.cpu.windows_cpu_sets(),len(ready)))
    batch.validate_manifest(manifest,op.queue());m=out/'MANIFEST.json';atomic(m,manifest)
    processes=[]
    for case,folder in ready:
        case['R040_resolved_manifest']=record(m);pointer=folder/'request.json';atomic(pointer,case)
        with (folder/'bootstrap.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,'-X','utf8',__file__,'--child',str(pointer),'--out',str(folder/'RESULT.json')],cwd=Path(__file__).resolve().parents[2],
                env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        processes.append((process,folder))
    results=[]
    for process,folder in processes:
        assert process.wait(timeout=90)==0,folder
        result=read(folder/'RESULT.json');assert result['PASS'];results.append(record(folder/'RESULT.json'))
    atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,parallel_worker_bootstraps=len(results),Native_optimizer_calls=0,
        full_Actual120_run_claimed=False,production_case_written=False,healthy_subset_with_excluded_cases_accepted=True,results=results,source=record(__file__)))
    print(dict(PASS=True,bootstraps=len(results),Native_optimizer_calls=0))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.child:child(a.child,a.out)
    else:parent(a.out)
