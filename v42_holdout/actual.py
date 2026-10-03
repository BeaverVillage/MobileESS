"""Route the exact PR128 Actual solve loop to sealed May inputs.

Calendar/output guards are adapted in an isolated function namespace; the
physical input application and solve loop AST is identical to PR128. No
historical frozen-tap backend is imported or invoked.
"""
import ast
import copy
import inspect
from .common import *
import v42_regcontrol.runner as frozen

def adapted_day():
    original=ast.parse(inspect.getsource(frozen.run_day)).body[0]
    node=copy.deepcopy(original)
    guard=node.body[3]
    if not isinstance(guard,ast.If) or 'APRIL_15_16_30_DIAGNOSTIC.json' not in ast.unparse(guard):
        raise ValueError('FROZEN_RUNNER_GUARD_SCHEMA_DRIFT')
    del node.body[3]  # The new caller requires all 31 May Planning freezes instead.
    class Routing(ast.NodeTransformer):
        def visit_Constant(self,n):
            if n.value=='APRIL_D1_VOLTAGE_RESPONSE.npz':
                return ast.copy_location(ast.Constant('MAY_D1_VOLTAGE_RESPONSE.npz'),n)
            return n
        def visit_If(self,n):
            if ast.unparse(n.test)=='dest.exists()':
                n.test=ast.parse("(dest/'V_ACTUAL_AC.npz').exists()",mode='eval').body
            return self.generic_visit(n)
        def visit_Call(self,n):
            self.generic_visit(n)
            if isinstance(n.func,ast.Attribute) and ast.unparse(n.func)=='dest.mkdir':
                n.keywords.append(ast.keyword(arg='exist_ok',value=ast.Constant(True)))
            for keyword in n.keywords:
                if keyword.arg=='raw_May_rows_loaded': keyword.value=ast.Constant(True)
            return n
    node=Routing().visit(node); ast.fix_missing_locations(node)
    # No allowed routing operation may change a scientific slot computation.
    old_loop=next(n for n in ast.walk(original) if isinstance(n,ast.For) and ast.unparse(n.iter)=='range(96)')
    new_loop=next(n for n in ast.walk(node) if isinstance(n,ast.For) and ast.unparse(n.iter)=='range(96)')
    if ast.dump(old_loop)!=ast.dump(new_loop): raise ValueError('PR128_ACTUAL_PHYSICAL_LOOP_DRIFT')
    namespace=dict(vars(frozen),OUT=OUT,OLD=OUT,INPUT=INPUT,BASE=BASE,require_april=require_may)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(ROOT/'v42_regcontrol/runner.py'),'exec'),namespace)
    return namespace['run_day']

def main():
    source_freeze(); plan=read(OUT/'ALL_MAY_PLANNING_FROZEN.json');physical=read(OUT/'ACTUAL_PHYSICAL_FREEZE.json')
    if not read(OUT/'D1_FORECAST_VINTAGE_CAUSALITY.json')['PASS']:raise ValueError('D1_VINTAGE_GATE_REQUIRED')
    if not plan['PASS'] or len(physical['days'])!=31: raise ValueError('MAY_ALL_FREEZES_REQUIRED')
    for row in physical['days']:
        resolve(row['physical']);resolve(row['Planning_freeze'])
    day_runner=adapted_day(); results=[]
    for day in DAYS:
        results.append(day_runner(day))
        write(OUT,'MAY_ACTUAL_PROGRESS.json',dict(completed_days=len(results),days=results))
    write(OUT,'MAY_CURRENT_ACTUAL_IMPLEMENTATION.json',dict(source=record(ROOT/'v42_regcontrol/runner.py'),
        physical_slot_loop_AST_exactly_PR128=True,autonomous_session=record(ROOT/'v42_regcontrol/session.py'),
        isolated_namespace_no_existing_modules_modified=True,calendar_routing_only=True,
        inherited_April_diagnostic_guard_replaced_by_all_31_May_freezes=True,
        Planning_tap_cap_replay=False,Actual_PQ_repair=0,Actual_reoptimization=0,
        source_parameters_changed=False,capacitor_fixed_ON=True,CapControl_count=0))

if __name__=='__main__': main()
