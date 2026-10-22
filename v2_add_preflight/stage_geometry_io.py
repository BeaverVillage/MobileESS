"""Compact immutable constructor IO for the already certified 96-slot view.

All recursive arithmetic, exact elimination, pricing and ranking methods are
the unchanged source methods. The constructor result is assembled from the
96 byte-bound component constructor certificates instead of retaining two
Python dictionaries with millions of identical integer pairs.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from unittest.mock import patch
import hashlib,ast,inspect,textwrap
import numpy as np
from .stage_common import *
from .static_pack import N_AUX


class Definitions(Mapping):
    def __init__(self, first, rows, order):self.first=first;self.rows=rows;self.order=order
    def __len__(self):return len(self.rows)
    def __iter__(self):
        for ordinal,key in enumerate(self.order):
            if ordinal and ordinal%1000000==0:print('SOURCE HELPER ITERATION',ordinal,flush=True)
            yield int(key)
    def __contains__(self,key):return isinstance(key,(int,np.integer)) and self.first<=key<self.first+len(self.rows)
    def __getitem__(self,key):
        if key not in self:raise KeyError(key)
        return int(self.rows[int(key)-self.first])


def assemble(case):
    b=case._blocks;rows=np.empty(96*N_AUX,dtype=np.int32);order=np.empty_like(rows);security={}
    folder=WORK/'GEOMETRY_CONSTRUCTOR'/case._stream_identity
    cache=folder/'DEFINITIONS.npz';receipt=folder/'CERTIFICATE.json';producer=record(__file__)
    if receipt.exists() and cache.exists():
        cert=read(receipt)
        if cert.get('producer')==producer and cert.get('math_sha')==case._stream_identity and cert.get('data')==record(cache):
            with np.load(cache) as z:
                rows=z['rows'];order=z['order'];pq=z['pq']
                security={t:z[f'security_{t:02d}'] for t in range(96)}
            assert len(rows)==len(order)==96*N_AUX
            for value in (rows,order,pq,*security.values()):value.setflags(write=False)
            print('SOURCE COMPLETE GEOMETRY CONSTRUCTOR IO CACHE VERIFIED',flush=True)
            return Definitions(b.nbase,rows,order),pq,security
    # Every component's unchanged source and independent constructor were
    # executed by stage_k48.certify. Blocks rechecks all their byte hashes.
    certificate=read(OUT/'K48_WHOLE96_INTERFACE_CERTIFICATION.json')
    assert certificate['representation_all96_PASS'] and len(certificate['records'])==96
    physical=np.array([str(n).split('[',1)[0] in ('Pch','Pdis','Q') for n in b.md['names']])
    for t,prior in enumerate(certificate['records']):
        actual=b.records[t]
        assert actual['view_matrix']['sha256']==prior['view_matrix']['sha256']
        if actual['view_domain']['sha256']!=prior['view_domain']['sha256']:
            # Current M2 changes response constants, not the helper pivot
            # equations/axes. Recheck every constructor-relevant input; its
            # only RHS restriction is zero for physical injections below.
            with np.load(prior['view_domain']['path']) as baseline:
                with np.load(actual['view_domain']['path']) as changed:
                    assert baseline.files==changed.files
                    assert all(np.array_equal(baseline[key],changed[key]) for key in baseline.files if key!='rhs')
        assert prior['independent_all_helper_definitions_PASS']
        A,d=b.get(t+1);eq=np.flatnonzero(d['sense']=='=')
        assert len(eq)==N_AUX
        lookup={str(n).replace('[','_binding[',1):j for j,n in enumerate(d['names'][b.nbase:])}
        local=np.array([lookup[str(n)] for n in d['row_names'][eq]],dtype=np.int32)
        assert len(set(map(int,local)))==N_AUX
        assert np.isfinite(d['rhs'][eq]).all() and np.all(d['rhs'][eq[local<48]]==0.)
        for ordinal,row in enumerate(eq):
            a,z=A.indptr[row:row+2];ids=A.indices[a:z];values=A.data[a:z]
            own=ids==b.nbase+local[ordinal]
            assert np.count_nonzero(own)==1 and values[own][0]==1.
            base=ids[ids<b.nbase];assert np.all(physical[base])
            other=ids[(ids>=b.nbase)&~own]
            # At zero physical dispatch, injections are exactly +0. Every
            # response depends only on those injections, so its source
            # binary64 value is rhs - sum(w*0) == rhs (including signed zero).
            assert np.all(other<b.nbase+48)
            if local[ordinal]<48:assert not len(other)
        rows[t*N_AUX+local]=eq+b.row_offsets[t+1]
        order[t*N_AUX:(t+1)*N_AUX]=b.nbase+t*N_AUX+local
        security[t]=np.flatnonzero(d['sense']!='=')+b.row_offsets[t+1]
        assert all(str(d['row_names'][i]).split('[',1)[0] in ('line_thermal_face','transformer_kVA','NormalAmps','voltage_upper','voltage_lower') for i in np.flatnonzero(d['sense']!='='))
        if t%12==0:print('SOURCE GEOMETRY COMPACT IO',t,flush=True)
    rows.setflags(write=False);order.setflags(write=False)
    definitions=Definitions(b.nbase,rows,order)
    pq=np.flatnonzero(physical);pq.setflags(write=False)
    folder.mkdir(parents=True,exist_ok=True);temp=cache.with_suffix('.tmp')
    with temp.open('wb') as stream:np.savez_compressed(stream,rows=rows,order=order,pq=pq,
        **{f'security_{t:02d}':value.astype(np.int32) for t,value in security.items()})
    temp.replace(cache)
    receipt.write_text(json.dumps(dict(PASS=True,producer=producer,math_sha=case._stream_identity,data=record(cache),
        all96_complete_source_and_independent_constructor_certificates_reused=True,
        every_current_binding_rechecked=True,all_zero_reference_dependency_conditions_proved=True)),encoding='utf-8')
    return definitions,pq,security


@contextmanager
def scope(case,modules):
    from .stage_m_case import FullCSR
    k=modules['table_v_k48'];oracle=k.original_oracle;independent=k.independent
    definitions,pq,security=assemble(case);numeric={};counters=dict(constructor_reuses=0,numerical_builds=0,numerical_reuses=0)
    original_init=oracle.Geometry.__init__;independent_init=independent.Geometry.__init__
    original_numerical=oracle.Geometry.numerical
    numeric_root=WORK/'GEOMETRY_NUMERIC'/case.case_sha;numeric_root.mkdir(parents=True,exist_ok=True)
    numeric_source=record(oracle.__file__)
    def init(self,A,d):
        if not isinstance(A,FullCSR):return original_init(self,A,d)
        assert A is case.original_A
        self.A,self.d,self.definitions,self.cache=A,d,definitions,{};counters['constructor_reuses']+=1
    def independent_constructor(self,A,d):
        if not isinstance(A,FullCSR):return independent_init(self,A,d)
        assert A is case.original_A
        self.A,self.d,self.definitions,self.cache,self.used=A,d,definitions,{},set();counters['constructor_reuses']+=1
    def numerical(self,x,errors):
        if not isinstance(self.A,FullCSR):return original_numerical(self,x,errors)
        # The component equations above have no physical leaves outside P/Q.
        # Cache only an identical P/Q AND error vector, within one immutable
        # case. First evaluation always executes the original arithmetic.
        key=hashlib.sha256(x[pq].tobytes()+errors[pq].tobytes()).hexdigest()
        path=numeric_root/(key+'.npz');receipt=numeric_root/(key+'.json')
        if key not in numeric and path.exists() and receipt.exists():
            cert=read(receipt)
            if (cert.get('case_sha')!=case.case_sha or cert.get('input_PQ_and_error_sha')!=key
                    or cert.get('source')!=numeric_source or cert.get('data')!=record(path)
                    or cert.get('original_numerical_executed') is not True):raise ValueError('SOURCE_NUMERIC_IO_CACHE_DRIFT')
            with np.load(path) as z:
                assert z.files==['x','errors'] and z['x'].shape==z['errors'].shape==(len(definitions),)
                numeric[key]=(z['x'],z['errors'])
        if key in numeric:
            x[definitions.first:],errors[definitions.first:]=numeric[key];counters['numerical_reuses']+=1
        else:
            print('SOURCE HELPER NUMERICAL BEGIN',flush=True)
            original_numerical(self,x,errors)
            # Bound cache memory; subsequent different centers replace it.
            numeric.clear();numeric[key]=(x[definitions.first:].copy(),errors[definitions.first:].copy())
            counters['numerical_builds']+=1
            temp=path.with_suffix('.tmp')
            with temp.open('wb') as stream:np.savez_compressed(stream,x=numeric[key][0],errors=numeric[key][1])
            temp.replace(path)
            receipt.write_text(json.dumps(dict(case_sha=case.case_sha,input_PQ_and_error_sha=key,source=numeric_source,
                data=record(path),original_numerical_executed=True,Native_optimize_calls=0)),encoding='utf-8')
            print('SOURCE HELPER NUMERICAL COMPLETE',flush=True)
    authority_cache=[]
    def compact_authority(self):
        A=case.original_A;d=case.original_d
        self.maps=dict(d,indptr=A.indptr,indices=A.indices,data=A.data)
        self.rho=int(np.flatnonzero(d['objective'])[0])
        self.cache,self.raw_cache,self.helper_defs={},{},definitions
        self.security_by_slot=security
    def authority(factory):
        if not authority_cache:authority_cache.append(factory())
        return authority_cache[0]
    # Replace only the nested constructor IO. The source's complete thermal
    # scan, four-facet ranking, projection, widths and score formula stay
    # literal. Avoid its optional unbounded Python term memoization.
    candidates=modules['m_candidates'];original=getattr(candidates,'_v43_original_grid_context',candidates.grid_context)
    zero_cache=[]
    def zero_reference(current):
        assert current.original_A is case.original_A and current.original_d is case.original_d
        if not zero_cache:
            x=np.zeros(case.original_A.shape[1],dtype=np.float64)
            x[definitions.first:]=case.original_d['rhs'][definitions.rows]
            x.setflags(write=False);zero_cache.append(x)
        return zero_cache[0]
    tree=ast.parse(textwrap.dedent(inspect.getsource(original)));changed=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ClassDef) and node.name=='CurrentAuthority':
            constructor=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
            constructor.body=ast.parse('_compact_current_authority(self)').body;changed.append('constructor')
        if isinstance(node,ast.Assign) and ast.unparse(node)=='authority = CurrentAuthority()':
            node.value=ast.parse('_compact_authority_cache(CurrentAuthority)',mode='eval').body;changed.append('cache')
    assert sorted(changed)==['cache','constructor'];ast.fix_missing_locations(tree)
    ns=dict(original.__globals__,_compact_current_authority=compact_authority,_compact_authority_cache=authority,
        base_grid_reference=zero_reference)
    exec(compile(tree,inspect.getfile(original),'exec'),ns)
    with patch.object(oracle.Geometry,'__init__',init),patch.object(independent.Geometry,'__init__',independent_constructor),patch.object(oracle.Geometry,'numerical',numerical),patch.object(candidates,'grid_context',ns['grid_context']),patch.object(candidates,'base_grid_reference',zero_reference):
        case._geometry_IO_counters=counters
        yield counters
