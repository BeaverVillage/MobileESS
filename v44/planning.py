"""V43 seven-RegControl Planning; SVR equipment is Actual-only by design."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from .common import DOC,read,verify,record,NotReady

REVISION='V44_V43_PLANNING_SVR12_ACTUAL_V1'

def check_native(native):
    certificate=read(native['electrical_certificate']['path'])
    if native.get('V44_SVR11') or certificate.get('model_regenerated') or 'SVR' in certificate.get('model_version',''):
        raise PermissionError('PLANNING_REQUIRES_ORIGINAL_V43_SEVEN_REG_COEFFICIENTS')
    verify([native['electrical_certificate']])
    return certificate

@contextmanager
def scope(day):
    from .daily import day_inputs
    row=day_inputs(day);check_native(read(row['files']['native']['path']))
    from v42_integrated.contract import physical_authority
    with physical_authority() as authority:
        if authority['controls']['RegControl_count']!=7 or len(authority['rows'])!=120:
            raise PermissionError('PLANNING_SVR_EQUIPMENT_CONTAMINATION')
        yield

def stage_scope(function):
    @wraps(function)
    def run(*args,**kwargs):
        item=args[0];day=item if isinstance(item,str) else item['day']
        with scope(day):return function(*args,**kwargs)
    return run

def golden(request):
    """Only exact May01 accepted A1, original inputs and all frozen sources."""
    from v43_actual.case import accepted
    from .daily import day_inputs
    if request['day']!='2025-05-01' or request['arm']!='B1' or request['stage']!='A1':return None
    certificate,freeze,native,windows,arrays=accepted();row=day_inputs(request['day'])
    for name,label in [('NATIVE_INPUT.json','native'),('WINDOWS.json','windows')]:
        if freeze['scientific_input'][name]['sha256']!=row['files'][label]['sha256']:return None
    check_native(native);verify([certificate['source_freeze']])
    source=read(certificate['source_freeze']['path']);verify(source['sources']+source['support']+source['scientific_inputs'])
    result=read(certificate['result']['path'])
    if not result['PASS'] or result['certified_gap']>.005:return None
    output=Path(certificate['planning_freeze']['path']).parent
    if not (output/'A_PREPARE_RECEIPT.json').is_file():raise NotReady('GOLDEN_ORIGINAL_A_PREPARE_RECEIPT_REQUIRED')
    return dict(result,freeze=certificate['planning_freeze'],planning=certificate['planning_arrays'],
        accepted_cache_output=str(output),reused_Golden003=True,new_Native_calls=0,
        original_accepted_result=certificate['result'],original_source_freeze=certificate['source_freeze'])
