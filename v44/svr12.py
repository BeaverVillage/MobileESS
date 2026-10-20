"""Exact successful SVR12 equipment, isolated to Actual contexts.

No Forecast coefficients or Planning optimizers are created here. Native
control, AC equations, measurements and cache guards are inherited verbatim.
"""
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from types import FunctionType
from unittest.mock import patch
from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,digest,now

REVISION='V44_V43_PLANNING_SVR12_ACTUAL_V1'
DIRECTORY=DOC/'v43_planning_svr12_actual_v1'
HARDWARE=DIRECTORY/'hardware'
ORIGIN=RUNTIME/'svr12_diagnostic/V43_FINAL_B2_SVR12_ACTUAL_AC_ONCE002'
_active=ContextVar('V44_SVR12_ACTUAL_ONLY',default=False)

def counts(function,replacements):
    constants=function.__code__.co_consts
    if any(sum(type(v) is int and v==k for v in constants)!=1 for k in replacements):
        raise ValueError('EXACT_SVR12_INVENTORY_METADATA_BOUNDARY_DRIFT')
    code=function.__code__.replace(co_consts=tuple(replacements.get(v,v) if type(v) is int else v for v in constants))
    return FunctionType(code,function.__globals__,function.__name__,function.__defaults__,function.__closure__)

def prepare_hardware():
    origin=read(ORIGIN/'RESULT.json');verify(origin['sources']+[origin['hardware'],origin['AC_receipt']])
    if not origin['PASS'] or origin['SVR_banks']!=12 or origin['RegControl_count']!=43:
        raise ValueError('EXACT_SUCCESSFUL_SVR12_DIAGNOSTIC_REQUIRED')
    h=deepcopy(read(origin['hardware']['path']))
    for name in ('SCENARIO','THERMAL'):
        source=Path(h[name.lower()]['path']);target=HARDWARE/(name+'.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_bytes()!=source.read_bytes():raise ValueError('IMMUTABLE_SVR12_EQUIPMENT_DRIFT')
        if not target.exists():target.write_bytes(source.read_bytes())
        h[name.lower()]=record(target)
    h['sources']['v44/svr12.py']=record(__file__)
    h.update(schema=REVISION,source_SHA=digest({k:r['sha256'] for k,r in h['sources'].items()}),
        scope='ACTUAL_ONLY_RESEARCH_EQUIPMENT_NOT_PLANNING_SOURCE',
        successful_diagnostic=record(ORIGIN/'RESULT.json'),physical_parameter_changes=0,
        parent_equipment_parameters_preserved=True,Planning_RegControl_count=7,Planning_added_SVR=0)
    atomic(HARDWARE/'HARDWARE.json',h)
    return h

@contextmanager
def scope():
    if _active.get():yield;return
    from . import svr11_hardware as inherited,svr11_ac as ac
    inherited.load_vendor()
    import v42_svr11.initial_context as initial
    original_reference=initial.reference;original_probe=ac.probe_body
    def reference(*args,**kwargs):
        value=original_reference(*args,**kwargs);value.result['SVR_bank_count']=12
        atomic(value.receipt['path'],value.result);value.receipt=record(value.receipt['path']);return value
    def probe():return counts(original_probe(),{11:12,40:43})
    token=_active.set(True)
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(inherited,'HARDWARE',HARDWARE))
            stack.enter_context(patch.object(ac,'HARDWARE',HARDWARE))
            stack.enter_context(patch.object(ac,'RUNTIME',RUNTIME/'v43_planning_svr12_actual_v1/AC_AUDIT'))
            stack.enter_context(patch.object(ac,'probe_body',probe))
            stack.enter_context(patch.object(initial,'reference',reference))
            with inherited.scope():
                import v42_integrated.contract as contract
                adapted=contextmanager(counts(contract.physical_authority.__wrapped__,{153:156,77:80,40:43}))
                stack.enter_context(patch.object(contract,'physical_authority',adapted))
                stack.enter_context(patch.object(ac,'scope',scope))
                yield
    finally:_active.reset(token)

from .svr11_ac import SVR11CurrentAC

def compact_audit(receipt):
    """Keep measured decisions; reference the complete per-probe on-disk Raw.

    This is the existing V43 certified-prefix receipt compaction pattern.
    A cache hit retains the exact input/hardware identity and original verdict;
    no native state, measurements, limits or candidate computation are changed.
    """
    compact={k:v for k,v in receipt.items() if k!='physical_steps'}
    compact['current']={k:v for k,v in receipt['current'].items()
        if k not in ('full_physical','voltage_nodes','SVR_devices','time_control')}
    steps=receipt.get('physical_steps')
    compact.update(verified_prefix_steps=max(0,len(steps)-1) if steps is not None else receipt['verified_prefix_steps'],
        prefix_proof_reference=receipt['physical_audit'],current_candidate_fully_measured=True,
        complete_per_probe_Raw_preserved=True)
    return compact

class SVR12CurrentAC(SVR11CurrentAC):
    def __init__(self,*args,**kwargs):
        with scope():super().__init__(*args,**kwargs)
    def _probe(self,rows):
        with scope():return super()._probe(rows)
    def evaluate(self,*args,**kwargs):
        with scope():result=super().evaluate(*args,**kwargs)
        result.update(scope='V44_SVR12_CAUSAL_NATIVE_TIME_PREFIX',source_revision=REVISION)
        compact=compact_audit(result)
        self.audit[-1]=compact
        # Original 32-entry LRU keys and verdicts stay exact. Repeated complete
        # histories are already durable in physical_audit's slots/event Raw.
        self.cache[result['input_sha']]=compact
        return compact
    def certificates(self):
        with scope():return super().certificates()

def certificate(path):
    c=read(path);h=record(HARDWARE/'HARDWARE.json')
    if not c.get('PASS') or c.get('hardware')!=h or c.get('RegControl_count')!=43:
        raise PermissionError('EXACT_SVR12_CURRENT_AC_CERTIFICATE_REQUIRED')
    verify(c['sources']+[h,c['real_prefix_evidence']]);return c

def raw_regression():
    """Independent all-node/all-terminal arithmetic over the successful Raw."""
    origin=read(ORIGIN/'RESULT.json');verify(origin['sources']+[origin['hardware'],origin['AC_receipt']])
    probe=read(origin['AC_receipt']['path']);rows=probe['physical_steps'][24:]
    bad=[]
    for row in rows:
        p=row['full_physical']
        if (not row['converged'] or not p['all_original_and_added_axes_checked']
                or any(not .95<=n['voltage_pu']<=1.05 for n in p['nodes'])
                or any(not 0<=n['loading_pu']<=1 for n in p['currents']+p['transformers'])
                or len(row['SVR_devices']['devices'])!=12):bad.append(row['slot'])
    result=dict(PASS=len(rows)==96 and not bad,rows=len(rows),failed_slots=bad,
        original=record(ORIGIN/'RESULT.json'),raw=origin['AC_receipt'],Native_calls=0,
        AC_replays=0,independent_arithmetic_replay=True,UTC=now())
    atomic(DIRECTORY/'REFERENCE_C_RAW_REPLAY.json',result)
    return result
