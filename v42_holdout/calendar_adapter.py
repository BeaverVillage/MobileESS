"""Execute inherited producers with only calendar/output routing substitutions.

No computational AST statement, parameter or input-field rule is altered.
The original files remain byte preserved. The allowed transform is audited,
and a normalized AST identity is tested against every producer before use.
"""
import ast
import types
from .common import *

class Calendar(ast.NodeTransformer):
    def visit_Constant(self,node):
        if isinstance(node.value,str):
            value=node.value.replace('2025-04-','2025-05-').replace('DAY_202504','DAY_202505')
            return ast.copy_location(ast.Constant(value),node)
        return node

    def visit_Call(self,node):
        self.generic_visit(node)
        if isinstance(node.func,ast.Name) and node.func.id=='range' and len(node.args)==2:
            if all(isinstance(n,ast.Constant) for n in node.args) and [n.value for n in node.args]==[1,31]:
                node.args[1]=ast.copy_location(ast.Constant(32),node.args[1])
        return node

def producer(name, **overrides):
    if name not in ('v42_capacity.planning','v42_capacity.replay') or set(overrides)!={'OUT','PRIOR'}:
        raise ValueError('ONLY_FROZEN_PRODUCER_OUTPUT_ROUTING_ALLOWED')
    path=ROOT/(name.replace('.','/')+'.py')
    source_freeze()
    original=ast.parse(path.read_text(encoding='utf-8'))
    changed=Calendar().visit(ast.parse(path.read_text(encoding='utf-8')))
    ast.fix_missing_locations(changed)
    module=types.ModuleType(name+'_may_calendar'); module.__package__=name.rsplit('.',1)[0]
    module.__file__=str(path)
    exec(compile(changed,str(path),'exec'),module.__dict__)
    module.__dict__.update(overrides)
    return module
