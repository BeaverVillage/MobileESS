from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import hashlib, json
import numpy as np
import pytest
from scipy import sparse

import builtins,importlib.util,sys,tempfile
from types import ModuleType,FunctionType
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
DRAFT=REPO/'tmp/v29_projection_cache_draft'
# Pure original AST loading is isolated from production package initializers.
_saved_common=sys.modules.pop('v42_b2_seed_recovery_v19.common',None)
_spec=importlib.util.spec_from_file_location('_v29_port_original_loader',DRAFT/'original_loader.py')
original_loader=importlib.util.module_from_spec(_spec)
sys.modules[_spec.name]=original_loader
try:_spec.loader.exec_module(original_loader)
finally:
    sys.modules.pop('v42_b2_seed_recovery_v19.common',None)
    if _saved_common is not None:sys.modules['v42_b2_seed_recovery_v19.common']=_saved_common
ProjectionAuthority=original_loader.ProjectionAuthority
build_blocks=original_loader.build_blocks;matrix_sha=original_loader.matrix_sha
domain_sha=original_loader.domain_sha;local_bound=original_loader.local_bound
full_checker=original_loader.full_checker;original_derive=original_loader.original_derive
original_verify=original_loader.original_verify;COUNTERS=original_loader.COUNTERS;PROOFS=original_loader.PROOFS
_pure_prices=original_loader.load('v42_m1_hybrid/pricing.py',('run_pricing',),dict())


def load_cache(path):
    namespace=ModuleType('_v29_cache_'+str(abs(hash(str(path)))))
    namespace.__file__=str(path);namespace.__package__='v42_autonomous_b2'
    code_root=Path(path).parents[1]
    def clone(function,relative,globals=None):
        # Only FAKE_SOURCE fixture metadata changes; original arithmetic/code
        # instructions and globals stay identical for the Native0 comparison.
        out=FunctionType(function.__code__.replace(co_filename=str(code_root/relative)),
            function.__globals__ if globals is None else globals,function.__name__,function.__defaults__,function.__closure__)
        out.__kwdefaults__=function.__kwdefaults__;return out
    block=SimpleNamespace(__file__=str(code_root/'v42_m1_hybrid/blocks.py'),matrix_sha=clone(matrix_sha,'v42_m1_hybrid/blocks.py'))
    decomposition=clone(original_loader.blocks['verify_decomposition'],'v42_m1_hybrid/blocks.py')
    price=SimpleNamespace(__file__=str(code_root/'v42_m1_hybrid/pricing.py'),
        local_exact_price_bound=clone(local_bound,'v42_m1_hybrid/bound.py'),
        run_pricing=clone(_pure_prices['run_pricing'],'v42_m1_hybrid/pricing.py'))
    model=SimpleNamespace(__file__=str(code_root/'v42_may_campaign_native90/m_model.py'),
        _domain_sha=clone(domain_sha,'v42_may_campaign_native90/m_model.py'))
    box=SimpleNamespace(__file__=str(code_root/'v42_b2_seed_recovery_v18/certificate_box.py'),
        derive=clone(original_loader.derive,'v42_b2_seed_recovery_v18/certificate_box.py'),
        verify=clone(original_loader.verify,'v42_b2_seed_recovery_v18/certificate_box.py'))
    authority_globals=dict(ProjectionAuthority.__init__.__globals__,certificate_box=box,
        verify_decomposition=decomposition,matrix_sha=block.matrix_sha,_domain_sha=model._domain_sha)
    authority=type('ProjectionAuthority',(),dict(
        __init__=clone(ProjectionAuthority.__init__,'v42_autonomous_b2/pricing_box.py',authority_globals),
        local_bound=clone(ProjectionAuthority.local_bound,'v42_autonomous_b2/pricing_box.py',authority_globals)))
    pbox=SimpleNamespace(__file__=str(code_root/'v42_autonomous_b2/pricing_box.py'),ProjectionAuthority=authority,
        certificate_box=box,verify_decomposition=decomposition)
    ordinary_import=builtins.__import__
    def scientific_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level==1 and tuple(fromlist)==('pricing_box',):
            return SimpleNamespace(pricing_box=pbox)
        if name=='v42_m1_hybrid':
            return SimpleNamespace(blocks=block,pricing=price)
        if name=='v42_may_campaign_native90':
            return SimpleNamespace(m_model=model)
        return ordinary_import(name,globals,locals,fromlist,level)
    namespace.__dict__['__builtins__']=dict(vars(builtins),__import__=scientific_import)
    exec(compile(Path(path).read_text(),str(path),'exec'),namespace.__dict__)
    return namespace

projection_cache=load_cache(REPO/'v42_autonomous_b2/pricing_cache.py')
AttemptProjectionCache=projection_cache._AttemptProjectionCache;receipt=projection_cache.receipt

@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix='v29_port_',dir=REPO/'tmp') as directory:
        yield Path(directory)

@pytest.fixture(autouse=True)
def original_record_import(monkeypatch):
    monkeypatch.setitem(sys.modules,'v42_b2_seed_recovery_v19.common',original_loader.shim)

local_exact_price_bound=local_bound

def resources(tmp_path,helpers=1,day='2025-05-01',attempt='fresh0',objective=1.):
    campaign=tmp_path/'kernel_campaign';attempt_root=campaign/'dates'/'B2'/day/'attempts'/attempt
    root=attempt_root/'output';attempt_root.mkdir(parents=True)
    source=attempt_root/'draft_original_source_binding.py';source.write_text('unchanged math fixture\n')
    n=4+helpers;A=sparse.lil_matrix((4+helpers,n))
    for j in range(4):A[j,j]=1.
    for k in range(helpers):A[4+k,4+k]=1.;A[4+k,0 if k==0 else 3+k]=-1.
    d=dict(names=np.array([f'route_flow[M{i},0]' for i in range(1,5)]+[f'original_helper_{k}' for k in range(helpers)]),
        lower=np.array([0.]*4+[-np.inf]*helpers),upper=np.array([1.]*4+[np.inf]*helpers),
        types=np.array(['B']*4+['C']*helpers),objective=np.array([.25,-.5,.75,0.]+[objective]*helpers),
        rhs=np.array([0.]*4+[.125]*helpers),sense=np.array(['>']*4+['=']*helpers),
        row_names=np.array([f'original_row_{k}' for k in range(4+helpers)]),constant=np.array(.5))
    case=SimpleNamespace(A=A.tocsr(),d=d,case_sha='case_'+day+'_'+attempt,point=np.zeros(n),
        output=root,identity=dict(day=day,arm='B2',fixture='CURRENT_SMALL_ORIGINAL_CASE'))
    decomp=build_blocks(case);source_sha='source_current_attempt_only'
    request=dict(root=str(campaign),run_id='current_campaign',day=day,arm='B2',attempt_id=attempt,
        implementation_SHA=source_sha,output=str(root),previous_attempts=[])
    request_path=attempt_root/'request.json';request_path.write_text(json.dumps(request))
    args=dict(authority_type=ProjectionAuthority,matrix_sha=matrix_sha,domain_sha=domain_sha,
        original_local_bound=local_bound,request_path=request_path,
        source_paths=[source,original_loader.__file__]+[proof['path'] for proof in PROOFS],expected_source_sha=source_sha,output_root=root)
    return SimpleNamespace(case=case,decomp=decomp,root=root,source=source,request=request,
        request_path=request_path,args=args,scope=AttemptProjectionCache(**args))

def test_one_unchanged_derive_verify_then_process_local_hits(tmp_path):
    x=resources(tmp_path,helpers=12);before=dict(COUNTERS)
    original_domain=domain_sha(x.case.d);original_matrix=matrix_sha(x.case.A)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'L1')
        first_receipt=a.receipt;assert not a.lower.flags.writeable and not a.upper.flags.writeable
        for i in range(10):
            b=x.scope.acquire(x.case,x.decomp,x.root/f'L{i+2}')
            assert b.receipt==first_receipt
            b.local_bound(x.decomp.nonunit_block,{0:Fraction(-1)},{})
            for block in x.decomp.units.values():
                cached=b.local_bound(block,{0:Fraction(1,3)},{})
                original=local_bound(block,{0:Fraction(1,3)},{})
                assert cached['exact_bound']==original['exact_bound']
            assert not (x.root/f'L{i+2}'/'FULL_CASE_PRICING_BOX_PROOF.json').exists()
        assert x.scope.stats['original_constructions']==1
        assert x.scope.stats['cache_hits']==10
        assert domain_sha(x.case.d)==original_domain and matrix_sha(x.case.A)==original_matrix
    assert COUNTERS['derive']-before['derive']==1 and COUNTERS['verify']-before['verify']==1

@pytest.mark.parametrize('objective',[1.,-1.,.125,-.125])
@pytest.mark.parametrize('helpers',[1,3,12])
def test_original_price_sum_and_independent_full_signed_checker_equal(tmp_path,objective,helpers):
    x=resources(tmp_path,helpers=helpers,objective=objective)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'L2')
        for round_number in range(3):
            authority=x.scope.acquire(x.case,x.decomp,x.root/f'L{round_number+3}')
            lam=Fraction(round_number-1,8);unit_pi=Fraction(round_number,16)
            full={'4':str(lam)}
            price={j:Fraction(float(v)) for j,v in enumerate(x.case.d['objective'])}
            row=x.case.A.getrow(4)
            for j,w in zip(row.indices,row.data):price[int(j)]-=lam*Fraction(float(w))
            total=Fraction(float(x.case.d['constant']))+lam*Fraction(float(x.case.d['rhs'][4]))
            for name,block in x.decomp.units.items():
                dual={0:str(unit_pi)};full[str(int(block.original_rows[0]))]=str(unit_pi)
                local={k:price[int(j)] for k,j in enumerate(block.original_columns)}
                total+=Fraction(authority.local_bound(block,local,dual)['exact_bound'])
            block=x.decomp.nonunit_block;dual={}
            for k,original in enumerate(block.original_rows):dual[k]='1/32';full[str(int(original))]='1/32'
            local={k:price[int(j)] for k,j in enumerate(block.original_columns)}
            nonunit=authority.local_bound(block,local,dual)
            assert nonunit['standalone_nonunit_pricing_closure_claimed'] is False
            total+=Fraction(nonunit['exact_bound'])
            # The independent original FULL signed evaluator is unchanged;
            # this fresh check does not accept the producer's claimed bound.
            cert=full_checker(x.case.A,x.case.d,full,lower=a.lower,upper=a.upper,case_sha=x.case.case_sha)
            assert total==Fraction(cert['exact_bound'])

@pytest.mark.parametrize('mutate',['matrix_value','matrix_axis','matrix_object','domain_lower','domain_upper',
    'rhs','sense','objective','constant','names','types','row_names','signed_zero','case_sha','case_identity',
    'case_root','decomp_sha','unit_axis','nonunit_axis','coupling_axis','column_owner','block_matrix','block_domain'])
def test_every_structural_change_revokes_reuse(tmp_path,mutate):
    x=resources(tmp_path,helpers=3)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'first')
        if mutate=='matrix_value':x.case.A.data[0]=2.
        elif mutate=='matrix_axis':x.case.A.indices[0]=1
        elif mutate=='matrix_object':x.case.A=x.case.A.copy()
        elif mutate=='domain_lower':x.case.d['lower'][0]=.25
        elif mutate=='domain_upper':x.case.d['upper'][0]=2.
        elif mutate=='rhs':x.case.d['rhs'][4]=.25
        elif mutate=='sense':x.case.d['sense'][4]='>'
        elif mutate=='objective':x.case.d['objective'][0]=.5
        elif mutate=='constant':x.case.d['constant']=np.array(1.)
        elif mutate=='names':x.case.d['names'][0]='tampered'
        elif mutate=='types':x.case.d['types'][0]='C'
        elif mutate=='row_names':x.case.d['row_names'][0]='tampered'
        elif mutate=='signed_zero':x.case.d['lower'][0]=-0.
        elif mutate=='case_sha':x.case.case_sha='another_case'
        elif mutate=='case_identity':x.case.identity['fixture']='tampered'
        elif mutate=='case_root':x.case.output=x.root/'different'
        elif mutate=='decomp_sha':x.decomp.case_sha='another_case'
        elif mutate=='unit_axis':next(iter(x.decomp.units.values())).original_columns[0]=1
        elif mutate=='nonunit_axis':x.decomp.nonunit_block.original_columns[0]=0
        elif mutate=='coupling_axis':x.decomp.coupling_rows[0]=0
        elif mutate=='column_owner':x.decomp.column_owner[0]=0
        elif mutate=='block_matrix':next(iter(x.decomp.units.values())).A.data[0]=2.
        else:x.decomp.nonunit_block.d['upper'][0]=3.
        with pytest.raises(ValueError,match='PROJECTION_CACHE_'):
            a.local_bound(x.decomp.nonunit_block,{0:Fraction(1)},{})
        assert x.scope._closed and x.scope._entry is None

@pytest.mark.parametrize('mutate',['source_bytes','request_attempt','request_day','request_source','proof_bytes',
    'proof_receipt','lower_bytes','upper_bytes','lower_writeable','upper_writeable','envelope_dtype',
    'authority_case','original_local_function'])
def test_source_scope_proof_and_envelope_tamper_is_rejected(tmp_path,mutate):
    x=resources(tmp_path,helpers=3)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'first');raw=x.scope._entry['authority']
        if mutate=='source_bytes':x.source.write_text('changed math fixture\n')
        elif mutate.startswith('request_'):
            key={'request_attempt':'attempt_id','request_day':'day','request_source':'implementation_SHA'}[mutate]
            request=dict(x.request);request[key]='tampered';x.request_path.write_text(json.dumps(request))
        elif mutate=='proof_bytes':Path(a.receipt['path']).write_text('{}\n')
        elif mutate=='proof_receipt':raw.receipt['sha256']='0'*64
        elif mutate in ('lower_bytes','upper_bytes'):
            array=getattr(raw,mutate.split('_')[0]);array.setflags(write=True);array[0]=.125;array.setflags(write=False)
        elif mutate.endswith('_writeable'):getattr(raw,mutate.split('_')[0]).setflags(write=True)
        elif mutate=='envelope_dtype':raw.lower=raw.lower.astype(np.float32);raw.lower.setflags(write=False)
        elif mutate=='authority_case':raw.case=SimpleNamespace(case_sha=x.case.case_sha)
        else:x.scope.original_local_bound=lambda *args:{}
        with pytest.raises(ValueError,match='PROJECTION_CACHE_'):
            x.scope.acquire(x.case,x.decomp,x.root/'second')
        assert x.scope._closed and x.scope._entry is None

def test_case_point_alone_can_change_without_structural_cache_miss(tmp_path):
    x=resources(tmp_path,helpers=12);before=dict(COUNTERS)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'L1');old=a.receipt
        x.case.point=np.ones_like(x.case.point)
        b=x.scope.acquire(x.case,x.decomp,x.root/'L2')
        assert b.receipt==old
        assert b.local_bound(x.decomp.nonunit_block,{0:Fraction(-1)},{})['exact_bound']=='-9/8'
    assert COUNTERS['derive']-before['derive']==1 and COUNTERS['verify']-before['verify']==1

def test_no_existing_proof_is_admitted_or_overwritten(tmp_path):
    x=resources(tmp_path);folder=x.root/'old';folder.mkdir(parents=True)
    proof=folder/'FULL_CASE_PRICING_BOX_PROOF.json';proof.write_text('historical proof remains untouched\n')
    before=receipt(proof)
    with x.scope:
        with pytest.raises(ValueError,match='EXISTING_PROOF_NOT_ADMITTED'):
            x.scope.acquire(x.case,x.decomp,folder)
    assert receipt(proof)==before and x.scope.stats['original_constructions']==0

@pytest.mark.parametrize('kind',['case_clone','decomp_clone','outside_root'])
def test_different_object_or_cross_root_cannot_reuse(tmp_path,kind):
    x=resources(tmp_path)
    with x.scope:
        x.scope.acquire(x.case,x.decomp,x.root/'first')
        case,decomp,output=x.case,x.decomp,x.root/'second'
        if kind=='case_clone':case=SimpleNamespace(**vars(case))
        elif kind=='decomp_clone':decomp=build_blocks(case)
        else:output=tmp_path/'other_attempt'/'output'/'first'
        with pytest.raises(ValueError,match='PROJECTION_CACHE_'):x.scope.acquire(case,decomp,output)

def test_new_attempt_scope_derives_fresh_not_historical_cache(tmp_path):
    first=resources(tmp_path,attempt='first');second=resources(tmp_path,attempt='second');before=dict(COUNTERS)
    with first.scope:a=first.scope.acquire(first.case,first.decomp,first.root/'L1');old=a.receipt
    with second.scope:
        b=second.scope.acquire(second.case,second.decomp,second.root/'L1')
        assert b.receipt['path']!=old['path']
    assert COUNTERS['derive']-before['derive']==2 and COUNTERS['verify']-before['verify']==2

def test_historical_case_root_cannot_be_retagged_by_request_only(tmp_path):
    first=resources(tmp_path,attempt='first');second=resources(tmp_path,attempt='second')
    with second.scope:
        with pytest.raises(ValueError,match='CURRENT_ATTEMPT_CASE_ROOT_OR_DAY'):
            second.scope.acquire(first.case,first.decomp,second.root/'L1')

@pytest.mark.parametrize('exception',[False,True])
def test_scope_teardown_revokes_proxies_and_clears_references(tmp_path,exception):
    x=resources(tmp_path)
    try:
        with x.scope:
            a=x.scope.acquire(x.case,x.decomp,x.root/'first')
            if exception:raise RuntimeError('test scoped unwind')
    except RuntimeError:pass
    assert x.scope._entry is None and x.scope._closed
    with pytest.raises(ValueError,match='SCOPE_CLOSED'):a.local_bound(x.decomp.nonunit_block,{}, {})
    with pytest.raises(ValueError,match='SCOPE_CLOSED'):x.scope.__enter__()

def test_readonly_cache_arrays_cannot_be_written_directly(tmp_path):
    x=resources(tmp_path)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'first')
        with pytest.raises(ValueError):a.lower[0]=3.
        with pytest.raises(ValueError):a.upper[0]=3.

def test_scoped_pricing_retains_original_function_and_local_bound(tmp_path):
    x=resources(tmp_path)
    def original(case,decomp,prices,ledger,output,**kwargs):
        return local_exact_price_bound(decomp.nonunit_block,{0:Fraction(-1)},{})
    with x.scope:
        routed=x.scope.scoped_pricing(original,lambda path:Path(path))
        assert routed.original_pricing.__code__ is original.__code__
        assert routed.original_local_bound is local_bound
        first=routed(x.case,x.decomp,None,None,x.root/'first')
        second=routed(x.case,x.decomp,None,None,x.root/'second')
        assert first['exact_bound']==second['exact_bound']=='-9/8'
        assert first['finite_box_full_original_equality_proof']==second['finite_box_full_original_equality_proof']

def test_false_first_implication_proof_still_fails_original_independent_verify(tmp_path,monkeypatch):
    x=resources(tmp_path);original=original_loader.projection['certificate_box'].derive
    def false(*args,**kwargs):
        lo,hi,proof=original(*args,**kwargs);proof['steps'][0]['exact_upper']='1/2';return lo,hi,proof
    monkeypatch.setattr(original_loader.projection['certificate_box'],'derive',false)
    with x.scope:
        with pytest.raises(ValueError,match='HELPER_BOX_EXACT_ENDPOINT_DRIFT'):
            x.scope.acquire(x.case,x.decomp,x.root/'first')
    assert x.scope._entry is None

def test_original_local_bound_exception_revokes_scope_even_if_caught(tmp_path):
    x=resources(tmp_path)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'first')
        with pytest.raises(ValueError,match='INVALID_LAGRANGIAN_DUAL_SIGN'):
            a.local_bound(next(iter(x.decomp.units.values())),{}, {0:'-1'})
        assert x.scope._entry is None and x.scope._closed

def test_original_pricing_exception_revokes_scope_even_if_caught(tmp_path):
    x=resources(tmp_path)
    def original(*args,**kwargs):raise RuntimeError('original pricing failed')
    with x.scope:
        routed=x.scope.scoped_pricing(original,lambda path:Path(path))
        with pytest.raises(RuntimeError,match='original pricing failed'):
            routed(x.case,x.decomp,None,None,x.root/'first')
        assert x.scope._entry is None and x.scope._closed

def test_mutation_during_original_local_bound_is_caught_before_return(tmp_path):
    x=resources(tmp_path)
    def mutate(block,objective,dual):
        result=local_bound(block,objective,dual)
        x.source.write_text('mutated during bound computation')
        return result
    args=dict(x.args,original_local_bound=mutate);scope=AttemptProjectionCache(**args)
    with scope:
        a=scope.acquire(x.case,x.decomp,x.root/'first')
        with pytest.raises(ValueError,match='SOURCE_BYTES_DRIFT'):
            a.local_bound(x.decomp.nonunit_block,{}, {})
        assert scope._entry is None and scope._closed

def test_instance_bound_method_substitution_cannot_bypass_original_math(tmp_path):
    x=resources(tmp_path)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'first')
        x.scope._entry['authority'].local_bound=lambda *args:dict(PASS=True,exact_bound='999')
        with pytest.raises(ValueError,match='ACTUAL_BOUND_CALLABLE_DRIFT'):
            a.local_bound(x.decomp.nonunit_block,{}, {})
        assert x.scope._closed

def test_original_pricing_code_replacement_is_rejected(tmp_path):
    x=resources(tmp_path)
    def original(*args,**kwargs):return {'original':True}
    def changed(*args,**kwargs):return {'fake_bound':'999'}
    with x.scope:
        routed=x.scope.scoped_pricing(original,lambda p:Path(p))
        original.__code__=changed.__code__
        with pytest.raises(ValueError,match='ORIGINAL_PRICING_CODE_DRIFT'):
            routed(x.case,x.decomp,None,None,x.root/'first')
        assert x.scope._closed

def test_draft_adapter_and_original_loader_bytes_are_source_bound(tmp_path):
    x=resources(tmp_path)
    paths={str(path) for path in x.scope.source_paths}
    assert str(Path(projection_cache.__file__).resolve()) in paths
    assert str(Path(original_loader.__file__).resolve()) in paths

def test_empty_original_source_list_is_rejected_before_self_source_append(tmp_path):
    x=resources(tmp_path)
    with pytest.raises(ValueError,match='ORIGINAL_SOURCE_RECEIPTS_REQUIRED'):
        AttemptProjectionCache(**dict(x.args,source_paths=[]))

def test_stored_bound_delegate_substitution_is_rejected(tmp_path):
    x=resources(tmp_path)
    with x.scope:
        a=x.scope.acquire(x.case,x.decomp,x.root/'first')
        x.scope._entry['original_authority_bound']=lambda *args:dict(PASS=True,exact_bound='999')
        with pytest.raises(ValueError,match='ACTUAL_BOUND_CALLABLE_DRIFT'):
            a.local_bound(x.decomp.nonunit_block,{}, {})
        assert x.scope._closed


def factory_resources(tmp_path):
    """Explicit FAKE_SOURCE fixture, not scientific deployment evidence."""
    x=resources(tmp_path/'small');code=tmp_path/'FAKE_SOURCE_CODE_ROOT'
    original_names=['v42_m1_hybrid/blocks.py','v42_m1_hybrid/bound.py',
        'v42_m1_hybrid/pricing.py','v42_may_campaign_native90/m_model.py',
        'v42_m1_research/check_lb.py','v42_m1_anytime/algorithms.py']
    execution_names=['v42_autonomous_b2/pricing_cache.py','v42_autonomous_b2/pricing_box.py',
        'v42_autonomous_b2/worker.py','v42_autonomous_b2/canonical_stream.py',
        'v42_b2_seed_recovery_v18/certificate_box.py']
    for name in original_names+execution_names:
        path=code/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((REPO/name).read_bytes())
    for folder in projection_cache.EXECUTION_FOLDERS:
        path=code/folder/'__init__.py';path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_text('# FAKE_SOURCE fixture package\n')
    originals={name:receipt(code/name)['sha256'] for name in original_names}
    for i in range(projection_cache.ORIGINAL_SOURCE_COUNT-len(originals)):
        name=f'FAKE_ORIGINAL_SOURCES/original_{i:04d}.py';path=code/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(f'# FAKE original {i}\n')
        originals[name]=receipt(path)['sha256']
    execution={p.relative_to(code).as_posix():receipt(p)['sha256']
        for folder in projection_cache.EXECUTION_FOLDERS
        for p in (code/folder).iterdir() if p.is_file() and p.suffix in ('.py','.html')}
    for i in range(projection_cache.MIN_EXECUTION_SOURCE_COUNT-len(execution)):
        name=f'v42_autonomous_b2/FAKE_EXECUTION_{i:03d}.py';path=code/name
        path.write_text(f'# FAKE execution {i}\n');execution[name]=receipt(path)['sha256']
    root=tmp_path/'FAKE_CAMPAIGN_ROOT';owned=root/'dates/B2/2025-05-01/attempts/fresh0'
    owned.mkdir(parents=True);source_sha=projection_cache._digest(execution)
    auth=root/'USER_ZERO_START_RETRY_AUTHORIZATION.json'
    auth.write_text(json.dumps(dict(schema='V42_USER_AUTHORIZED_ZERO_START_RETRY_V1',
        campaign_root=str(root),scope='VERIFIED_SOURCE_REPAIR_FRESH_DATE_RETRY',restart_from_zero=True,
        native_budget_seconds=5400,previous_checkpoint_reuse=False,previous_native_budget_carry=False,
        old_attempts_and_accounting_preserved=True,normal_workers_must_continue=True,
        applies_to_hourly_verified_repairs=True)))
    inputs=root/'FAKE_FRESH_INPUTS';inputs.mkdir()
    manifest=dict(schema='V42_AUTONOMOUS_B2_V20',run_id='FAKE_CURRENT_CAMPAIGN',attempt_ids=['fresh0'],
        input_folders={'2025-05-01':str(inputs)},builder_original_sources=originals,
        execution_sources=execution,execution_SHA=source_sha,restart_from_zero=True,prior_attempts={},
        historical_bound_point_reuse=False,reset_authorization=receipt(auth))
    mpath=root/'FAKE_SOURCE98_MANIFEST.json';mpath.write_text(json.dumps(manifest))
    request=dict(root=str(root),run_id=manifest['run_id'],arm='B2',day='2025-05-01',attempt_id='fresh0',
        manifest=str(mpath),manifest_SHA=receipt(mpath)['sha256'],implementation_SHA=source_sha,
        deployment_SHA=source_sha,input_folder=str(inputs),output=str(owned/'output'),
        result=str(owned/'RESULT.json'),progress=str(owned/'progress.json'),error=str(owned/'error.json'),
        restart_from_zero=True,previous_attempts=[],native_budget_seconds=5400,wall_budget_seconds=None,
        target_gap=.03,Threads=1,P2_calls=0,reset_authorization=receipt(auth))
    request_path=owned/'request.json';request_path.write_text(json.dumps(request))
    module=load_cache(code/'v42_autonomous_b2/pricing_cache.py');x.case.output=owned/'output'
    return SimpleNamespace(x=x,code=code,root=root,owned=owned,request=request,request_path=request_path,
        manifest=manifest,manifest_path=mpath,module=module,auth=auth)


def reseal_fixture(x):
    x.manifest_path.write_text(json.dumps(x.manifest));x.request['manifest_SHA']=receipt(x.manifest_path)['sha256']
    x.request_path.write_text(json.dumps(x.request))


def test_factory_complete_declared_source_request_scope_and_hit_receipt(tmp_path):
    x=factory_resources(tmp_path);before=dict(COUNTERS)
    with x.module.create_scope(x.request,x.manifest,x.code) as scope:
        first=scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L1');proof=first.receipt
        second=scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L2');assert second.receipt==proof
        path=x.x.case.output/'L2/CURRENT_ATTEMPT_PROJECTION_REUSE_RECEIPT.json';reuse=json.loads(path.read_text())
        assert reuse['first_same_attempt_original_proof']==proof
        assert reuse['fresh_derivation_or_independent_replay_claimed'] is False
        assert reuse['prices_or_duals_or_local_bounds_or_Global_LB_cached'] is False
        assert reuse['current_request']==receipt(x.request_path)
        assert not (path.parent/'FULL_CASE_PRICING_BOX_PROOF.json').exists()
        assert len(scope.source_paths)==1007+97+2
    assert COUNTERS['derive']-before['derive']==1 and COUNTERS['verify']-before['verify']==1


@pytest.mark.parametrize('change',['declared_bad_sha','byte_drift','missing_original','missing_execution',
    'extra_execution','unsafe_source_path','source_digest','request_sha','request_dict','source_root',
    'manifest_dict','manifest_path'])
def test_factory_declared_source_admission_fails_before_derivation(tmp_path,change):
    x=factory_resources(tmp_path);before=dict(COUNTERS);root=x.code
    if change=='declared_bad_sha':
        x.manifest['builder_original_sources']['v42_m1_hybrid/bound.py']='0'*64;reseal_fixture(x)
    elif change=='byte_drift':(x.code/'v42_m1_hybrid/bound.py').write_text('tampered\n')
    elif change=='missing_original':x.manifest['builder_original_sources'].pop('v42_m1_hybrid/bound.py');reseal_fixture(x)
    elif change=='missing_execution':
        x.manifest['execution_sources'].pop('v42_autonomous_b2/worker.py')
        x.manifest['execution_SHA']=x.module._digest(x.manifest['execution_sources'])
        x.request['implementation_SHA']=x.request['deployment_SHA']=x.manifest['execution_SHA'];reseal_fixture(x)
    elif change=='extra_execution':(x.code/'v42_autonomous_b2/extra.py').write_text('tampered\n')
    elif change=='unsafe_source_path':
        old=x.manifest['builder_original_sources'].pop('v42_m1_hybrid/bound.py')
        x.manifest['builder_original_sources']['../bound.py']=old;reseal_fixture(x)
    elif change=='source_digest':x.manifest['execution_SHA']='0'*64;reseal_fixture(x)
    elif change=='request_sha':x.request['manifest_SHA']='0'*64;x.request_path.write_text(json.dumps(x.request))
    elif change=='request_dict':x.request['run_id']='changed'
    elif change=='source_root':root=x.code.parent
    elif change=='manifest_dict':x.manifest['run_id']='changed'
    else:x.request['manifest']=str(x.code/'manifest.json')
    with pytest.raises((ValueError,FileNotFoundError)):x.module.create_scope(x.request,x.manifest,root)
    assert COUNTERS==before


@pytest.mark.parametrize('change',['C_root','other_day','other_attempt','nested_output','traversal',
    'other_result','request_source','previous_attempts','missing_reset','unauthorized_reset',
    'wrong_auth_root','auth_byte_drift','prior_native','historical_point'])
def test_factory_exact_owned_fresh_zero_admission(tmp_path,change):
    x=factory_resources(tmp_path);before=dict(COUNTERS)
    if change=='C_root':x.request['root']='C:\\foreign_campaign'
    elif change=='other_day':x.request['day']='2025-05-02'
    elif change=='other_attempt':x.request['attempt_id']='different'
    elif change=='nested_output':x.request['output']=str(x.owned/'output/nested')
    elif change=='traversal':x.request['output']=str(x.owned/'output/../output')
    elif change=='other_result':x.request['result']=str(x.root/'RESULT.json')
    elif change=='request_source':x.request['implementation_SHA']='0'*64
    elif change=='previous_attempts':x.request['previous_attempts']=['old_attempt']
    elif change=='missing_reset':x.request.pop('restart_from_zero')
    elif change=='unauthorized_reset':x.request.pop('reset_authorization')
    elif change=='wrong_auth_root':
        auth=json.loads(x.auth.read_text());auth['campaign_root']=str(x.code);x.auth.write_text(json.dumps(auth))
        x.request['reset_authorization']=x.manifest['reset_authorization']=receipt(x.auth);reseal_fixture(x)
    elif change=='auth_byte_drift':x.auth.write_text('{}')
    elif change=='prior_native':x.manifest['prior_attempts']={'old':{'Native_Runtime':5}};reseal_fixture(x)
    else:x.manifest['historical_bound_point_reuse']=True;reseal_fixture(x)
    x.request_path.write_text(json.dumps(x.request))
    with pytest.raises((ValueError,FileNotFoundError)):x.module.create_scope(x.request,x.manifest,x.code)
    assert COUNTERS==before


@pytest.mark.parametrize('target',['authority_init','authority_bound','matrix_sha','domain_sha','original_local',
    'original_pricing','derive','verify','decomposition'])
def test_factory_rejects_code_mutated_after_module_load_before_first_scope(tmp_path,target):
    x=factory_resources(tmp_path)
    func={'authority_init':x.module._ORIGINAL_AUTHORITY.__init__,
        'authority_bound':x.module._ORIGINAL_AUTHORITY.local_bound,'matrix_sha':x.module._ORIGINAL_MATRIX_SHA,
        'domain_sha':x.module._ORIGINAL_DOMAIN_SHA,'original_local':x.module._ORIGINAL_LOCAL_BOUND,
        'original_pricing':x.module._ORIGINAL_PRICING,'derive':x.module._ORIGINAL_DERIVE,
        'verify':x.module._ORIGINAL_VERIFY,'decomposition':x.module._ORIGINAL_DECOMPOSITION}[target];old=func.__code__
    try:
        func.__code__=(lambda *args,**kwargs:None).__code__
        with pytest.raises(ValueError,match='MODULE_LOAD_ORIGINAL_CODE_DRIFT'):
            x.module.create_scope(x.request,x.manifest,x.code)
    finally:func.__code__=old


@pytest.mark.parametrize('change',['manifest_bytes','auth_bytes','source_bytes','reuse_bytes','loaded_module_root','extra_source_file'])
def test_factory_active_seals_and_reuse_receipt_drift_revokes_scope(tmp_path,change):
    x=factory_resources(tmp_path)
    with x.module.create_scope(x.request,x.manifest,x.code) as scope:
        a=scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L1');scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L2')
        if change=='loaded_module_root':x.module.blocks.__file__=str(x.code.parent/'blocks.py')
        elif change=='extra_source_file':(x.code/'v42_autonomous_b2/added_during_scope.py').write_text('not declared\n')
        else:
            path={'manifest_bytes':x.manifest_path,'auth_bytes':x.auth,'source_bytes':x.code/'v42_m1_hybrid/bound.py',
                'reuse_bytes':x.x.case.output/'L2/CURRENT_ATTEMPT_PROJECTION_REUSE_RECEIPT.json'}[change]
            path.write_text('tampered\n')
        with pytest.raises(ValueError,match='PROJECTION_CACHE_'):a.local_bound(x.x.decomp.nonunit_block,{0:Fraction(1)}, {})
        assert scope._closed and scope._entry is None


def test_factory_never_overwrites_existing_current_round_reuse_receipt(tmp_path):
    x=factory_resources(tmp_path)
    with x.module.create_scope(x.request,x.manifest,x.code) as scope:
        scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L1')
        path=x.x.case.output/'L2/CURRENT_ATTEMPT_PROJECTION_REUSE_RECEIPT.json';path.parent.mkdir();path.write_text('preserved old bytes')
        with pytest.raises(FileExistsError):scope.acquire(x.x.case,x.x.decomp,path.parent)
        assert path.read_text()=='preserved old bytes' and scope._closed


def test_native_model_constructor_is_not_used_by_factory_or_projection_scope(tmp_path):
    x=factory_resources(tmp_path);calls=[]
    def denied_model(*args,**kwargs):calls.append('model');raise PermissionError('Native constructor denied')
    with patch.dict(x.module._ORIGINAL_PRICING.__globals__,gp=SimpleNamespace(Model=denied_model)):
        with x.module.create_scope(x.request,x.manifest,x.code) as scope:
            scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L1');scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L2')
    assert calls==[]


@pytest.mark.parametrize('target',['derive','verify','decomposition','constructor_box','constructor_decomposition'])
def test_factory_original_helper_alias_substitution_is_rejected(tmp_path,target):
    x=factory_resources(tmp_path);replacement=lambda *args,**kwargs:None
    if target in ('derive','verify'):setattr(x.module._ORIGINAL_BOX,target,replacement)
    elif target=='decomposition':x.module.pricing_box.verify_decomposition=replacement
    elif target=='constructor_box':x.module._ORIGINAL_AUTHORITY.__init__.__globals__['certificate_box']=SimpleNamespace(derive=replacement,verify=replacement)
    else:x.module._ORIGINAL_AUTHORITY.__init__.__globals__['verify_decomposition']=replacement
    with pytest.raises(ValueError,match='MODULE_LOAD_ORIGINAL_CODE_DRIFT'):
        x.module.create_scope(x.request,x.manifest,x.code)


@pytest.mark.parametrize('change',['code','alias'])
def test_helper_tamper_during_original_construction_cannot_be_admitted(tmp_path,monkeypatch,change):
    x=factory_resources(tmp_path);original=original_loader.box['derive']
    verify=x.module._ORIGINAL_VERIFY;verify_code=verify.__code__
    def mutate_after_original_derive(*args,**kwargs):
        result=original(*args,**kwargs)
        if change=='code':verify.__code__=(lambda *args,**kwargs:None).__code__
        else:x.module._ORIGINAL_BOX.derive=lambda *args,**kwargs:None
        return result
    with x.module.create_scope(x.request,x.manifest,x.code) as scope:
        monkeypatch.setitem(original_loader.box,'derive',mutate_after_original_derive)
        try:
            with pytest.raises(ValueError,match='MODULE_LOAD_ORIGINAL_CODE_DRIFT'):
                scope.acquire(x.x.case,x.x.decomp,x.x.case.output/'L1')
        finally:verify.__code__=verify_code
        assert scope._closed and scope._entry is None
