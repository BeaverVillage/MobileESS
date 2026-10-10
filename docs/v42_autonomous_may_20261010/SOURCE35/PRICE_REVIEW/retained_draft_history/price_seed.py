"""Source35 external draft: current F1 prices, separately from certified LB.

This prototype adds no solver call. It replaces only the input of an already
scheduled original L1/L4 lp_round when the driver has selected the zero dual.
It never returns the F1 dual as the driver's certified dual or edits Frontier.
Production port must bind this module into its declared execution source map.
"""
import copy
import inspect
import json
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

from v42_autonomous_b2 import f1_state,f1_basis,worker
from v42_m1_anytime import algorithms
from v42_m1_hybrid import blocks,pricing,verify
from v42_m1_research import lb
from v42_b2_seed_recovery_v18 import certificate_box

_LP=algorithms.lp_round
_REPAIR=lb.repair_affine_equality_duals
_CHECK=certificate_box.check
_DECOMP=blocks.verify_decomposition
_ORIGINALS=((algorithms,'lp_round',_LP,_LP.__code__),
            (lb,'repair_affine_equality_duals',_REPAIR,_REPAIR.__code__),
            (certificate_box,'check',_CHECK,_CHECK.__code__),
            (blocks,'verify_decomposition',_DECOMP,_DECOMP.__code__))
_SCOPE_FUNCTIONS=MappingProxyType({name:getattr(f1_state.Scope,name) for name in
             ('verify_state','_authority_check','_ledger','_state_metadata_digest')})
_SCOPE_CODE=MappingProxyType({name:fn.__code__ for name,fn in _SCOPE_FUNCTIONS.items()})
_HELPER_FUNCTIONS=MappingProxyType({name:getattr(f1_state,name) for name in
              ('case_fingerprint','_array_digest','_record','_digest')})
_HELPER_CODE=MappingProxyType({name:fn.__code__ for name,fn in _HELPER_FUNCTIONS.items()})
_PRICE_HELPERS=tuple((pricing,n,getattr(pricing,n),getattr(pricing,n).__code__) for n in
                   ('make_prices','run_lp_prices','run_pricing'))+(
                   (verify,'verify_global_lagrangian_bound',verify.verify_global_lagrangian_bound,
                    verify.verify_global_lagrangian_bound.__code__),)
_AUTHORITY_FUNCTIONS=MappingProxyType({cls:getattr(cls,'_authority_now') for cls in (f1_state.Scope,f1_basis.Scope)})
_AUTHORITY_CODE=MappingProxyType({cls:fn.__code__ for cls,fn in _AUTHORITY_FUNCTIONS.items()})
_WORKER_FUNCTIONS=MappingProxyType({n:getattr(worker,n) for n in
    ('verify_request','sources','scientific_sources','digest','sha','read','record')})
_WORKER_CODES=MappingProxyType({n:fn.__code__ for n,fn in _WORKER_FUNCTIONS.items()})

def _production_authority(request,code_root,adapter):
    """External draft binds its own SHA; production binds complete registry."""
    own=Path(__file__).resolve()
    if not own.is_relative_to(code_root):
        if own.parent!=Path(r'D:\v42_f1_price_seed35_candidate_20261010_01') or own.name!='price_seed.py':
            raise PermissionError('PRICE_SEED_EXTERNAL_DRAFT_PATH_REQUIRED')
        return dict(external_candidate_only=True,adapter_source=adapter)
    expected=code_root/'v42_autonomous_b2/f1_price_seed.py'
    if own!=expected:raise PermissionError('PRICE_SEED_DECLARED_MODULE_PATH_REQUIRED')
    if worker.ROOT.resolve()!=code_root:raise PermissionError('PRICE_SEED_IMMUTABLE_WORKER_ROOT_REQUIRED')
    for name,fn in _WORKER_FUNCTIONS.items():
        if getattr(worker,name) is not fn or fn.__code__ is not _WORKER_CODES[name]:
            raise PermissionError('PRICE_SEED_ORIGINAL_REQUEST_VERIFIER_REQUIRED:'+name)
    declared=_read(request['manifest'])
    for relative,expected_sha in dict(declared['builder_original_sources'],**declared['execution_sources']).items():
        path=(code_root/relative).resolve()
        if not path.is_relative_to(code_root):raise PermissionError('PRICE_SEED_DECLARED_SOURCE_ESCAPE')
        if f1_state._record(path)['sha256']!=expected_sha:
            raise PermissionError('GLOBAL_SOURCE_INTEGRITY_FAILURE:PRICE_SEED_SHARED_SOURCE_SHA_DRIFT:'+relative)
    manifest=worker.verify_request(request)
    if manifest['execution_sources'].get('v42_autonomous_b2/f1_price_seed.py')!=adapter['sha256']:
        raise PermissionError('GLOBAL_SOURCE_INTEGRITY_FAILURE:PRICE_SEED_OWN_DECLARED_SOURCE_REQUIRED')
    protected=(f1_state,f1_basis,algorithms,lb,blocks,pricing,verify,certificate_box,worker)
    loaded={}
    for module in protected:
        path=(code_root/(module.__name__.replace('.','/')+'.py')).resolve()
        if Path(module.__file__).resolve()!=path:
            raise PermissionError('PRICE_SEED_LOADED_IMMUTABLE_SOURCE_REQUIRED:'+module.__name__)
        relative=path.relative_to(code_root).as_posix()
        expected_sha=manifest['execution_sources'].get(relative,manifest['builder_original_sources'].get(relative))
        rec=f1_state._record(path)
        if expected_sha!=rec['sha256']:
            raise PermissionError('GLOBAL_SOURCE_INTEGRITY_FAILURE:PRICE_SEED_LOADED_SOURCE_NOT_DECLARED:'+relative)
        loaded[relative]=rec
    return dict(external_candidate_only=False,execution_SHA=manifest['execution_SHA'],
                manifest=f1_state._record(request['manifest']),adapter_source=adapter,loaded_sources=loaded)

def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()

def _digest(value):return sha256(_json(value)).hexdigest()

def _read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def _dual(values):
    """Normalize exact row-axis strings without rounding a multiplier."""
    result={}
    for k,v in values.items():
        i=int(k)
        if str(i)!=str(k) or i<0:raise PermissionError('PRICE_SEED_ROW_AXIS_REQUIRED')
        q=Fraction(v)
        if q:result[str(i)]=str(q)
    return result

def _dual_sha(values):
    raw='\n'.join(f'{i}:{values[str(i)]}' for i in sorted(map(int,values))).encode('ascii')
    return sha256(raw).hexdigest()

def _callable_seal(value):
    target=value.__func__ if inspect.ismethod(value) else value
    cells=getattr(target,'__closure__',None) or ()
    closures=tuple((cell,cell.cell_contents) for cell in cells)
    return (value.__self__ if inspect.ismethod(value) else None,target,getattr(target,'__code__',None),
            getattr(target,'__globals__',None),closures,getattr(target,'__defaults__',None),
            copy.copy(getattr(target,'__kwdefaults__',None)))

def _same_callable(value,seal):
    current=_callable_seal(value)
    return (all(current[i] is seal[i] for i in (0,1,2,3,5))
        and current[6]==seal[6] and len(current[4])==len(seal[4])
        and all(c is ec and v is ev for (c,v),(ec,ev) in zip(current[4],seal[4])))

def _function_namespace(function):
    """Bind the actual approved routed helpers at lazy construction."""
    result=[]
    for name in function.__code__.co_names:
        if name not in function.__globals__:continue
        value=function.__globals__[name]
        result.append((function.__globals__,name,value,_callable_seal(value)))
    return result

def _guard_namespace(rows):
    for namespace,name,value,seal in rows:
        current=namespace.get(name)
        if current is not value or not _same_callable(current,seal):
            raise PermissionError('PRICE_SEED_DELEGATE_NAMESPACE_DRIFT:'+name)

class PriceSeed:
    """One lazy same-attempt computational input adapter; no state imports."""
    def __init__(self, original_lp_round, request, code_root, get_f1_scope, owned, writer):
        if original_lp_round is not _LP or original_lp_round.__code__ is not _ORIGINALS[0][3]:
            raise PermissionError('PRICE_SEED_ORIGINAL_LP_ROUND_REQUIRED')
        self.original=original_lp_round
        self.request=copy.deepcopy(request);self.request_digest=_digest(self.request)
        self.code_root=Path(code_root).resolve();self.get_f1_scope=get_f1_scope
        self.owned=owned;self.writer=writer
        self.owner_seals={n:_callable_seal(getattr(self,n)) for n in ('original','get_f1_scope','owned','writer')}
        self.adapter=f1_state._record(__file__)
        self.authority=_production_authority(self.request,self.code_root,self.adapter)
        self.alias=algorithms.lp_round;self.alias_seal=_callable_seal(self.alias)
        if self.alias is not _LP and getattr(self.alias,'original_lp_round',None) is not _LP:
            raise PermissionError('PRICE_SEED_APPROVED_LAZY_ALIAS_REQUIRED')
        self.namespace=[]
        for f in (_LP,_REPAIR,_CHECK,_DECOMP,self.owned,self.writer,self.get_f1_scope):
            self.namespace.extend(_function_namespace(f))
        self.helpers=[(pricing,n,getattr(pricing,n),_callable_seal(getattr(pricing,n))) for n in
                      ('make_prices','run_lp_prices','run_pricing')]
        self.helpers.append((verify,'verify_global_lagrangian_bound',verify.verify_global_lagrangian_bound,
                             _callable_seal(verify.verify_global_lagrangian_bound)))
        self.entered=False
        self.current_scope=None
        self.integrity_originals=_ORIGINALS
        self.integrity_helpers=_PRICE_HELPERS
        self.table_identities={name:globals()[name] for name in
            ('_SCOPE_FUNCTIONS','_SCOPE_CODE','_HELPER_FUNCTIONS','_HELPER_CODE','_AUTHORITY_FUNCTIONS','_AUTHORITY_CODE',
             '_WORKER_FUNCTIONS','_WORKER_CODES')}
        for module,name,fn,code in self.integrity_helpers:
            current=getattr(module,name)
            if (fn.__code__ is not code or (current is not fn and
                    not (name=='run_pricing' and getattr(current,'original_pricing',None) is fn))):
                raise PermissionError('PRICE_SEED_ORIGINAL_PRICE_HELPER_REQUIRED:'+name)

    def _integrity(self):
        if self.entered:raise PermissionError('PRICE_SEED_REENTRANT_CALL_FORBIDDEN')
        if _digest(self.request)!=self.request_digest:
            raise PermissionError('PRICE_SEED_REQUEST_DRIFT')
        if f1_state._record(__file__)!=self.adapter:
            raise PermissionError('GLOBAL_SOURCE_INTEGRITY_FAILURE:PRICE_SEED_ADAPTER_SOURCE_DRIFT')
        if _production_authority(self.request,self.code_root,self.adapter)!=self.authority:
            raise PermissionError('PRICE_SEED_COMPLETE_SOURCE_AUTHORITY_DRIFT')
        for name,seal in self.owner_seals.items():
            if not _same_callable(getattr(self,name),seal):raise PermissionError('PRICE_SEED_SCOPE_DELEGATE_DRIFT:'+name)
        if not _same_callable(algorithms.lp_round,self.alias_seal):raise PermissionError('PRICE_SEED_ROUTING_ALIAS_DRIFT')
        if _ORIGINALS is not self.integrity_originals or _PRICE_HELPERS is not self.integrity_helpers:
            raise PermissionError('PRICE_SEED_CODE_BINDING_TABLE_DRIFT')
        if any(globals()[name] is not ref for name,ref in self.table_identities.items()):
            raise PermissionError('PRICE_SEED_VERIFIER_BINDING_TABLE_DRIFT')
        if (_LP is not self.integrity_originals[0][2] or _REPAIR is not self.integrity_originals[1][2]
                or _CHECK is not self.integrity_originals[2][2] or _DECOMP is not self.integrity_originals[3][2]):
            raise PermissionError('PRICE_SEED_BOUND_ORIGINAL_FUNCTION_DRIFT')
        for module,name,fn,code in self.integrity_originals:
            if fn.__code__ is not code:raise PermissionError('PRICE_SEED_ORIGINAL_CODE_DRIFT:'+name)
            if name!='lp_round' and getattr(module,name) is not fn:
                raise PermissionError('PRICE_SEED_ORIGINAL_ALIAS_DRIFT:'+name)
        for module,name,fn,seal in self.helpers:
            if getattr(module,name) is not fn or not _same_callable(fn,seal):
                raise PermissionError('PRICE_SEED_PRICE_HELPER_DRIFT:'+name)
        for name,code in _SCOPE_CODE.items():
            if (getattr(f1_state.Scope,name) is not _SCOPE_FUNCTIONS[name]
                    or getattr(f1_state.Scope,name).__code__ is not code):
                raise PermissionError('PRICE_SEED_F1_SCOPE_CODE_DRIFT:'+name)
        for name,code in _HELPER_CODE.items():
            if getattr(f1_state,name) is not _HELPER_FUNCTIONS[name] or getattr(f1_state,name).__code__ is not code:
                raise PermissionError('PRICE_SEED_F1_HELPER_DRIFT:'+name)
        for cls,fn in _AUTHORITY_FUNCTIONS.items():
            if getattr(cls,'_authority_now') is not fn or fn.__code__ is not _AUTHORITY_CODE[cls]:
                raise PermissionError('PRICE_SEED_F1_AUTHORITY_DESCRIPTOR_DRIFT')
        _guard_namespace(self.namespace)

    def _state(self,case,budget,scope):
        if scope.request!=self.request or scope.code_root!=self.code_root:
            raise PermissionError('PRICE_SEED_CURRENT_REQUEST_SCOPE_REQUIRED')
        # The verifier checks issuer/token, all stored arrays/case/input/source
        # identities, original FULL replay packet, and known original ledger.
        for name,expected in _SCOPE_FUNCTIONS.items():
            actual=getattr(scope,name)
            fn=actual.__func__ if inspect.ismethod(actual) else actual
            if (name in vars(scope) or getattr(type(scope),name) is not expected or fn is not expected
                    or (inspect.ismethod(actual) and actual.__self__ is not scope)):
                raise PermissionError('PRICE_SEED_ORIGINAL_STATE_DESCRIPTOR_REQUIRED:'+name)
        authority=getattr(scope,'_authority_now')
        if (type(scope) not in _AUTHORITY_FUNCTIONS or '_authority_now' in vars(scope)
                or not inspect.ismethod(authority) or authority.__self__ is not scope
                or authority.__func__ is not _AUTHORITY_FUNCTIONS[type(scope)]):
            raise PermissionError('PRICE_SEED_LIVE_AUTHORITY_DESCRIPTOR_REQUIRED')
        state=scope.verify_state(case,budget)
        return state

    def _seed(self,case,decomp,budget,scope):
        state=self._state(case,budget,scope)
        if state.pi is None:return None,dict(reason='FINITE_F1_PI_UNAVAILABLE')
        decomposition=_DECOMP(case,decomp)
        if decomposition.get('PASS') is not True or decomposition.get('case_sha')!=case.case_sha:
            raise PermissionError('PRICE_SEED_ORIGINAL_DECOMPOSITION_REQUIRED')
        selection_path=Path(self.request['output'])/'F1_FULL_DOMAIN_LB_SELECTION.json'
        selection=_read(selection_path)
        initial_dual_path=Path(self.request['output'])/'INITIAL_EXACT_ORIGINAL_DUAL.json'
        initial_cert_path=Path(self.request['output'])/'INITIAL_EXACT_LB_CERTIFICATE.json'
        initial_dual=_dual(_read(initial_dual_path));initial_cert=_read(initial_cert_path)
        selected=[c['certificate'] for c in selection['candidates'] if c['kind']==selection.get('selected')]
        if (selection.get('PASS') is not True or selection.get('case_sha')!=case.case_sha
                or Fraction(selection['maximum_exact_bound'])!=0 or len(selected)!=1
                or not selected[0].get('PASS') or selected[0].get('case_sha')!=case.case_sha
                or Fraction(selected[0]['exact_bound'])!=0
                or selected[0].get('dual_SHA256')!=_dual_sha({}) or initial_dual
                or initial_cert.get('PASS') is not True or initial_cert.get('case_sha')!=case.case_sha
                or Fraction(initial_cert['exact_bound'])!=0 or Fraction(initial_cert['exact_Global_LB'])!=0
                or initial_cert.get('dual_SHA256')!=_dual_sha({})
                or initial_cert.get('selected_candidate')!=selection['selected']):
            raise PermissionError('PRICE_SEED_CURRENT_ZERO_SELECTION_REQUIRED')
        records=[c['certificate'] for c in selection['candidates'] if c['kind']=='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI']
        if not records and str(selection.get('f1_status','')).startswith('F1_CANDIDATE_NOT_CERTIFIABLE:'):
            return None,dict(reason='ORIGINAL_F1_FULL_DOMAIN_CANDIDATE_NOT_CERTIFIABLE')
        if len(records)!=1:raise PermissionError('PRICE_SEED_CURRENT_CERTIFIED_F1_CANDIDATE_REQUIRED')
        dual,repair=_REPAIR(case.A,case.d,state.pi)
        dual=_dual(dual)
        certificate=_CHECK(case.A,case.d,dual,case_sha=case.case_sha)
        if (certificate.get('PASS') is not True or certificate.get('case_sha')!=case.case_sha
                or certificate.get('dual_SHA256')!=_dual_sha(dual)):
            raise PermissionError('PRICE_SEED_FULL_DOMAIN_CERTIFICATE_REQUIRED')
        previous=records[0]
        keys=('PASS','case_sha','exact_bound','dual_SHA256','source_rows_SHA256','nonzero_dual_rows')
        if any(previous.get(k)!=certificate.get(k) for k in keys):
            raise PermissionError('PRICE_SEED_ORIGINAL_CANDIDATE_CERTIFICATE_DRIFT')
        if Fraction(certificate['exact_bound'])>=0:
            return None,dict(reason='NEGATIVE_CERTIFIED_PRICE_SEED_NOT_AVAILABLE')
        coupling={str(int(i)):dual[str(int(i))] for i in decomp.coupling_rows if str(int(i)) in dual}
        if not coupling:return None,dict(reason='CERTIFIED_F1_COUPLING_IS_ZERO')
        evidence=dict(reason='CURRENT_F1_NEGATIVE_VALID_FULL_DOMAIN_CERTIFICATE_PRICE_ONLY',
            identity={k:self.request[k] for k in f1_state.IDENTITY_KEYS},case_sha=case.case_sha,
            implementation_SHA=self.request['implementation_SHA'],source_authority=copy.deepcopy(scope._authority),
            state_packet=copy.deepcopy(state.packet),completed_F1_native=copy.deepcopy(state.native_call),
            selection=f1_state._record(selection_path),initial_certified_dual=f1_state._record(initial_dual_path),
            initial_exact_certificate=f1_state._record(initial_cert_path),full_domain_certificate=certificate,affine_repair=repair,
            repaired_dual_SHA256=_dual_sha(dual),nonzero_original_rows=len(dual),nonzero_coupling_rows=len(coupling),
            adapter_source=self.adapter,Native_calls_added=0,Native_objective_used_as_Global_LB=False,
            selected_certified_dual_replaced=False,certified_frontier_modified=False,performance_claimed=False)
        return MappingProxyType(dual),evidence

    def __call__(self,case,decomp,dual,budget,frontier,path,method,kind='LP_ONLY',*,context=None):
        self._integrity()
        path=Path(self.owned(path)).resolve()
        if not path.is_relative_to(Path(self.request['output']).resolve()):
            raise PermissionError('PRICE_SEED_CURRENT_PRICE_OUTPUT_REQUIRED')
        eligible=(method=='L1' and kind=='LP_ONLY') or (method=='L4' and kind=='MILP_AND_LP')
        incoming=_dual(dual);before=Fraction(frontier.lb)
        reason='ORIGINAL_COMPUTATIONAL_PRICE_UNCHANGED'
        scope=self.get_f1_scope()
        if (not self.authority['external_candidate_only'] and type(budget) is not worker.ReceiptDateBudget):
            raise PermissionError('PRICE_SEED_CANONICAL_OWN_BUDGET_REQUIRED')
        if self.current_scope is not None and scope is not self.current_scope:
            raise PermissionError('PRICE_SEED_CURRENT_SCOPE_CHANGED')
        if scope is not None:self.current_scope=scope
        price=dual;evidence=None
        if eligible and not incoming and before==0 and scope is not None and scope.state is not None:
            seed,evidence=self._seed(case,decomp,budget,scope)
            if seed is not None:price=dict(seed);reason='CURRENT_F1_COMPUTATIONAL_PRICE_ONLY'
        if evidence is None:evidence=dict(reason=reason)
        self._integrity()
        if price is not dual:
            self.writer(path/'CURRENT_F1_COMPUTATIONAL_PRICE_SEED.json',dict(schema='V42_V35_DRAFT_CURRENT_F1_PRICE_SEED',
                PASS=True,method=method,kind=kind,certified_LB_before=str(before),evidence=evidence,
                computational_price_dual=price,original_driver_certified_dual=incoming))
        self._integrity()
        # The unchanged producer independently checks the generated full dual,
        # publishes only a stronger certified bound, and decides its return.
        # This wrapper forwards that exact return, never pairing seed+zero LB.
        self.entered=True
        try:
            result=self.original(case,decomp,price,budget,frontier,path,method,kind,context=context)
        finally:
            self.entered=False
            self._integrity()
        return result

def scoped_lp_round(original,request,code_root,get_f1_scope,owned,writer):
    return PriceSeed(original,request,code_root,get_f1_scope,owned,writer)
