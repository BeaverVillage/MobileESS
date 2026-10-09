"""Current-attempt process-local reuse of a scope-created projection authority.

No disk proof is admitted. The first original constructor derives and verifies
the proof. Every reuse rechecks its exact structural and scope fingerprints.
"""
from pathlib import Path
import hashlib, json
from types import FunctionType
import numpy as np

from datetime import date
import re
from . import pricing_box
from v42_m1_hybrid import blocks, pricing
from v42_may_campaign_native90 import m_model

# Capture immutable code objects before the worker installs proof-path aliases.
_ORIGINAL_AUTHORITY = pricing_box.ProjectionAuthority
_ORIGINAL_MATRIX_SHA = blocks.matrix_sha
_ORIGINAL_DOMAIN_SHA = m_model._domain_sha
_ORIGINAL_LOCAL_BOUND = pricing.local_exact_price_bound
_ORIGINAL_PRICING = pricing.run_pricing
_ORIGINAL_BOX = pricing_box.certificate_box
_ORIGINAL_DERIVE = _ORIGINAL_BOX.derive
_ORIGINAL_VERIFY = _ORIGINAL_BOX.verify
_ORIGINAL_DECOMPOSITION = pricing_box.verify_decomposition
_ORIGINAL_CODES = (_ORIGINAL_AUTHORITY.__init__.__code__,
    _ORIGINAL_AUTHORITY.local_bound.__code__, _ORIGINAL_MATRIX_SHA.__code__,
    _ORIGINAL_DOMAIN_SHA.__code__, _ORIGINAL_LOCAL_BOUND.__code__,
    _ORIGINAL_PRICING.__code__,_ORIGINAL_DERIVE.__code__,
    _ORIGINAL_VERIFY.__code__,_ORIGINAL_DECOMPOSITION.__code__)
_ORIGINAL_MODULES = ((pricing_box,'v42_autonomous_b2/pricing_box.py'),
    (blocks,'v42_m1_hybrid/blocks.py'),(m_model,'v42_may_campaign_native90/m_model.py'),
    (pricing,'v42_m1_hybrid/pricing.py'),(_ORIGINAL_BOX,'v42_b2_seed_recovery_v18/certificate_box.py'))
EXECUTION_FOLDERS = ('v42_b2_seed_recovery_v19','v42_b2_seed_recovery_v18r3',
    'v42_b2_seed_recovery_v18r2','v42_b2_seed_recovery_v18',
    'v42_b2_start_recovery_v13','v42_b2_build_authority_v13','v42_autonomous_b2')
ORIGINAL_SOURCE_COUNT = 1007
MIN_EXECUTION_SOURCE_COUNT = 97

def _absolute_d(path):
    raw=Path(path)
    if (not raw.is_absolute() or raw.drive.upper()!='D:'
        or '..' in raw.parts or str(raw).startswith('\\\\')):
        raise ValueError('PROJECTION_CACHE_ABSOLUTE_OWNED_D_PATH_REQUIRED')
    return raw.resolve()

def _request_paths(request,request_path,output_root):
    root=_absolute_d(request['root'])
    day=request['day'];attempt=request['attempt_id']
    if (not isinstance(day,str) or not re.fullmatch(r'2025-05-[0-9]{2}',day)
        or date.fromisoformat(day).month!=5
        or not isinstance(attempt,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',attempt)
        or request.get('arm')!='B2'):
        raise ValueError('PROJECTION_CACHE_EXACT_DATE_ATTEMPT_REQUIRED')
    owned=root/'dates'/'B2'/day/'attempts'/attempt
    if (_absolute_d(output_root)!=owned/'output'
        or _absolute_d(request['output'])!=owned/'output'
        or _absolute_d(request_path)!=owned/'request.json'):
        raise ValueError('PROJECTION_CACHE_EXACT_CURRENT_ATTEMPT_PATH_REQUIRED')
    return root,owned


def receipt(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha)

def array_sha(value):
    value=np.asarray(value);h=hashlib.sha256()
    h.update(value.dtype.str.encode());h.update(np.asarray(value.shape,dtype='<i8').tobytes())
    h.update(np.ascontiguousarray(value).tobytes())
    return h.hexdigest()

def rebound(original,namespace):
    result=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    result.__kwdefaults__=original.__kwdefaults__
    return result

class CachedAuthority:
    def __init__(self,scope,entry):self._scope,self._entry=scope,entry

    def local_bound(self,block,exact_objective,dual):
        try:
            self._scope._validate_entry(self._entry)
            result=self._entry['original_authority_bound'](block,exact_objective,dual)
            self._scope._validate_entry(self._entry)
            return result
        except Exception:
            self._scope.close();raise

    @property
    def receipt(self):
        self._scope._validate_entry(self._entry)
        return dict(self._entry['proof_receipt'])

    @property
    def lower(self):
        self._scope._validate_entry(self._entry)
        return self._entry['authority'].lower

    @property
    def upper(self):
        self._scope._validate_entry(self._entry)
        return self._entry['authority'].upper

class _AttemptProjectionCache:
    def __init__(self,*,authority_type,matrix_sha,domain_sha,original_local_bound,
                 request_path,source_paths,expected_source_sha,output_root):
        self.authority_type=authority_type;self.matrix_sha=matrix_sha;self.domain_sha=domain_sha
        self.original_local_bound=original_local_bound
        self._code_binding=(authority_type.__init__.__code__,authority_type.local_bound.__code__,
                            original_local_bound.__code__,matrix_sha.__code__,domain_sha.__code__)
        self.request_path=Path(request_path).resolve();self.output_root=Path(output_root).resolve()
        self._root_identity=str(self.output_root)
        self._request_receipt=receipt(self.request_path)
        self._request=json.loads(self.request_path.read_text(encoding='utf-8-sig'))
        _request_paths(self._request,self.request_path,self.output_root)
        for key in ('run_id','day','arm','attempt_id','implementation_SHA','output'):
            if not isinstance(self._request.get(key),str) or not self._request[key]:
                raise ValueError('PROJECTION_CACHE_REQUEST_IDENTITY_REQUIRED:'+key)
        if self._request['arm']!='B2' or self._request['implementation_SHA']!=expected_source_sha:
            raise ValueError('PROJECTION_CACHE_CURRENT_SOURCE_REQUEST_MISMATCH')
        if Path(self._request['output']).resolve()!=self.output_root:
            raise ValueError('PROJECTION_CACHE_REQUEST_OWNED_ROOT_MISMATCH')
        self.expected_source_sha=expected_source_sha
        supplied_source_paths=tuple(Path(path).resolve() for path in source_paths)
        if not supplied_source_paths:raise ValueError('PROJECTION_CACHE_ORIGINAL_SOURCE_RECEIPTS_REQUIRED')
        self.source_paths=tuple(dict.fromkeys(list(supplied_source_paths)
                                              +[Path(__file__).resolve()]))
        if not self.source_paths:raise ValueError('PROJECTION_CACHE_SOURCE_RECEIPTS_REQUIRED')
        self._source_receipts=tuple(receipt(path) for path in self.source_paths)
        self._active=False;self._closed=False;self._entry=None
        self.stats=dict(original_constructions=0,cache_hits=0,entry_validations=0)

    def __enter__(self):
        if self._closed or self._active:raise ValueError('PROJECTION_CACHE_SCOPE_CLOSED_OR_REENTERED')
        self._active=True;return self

    def close(self):
        self._active=False;self._closed=True
        if self._entry is not None:self._entry['authority']=None
        self._entry=None

    def __exit__(self,*exception):self.close()

    def _require_active(self):
        if not self._active or self._closed:raise ValueError('PROJECTION_CACHE_SCOPE_CLOSED')

    def _context_check(self):
        self._require_active()
        if str(self.output_root.resolve())!=self._root_identity:
            raise ValueError('PROJECTION_CACHE_OWNED_ROOT_DRIFT')
        if receipt(self.request_path)!=self._request_receipt:
            raise ValueError('PROJECTION_CACHE_CURRENT_REQUEST_DRIFT')
        if tuple(receipt(path) for path in self.source_paths)!=self._source_receipts:
            raise ValueError('PROJECTION_CACHE_SOURCE_BYTES_DRIFT')
        current=(self.authority_type.__init__.__code__,self.authority_type.local_bound.__code__,
                 self.original_local_bound.__code__,self.matrix_sha.__code__,self.domain_sha.__code__)
        if current!=self._code_binding:raise ValueError('PROJECTION_CACHE_ORIGINAL_CODE_OBJECT_DRIFT')

    def _blocks(self,decomp):
        blocks=tuple(sorted(decomp.units.items()))+(('NONUNIT',decomp.nonunit_block),)
        return (id(decomp),decomp.case_sha,
            array_sha(decomp.coupling_rows),array_sha(decomp.column_owner),
            tuple((name,id(block),id(block.A),id(block.d),self.matrix_sha(block.A),
                self.domain_sha(block.d),array_sha(block.original_rows),array_sha(block.original_columns))
                for name,block in blocks))

    def _fingerprint(self,case,decomp):
        if (Path(case.output).resolve()!=self.output_root or case.identity.get('day')!=self._request['day']
            or case.identity.get('arm')!=self._request['arm']):
            raise ValueError('PROJECTION_CACHE_CURRENT_ATTEMPT_CASE_ROOT_OR_DAY_MISMATCH')
        identity=json.dumps(case.identity,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        return (id(case),case.case_sha,id(case.A),id(case.d),self.matrix_sha(case.A),
                self.domain_sha(case.d),self._blocks(decomp),str(Path(case.output).resolve()),
                hashlib.sha256(identity).hexdigest())

    def _owned_output(self,output):
        path=Path(output).resolve()
        if not path.is_relative_to(self.output_root):
            raise ValueError('PROJECTION_CACHE_PRICE_OUTPUT_ROOT_ESCAPE')
        return path

    def _validate_entry(self,entry):
        try:
            self._context_check()
            if entry is not self._entry or entry.get('authority') is None:
                raise ValueError('PROJECTION_CACHE_REVOKED_ENTRY')
            case,decomp=entry['case'],entry['decomp'];authority=entry['authority']
            bound=authority.local_bound
            stored=entry['original_authority_bound']
            if (getattr(bound,'__self__',None) is not authority
                or getattr(bound,'__func__',None) is not entry['original_authority_function']
                or bound.__func__.__code__ is not self._code_binding[1]
                or getattr(stored,'__self__',None) is not authority
                or getattr(stored,'__func__',None) is not bound.__func__
                or stored.__func__.__code__ is not self._code_binding[1]):
                raise ValueError('PROJECTION_CACHE_ACTUAL_BOUND_CALLABLE_DRIFT')
            if self._fingerprint(case,decomp)!=entry['fingerprint']:
                raise ValueError('PROJECTION_CACHE_ORIGINAL_STRUCTURAL_IDENTITY_DRIFT')
            if (authority.case is not case or authority.decomp is not decomp
                or authority.original_local_bound is not self.original_local_bound
                or authority.case_sha!=case.case_sha
                or authority.matrix_sha!=entry['fingerprint'][4]
                or authority.domain_sha!=entry['fingerprint'][5]):
                raise ValueError('PROJECTION_CACHE_AUTHORITY_BINDING_DRIFT')
            if authority.lower.flags.writeable or authority.upper.flags.writeable:
                raise ValueError('PROJECTION_CACHE_ENVELOPE_NOT_READ_ONLY')
            if (array_sha(authority.lower),array_sha(authority.upper))!=entry['envelope_sha']:
                raise ValueError('PROJECTION_CACHE_ENVELOPE_BYTES_DRIFT')
            if authority.receipt!=entry['proof_receipt'] or receipt(entry['proof_receipt']['path'])!=entry['proof_receipt']:
                raise ValueError('PROJECTION_CACHE_GENERATED_PROOF_RECEIPT_DRIFT')
            if not Path(entry['proof_receipt']['path']).resolve().is_relative_to(self.output_root):
                raise ValueError('PROJECTION_CACHE_PROOF_ROOT_ESCAPE')
            self.stats['entry_validations']+=1
        except Exception:
            self.close();raise

    def acquire(self,case,decomp,output):
        try:
            self._context_check();output=self._owned_output(output)
            if self._entry is not None:
                if case is not self._entry['case'] or decomp is not self._entry['decomp']:
                    raise ValueError('PROJECTION_CACHE_CASE_OR_DECOMPOSITION_OBJECT_DRIFT')
                self._validate_entry(self._entry);self.stats['cache_hits']+=1
                return CachedAuthority(self,self._entry)
            proof_path=output/'FULL_CASE_PRICING_BOX_PROOF.json'
            if proof_path.exists():raise ValueError('PROJECTION_CACHE_EXISTING_PROOF_NOT_ADMITTED')
            before=self._fingerprint(case,decomp)
            authority=self.authority_type(case,decomp,output,self.original_local_bound)
            self.stats['original_constructions']+=1
            self._context_check()
            if self._fingerprint(case,decomp)!=before:
                raise ValueError('PROJECTION_CACHE_CONSTRUCTION_MUTATED_ORIGINAL_CASE')
            if not Path(authority.receipt['path']).resolve().is_relative_to(output):
                raise ValueError('PROJECTION_CACHE_FIRST_GENERATED_PROOF_ROOT_ESCAPE')
            authority.lower.setflags(write=False);authority.upper.setflags(write=False)
            entry=dict(case=case,decomp=decomp,authority=authority,fingerprint=before,
                envelope_sha=(array_sha(authority.lower),array_sha(authority.upper)),
                proof_receipt=dict(authority.receipt),original_authority_bound=authority.local_bound,
                original_authority_function=self.authority_type.local_bound)
            self._entry=entry;self._validate_entry(entry)
            return CachedAuthority(self,entry)
        except Exception:
            self.close();raise

    def scoped_pricing(self,original,output_directory):
        original_code=original.__code__
        def run(case,decomp,prices,ledger,output,**kwargs):
            try:
                if original.__code__ is not original_code:
                    raise ValueError('PROJECTION_CACHE_ORIGINAL_PRICING_CODE_DRIFT')
                authority=self.acquire(case,decomp,output_directory(output))
                namespace=dict(original.__globals__,local_exact_price_bound=authority.local_bound,
                               output_directory=output_directory)
                result=rebound(original,namespace)(case,decomp,prices,ledger,output,**kwargs)
                self._validate_entry(self._entry)
                return result
            except Exception:
                self.close();raise
        run.original_pricing=original;run.original_local_bound=self.original_local_bound
        return run


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _loaded_originals_check():
    current=(_ORIGINAL_AUTHORITY.__init__.__code__,
        _ORIGINAL_AUTHORITY.local_bound.__code__,_ORIGINAL_MATRIX_SHA.__code__,
        _ORIGINAL_DOMAIN_SHA.__code__,_ORIGINAL_LOCAL_BOUND.__code__,_ORIGINAL_PRICING.__code__,
        _ORIGINAL_DERIVE.__code__,_ORIGINAL_VERIFY.__code__,_ORIGINAL_DECOMPOSITION.__code__)
    constructor_globals=_ORIGINAL_AUTHORITY.__init__.__globals__
    if (current!=_ORIGINAL_CODES or pricing_box.ProjectionAuthority is not _ORIGINAL_AUTHORITY
        or blocks.matrix_sha is not _ORIGINAL_MATRIX_SHA
        or m_model._domain_sha is not _ORIGINAL_DOMAIN_SHA
        or pricing.local_exact_price_bound is not _ORIGINAL_LOCAL_BOUND
        or pricing_box.certificate_box is not _ORIGINAL_BOX
        or _ORIGINAL_BOX.derive is not _ORIGINAL_DERIVE or _ORIGINAL_BOX.verify is not _ORIGINAL_VERIFY
        or pricing_box.verify_decomposition is not _ORIGINAL_DECOMPOSITION
        or constructor_globals.get('certificate_box') is not _ORIGINAL_BOX
        or constructor_globals.get('verify_decomposition') is not _ORIGINAL_DECOMPOSITION
        or constructor_globals.get('matrix_sha') is not _ORIGINAL_MATRIX_SHA
        or constructor_globals.get('_domain_sha') is not _ORIGINAL_DOMAIN_SHA):
        raise ValueError('PROJECTION_CACHE_MODULE_LOAD_ORIGINAL_CODE_DRIFT')


def _loaded_source_roots_check(code_root):
    for module,relative in _ORIGINAL_MODULES:
        if Path(module.__file__).resolve()!=code_root/relative:
            raise ValueError('PROJECTION_CACHE_ORIGINAL_MODULE_IMPORTED_FROM_OTHER_SOURCE_ROOT')
    functions=(_ORIGINAL_AUTHORITY.__init__,_ORIGINAL_AUTHORITY.local_bound,
        _ORIGINAL_MATRIX_SHA,_ORIGINAL_DOMAIN_SHA,_ORIGINAL_LOCAL_BOUND,_ORIGINAL_PRICING,
        _ORIGINAL_DERIVE,_ORIGINAL_VERIFY,_ORIGINAL_DECOMPOSITION)
    relatives=('v42_autonomous_b2/pricing_box.py','v42_autonomous_b2/pricing_box.py',
        'v42_m1_hybrid/blocks.py','v42_may_campaign_native90/m_model.py',
        'v42_m1_hybrid/bound.py','v42_m1_hybrid/pricing.py',
        'v42_b2_seed_recovery_v18/certificate_box.py','v42_b2_seed_recovery_v18/certificate_box.py',
        'v42_m1_hybrid/blocks.py')
    if any(Path(function.__code__.co_filename).resolve()!=code_root/relative
           for function,relative in zip(functions,relatives)):
        raise ValueError('PROJECTION_CACHE_ORIGINAL_CODE_IMPORTED_FROM_OTHER_SOURCE_ROOT')


def _relative_source(name):
    if (not isinstance(name,str) or not name or '\\' in name or ':' in name
        or name.startswith('/') or any(p in ('','..','.') for p in name.split('/'))):
        raise ValueError('PROJECTION_CACHE_DECLARED_SOURCE_PATH_DRIFT')
    return Path(name)


def _fresh_authorization(request,manifest,root):
    if (request.get('restart_from_zero') is not True
        or manifest.get('restart_from_zero') is not True
        or request.get('previous_attempts')!=[] or manifest.get('prior_attempts')!={}
        or manifest.get('historical_bound_point_reuse') is not False
        or request.get('native_budget_seconds')!=5400
        or request.get('wall_budget_seconds') is not None
        or request.get('target_gap')!=.03 or request.get('Threads')!=1
        or request.get('P2_calls')!=0):
        raise ValueError('PROJECTION_CACHE_FRESH_ZERO_CURRENT_REQUEST_REQUIRED')
    supplied=request.get('reset_authorization')
    if not isinstance(supplied,dict) or supplied!=manifest.get('reset_authorization'):
        raise ValueError('PROJECTION_CACHE_FRESH_ZERO_AUTHORIZATION_REQUIRED')
    path=_absolute_d(supplied['path'])
    if path!=root/'USER_ZERO_START_RETRY_AUTHORIZATION.json' or receipt(path)!=supplied:
        raise ValueError('PROJECTION_CACHE_RESET_AUTHORIZATION_SHA_OR_ROOT_DRIFT')
    authority=json.loads(path.read_text(encoding='utf-8-sig'))
    required=dict(schema='V42_USER_AUTHORIZED_ZERO_START_RETRY_V1',
        scope='VERIFIED_SOURCE_REPAIR_FRESH_DATE_RETRY',restart_from_zero=True,
        native_budget_seconds=5400,previous_checkpoint_reuse=False,
        previous_native_budget_carry=False,old_attempts_and_accounting_preserved=True,
        normal_workers_must_continue=True,applies_to_hourly_verified_repairs=True)
    if (_absolute_d(authority['campaign_root'])!=root
        or any(authority.get(k)!=v for k,v in required.items())):
        raise ValueError('PROJECTION_CACHE_RESET_AUTHORIZATION_POLICY_DRIFT')
    return supplied


class Scope(_AttemptProjectionCache):
    """Admitted production scope; create only through create_scope."""
    def __init__(self,*,seal,**kwargs):
        self._seal=seal;self._seal_digest=_digest(seal);self._reuse_receipts=()
        super().__init__(**kwargs)

    def _context_check(self):
        _loaded_originals_check()
        _loaded_source_roots_check(Path(self._seal['code_root']))
        if _digest(self._seal)!=self._seal_digest:
            raise ValueError('PROJECTION_CACHE_DECLARED_SOURCE_BINDING_DRIFT')
        if _execution_names(Path(self._seal['code_root']))!=set(self._seal['execution_names']):
            raise ValueError('PROJECTION_CACHE_ACTIVE_EXECUTION_SOURCE_SET_DRIFT')
        for key in ('manifest','authorization'):
            if receipt(self._seal[key]['path'])!=self._seal[key]:
                raise ValueError('PROJECTION_CACHE_CURRENT_SEALED_'+key.upper()+'_DRIFT')
        for row in self._reuse_receipts:
            if receipt(row['path'])!=row:
                raise ValueError('PROJECTION_CACHE_CURRENT_ROUND_REUSE_RECEIPT_DRIFT')
        super()._context_check()

    def acquire(self,case,decomp,output):
        before=self.stats['cache_hits']
        authority=super().acquire(case,decomp,output)
        if self.stats['cache_hits']!=before:
            try:
                output=self._owned_output(output);output.mkdir(parents=True,exist_ok=True)
                path=output/'CURRENT_ATTEMPT_PROJECTION_REUSE_RECEIPT.json'
                value=dict(schema='V42_CURRENT_ATTEMPT_PROJECTION_REUSE_V29',
                    run_id=self._request['run_id'],day=self._request['day'],arm='B2',
                    attempt_id=self._request['attempt_id'],implementation_SHA=self.expected_source_sha,
                    case_sha=case.case_sha,current_round_output=str(output),
                    first_same_attempt_original_proof=dict(self._entry['proof_receipt']),
                    source_manifest=dict(self._seal['manifest']),current_request=dict(self._request_receipt),
                    same_owned_case_and_decomposition_objects=True,
                    fresh_derivation_or_independent_replay_claimed=False,
                    prices_or_duals_or_local_bounds_or_Global_LB_cached=False,
                    original_local_and_independent_FULL_signed_checks_still_required=True,
                    historical_or_cross_attempt_proof_admission=False,
                    original_derive_calls_added=0,original_envelope_verify_calls_added=0,
                    Native_calls_added=0,standalone_NONUNIT_closure_claimed=False)
                # A repeated output never overwrites evidence or admits an old receipt.
                with path.open('x',encoding='utf-8') as stream:
                    json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
                self._reuse_receipts+= (receipt(path),)
                self._context_check()
            except Exception:
                self.close();raise
        return authority

    def scoped_pricing(self,original,output_directory):
        _loaded_originals_check()
        if original is not _ORIGINAL_PRICING:
            raise ValueError('PROJECTION_CACHE_MODULE_LOAD_ORIGINAL_PRICING_REQUIRED')
        return super().scoped_pricing(original,output_directory)


def create_scope(request,manifest,code_root):
    """Lazy admission for the worker's current fresh request and source seal.

    Import this module before installing pricing aliases. The returned scope
    spans the complete proof_scope attempt, with one original first derivation.
    """
    _loaded_originals_check()
    code_root=_absolute_d(code_root)
    if Path(__file__).resolve()!=code_root/'v42_autonomous_b2'/'pricing_cache.py':
        raise ValueError('PROJECTION_CACHE_ADAPTER_IMPORTED_FROM_OTHER_SOURCE_ROOT')
    _loaded_source_roots_check(code_root)
    output=_absolute_d(request['output']);request_path=output.parent/'request.json'
    root,owned=_request_paths(request,request_path,output)
    current=json.loads(request_path.read_text(encoding='utf-8-sig'))
    if current!=request:raise ValueError('PROJECTION_CACHE_CURRENT_REQUEST_FILE_DRIFT')
    for key,name in (('result','RESULT.json'),('progress','progress.json'),('error','error.json')):
        if _absolute_d(request[key])!=owned/name:
            raise ValueError('PROJECTION_CACHE_CURRENT_ATTEMPT_PACKET_PATH_DRIFT')
    manifest_path=_absolute_d(request['manifest']);manifest_receipt=receipt(manifest_path)
    if (manifest_path.parent!=root or manifest_receipt['sha256']!=request['manifest_SHA']
        or json.loads(manifest_path.read_text(encoding='utf-8-sig'))!=manifest
        or manifest.get('schema')!='V42_AUTONOMOUS_B2_V20'
        or manifest.get('run_id')!=request['run_id']
        or request['attempt_id'] not in manifest.get('attempt_ids',[manifest.get('attempt_id')])
        or request['day'] not in manifest.get('input_folders',{})
        or _absolute_d(request['input_folder'])!=_absolute_d(manifest['input_folders'][request['day']])):
        raise ValueError('PROJECTION_CACHE_CURRENT_SOURCE_MANIFEST_DRIFT')
    authorization=_fresh_authorization(request,manifest,root)
    originals=manifest.get('builder_original_sources');execution=manifest.get('execution_sources')
    if (not isinstance(originals,dict) or len(originals)!=ORIGINAL_SOURCE_COUNT
        or not isinstance(execution,dict) or len(execution)<MIN_EXECUTION_SOURCE_COUNT
        or not set(originals).isdisjoint(execution)
        or _digest(execution)!=manifest.get('execution_SHA')
        or request['implementation_SHA']!=manifest.get('execution_SHA')
        or request.get('deployment_SHA')!=manifest.get('execution_SHA')):
        raise ValueError('PROJECTION_CACHE_COMPLETE_DECLARED_SOURCE_SEAL_REQUIRED')
    actual_execution=_execution_names(code_root)
    if set(execution)!=actual_execution:
        raise ValueError('PROJECTION_CACHE_EXECUTION_SOURCE_SET_INCOMPLETE')
    declared=dict(originals)
    for name,sha in execution.items():
        if name in declared and declared[name]!=sha:
            raise ValueError('PROJECTION_CACHE_CONFLICTING_DECLARED_SOURCE_SHA')
        declared[name]=sha
    required=('v42_autonomous_b2/pricing_cache.py','v42_autonomous_b2/pricing_box.py',
        'v42_autonomous_b2/worker.py','v42_autonomous_b2/canonical_stream.py',
        'v42_m1_hybrid/blocks.py','v42_m1_hybrid/bound.py','v42_m1_hybrid/pricing.py',
        'v42_may_campaign_native90/m_model.py','v42_b2_seed_recovery_v18/certificate_box.py',
        'v42_m1_research/check_lb.py','v42_m1_anytime/algorithms.py')
    if not set(required).issubset(declared):
        raise ValueError('PROJECTION_CACHE_ORIGINAL_CHECKER_SOURCE_SET_INCOMPLETE')
    paths=[]
    for name,expected in sorted(declared.items()):
        path=code_root/_relative_source(name)
        if (not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected)
            or not path.resolve().is_relative_to(code_root)
            or receipt(path)['sha256']!=expected):
            raise ValueError('PROJECTION_CACHE_DECLARED_SOURCE_SHA_DRIFT:'+name)
        paths.append(path)
    seal=dict(code_root=str(code_root),declared_sources=declared,manifest=manifest_receipt,
              authorization=dict(authorization),source_SHA=manifest['execution_SHA'],
              execution_names=sorted(execution))
    return Scope(seal=seal,authority_type=_ORIGINAL_AUTHORITY,matrix_sha=_ORIGINAL_MATRIX_SHA,
        domain_sha=_ORIGINAL_DOMAIN_SHA,original_local_bound=_ORIGINAL_LOCAL_BOUND,
        request_path=request_path,source_paths=paths+[manifest_path,Path(authorization['path'])],
        expected_source_sha=manifest['execution_SHA'],output_root=output)


def _execution_names(code_root):
    return {p.relative_to(code_root).as_posix() for folder in EXECUTION_FOLDERS
        for p in (code_root/folder).iterdir() if p.is_file() and p.suffix in ('.py','.html')}
