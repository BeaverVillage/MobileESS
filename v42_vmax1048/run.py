"""Prepare or dispatch the explicitly authorized diagnostic; no production sweep."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import shutil

from v42_pr134_b1.common import atomic,read,process,same_process,now
from v42_common_campaign.authority import ROOT,singleton
from .authority import prepare,verify_request,assert_peers


def launch(request_path):
    path=Path(request_path).resolve();request=read(path)
    verify_request(request);assert_peers(request)
    if shutil.disk_usage(request['root']).free<4*1024**3:
        raise PermissionError('VMAX1048_STORAGE_HEADROOM')
    attempt=path.parent
    if Path(request['result']).exists():
        raise PermissionError('VMAX1048_COMPLETED_ATTEMPT_NEVER_OVERWRITTEN')
    owner=attempt/'PROCESS.json'
    if owner.exists():
        if same_process(read(owner)):
            raise PermissionError('VMAX1048_EXISTING_OWNED_DIAGNOSTIC_WORKER')
        raise PermissionError('VMAX1048_INTERRUPTED_ATTEMPT_REQUIRES_MEASURED_RECOVERY')
    with singleton(attempt/'DISPATCH.lock'):
        if owner.exists() or Path(request['result']).exists():
            raise PermissionError('VMAX1048_CONCURRENT_OR_PRIOR_DISPATCH_REJECTED')
        stdout=(attempt/'worker.stdout.log').open('ab');stderr=(attempt/'worker.stderr.log').open('ab')
        try:
            child=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','v42_vmax1048.worker',str(path)],
                cwd=ROOT,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
                stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        finally:stdout.close();stderr.close()
        atomic(owner,process(child.pid))
    atomic(attempt/'DISPATCH_STATUS.json',dict(state='REAL_DIAGNOSTIC_RUNNING',PID=child.pid,
        official_campaign_authorized=False,UTC=now()))
    return child


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('path');parser.add_argument('--regression-receipt')
    parser.add_argument('--existing-canary-root');parser.add_argument('--original-result')
    args=parser.parse_args()
    if args.action=='prepare':
        print(prepare(args.path,args.regression_receipt,args.existing_canary_root,args.original_result))
    else:
        child=launch(args.path);child.wait()
        print(dict(exit_code=child.returncode))
