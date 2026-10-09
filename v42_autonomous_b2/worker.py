from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import argparse
import psutil
from v42_b2_seed_recovery_v19.common import ROOT,read,record,sha,digest
from v42_b2_seed_recovery_v19.policy import source_files as scientific_sources,exact_prior_runtime
from v42_may_campaign_native90.a_routing import rebound

CANONICAL=Path(r'D:\MobileESS_V42')

def sources():
    return dict(scientific_sources(),**{p.relative_to(ROOT).as_posix():sha(p)
        for p in sorted((ROOT/'v42_autonomous_b2').glob('*.py'))})

def verify_request(request):
    root=Path(request['root']).resolve();m=read(request['manifest'])
    if (Path(request['manifest']).parent.resolve()!=root or m['schema']!='V42_AUTONOMOUS_B2_V20'
        or m['execution_sources']!=sources() or m['execution_SHA']!=digest(sources())
        or request['manifest_SHA']!=sha(request['manifest']) or request['implementation_SHA']!=m['execution_SHA']
        or request['attempt_id']!=m['attempt_id'] or request['run_id']!=m['run_id']
        or request['arm']!='B2' or request['day'] not in m['input_folders']
        or request['Threads']!=1 or request['P2_calls']!=0 or request['target_gap']!=.03
        or request['native_budget_seconds']!=5400 or request['wall_budget_seconds'] is not None
        or m['initialization_native_limit_seconds']!=5400):
        raise PermissionError('B2_DEPLOYMENT_OR_REQUEST_SEAL_DRIFT')
    attempt=root/'dates/B2'/request['day']/'attempts'/m['attempt_id']
    for k,n in [('result','RESULT.json'),('output','output'),('progress','progress.json'),('error','error.json')]:
        if Path(request[k]).resolve()!=attempt/n:raise PermissionError('FRESH_ATTEMPT_PATH_DRIFT')
    if Path(request['input_folder']).resolve()!=Path(m['input_folders'][request['day']]).resolve():
        raise PermissionError('INPUT_FOLDER_DRIFT')
    for relative,s in m['builder_original_sources'].items():
        if sha(ROOT/relative)!=s:raise PermissionError('ORIGINAL_SCIENCE_SOURCE_DRIFT:'+relative)
    # Canonical provenance is admitted only for the byte-identical frozen source.
    if sha(ROOT/'v42_capacity/reference.py')!=sha(CANONICAL/'v42_capacity/reference.py'):
        raise PermissionError('CANONICAL_INPUT_PROVENANCE_SOURCE_DRIFT')
    for r in m['inherited_B1_results'].values():
        if record(r['path'])!=r:raise PermissionError('B1_RESULT_SHA_DRIFT')
    for day,r in m['prior_attempts'].items():exact_prior_runtime(r,root=root,day=day)
    return m

def assert_peers(request):
    seen={request['day']};slots={request['worker_slot']}
    for p in psutil.process_iter(['name']):
        if p.pid==psutil.Process().pid or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
        try:
            args=p.cmdline();module=args[args.index('-m')+1] if '-m' in args else ''
            if module=='v42_autonomous_b2.worker':
                peer=read(args[-1]);verify_request(peer)
                if peer['day'] in seen or peer['worker_slot'] in slots:raise PermissionError('DUPLICATE_B2_DAY_OR_SLOT')
                seen.add(peer['day']);slots.add(peer['worker_slot'])
            elif module.endswith('.worker') and module.startswith(('v42_may','v42_b2','v42_m1','v42_a_stage','v42_autonomous_b3')):
                raise PermissionError('OTHER_SCIENTIFIC_WORKER_ACTIVE')
        except psutil.Error:continue
    if len(slots)>3:raise PermissionError('B2_MAX_THREE_WORKERS')

@contextmanager
def worker_scope(request):
    from v42_b2_seed_recovery_v19 import execution
    with patch.object(execution,'verify_request',verify_request),patch.object(execution,'assert_peers',assert_peers):
        with execution.worker_scope(request) as m:yield m

def run(path):
    from v42_b2_seed_recovery_v19 import worker as original
    from v42_may_campaign_native90 import inputs
    # The original generator compares its immutable provenance record including
    # absolute path. Its arithmetic, input bytes and all checks stay unchanged.
    generated=rebound(inputs.generate_b2,dict(inputs.generate_b2.__globals__,ROOT=CANONICAL))
    with patch.object(inputs,'generate_b2',generated):
        return rebound(original.run,dict(original.run.__globals__,verify_request=verify_request,
            worker_scope=worker_scope))(path)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('request');a=p.parse_args();raise SystemExit(run(a.request))
