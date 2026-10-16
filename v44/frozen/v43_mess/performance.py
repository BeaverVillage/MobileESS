"""Read-only current-case caches and phase timing; original arithmetic retained."""
from contextlib import contextmanager
from functools import wraps
import ast
import inspect
import json
import textwrap
from time import perf_counter,process_time

import numpy as np

from v43.common import record


@contextmanager
def phase(case_or_folder,name):
    folder=getattr(case_or_folder,'output',case_or_folder)
    wall=perf_counter();cpu=process_time();error=None
    try:yield
    except BaseException as exc:error=repr(exc);raise
    finally:
        from pathlib import Path
        path=Path(folder)/'V43_PREPARATION_PROFILE.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(dict(stage=name,wall_seconds=perf_counter()-wall,
                CPU_seconds=process_time()-cpu,error=error,Native_optimize_included=False))+'\n')


def profiled_build(original,*,stage='M1'):
    source=textwrap.dedent(inspect.getsource(original));tree=ast.parse(source);changed=[]
    if stage not in ('M1','M2'):raise ValueError('EXPLICIT_M1_M2_MODEL_STAGE_REQUIRED')
    route_counts=dict(M_authority=0,A_parent=0,native_stage=0,deadline=0)
    if stage=='M2':
        class StageRoute(ast.NodeTransformer):
            def visit_Attribute(self,node):
                if isinstance(node.value,ast.Name) and node.value.id=='Stage':
                    if node.attr=='M1':node.attr='M2';route_counts['M_authority']+=1
                    elif node.attr=='A1':node.attr='A2';route_counts['A_parent']+=1
                return node
            def visit_ClassDef(self,node):
                if node.name=='ConstructionDeadline':
                    for statement in node.body:
                        if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='stage' for t in statement.targets):
                            if not isinstance(statement.value,ast.Constant) or statement.value.value!='M1':raise ValueError('M2_DEADLINE_STAGE_BOUNDARY_DRIFT')
                            statement.value.value='M2';route_counts['deadline']+=1
                return self.generic_visit(node)
            def visit_Call(self,node):
                if ast.unparse(node.func)=='native.solve':
                    if not isinstance(node.args[0],ast.Constant) or node.args[0].value!='M1':raise ValueError('M2_NATIVE_STAGE_BOUNDARY_DRIFT')
                    node.args[0].value='M2';route_counts['native_stage']+=1
                return self.generic_visit(node)
        tree=StageRoute().visit(tree)
        if route_counts!=dict(M_authority=2,A_parent=1,native_stage=1,deadline=1):
            raise ValueError('M2_ORIGINAL_STAGE_ROUTING_SHAPE_DRIFT:'+str(route_counts))
    stages={'native.solve':'ORIGINAL_MODEL_CONSTRUCTION','arrays':'ORIGINAL_MATRIX_EXPORT',
        'Compact':'EXACT_COMPACT_CONSTRUCTION','presolve.run':'EXACT_STATIC_PRESOLVE',
        'verify_transport':'INDEPENDENT_TRANSPORT_PROOF','_freeze_transport':'TRANSPORT_HASH_FREEZE'}
    class Profile(ast.NodeTransformer):
        def visit_Expr(self,node):return self.wrap(node)
        def visit_Assign(self,node):return self.wrap(node)
        def wrap(self,node):
            value=getattr(node,'value',None)
            if not isinstance(value,ast.Call):return node
            name=ast.unparse(value.func)
            if name not in stages:return node
            changed.append(name)
            context=ast.Call(func=ast.Name('_v43_phase',ast.Load()),args=[ast.Name('out',ast.Load()),ast.Constant(stages[name])],keywords=[])
            return ast.copy_location(ast.With(items=[ast.withitem(context_expr=context)],body=[node]),node)
    tree=Profile().visit(tree);ast.fix_missing_locations(tree)
    if set(changed)!=set(stages) or len(changed)!=len(stages):raise ValueError('M_BUILD_PROFILE_BOUNDARY_DRIFT')
    namespace=dict(original.__globals__,_v43_phase=phase)
    exec(compile(tree,inspect.getfile(original),'exec'),namespace)
    routed=namespace[original.__name__];routed._v43_profiled_ast=tree;routed._v43_stage_route=route_counts
    return routed


def install(case,modules):
    """Cache only immutable source data within this one bound case/worker."""
    if getattr(case,'_v43_cache_installed',False):return
    m=modules['m_engine'];c=modules['m_candidates']
    # No source matrix/domain can be edited after cache certification. Native
    # models receive their normal independent copies; final case SHA replay
    # still runs before accepting any result.
    for A in (case.A,case.original_A):
        for name in ('data','indices','indptr'):getattr(A,name).setflags(write=False)
    for d in (case.d,case.original_d):
        for value in d.values():
            if isinstance(value,np.ndarray):value.setflags(write=False)
    key=(case.case_sha,id(case.original_A),id(case.original_d),id(case.A),id(case.d))
    cache={};case._v43_cache_installed=True;case._v43_runtime_cache=cache
    counters=dict(authority_builds=0,authority_reuses=0,term_hits=0,term_misses=0,
        projection_hits=0,projection_misses=0,PCS_builds=0,PCS_reuses=0,reference_builds=0,reference_reuses=0)
    case._v43_cache_counters=counters
    def check(current):
        got=(current.case_sha,id(current.original_A),id(current.original_d),id(current.A),id(current.d))
        if got!=key:raise ValueError('CURRENT_M_CACHE_CASE_OR_ARRAY_IDENTITY_CHANGED')
    def authority(current,factory):
        check(current)
        if 'authority' not in cache:
            with phase(current,'BEAM_STATIC_AUTHORITY'):
                obj=factory();terms=obj.terms;project=obj.project;term_cache={};project_cache={}
                def cached_terms(i):
                    if i not in term_cache:term_cache[i]=terms(i);counters['term_misses']+=1
                    else:counters['term_hits']+=1
                    return term_cache[i]
                def cached_project(i,t):
                    k=(i,t)
                    if k not in project_cache:project_cache[k]=project(i,t);counters['projection_misses']+=1
                    else:counters['projection_hits']+=1
                    return dict(project_cache[k])
                obj.terms=cached_terms;obj.project=cached_project;cache['authority']=obj;counters['authority_builds']+=1
        else:counters['authority_reuses']+=1
        return cache['authority']
    if not hasattr(c,'_v43_original_grid_context'):
        c._v43_original_grid_context=c.grid_context;c._v43_original_vertices=c.pcs_vertices
        c._v43_original_reference=c.base_grid_reference
    source=textwrap.dedent(inspect.getsource(c._v43_original_grid_context))
    if source.count('authority = CurrentAuthority()')!=1:raise ValueError('M_CONTEXT_CACHE_BOUNDARY_DRIFT')
    namespace=dict(c._v43_original_grid_context.__globals__,_v43_authority=authority)
    exec(compile(source.replace('authority = CurrentAuthority()',
        'authority = _v43_authority(case, CurrentAuthority)'),inspect.getfile(c._v43_original_grid_context),'exec'),namespace)
    def timed_context(current,point):
        check(current)
        with phase(current,'BEAM_GRID_CONTEXT'):return namespace['grid_context'](current,point)
    def vertices(current):
        check(current)
        if 'vertices' not in cache:
            with phase(current,'BEAM_ORIGINAL_PCS_AUTHORITY'):
                cache['vertices']=c._v43_original_vertices(current);cache['vertices'].setflags(write=False)
                counters['PCS_builds']+=1
        else:counters['PCS_reuses']+=1
        return cache['vertices']
    def reference(current):
        check(current)
        if 'reference' not in cache:
            with phase(current,'BEAM_ZERO_DISPATCH_REFERENCE'):
                cache['reference']=c._v43_original_reference(current);cache['reference'].setflags(write=False)
                counters['reference_builds']+=1
        else:counters['reference_reuses']+=1
        return cache['reference']
    c.grid_context=timed_context;c.pcs_vertices=vertices;c.base_grid_reference=reference
    # The dynamically reused grid function has its own namespace. Supply the
    # same cached seedless helper there; no score formula changes.
    namespace['base_grid_reference']=reference
    case._v43_original_runtime_sources=[record(inspect.getfile(c._v43_original_grid_context)),record(__file__)]


def record_caches(case,path):
    from v43.common import atomic
    atomic(path,dict(counters=getattr(case,'_v43_cache_counters',{}),
        scope='SINGLE_CURRENT_CASE_READ_ONLY_MATRICES',cross_case_or_historical_cache_reuse=False,
        original_arithmetic_retained=True))
