"""Keep historical boundary checks; distinguish this leased campaign's own workers."""
from pathlib import Path
import os,psutil
from v44.common import read
from v44.locks import alive,EXTERNAL_LOCKS


def authorized_peer(process,request,entry):
    args=process.get('cmdline') or []
    if entry not in args or '--worker' not in args:return False
    try:peer=read(Path(args[args.index('--worker')+1]))
    except (IndexError,OSError,ValueError):return False
    if peer.get('lease')!=request['lease'] or peer.get('campaign_root')!=request['campaign_root']:return False
    if process['pid']==os.getpid():return peer['day']==request['day'] and peer['arm']==request['arm'] and peer['case_root']==request['case_root']
    return (request.get('r038_phase')=='ACTUAL_PARALLEL' and peer.get('r038_phase')=='ACTUAL_PARALLEL'
            and peer.get('sequence_mode')=='MAIN' and peer.get('R045_authorization')==request.get('R045_authorization'))


def boundary(request):
    from .operations import CAMPAIGN,ENTRY,authority,request_authority
    from v44_recovery_r029 import operations as old,handover
    authority();request_authority(request)
    lease=request['lease'];args=psutil.Process(lease['pid']).cmdline() if alive(lease) else []
    if (not alive(lease) or lease!=read(CAMPAIGN/'COORDINATOR_LEASE.json')
        or Path(lease['root']).resolve()!=CAMPAIGN.resolve() or ENTRY not in args or '--run' not in args
        or set(lease['external_locks'])!={str(p) for p in EXTERNAL_LOCKS}):
        raise PermissionError('R045_CURRENT_REAL_COORDINATOR_LEASE_REQUIRED')
    guard=read(old.OPS/'R029_HANDOVER_GUARD.json');historical=read(old.CAMPAIGN/'COORDINATOR_LEASE.json')
    foreign=[p for p in old.workers() if not authorized_peer(p,request,ENTRY)]
    if not handover.boundary(guard,lease=historical,workers=foreign):
        raise PermissionError('R045_HISTORICAL_PROTECTED_OR_FOREIGN_WORKER_PRESENT')
    if Path(request['case_root']).resolve()==Path(guard['protected_case_root']).resolve():
        raise PermissionError('R045_PROTECTED_CASE_CANNOT_BE_RESTARTED')
    return guard
