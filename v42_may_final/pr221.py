"""Bind frozen PR221 functions to this date's source case and native ledger.

The archived MILP formulation stays unchanged. Case incumbents require a fresh
FULL replay; bounded redispatch scoring changes only candidate admission.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fractions import Fraction
import ast, gc, inspect, json, sys, textwrap, time
import numpy as np
from v42_pr134_b1.common import atomic, read, record, sha, digest

HEAD='a874df15b9a306a7d769a60622b40fb76de3ffcc'

class InterfaceBlocked(ValueError):
    pass

def rebound(function, replacements=(), namespace=None, axes=None):
    text=textwrap.dedent(inspect.getsource(function))
    for old,new in replacements:
        if text.count(old)!=1: raise InterfaceBlocked('PR221_ADAPTER_BODY_AXIS_DRIFT:'+old)
        text=text.replace(old,new)
    tree=ast.parse(text);counts={key:0 for key in axes or {}}
    class BindAxes(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is int and node.value in counts:
                counts[node.value]+=1
                return ast.copy_location(ast.Constant(value=int(axes[node.value])),node)
            return node
    tree=BindAxes().visit(tree);ast.fix_missing_locations(tree)
    if any(count==0 for count in counts.values()):raise InterfaceBlocked('PR221_ARCHIVED_AXIS_LITERAL_DRIFT:'+str(counts))
    env=dict(function.__globals__);env.update(namespace or {})
    exec(compile(tree,inspect.getfile(function),'exec'),env)
    return env[function.__name__]

def current_axes(case):
    """Admit named current coordinates, rather than one archived day's sizes."""
    for A,d in ((case.A,case.d),(case.original_A,case.original_d)):
        if (A.shape!=(len(d['row_names']),len(d['names'])) or not A.has_canonical_format
                or not np.isfinite(A.data).all() or len(set(map(str,d['names'])))!=A.shape[1]):
            raise InterfaceBlocked('PR221_CURRENT_MATRIX_NAMED_AXES_INVALID')
        obj=np.flatnonzero(d['objective'])
        if (len(obj)!=1 or str(d['names'][obj[0]])!='rho_max' or d['objective'][obj[0]]!=1
                or float(d['constant'])!=0):raise InterfaceBlocked('PR221_CURRENT_OBJECTIVE_DRIFT')
    sites,initial,arcs,battery,_=case.graph
    if (len(sites)!=24 or set(initial)!={'MESS01','MESS02','MESS03','MESS04'}
            or max(a[3] for a in arcs)!=96):raise InterfaceBlocked('PR221_CURRENT_PHYSICAL_AXES_DRIFT')
    route=np.asarray([j for j,n in enumerate(map(str,case.d['names'])) if n.startswith(('route_flow[','node_activity['))],dtype=int)
    modes=np.asarray([j for j,n in enumerate(map(str,case.d['names'])) if n.startswith('charge_mode[')],dtype=int)
    binaries=set(map(int,np.flatnonzero(case.d['types']=='B')))
    expected_modes={f'charge_mode[{u},{t}]' for u in initial for t in range(96)}
    if (set(map(str,case.d['names'][modes]))!=expected_modes or len(route)==0 or binaries-set(map(int,route))!=set(map(int,modes))
            or np.any(case.d['types'][modes]!='B') or np.any(case.d['lower'][modes]!=0)
            or np.any(case.d['upper'][modes]!=1) or np.any(case.d['objective'][route]!=0)):
        raise InterfaceBlocked('PR221_CURRENT_ROUTE_OR_MODE_AUTHORITY_DRIFT')
    return dict(source_rows=case.A.shape[0],source_columns=case.A.shape[1],
        FULL_rows=case.original_A.shape[0],FULL_columns=case.original_A.shape[1],
        route_columns=len(route),keep_columns=case.A.shape[1]-len(route),
        route_binary=int(np.count_nonzero(case.d['types'][route]=='B')),
        route_continuous=int(np.count_nonzero(case.d['types'][route]=='C')),
        source_binary=len(binaries),charge_modes=384)

def pcs_context(case):
    from v42_ultracompact.current_verify import physical_pcs_authority
    from v42_ultracompact.polytope import vertices
    planes=physical_pcs_authority(case.original_A,case.original_d,case.graph)
    limit=Fraction(float(case.graph[3].p_limit))
    points=vertices(planes+[(Fraction(1),Fraction(0),limit),(Fraction(-1),Fraction(0),limit)])
    if not points:raise InterfaceBlocked('PR221_CURRENT_PCS_CONTEXT_EMPTY')
    return dict(PASS=True,case_sha=case.case_sha,original_matrix_sha=case.identity['original_matrix_sha'],
        original_domain_sha=case.identity['original_domain_sha'],PCS16_vertices_exact=[[str(p),str(q)] for p,q in points],
        original_current_physical_blocks_verified=True,historical_context_read=False,Native_optimize_calls=0)

def verify_tools(manifest):
    root=Path(manifest['code_root'])
    for relative,expected in manifest['PR221_tool_sources'].items():
        if sha(root/relative)!=expected: raise PermissionError('SVR11_GLOBAL_PR221_SOURCE_SHA_DRIFT:'+relative)

def _optimize_case(case,budget,progress=None,*,stage_identity=None,initial_point=None,
                  strict_validator=None,plan_exporter=None,_bindings=None,**kwargs):
    from v42_svr11.authority import active,verify
    from v42_common_mess import engine as cold
    from v42_common_mess.budget import StageBudget
    manifest=active();verify_tools(manifest);stage_identity=stage_identity or {}
    out=case.output;docs=out/'PR221';docs.mkdir(exist_ok=False)
    axes=current_axes(case)
    atomic(docs/'CURRENT_CASE_AXES.json',dict(PASS=True,case_sha=case.case_sha,**axes))
    atomic(docs/'SIGNED_SELECTION_CONTEXT.json',pcs_context(case))
    if case.bundle['day']!=stage_identity.get('day',case.bundle['day']):
        raise PermissionError('SVR11_GLOBAL_PR221_ARM_DATE_BINDING_DRIFT')
    ledger=StageBudget(budget)
    validator=strict_validator or cold._strict
    from .incumbent import admit,Bank
    from .dispatch_score import refine
    bank=Bank(case)
    arm=stage_identity.get('arm',case.identity.get('arm','B2'))
    inherited=admit(case,manifest.get('validated_case_incumbents',[]),docs,validator,arm)
    for x,cert in inherited:bank.offer(x,cert)
    candidate=initial_point if initial_point is not None else getattr(case,'point',None)
    candidate_cert=cold._validate(case,candidate,docs/'CURRENT_STAGE_POINT.npz',validator,
        ledger,'CURRENT_STAGE_FULL_REPLAY')
    if candidate_cert is not None:bank.offer(candidate,candidate_cert)
    case.point=None if candidate_cert is None else np.asarray(candidate,dtype=float).copy()
    if bank.best is not None:case.point=bank.best[0].copy()
    # The original initializer retains current-case replay and measured budget.
    point,strict,initialization=cold._initialize(case,ledger,validator,progress,None)
    if point is not None:bank.offer(point,strict)
    if bank.best is not None:point,strict=bank.best
    bank.save(docs,arm)
    initial_ub=None if strict is None else strict['Global_UB']
    calls=[];error=None;termination='NO_INITIAL_FULL_FEASIBLE';joint_full_count=0
    if point is not None:
        np.savez_compressed(docs/'INITIAL_POINT.npz',point=point)
        aliases=read(out/'CURRENT_C2_ALIASES.json')
        with np.load(out/'CURRENT_C2_AXES.npz') as z: columns=z['columns'].copy()
        case.aliases=aliases;case.selected_columns=columns
        from tools.adaptive_perf_v3 import bootstrap as b,cache,feedback,grid,worker
        from tools.adaptive_compact_joint import beam,resume_feedback as body
        from tools.adaptive_compact_joint import direct
        from tools.global_local_multistart1800 import joint
        from tools.global_local_multistart1800.dag import Graph
        from tools.time_decomposed_lb import grid as streamed
        from tools.minimax_beam1800 import grid as priorgrid,routes
        from tools.u4_primal_alns import verify as v
        # Every imported research function must be the exact PR221 file bytes.
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__name__','');file=getattr(module,'__file__',None)
            if name.startswith('tools.') and file and str(file).endswith('.py'):
                parts=Path(file).parts
                if 'tools' in parts:
                    rel='/'.join(parts[parts.index('tools'):])
                    expected=manifest['PR221_tool_sources'].get(rel)
                    if expected is None or sha(file)!=expected:raise PermissionError('SVR11_GLOBAL_IMPORTED_PR221_FILE_DRIFT:'+rel)
        v.ROOT=Path(manifest['code_root']);v.DOCS=docs;v.SOURCE=out;v.CASE_SHA=case.case_sha
        v.MATRIX_SHA=v.matrix_sha(case.A);v.DOMAIN_SHA=v.domain_sha(case.d)
        v.FULL_MATRIX_SHA=case.identity['original_matrix_sha'];v.FULL_DOMAIN_SHA=case.identity['original_domain_sha']
        def point_load(path):
            with np.load(path,allow_pickle=False) as z:x=z['point'].copy()
            if x.shape!=(case.A.shape[1],) or not np.isfinite(x).all():raise InterfaceBlocked('PR221_CURRENT_POINT_AXIS')
            return x
        v.load_point=point_load
        def guard():
            verify(Path(manifest['root'])/'CAMPAIGN_MANIFEST.json');verify_tools(manifest)
        def safety():
            guard()
            from v42_svr11.resources import snapshot
            from v42_svr11.processes import workers
            memory=snapshot();peers=workers(manifest['root'],manifest['execution_SHA'])
            reserve=manifest['B3_memory_admission']['system_reserve_bytes']
            if memory['RAM_available']<reserve or memory['Commit_available']<reserve:
                raise PermissionError('SVR11_GLOBAL_RAM_COMMIT_GATE')
            return dict(PASS=True,memory=memory,owned_workers=len(peers),Threads=1)
        authority_raw=docs/'VERIFIED_CASE_AUTHORITY.npz'
        np.savez_compressed(authority_raw,point=point)
        def configure():
            for module in tuple(sys.modules.values()):
                name=getattr(module,'__name__','')
                if name.startswith('tools.') and hasattr(module,'DOCS'):module.DOCS=docs
                if name.startswith('tools.') and hasattr(module,'RAW_REL'):module.RAW_REL=str(authority_raw)
            b.DOCS=docs;worker.DOCS=docs;cache.DOCS=docs;feedback.DOCS=docs;grid.DOCS=docs
        configure();b.configure=configure;feedback.configure=configure;body.configure=configure
        worker.configure=configure;worker.guard=guard;worker.full_guard=guard
        worker.r=SimpleNamespace(audit=lambda _:safety(),memory=lambda:safety()['memory'],
            admit=lambda before,after:safety(),callbackcheck=safety)
        atomic(docs/'EXECUTION_POLICY.json',dict(maximum_single_call_seconds=140,Threads=1,
            Native_limit=1800,PR221_HEAD=HEAD,backend='DIRECT',additional_Pilot=False))
        replay=docs/'INITIAL_FULL.json'
        def certify(x,path):
            np.savez_compressed(path,point=x)
            cert=validator(case,path,{})
            if cert.get('PASS') is not True:raise InterfaceBlocked('PR221_CURRENT_ORIGINAL_FULL_REPLAY_FAILED')
            cert=dict(cert,point_path=str(path),point_vector_sha256=v.vector_sha(x),case_sha=case.case_sha)
            atomic(path.with_suffix('.REPLAY.json'),cert)
            return path.with_suffix('.REPLAY.json'),cert
        replay,strict=certify(point,docs/'INITIAL_POINT.npz')
        # Bind only the row accessor's input identity. Its exact projection and
        # original row/helper checks are unchanged; no historical rows are read.
        inherited=dict(PASS=True,base_commit=v.SOURCE_SHA,case_sha=case.case_sha,
            original_matrix_sha=case.identity['original_matrix_sha'],original_domain_sha=case.identity['original_domain_sha'],
            source_records={str(out/name):sha(out/name) for name in ('FULL_A.npz','FULL_DATA.npz')})
        def current_read(path):
            if Path(path).name=='NATIVE0.json':return inherited
            return read(path)
        original_init=streamed.SelectiveAuthority.__init__
        _bindings.enter_context(patch.object(streamed.SelectiveAuthority,'__init__',rebound(original_init,
            namespace=dict(SAVED=out,CASE=case.case_sha,read=current_read),
            axes={1130336:axes['FULL_rows'],344967:axes['FULL_columns']})))
        spec_builder=rebound(joint.build_spec,axes={9322:axes['source_binary']})
        transformed=rebound(direct.transform,namespace=dict(build_spec=spec_builder,
            integer_proof=lambda *a,**k:direct.integer_proof(*a,**k)),axes={
                216674:axes['route_columns'],137603:axes['keep_columns'],
                8938:axes['route_binary'],207736:axes['route_continuous']})
        _bindings.enter_context(patch.object(direct,'transform',transformed))
        _bindings.enter_context(patch.object(cache,'independent_links',rebound(cache.independent_links,
            axes={354277:axes['source_columns']})))
        coefficient=Path(case.bundle['electrical_certificate']['path'])
        grid.g.COEFFICIENTS=Path(read(coefficient)['outputs']['planning_coefficients']['path'])
        # Depth4 is generated anew from this day's DAG instead of importing the
        # historical May01 candidate reservoir. Beam rules are unchanged.
        _bindings.enter_context(patch.object(beam,'generate',rebound(beam.generate,[
            ("legacy=read(OLD_DOCS/'GLOBAL_CANDIDATE_POOL.json')['candidates']","legacy=[]"),
            ("'PR220_AUTHORITY'","'VERIFIED_CASE_AUTHORITY'")])) )
        context,_=grid.refresh(case,point,0)
        beam.generate(case,point,context,replay,size=8,epoch=0)
        body.beta=SimpleNamespace(DOCS=docs)
        # Stage budget owns actual Optimize and failure Runtime; inline model
        # readback replaces a separate Native0 pilot in an actual campaign.
        def native(model,callback):
            return ledger.optimize(model,track='M_PR221_DIRECT',label='PR221_JOINT',
                requested_seconds=float(model.Params.TimeLimit),callback=callback)
        execute=rebound(worker.execute,[
            ("assert read(DOCS/'NATIVE0_GATE.json')['PASS']","assert read(out/'NATIVE_READBACK.json')['PASS']"),
            ('model.optimize(callback)','_current_native(model,callback)')],dict(_current_native=native),axes={715596:axes['source_rows']})
        latest=point.copy();best=point.copy();best_strict=strict;seen=set();timer=b.Timing()
        static=cache.get(case,timer)
        termination='NATIVE_BUDGET_WITH_RETURN_RESERVE'
        try:
            for epoch in range(1,129):
                if ledger.remaining()<15:break
                safety()
                configure();pools,signature=feedback.generate(case,latest,replay,epoch,seen,b.Timing())
                if pools is None:termination='VALID_CANDIDATE_SIGNATURES_EXHAUSTED';break
                beam_signature=signature
                context=read(docs/f'OPTIMIZATION_FEEDBACK_{epoch:02d}.json')['original_grid_context']
                pools,signature=refine(case,latest,context,pools,docs,epoch)
                if 'DIRECT|'+signature in seen:
                    seen.update(form+'|'+beam_signature for form in ('JOINT','DIRECT'))
                    continue
                folder=docs/'packages'/f'POOL_{epoch:03d}'
                cache.fast_save(case,latest,replay,pools,f'POOL_{epoch:03d}',folder,static,b.Timing())
                seconds=min(140.,ledger.remaining()-10)
                if progress:progress(dict(phase='M_PR221_ADAPTIVE_DIRECT_JOINT',stage=stage_identity.get('stage'),
                    verified_UB=best_strict['Global_UB'],native_runtime_seconds=ledger.used(),remaining_native_seconds=ledger.remaining()))
                output=docs/'calls'/f'{epoch:03d}';args=SimpleNamespace(output=output,spec=folder/'SPEC.json',mode='native',seconds=seconds)
                rc=execute(args);q=read(output/'NATIVE_CALL.json');calls.append(record(output/'NATIVE_CALL.json'))
                if q['Native_Runtime'] is None:raise PermissionError('SVR11_GLOBAL_PR221_UNMEASURED_RUNTIME')
                if rc or q['callback_errors']:raise InterfaceBlocked('PR221_CURRENT_NATIVE_FAILURE:'+str(q.get('error')))
                pool_full_ubs=[]
                for capture in q['captures']:
                    if not capture['strict_literal_lambda']:continue
                    x=point_load(capture['dense_lift']['path'])
                    rp,cert=certify(x,output/f'FULL_{joint_full_count:03d}.npz');joint_full_count+=1
                    pool_full_ubs.append(cert['Global_UB']);bank.offer(x,cert)
                    if cert['Global_UB']<best_strict['Global_UB']:
                        best=x.copy();best_strict=cert;replay=rp
                        np.savez_compressed(authority_raw,point=best)
                latest=best.copy()
                atomic(output/'POOL_AND_CASE_UB.json',dict(pool_Solver_ObjVal=q.get('ObjVal'),
                    pool_FULL_verified_UB=min(pool_full_ubs) if pool_full_ubs else None,**bank.fields(),
                    restricted_ObjBound_is_Global_LB=False))
                bank.save(docs,arm)
                seen.update(form+'|'+signature for form in ('JOINT','DIRECT'))
                seen.update(form+'|'+beam_signature for form in ('JOINT','DIRECT'))
            point=best;strict=best_strict
        finally:
            streamed.SelectiveAuthority.__init__=original_init
        if joint_full_count==0:raise InterfaceBlocked('PR221_NO_FOUR_MESS_JOINT_FULL_RESULT')
    feasible=point is not None and joint_full_count>0
    if feasible:
        replay,strict=certify(point,out/'BEST_STRICT_UB_POINT.npz')
        atomic(out/'BEST_STRICT_UB_CERTIFICATE.json',strict)
        case.point=point.copy();plan=plan_exporter(case,point)
    else:plan=None
    ub=None if not feasible else strict['Global_UB']
    result=dict(engine_version='PR221_ADAPTIVE_DIRECT_4MESS_JOINT',algorithm_version='PR221_ADAPTIVE_DIRECT_4MESS_JOINT',
        day=case.bundle['day'],arm=stage_identity.get('arm',case.identity.get('arm','B2')),stage_identity=stage_identity,
        case_sha=case.case_sha,scientific_case_sha=case.case_sha,accepted=feasible,feasible_accepted=feasible,PASS=feasible,
        UB=ub,verified_UB=ub,initial_verified_UB=initial_ub,final_verified_UB=ub,
        exact_Global_UB=None if not feasible else strict['exact_Global_UB'],
        global_gap_certified=False,certified_Global_LB=None,LB=None,certified_gap=None,
        independent_dual_status='NOT_CERTIFIED',independent_global_bound_verified=False,
        independent_global_gap_available=False,restricted_ObjBound_is_Global_LB=False,
        Native_Runtime=ledger.used(),native_runtime_seconds=ledger.used(),native_runtime_limit_seconds=1800,
        P2_calls=0,AIDC_optimization_calls=0,LB_optimizer_calls=0,error=error,
        termination=termination,status='FULL_FEASIBLE_ACCEPTED' if feasible else 'M_NO_VALID_FEASIBLE',
        classification='FULL_FEASIBLE_ACCEPTED' if feasible else 'M_NO_VALID_FEASIBLE',
        certificate=dict(strict_UB=record(out/'BEST_STRICT_UB_CERTIFICATE.json') if feasible else None,
            exact_LB=None,original_domain_equivalence=case.identity.get('transport')),
        mess=plan,planning=case.planning,output=str(out),PR221_HEAD=HEAD,
        all_four_route_decision_free=True,all384_Mode_free=True,no_MOVE_forcing=True,
        joint_calls=calls,joint_FULL_count=joint_full_count,**bank.fields(),
        validated_same_case_incumbents_admitted=len(inherited),cross_date_points_reused=False,
        candidate_score_version='JOINT_REDISPATCH_SHORTLIST_V1',new_scoring_is_not_FULL_UB_or_Global_LB=True)
    atomic(out/'M_STAGE_RESULT.json',result)
    return result,point if feasible else None

def optimize_case(*args,**kwargs):
    with ExitStack() as bindings:
        return _optimize_case(*args,_bindings=bindings,**kwargs)

@contextmanager
def attached():
    import v42_common_mess, v42_common_mess.engine
    with patch.object(v42_common_mess,'optimize_case',optimize_case),patch.object(v42_common_mess.engine,'optimize_case',optimize_case):
        yield
