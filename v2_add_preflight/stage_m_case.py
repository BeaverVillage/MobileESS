"""Disk-streamed original FULL authority and the sealed static Native case.

Only representation/IO is adapted. The source Geometry, K48 selectors,
pricing, Beam and Direct Joint operate on the same original row universe.
The raw reference and normalized view have separate identities. A single
component cache avoids materializing the 302M-nonzero FULL reference twice.
"""
from bisect import bisect_right
from contextlib import contextmanager
import gc,hashlib,pickle,ast,inspect,textwrap
from types import SimpleNamespace,MethodType
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from v42_native.contracts import digest
from .stage_k48 import slot_view
from .static_pack import PACK,N_AUX
from .static_screen import CACHE

class Axis:
    def __init__(self,blocks,key,lengths):
        self.blocks=blocks;self.key=key;self.offset=np.r_[0,np.cumsum(lengths)];self.shape=(int(self.offset[-1]),);self.ndim=1
    def __len__(self):return self.shape[0]
    def __iter__(self):
        for b in range(97):yield from self.blocks.get(b)[1][self.key]
    def __getitem__(self,item):
        if np.isscalar(item):
            item=int(item);item=item+len(self) if item<0 else item;b=bisect_right(self.offset,item)-1
            return self.blocks.get(b)[1][self.key][item-int(self.offset[b])]
        ids=np.arange(len(self))[item] if isinstance(item,slice) else np.asarray(item)
        if ids.dtype==bool:ids=np.flatnonzero(ids)
        result=np.empty(len(ids),dtype=object);bs=np.searchsorted(self.offset,ids,side='right')-1
        for b in np.unique(bs):
            mask=bs==b;result[mask]=self.blocks.get(int(b))[1][self.key][ids[mask]-self.offset[b]]
        return np.asarray(result.tolist(),dtype=str)
    def __eq__(self,other):
        return np.concatenate([np.asarray(self.blocks.get(b)[1][self.key])==other for b in range(97)])
    def __ne__(self,other):return ~self.__eq__(other)
    def copy(self):return self[:]

class Flat:
    def __init__(self,blocks,key):self.blocks=blocks;self.key=key;self.dtype=np.dtype('float64' if key=='data' else 'int32')
    def setflags(self,write=False):
        if write:raise ValueError('IMMUTABLE_ORIGINAL_FULL_VIEW')
        getattr(self.blocks.mob,self.key).setflags(write=False)
    def __getitem__(self,item):
        assert isinstance(item,slice) and item.step in (None,1)
        a,b=int(item.start),int(item.stop);block=bisect_right(self.blocks.nz_offsets,a)-1
        if a==b:return np.array([],dtype=self.dtype)
        assert b<=self.blocks.nz_offsets[block+1]
        A,_=self.blocks.get(block);values=getattr(A,self.key)[a-self.blocks.nz_offsets[block]:b-self.blocks.nz_offsets[block]]
        if self.key=='indices' and block:
            values=values.copy();mask=values>=self.blocks.nbase;values[mask]+=(block-1)*N_AUX
        return values

class Blocks:
    def __init__(self,pack=PACK,stage='M1',view_root=None,reference_proof=None):
        import types
        self.pack=pack;self.stage=stage
        self.view_root=Path(view_root) if view_root is not None else WORK/stage/'view'
        self.reference_proof=Path(reference_proof) if reference_proof is not None else (OUT if stage=='M1' else OUT/'stage_m2')/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json'
        self.view=types.FunctionType(slot_view.__code__,dict(slot_view.__globals__,PACK=pack),argdefs=slot_view.__defaults__)
        with np.load(pack/'MOBILITY_DOMAIN.npz') as z:self.md={k:z[k] for k in z.files}
        self.mob=sp.load_npz(pack/'MOBILITY.npz');self.nbase=self.mob.shape[1]
        self.md['names']=self.md['names'].astype(object);self.md['row_names']=self.md['row_names'].astype(object)
        self.current=None;self.cached=None;self.records=[];self.row_lengths=[self.mob.shape[0]];self.nz_lengths=[self.mob.nnz]
        ptr=[self.mob.indptr.copy()];offset=self.mob.nnz
        for t in range(96):
            path=self.view_root/f'{t:02d}';path.mkdir(parents=True,exist_ok=True)
            committed=path/'COMMITTED.json'
            valid=False
            if committed.exists():
                proof=read(committed)
                valid=proof.get('producer',{}).get('sha256')==record(ROOT/'v2_add_preflight/stage_k48.py')['sha256']
                valid &= proof['raw_component']['sha256']==record(pack/f'{t:02d}/MATRIX.npz')['sha256']
                valid &= proof['view_matrix']['sha256']==record(path/'A.npz')['sha256'] and proof['view_domain']['sha256']==record(path/'D.npz')['sha256']
            if valid:A=sp.load_npz(path/'A.npz')
            else:
                A,d,proof=self.view(t,self.md)
                sp.save_npz(path/'A.npz',A)
                local={k:d[k][self.nbase:] for k in ('names','lower','upper','types','objective')}
                local.update({k:d[k] for k in ('row_names','rhs','sense')})
                for k in ('names','row_names'):local[k]=local[k].astype(str)
                np.savez_compressed(path/'D.npz',**local)
                proof.update(view_matrix=record(path/'A.npz'),view_domain=record(path/'D.npz'))
            self.row_lengths.append(A.shape[0]);self.nz_lengths.append(A.nnz);ptr.append(A.indptr[1:].astype(np.int64)+offset);offset+=A.nnz
            self.records.append(proof)
        self.indptr=np.concatenate(ptr).astype(np.int64);self.row_offsets=np.r_[0,np.cumsum(self.row_lengths)]
        self.nz_offsets=np.r_[0,np.cumsum(self.nz_lengths)];self.shape=(int(self.row_offsets[-1]),self.nbase+96*N_AUX)
    def get(self,b):
        if b==0:return self.mob,self.md
        if self.current!=b:
            self.cached=None;self.current=b
            path=self.view_root/f'{b-1:02d}';A=sp.load_npz(path/'A.npz')
            with np.load(path/'D.npz') as z:d={k:z[k] for k in z.files}
            for k in ('names','lower','upper','types','objective'):d[k]=np.r_[self.md[k],d[k]]
            # These axis blocks contain only the local auxiliary names; the
            # physical mobility columns belong solely to domain block0.
            self.cached=(A,d)
        return self.cached
    def domain(self):
        d={k:np.empty(self.shape[1] if k in ('lower','upper','types','objective') else self.shape[0],
            dtype='U1' if k in ('types','sense') else float) for k in ('lower','upper','types','objective','rhs','sense')}
        for k in ('lower','upper','types','objective'):d[k][:self.nbase]=self.md[k]
        d['rhs'][:self.mob.shape[0]]=self.md['rhs'];d['sense'][:self.mob.shape[0]]=self.md['sense']
        for b in range(1,97):
            _,local=self.get(b);lo=self.nbase+(b-1)*N_AUX;rs=slice(self.row_offsets[b],self.row_offsets[b+1])
            for k in ('lower','upper','types','objective'):d[k][lo:lo+N_AUX]=local[k][self.nbase:]
            for k in ('rhs','sense'):d[k][rs]=local[k]
        d['constant']=np.asarray(0.)
        d['names']=Names(self);d['row_names']=Axis(self,'row_names',self.row_lengths)
        return d

class Names(Axis):
    def __init__(self,blocks):super().__init__(blocks,'names',[blocks.nbase]+[N_AUX]*96)
    def __iter__(self):
        yield from self.blocks.md['names']
        for b in range(1,97):yield from self.blocks.get(b)[1]['names'][self.blocks.nbase:]
    def __getitem__(self,item):
        if np.isscalar(item):
            j=int(item)
            if j<0:j+=len(self)
            if j<self.blocks.nbase:return self.blocks.md['names'][j]
            b=(j-self.blocks.nbase)//N_AUX+1;k=(j-self.blocks.nbase)%N_AUX
            return self.blocks.get(b)[1]['names'][self.blocks.nbase+k]
        ids=np.arange(len(self))[item] if isinstance(item,slice) else np.asarray(item)
        if ids.dtype==bool:ids=np.flatnonzero(ids)
        result=[]
        for j in ids:result.append(self[int(j)])
        return np.array(result,dtype=str)
    def __eq__(self,other):
        result=np.zeros(len(self),dtype=bool);result[:self.blocks.nbase]=self.blocks.md['names']==other
        if other=='rho_max' or not str(other).startswith(('injection_','response_')):return result
        for b in range(1,97):
            lo=self.blocks.nbase+(b-1)*N_AUX;result[lo:lo+N_AUX]=self.blocks.get(b)[1]['names'][self.blocks.nbase:]==other
        return result

class FullCSR:
    def __init__(self,blocks,absolute=False):
        self.blocks=blocks;self.shape=blocks.shape;self.indptr=blocks.indptr;self.nnz=int(blocks.nz_offsets[-1]);self.absolute=absolute
        self.indices=Flat(blocks,'indices');self.data=Flat(blocks,'data')
    def tocsr(self):return self
    def __abs__(self):return FullCSR(self.blocks,True)
    def __matmul__(self,x):
        y=np.empty(self.shape[0])
        for b in range(97):
            A,_=self.blocks.get(b);v=x[:self.blocks.nbase] if b==0 else np.r_[x[:self.blocks.nbase],x[self.blocks.nbase+(b-1)*N_AUX:self.blocks.nbase+b*N_AUX]]
            y[self.blocks.row_offsets[b]:self.blocks.row_offsets[b+1]]=(abs(A) if self.absolute else A)@v
        return y
    def __getitem__(self,rows):
        # Source K48 takes only physical rows here. Full geometry and pricing
        # use the streaming arrays and include every IEEE8500 security row.
        if isinstance(rows,tuple):return self[rows[0]][:,rows[1]]
        rows=np.asarray(rows);assert rows.size==0 or int(rows.max())<self.blocks.mob.shape[0]
        return sp.hstack((self.blocks.mob[rows],sp.csr_matrix((len(rows),96*N_AUX))),format='csr')

def reference_identity(blocks):
    """Separate, explicit composite identity; no fictitious monolithic hash."""
    return digest(dict(raw_reference=record(blocks.reference_proof),
        view='positive-dyadic-helper-and-literal-helper-bound-view-v1',records=blocks.records))

def build_case(stage='M1',*,current_root=None,current_pack=None,current_proof=None,current_anchor=None,current_view=None,arm=None,k48_only=False):
    from v42_supercompact.formulation import Compact
    assert stage in ('M1','M2')
    root=(RUN if stage=='M1' else WORK/'M2') if current_root is None else Path(current_root)
    pack=(PACK if stage=='M1' else root/'SOURCE_YY_FULL96') if current_pack is None else Path(current_pack)
    start=time.perf_counter();blocks=Blocks(pack,stage,view_root=current_view if current_view is not None else (None if current_root is None else root/'view'),reference_proof=current_proof)
    A=FullCSR(blocks);d=blocks.domain();guard(start)
    if k48_only:
        # K48 reads the actual original FULL authority, never the selected UB
        # model, graph or inverse. Keep their immutable file identities while
        # leaving those unused bytes on disk during this Native0-only phase.
        with np.load(root/'native/COMPLETE_A.npz') as z:shape=tuple(z['shape'])
        selected=SimpleNamespace(shape=shape,deferred_selected_UB_only=True);sd=None;graph=None;p=None
    else:
        selected=sp.load_npz(root/'native/COMPLETE_A.npz')
        with np.load(root/'native/COMPLETE_DOMAIN.npz') as z:sd={k:z[k] for k in z.files}
        from .stage_native_io import TextNames
        for key in ('names','row_names'):sd[key]=TextNames(sd[key])
        with (root/'mobility/TRANSPORT.pkl').open('rb') as f:transport=pickle.load(f)
        source_inverse=transport['presolve'];graph=transport['graph']
    # Presolve.inverse reads exactly these three fields. Its historical
    # construction matrices and Compact copies are not runtime authorities;
    # the actual current Native matrix and raw components above are. Retain
    # the unchanged inverse method with its complete proof fields only.
        p=SimpleNamespace(initial_names=source_inverse.initial_names,col_ids=source_inverse.col_ids,steps=source_inverse.steps)
        p.inverse=MethodType(type(source_inverse).inverse,p)
        del source_inverse,transport
    gc.collect()
    anchor=current_anchor if current_anchor is not None else (record(OUT/'SOURCE_YY_PLANNING_ANCHOR.csv') if stage=='M1' else record(root/'A2_FIXTURE.json'))
    case=SimpleNamespace(A=selected,d=sd,original_A=A,original_d=d,graph=graph,output=WORK/stage if current_root is None else root/'RUNTIME',bundle=read(day_inputs()['files']['native']['path']),
        identity=dict(schema='V2_ADD_SOURCE_YY_EXPLICIT_COMPOSITE_ROW_VIEW',day='2025-05-01',arm=arm or ('B2' if stage=='M1' else 'B3'),stage=stage,source_sha=digest(SOURCE),
            parent_case_sha=anchor.get('parent_case_sha') if current_anchor is not None else record(OUT/'SOURCE_YY_COMPLETE_INPUT_CASE_IDENTITY.json')['sha256'],
            aidc_anchor=anchor['aidc_anchor'] if current_anchor is not None else digest(anchor)))
    case.output.mkdir(exist_ok=True)
    files=day_inputs()['files']
    case.identity.update(science_sha=digest(dict(original_r043=SOURCE,
        reuse_manifest=record(ROOT/'docs/v44/V43_MESS_REUSE_SOURCE_MANIFEST.json'))),
        qos_sha=digest({k:files[k] for k in ('windows','actual_input','request_descriptors')}),
        physical_contract_sha=digest(dict(hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),
            full_axes=record(OUT/'SOURCE_YY_GRID_AXES.json'))))
    case.identity['composite_original_reference_sha']=reference_identity(blocks);case.case_sha=digest(case.identity)
    def lift(x):
        if k48_only:raise PermissionError('SELECTED_UB_MODEL_NOT_LOADED_IN_NATIVE0_K48_PHASE')
        orig=p.inverse(x[:len(p.col_ids)])[:blocks.nbase];full=np.zeros(A.shape[1]);full[:blocks.nbase]=orig
        for t in range(96):
            with np.load(root/'native'/f'{t:02d}_MAP.npz') as z:mp=z['original_aux_to_native']
            cache=CACHE if stage=='M1' and current_root is None else root/'screen'
            u=x[mp[:48]];C=sp.load_npz(cache/f'{t:02d}/RECONSTRUCTION.npz');a=np.load(cache/f'{t:02d}/CONSTANT.npy')
            grid=np.r_[u,a+C@u];retained=mp>=0;grid[retained]=x[mp[retained]]
            lo=blocks.nbase+t*N_AUX;full[lo:lo+N_AUX]=grid
        return full
    case.lift=lift;case._stream_identity=case.identity['composite_original_reference_sha'];case._blocks=blocks
    case.raw_pack=pack
    case._runtime_storage_root=root;case._k48_only=k48_only
    case.mess_stage_budget_seconds=900.
    from .stage_m_validation import validate,strict
    case.validate_full=lambda x:validate(case,x)
    case.strict_validator=strict
    immutable=[root/'native/COMPLETE_A.npz',root/'native/COMPLETE_DOMAIN.npz',pack/'MOBILITY.npz',pack/'MOBILITY_DOMAIN.npz',root/'mobility/TRANSPORT.pkl']
    for t in range(96):
        immutable.extend([pack/f'{t:02d}'/name for name in ('MATRIX.npz','ROWS.npz','DOMAIN.npz')])
        immutable.extend([blocks.view_root/f'{t:02d}'/name for name in ('A.npz','D.npz')])
    case._immutable_file_stats={str(path):(path.stat().st_size,path.stat().st_mtime_ns) for path in immutable}
    return case

@contextmanager
def source_binding(case):
    """Source algorithms unchanged; hash/physical-axis IO handles streaming."""
    from v44.frozen.v43_mess.library import load
    from .stage_threads import scope as m_threads
    modules=load();saved=[]
    def patch(obj,key,value):saved.append((obj,key,getattr(obj,key)));setattr(obj,key,value)
    k=modules['table_v_k48'];engine=modules['m_engine']
    old_matrix=engine.matrix_sha;old_domain=engine.domain_sha
    def matrix(A):return case._stream_identity if isinstance(A,FullCSR) else old_matrix(A)
    def domain(d):return case._stream_identity if isinstance(d.get('names'),Names) else old_domain(d)
    def identity(c):
        # The unchanged source UB engine makes a shallow Case copy.
        assert (c.case_sha==case.case_sha and digest(c.identity)==c.case_sha
            and c.original_A is case.original_A and c.original_d is case.original_d
            and c.A is case.A and c.d is case.d)
        for path,expected in case._immutable_file_stats.items():
            st=Path(path).stat()
            if (st.st_size,st.st_mtime_ns)!=expected:raise ValueError('CURRENT_COMPOSITE_AUTHORITY_FILE_CHANGED:'+path)
        return dict(day='2025-05-01',stage_case_sha=c.case_sha,source_sha=c.identity['source_sha'],parent_case_sha=c.identity['parent_case_sha'],
            arm=c.identity['arm'],stage=c.identity['stage'],aidc_anchor=c.identity['aidc_anchor'],matrix_sha=c._stream_identity,domain_sha=c._stream_identity,
            identity_kind='EXPLICIT_COMPOSITE_ROW_VIEW_NOT_MONOLITHIC_CSR_HASH')
    original_axes=k.physical_axes
    def physical_axes(A,d):
        if isinstance(A,FullCSR):return original_axes(case._blocks.mob,case._blocks.md)
        return original_axes(A,d)
    for mod in modules.values():
        if hasattr(mod,'matrix_sha'):patch(mod,'matrix_sha',matrix)
        if hasattr(mod,'domain_sha'):patch(mod,'domain_sha',domain)
    patch(k,'identity',identity);patch(k,'physical_axes',physical_axes)
    # The source StageBudget checks the same actual case identity through the
    # public runtime IO hook. It must see the explicit composite authority too.
    import v44.runtime as runtime
    patch(runtime,'current_identity',identity)
    from v44.cap300 import CALL_CAP
    patch(modules['m_adaptive'],'JOINT_CAP_SECONDS',CALL_CAP)
    import v44.budget as stage_budget
    patch(stage_budget,'JOINT_CALL_CAP',CALL_CAP)
    axes=read(OUT/'SOURCE_YY_GRID_AXES.json');parent=np.flatnonzero(axes['parent_mask'])
    names=[axes['line'][j]['element']+'::'+str(axes['line'][j]['physical_phase']) for j in parent]
    names +=[r['element']+'::W'+str(r['winding']) for r in axes['transformer_winding']]
    names +=['transformer.mobile_port_'+s+'::all' for s in [f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]]
    patch(k,'_coefficient_metadata',lambda c:dict(node_names=axes['nodes'],branch_names=names,transformer_ratings=np.r_[np.ones(len(parent)),axes['tx_kVA'],np.full(24,600.)]))
    original_metadata=k.original_oracle.metadata
    def metadata(name,coeff):
        result=original_metadata(name,coeff)
        if result['family']=='NormalAmps' and result['asset'].endswith('/port600'):
            result=dict(result,scale=.8,normalization_basis='600kVA port current / separate 750kVA winding current')
        return result
    patch(k.original_oracle,'metadata',metadata)
    # Pure lifetime/IO change: Source no longer reads these two temporary
    # matrices after the final vstack. Release them before allocating textual
    # Native domains. All sparse products, their order and proofs stay literal.
    tree=ast.parse(textwrap.dedent(inspect.getsource(engine.direct_joint)));body=tree.body[0].body;released=0
    for index,node in enumerate(list(body)):
        if (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='A' for t in node.targets)
                and isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='sparse.vstack'):
            body.insert(index+1,ast.Delete(targets=[ast.Name('product',ast.Del()),ast.Name('dynamic',ast.Del())]));released+=1
    assert released==1;ast.fix_missing_locations(tree);namespace=dict(engine.__dict__)
    exec(compile(tree,engine.__file__,'exec'),namespace);patch(engine,'direct_joint',namespace['direct_joint'])
    request=dict(day='2025-05-01',arm=case.identity['arm'],stage=case.identity['stage'],worker_slot=1,Threads=4)
    try:
        with m_threads(request) as effective:
            modules['_effective_r043_parameters']=effective
            from v44.frozen.v43_mess.performance import install
            if not case._k48_only:
                candidate_module=modules['m_candidates']
                # Source performance caches own case-sized closures. Restore
                # their previous IO functions when this case scope closes so
                # constructing a later M case cannot retain both matrices.
                for key in ('grid_context','pcs_vertices','base_grid_reference'):
                    saved.append((candidate_module,key,getattr(candidate_module,key)))
                install(case,modules)
            # Every PCS equation lies in the literal mobility prefix. Use
            # that same authority for the inherited Q250 scoring polygon;
            # grid-only helpers cannot alter a PCS equation.
            from v44.q250_m4 import pcs_vertices,check_plan
            light=SimpleNamespace(original_A=case._blocks.mob,original_d=case._blocks.md,graph=case.graph)
            vertex=lambda current:pcs_vertices(light)
            patch(modules['m_candidates'],'pcs_vertices',vertex)
            if hasattr(modules['m_candidates'],'_v43_original_vertices'):
                patch(modules['m_candidates'],'_v43_original_vertices',vertex)
            def export(current,point):
                plan=engine.export_plan(current,point);check_plan(plan);return plan
            case.plan_exporter=export
            yield modules
    finally:
        for obj,key,value in reversed(saved):setattr(obj,key,value)
