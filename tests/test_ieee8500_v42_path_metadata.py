"""Real original source reachability regression, with no DSS context or solve."""
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from ieee8500_v42.correct_path_metadata import static_original_graph


def _source_topology_function():
    # Exercise the exact production helper without importing its unrelated DSS
    # backend. A static metadata regression must not initialize that backend.
    path=Path(__file__).resolve().parents[1]/'ieee8500_v42/sensitivity.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='topology_paths')
    namespace={}
    exec(compile(ast.Module(body=[helper],type_ignores=[]),str(path),'exec'),namespace)
    return namespace['topology_paths']


topology_paths=_source_topology_function()


class PathMetadataTests(unittest.TestCase):
    def test_source_reactor_reaches_all_original_buses_with_inventory_omission(self):
        expected,inventory,reactors,_=static_original_graph()
        self.assertNotIn('reactors',inventory)
        selected=[reactors[0]]
        def select(name):selected[0]=next(r for r in reactors if r['element'].split('.',1)[1]==name)
        d=SimpleNamespace(Reactors=SimpleNamespace(AllNames=lambda:[r['element'].split('.',1)[1] for r in reactors],Name=select),
            CktElement=SimpleNamespace(Enabled=lambda:selected[0]['enabled'],BusNames=lambda:selected[0]['buses']))
        actual=topology_paths(SimpleNamespace(inventory=inventory,d=d))
        self.assertEqual(actual,expected)
        self.assertEqual(len(actual),4876)
        self.assertEqual(len(actual['l3234149']),37)
        self.assertEqual(len(actual['sx2748781a']),127)
        self.assertIn('reactor.hvmv_sub_hsb',actual['sx2748781a'])

    def test_missing_source_reactor_cannot_masquerade_as_zero_intersection(self):
        _,inventory,_,_=static_original_graph()
        d=SimpleNamespace(Reactors=SimpleNamespace(AllNames=lambda:[]))
        actual=topology_paths(SimpleNamespace(inventory=inventory,d=d))
        self.assertEqual(actual,{'sourcebus':set()})


if __name__=='__main__':unittest.main()
