"""Select only stage labels and fixed M1 constants in the original A core.

No AIDC equation, variable, option domain, CC4 allocation, objective, pricing,
integer-restoration or numerical policy is replaced by the PR231 D0 engine.
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
import inspect
from pathlib import Path
from types import FunctionType
from unittest.mock import patch

import numpy as np

from v43.common import ROOT,read,record,atomic,verify_records
from v42_native.contracts import digest


def require_m1(result):
    if (result.get('arm')!='B3' or result.get('stage')!='M1' or result.get('FULL_feasible') is not True
            or result.get('upper',{}).get('FULL_validated') is not True or not result.get('MESS_plan')):
        raise ValueError('A2_REQUIRES_CURRENT_B3_M1_ORIGINAL_FULL_FEASIBLE_PLAN')
    plan=result['MESS_plan']
    if plan['case_sha']!=result['case_sha'] or digest({k:v for k,v in plan.items() if k!='plan_sha'})!=plan['plan_sha']:
        raise ValueError('A2_M1_PLAN_SHA_OR_CASE_DRIFT')
    if plan['P_sign']!='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch' or plan['time_axis']!=list(range(96)):
        raise ValueError('A2_ORIGINAL_MESS_SIGN_AXIS_REQUIRED')
    return deepcopy(plan)


def source_tree(module,name):
    source=Path(module.__file__).read_text(encoding='utf-8-sig')
    return deepcopy(next(n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name))


def fixed_grid(module,mess):
    """Same PR189 Planning function; two checked stage/constant substitutions."""
    tree=source_tree(module,'planning_grid');count=dict(stage=0,control=0)
    class Route(ast.NodeTransformer):
        def visit_Attribute(self,node):
            if (isinstance(node.value,ast.Name) and node.value.id=='Stage' and node.attr=='A1'):
                node.attr='A2';count['stage']+=1
            return node
        def visit_Expr(self,node):
            if (isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute)
                    and isinstance(node.value.func.value,ast.Name) and node.value.func.value.id=='row'
                    and node.value.func.attr=='append' and len(node.value.args)==1
                    and isinstance(node.value.args[0],ast.Constant) and node.value.args[0].value==0.):
                node.value.args[0]=ast.Call(func=ast.Name(id='_v43_fixed_M1_control',ctx=ast.Load()),
                    args=[ast.Name(id='name',ctx=ast.Load()),ast.Name(id='t',ctx=ast.Load())],keywords=[])
                count['control']+=1
            return self.generic_visit(node)
    tree=Route().visit(tree)
    if count!=dict(stage=2,control=1):raise ValueError('PR189_FIXED_M1_GRID_SOURCE_SHAPE_DRIFT:'+str(count))
    tree.body.insert(0,ast.parse('stage=Stage.A2').body[0])
    def control(name,t):
        site=name.split('[',1)[1][:-1]
        key='P_by_site' if name.startswith('mess_p_kw[') else 'Q_by_site' if name.startswith('mess_q_kvar[') else None
        if key is None:raise ValueError('A2_UNSUPPORTED_ORIGINAL_MESS_CONTROL:'+name)
        return float(mess[key][site][t])
    namespace=dict(module.__dict__,_v43_fixed_M1_control=control)
    unit=ast.Module(body=[tree],type_ignores=[]);ast.fix_missing_locations(unit)
    exec(compile(unit,module.__file__,'exec'),namespace)
    function=namespace['planning_grid'];function._v42_dynamic_bundle_day_routed=True
    return function,count


LABELS={'B1':'B3','A1_P1_ONLY_ACCEPTED':'A2_P1_ONLY_ACCEPTED',
    'B1_P1_FREEZE.json':'B3_A2_P1_FREEZE.json','A1_FREEZE.json':'A2_MATERIALIZER_FREEZE.json'}


def routed_function(module,name,namespace,mess):
    tree=source_tree(module,name);changes=dict(labels=0,planning_check=0,materialized_mess=0)
    class Route(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str) and node.value in LABELS:
                node.value=LABELS[node.value];changes['labels']+=1
            return node
        def visit_keyword(self,node):
            if node.arg=='A1_P1_ONLY_ACCEPTED':node.arg='A2_P1_ONLY_ACCEPTED'
            elif node.arg=='A1_ACCEPTED':node.arg='A2_full_hierarchy_accepted'
            elif node.arg=='all_MESS_PQ_zero':node.value=ast.Call(func=ast.Name(id='_v43_M1_zero',ctx=ast.Load()),args=[],keywords=[])
            if name=='_planning' and node.arg in ('MESS_P_kw','MESS_Q_kvar'):
                node.value=ast.Call(func=ast.Name(id='_v43_M1_unit_array',ctx=ast.Load()),
                    args=[ast.Constant(value='P_kW' if node.arg=='MESS_P_kw' else 'Q_kvar')],keywords=[])
                changes['materialized_mess']+=1
            return self.generic_visit(node)
        def visit_If(self,node):
            if (name=='_planning' and any(isinstance(c,ast.Constant) and c.value=='A_B1_ORIGINAL_MESS_PQ_NOT_ZERO' for c in ast.walk(node))):
                changes['planning_check']+=1
                return ast.Expr(value=ast.Call(func=ast.Name(id='_v43_require_M1_controls',ctx=ast.Load()),
                    args=[ast.Name(id='coeff',ctx=ast.Load()),ast.Name(id='controls',ctx=ast.Load())],keywords=[]))
            return self.generic_visit(node)
    tree=Route().visit(tree)
    if name=='_paths':
        tree.body.insert(1,ast.parse("if day != '2025-05-01': raise ValueError('A2_MAY01_ONLY')").body[0])
    if name=='_planning' and (changes['planning_check'],changes['materialized_mess'])!=(1,2):
        raise ValueError('PR189_A2_MATERIALIZER_SOURCE_SHAPE_DRIFT')
    unit=ast.Module(body=[tree],type_ignores=[]);ast.fix_missing_locations(unit)
    exec(compile(unit,module.__file__,'exec'),namespace)
    return namespace[name],changes


@contextmanager
def scope(request,m1_result):
    """Process-local adapter. Caller owns immutable sources, locks and budget."""
    mess=require_m1(m1_result)
    import v42_may_campaign_native90.a_stage as original
    import v42_pr134_b1.native as binder
    import v42_boundary.model as boundary
    import v42_compact.native as compact
    from v43_followup.physical_cache import load_current_date_physical_cache
    from v42_may_campaign_native90 import a_cache
    original_bind=binder.bind;original_loader=a_cache.load_current_date_physical_cache
    namespace=dict(original.__dict__);changes={}
    namespace['_v43_M1_zero']=lambda:all(float(v)==0. for field in ('P_by_site','Q_by_site') for a in mess[field].values() for v in a)
    namespace['_v43_M1_unit_array']=lambda key:np.asarray([mess[key][u] for u in sorted(mess[key])]).T
    def require_controls(coeff,controls):
        for t,(c,row) in enumerate(zip(coeff,controls)):
            for name,value in zip(c.control_names,row):
                if name.startswith('aidc_load_kw['):continue
                field='P_by_site' if name.startswith('mess_p_kw[') else 'Q_by_site'
                if float(value)!=float(mess[field][name.split('[',1)[1][:-1]][t]):
                    raise ValueError('A2_FIXED_M1_CONTROL_NOT_EXACT')
    namespace['_v43_require_M1_controls']=require_controls
    for name in ('_paths','_prepare','prepare','verify_case','_native','_physical','_planning','run'):
        _,changes[name]=routed_function(original,name,namespace,mess)
    def bind(*args,**kwargs):
        answer=original_bind(*args,**kwargs)
        boundary.planning_grid,grid_changes=fixed_grid(boundary,mess)
        # Preserve bind's current output/C1/coefficients globals; only controls
        # and Stage are routed. Existing all-transformer wrapper still applies.
        compact.frozen_a1_grid=boundary.planning_grid
        changes['grid']=grid_changes
        return answer
    def cached(current_request,fresh_data,check=lambda:None,progress=None):
        # Old B1 is the local-domain proof's producer identity, not A2 math.
        # Domain evidence is requested separately; no A1 FULL certificate/LB.
        cache_request=dict(request['physical_domain_request'],output=current_request['output'])
        try:return load_current_date_physical_cache(cache_request,fresh_data,
            case_proof=request['physical_cache_case_proof']['path'],check=check,progress=progress,original_loader=original_loader)
        except Exception as error:raise RuntimeError('A2_REQUIRED_COMPLETE_LOCAL_DOMAIN_REUSE_FAILED') from error
    oldphysical=namespace['_physical']
    def physical(*args,**kwargs):
        Physical,power=oldphysical(*args,**kwargs)
        from v42_a_stage_acceptance.physical import Physical as inherited
        import v42_pr134_sc.snapshot as snapshot
        tree=source_tree(snapshot,'certify');stage_count=0
        class A2(ast.NodeTransformer):
            def visit_Attribute(self,node):
                nonlocal stage_count
                if isinstance(node.value,ast.Name) and node.value.id=='Stage' and node.attr=='A1':
                    node.attr='A2';stage_count+=1
                return node
        tree=A2().visit(tree)
        if stage_count!=1:raise ValueError('A2_ORIGINAL_PHYSICAL_STAGE_SOURCE_SHAPE')
        ns=dict(snapshot.__dict__);unit=ast.Module(body=[tree],type_ignores=[]);ast.fix_missing_locations(unit)
        exec(compile(unit,snapshot.__file__,'exec'),ns)
        verification=dict(inherited.verify.__globals__,certify=ns['certify'])
        Physical.verify=FunctionType(inherited.verify.__code__,verification,inherited.verify.__name__,inherited.verify.__defaults__)
        return Physical,power
    namespace['_physical']=physical
    verify_records([request['physical_cache_case_proof']])
    atomic(Path(request['output']).parent/'A2_SELECTIVE_SOURCE_BINDING.json',dict(
        source=record(__file__),changes=changes,original_core=record(original.__file__),
        grid_source=record(boundary.__file__),fixed_M1_plan_sha=mess['plan_sha'],
        old_FULL_certificate_or_UB_LB_transferred=False,P2_calls=0))
    with patch.object(binder,'bind',bind),patch.object(a_cache,'load_current_date_physical_cache',cached):
        yield namespace['run']
