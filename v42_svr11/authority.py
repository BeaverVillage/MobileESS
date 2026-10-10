from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from v42_pr134_b1.common import atomic,read,record,digest,sha
from v42_common_campaign.authority import ROOT,source_files
from . import DAYS

_active=ContextVar('svr11_epoch',default=None)

def active():
    return _active.get()

def verify(path):
    m=read(path)
    if m.get('svr11_campaign') is not True or m.get('authorization')!='V42_FINAL_USER_20261011':
        raise PermissionError('SVR11_EXPLICIT_USER_AUTHORITY_REQUIRED')
    if m['execution_SHA']!=digest(m['execution_sources']) or m['execution_sources']!=source_files():
        raise PermissionError('SVR11_GLOBAL_SOURCE_INTEGRITY_FAILURE')
    for key in ('hardware','scenario','thermal'):
        if record(m[key]['path'])!=m[key]:
            raise PermissionError('SVR11_GLOBAL_HARDWARE_INTEGRITY_FAILURE:'+key)
    if 'predecessor_drain_contract' in m and record(m['predecessor_drain_contract']['path'])!=m['predecessor_drain_contract']:
        raise PermissionError('SVR11_GLOBAL_PREDECESSOR_CONTRACT_DRIFT')
    if 'model_checkpoint_reuse_contract' in m and record(m['model_checkpoint_reuse_contract']['path'])!=m['model_checkpoint_reuse_contract']:
        raise PermissionError('SVR11_GLOBAL_MODEL_CHECKPOINT_REUSE_CONTRACT_DRIFT')
    h=read(m['hardware']['path'])
    if not h['PASS'] or h['source_SHA']!=m['execution_SHA'] or h['SVR_count']!=11:
        raise PermissionError('SVR11_MINIMUM_IMPLEMENTATION_PREFLIGHT_REQUIRED')
    return m

@contextmanager
def scope(manifest_path):
    m=verify(manifest_path); token=_active.set(m)
    # A new hardware epoch has its own finite current authority; cache must
    # never retain a predecessor compiled inventory within this process.
    from v42_thermal.authority import current_authority
    current_authority.cache_clear()
    try: yield m
    finally:
        _active.reset(token);current_authority.cache_clear()
        verify(manifest_path)

def thermal():
    m=active()
    if m is None:return None
    if record(m['thermal']['path'])!=m['thermal']:
        raise PermissionError('SVR11_GLOBAL_THERMAL_INTEGRITY_FAILURE')
    return read(m['thermal']['path'])

def verify_request(request):
    m=verify(request['manifest'])
    if (request['source_SHA']!=m['execution_SHA'] or request['manifest_SHA']!=sha(request['manifest'])
        or request['day'] not in DAYS or request['arm'] not in ('B0','B1','B2','B3')
        or Path(request['code_root']).resolve()!=ROOT or request['run_id']!=m['run_id']):
        raise PermissionError('SVR11_REQUEST_EPOCH_DRIFT')
    owned=Path(m['root'])/'dates'/request['arm']/request['day']/'attempts'/request['attempt_id']
    if (Path(request['root']).resolve()!=Path(m['root']).resolve()
        or Path(request['input_folder']).resolve()!=Path(m['root'])/'inputs'/request['arm']/request['day']
        or Path(request['output']).resolve()!=owned/'output'
        or Path(request['result']).resolve()!=owned/'RESULT.json'):
        raise PermissionError('SVR11_REQUEST_OUTPUT_OWNERSHIP_DRIFT')
    for r in m['input_receipts'][request['day']]:
        if record(r['path'])!=r:raise PermissionError('SVR11_FROZEN_INPUT_DRIFT:'+r['path'])
    return m

def design(receipt,source_SHA):
    m=active()
    if m is None or receipt!=m['hardware'] or source_SHA!=m['execution_SHA']:
        raise PermissionError('SVR11_SCOPED_HARDWARE_AUTHORITY_REQUIRED')
    return dict(read(receipt['path']),scenario=m['scenario'],scenario_SHA=read(m['scenario']['path'])['scenario_SHA'])
