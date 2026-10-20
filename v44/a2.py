"""Dated A2 metadata adapter over the unchanged PR189 equations/acceptance."""
import ast
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch

from .config import require_day
from .stages import require_m1
from .frozen.v43_a2 import adapter as frozen


def routed_function(module,name,namespace,mess,day):
    """Only replace the explicit date gate; no selected jobs or math constants."""
    function,changes=frozen.routed_function(module,name,namespace,mess)
    if name!='_paths':return function,changes
    tree=frozen.source_tree(module,name)
    # _paths in PR189 accepts all May dates. The V44 guard is explicitly narrower (seven days).
    tree=deepcopy(tree)
    class Labels(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str) and node.value in frozen.LABELS:node.value=frozen.LABELS[node.value]
            return node
    tree=Labels().visit(tree)
    tree.body.insert(0,ast.parse("_v44_require_day(request['day'])").body[0])
    unit=ast.Module(body=[tree],type_ignores=[]);ast.fix_missing_locations(unit)
    namespace['_v44_require_day']=require_day
    exec(compile(unit,module.__file__,'exec'),namespace)
    return namespace[name],dict(changes,V44_dated_guard=day)


@contextmanager
def scope(request,m1_result):
    day=require_day(request['day']);require_m1(m1_result,day)
    original=frozen.routed_function
    def route(module,name,namespace,mess):
        # Avoid recursive substitution while compiling the original selective route.
        with patch.object(frozen,'routed_function',original):
            return routed_function(module,name,namespace,mess,day)
    with patch.object(frozen,'require_m1',lambda result:require_m1(result,day)),patch.object(frozen,'routed_function',route):
        # V43's cache helper is May01/Golden002-specific. Route only that IO
        # verifier to the dated accepted-A1 cache; keep its original math body.
        from .daily import load_current_date_physical_cache
        import v43_followup.physical_cache as cache
        with patch.object(cache,'load_current_date_physical_cache',load_current_date_physical_cache):
            with frozen.scope(request,m1_result) as run:yield run
