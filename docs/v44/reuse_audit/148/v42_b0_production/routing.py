"""Isolated legacy function namespaces; only day/output/input routing changes."""
import ast
import copy
import inspect
import shutil
import types
from pathlib import Path

from v42_capacity.common import day_folder
from .authority import INPUT, HOLDOUT, read, record
from v42_orchestrator.ledger import atomic


def single_day_producer(name, day, output):
    from v42_holdout.calendar_adapter import producer
    module = producer(name, OUT=output, PRIOR=INPUT)
    if name == 'v42_capacity.planning':
        # Same scientific loop body; select one frozen May date for worker isolation.
        original = ast.parse(inspect.getsource(module.main))
        for node in ast.walk(original):
            if isinstance(node, ast.For) and ast.unparse(node.iter) == 'range(1, 31)':
                node.iter = ast.Tuple(elts=[ast.Constant(int(day[-2:]))], ctx=ast.Load())
        # inspect reads original April source. Reapply the reviewed calendar transform.
        from v42_holdout.calendar_adapter import Calendar
        changed = Calendar().visit(original)
        ast.fix_missing_locations(changed)
        exec(compile(changed, module.__file__, 'exec'), module.__dict__)
        selected = [n for n in ast.walk(changed) if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == 'd']
        if len(selected) != 1 or ast.unparse(selected[0].iter) != f'({int(day[-2:])},)':
            raise ValueError('Single-day planning routing drift')
    return module


def planning(day, output):
    single_day_producer('v42_capacity.planning', day, output).main()
    import v42_holdout.planning as frozen
    namespace = dict(frozen.generate.__globals__, OUT=output, INPUT=INPUT,
                     destination=lambda d: output / 'BUNDLE' / day_folder(d))
    generate = types.FunctionType(frozen.generate.__code__, namespace)
    generate(day)
    folder = output / 'BUNDLE' / day_folder(day)
    return folder


def actual(day, output, planning_folder, truth_folder):
    folder = output / 'BUNDLE' / day_folder(day)
    folder.mkdir(parents=True)
    shutil.copyfile(planning_folder / 'REFERENCE.json', folder / 'REFERENCE.json')
    for name in ('ACTUAL_REALIZED_SERVICE_AUTHORITY_LEDGER.csv', 'ACTUAL_REALIZED_SERVICE_AUTHORITY_AUDIT.json'):
        shutil.copyfile(truth_folder / name, output / name)
    replay = single_day_producer('v42_capacity.replay', day, output)
    replay.main(days=[int(day[-2:])])
    return folder


def fresh(day, output, planning_folder, actual_folder, run_id):
    from v42_holdout.actual import adapted_day
    from v42_holdout.common import BASE as OLD_BASE
    import v42_regcontrol.runner as frozen
    function = adapted_day()
    # This one path is an independently accepted Actual output, not a Planning file.
    source = ast.parse(inspect.getsource(frozen.run_day))
    original_loop = next(n for n in ast.walk(source) if isinstance(n, ast.For) and ast.unparse(n.iter) == 'range(96)')
    # Reconstruct the already reviewed May routing, then add only physical-file routing.
    node = copy.deepcopy(source.body[0])
    del node.body[3]
    class Route(ast.NodeTransformer):
        def visit_Constant(self, n):
            if n.value == 'APRIL_D1_VOLTAGE_RESPONSE.npz':
                return ast.copy_location(ast.Constant('MAY_D1_VOLTAGE_RESPONSE.npz'), n)
            return n
        def visit_If(self, n):
            if ast.unparse(n.test) == 'dest.exists()':
                n.test = ast.parse("(dest/'V_ACTUAL_AC.npz').exists()", mode='eval').body
            return self.generic_visit(n)
        def visit_Call(self, n):
            self.generic_visit(n)
            if isinstance(n.func, ast.Attribute) and ast.unparse(n.func) == 'dest.mkdir':
                n.keywords.append(ast.keyword(arg='exist_ok', value=ast.Constant(True)))
            for keyword in n.keywords:
                if keyword.arg == 'raw_May_rows_loaded':
                    keyword.value = ast.Constant(True)
            return n
        def visit_Assign(self, n):
            if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'physical_path':
                if ast.unparse(n.value) != "old / 'ACTUAL_PHYSICAL.npz'":
                    raise ValueError('Actual physical path routing drift')
                n.value = ast.Name(id='BOUND_ACTUAL_PHYSICAL', ctx=ast.Load())
            return self.generic_visit(n)
    node = Route().visit(node)
    ast.fix_missing_locations(node)
    new_loop = next(n for n in ast.walk(node) if isinstance(n, ast.For) and ast.unparse(n.iter) == 'range(96)')
    if ast.dump(new_loop) != ast.dump(original_loop):
        raise ValueError('Existing B0 native scientific slot-loop AST changed')
    output.mkdir(parents=True, exist_ok=True)
    atomic(output / 'PREREGISTRATION.json', dict(exact_base=OLD_BASE, production_run_id=run_id,
        execution_base='0760b8f56398344e55d938b175d88761d19ff657',
        inherited_contract_source=record(HOLDOUT / 'PREREGISTRATION.json')))
    namespace = dict(function.__globals__, OUT=output, OLD=planning_folder.parents[1], INPUT=INPUT,
                     BOUND_ACTUAL_PHYSICAL=actual_folder / 'ACTUAL_PHYSICAL.npz')
    exec(compile(ast.Module(body=[node], type_ignores=[]), inspect.getfile(frozen), 'exec'), namespace)
    result = namespace['run_day'](day)
    atomic(output / 'ROUTING_AUDIT.json', dict(PASS=True, scientific_96_slot_loop_AST_identical=True,
        only_calendar_output_and_accepted_Actual_physical_path_routed=True,
        source=record(Path(inspect.getfile(frozen)))))
    return output / 'BUNDLE' / day_folder(day), result
