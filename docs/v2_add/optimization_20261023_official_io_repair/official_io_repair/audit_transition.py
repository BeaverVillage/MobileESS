"""Audit only directory routing, Windows JSON IO, and their provenance."""
import ast,sys,json,copy
from pathlib import Path
HERE=Path(__file__).parent;H=HERE.parent
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT))
from v2_add_preflight.stage_common import read,record
from v2_add_preflight.stage_campaign import source_files
from v2_add_preflight.prestart_execution import atomic

def parse(p):return ast.parse(Path(p).read_text(encoding='utf8'))
def same(a,b):assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False),'UNAPPROVED_NON_IO_AST_CHANGE'
before_a=parse(HERE/'stage_a_casefactory.py');after_a=parse(ROOT/'v2_add_preflight/stage_a_casefactory.py')
run=next(n for n in after_a.body if isinstance(n,ast.FunctionDef) and n.name=='run')
withnode=run.body[0];assert ast.unparse(withnode.body[0]).startswith('source_request = dict(request, output=')
assert ast.unparse(withnode.body[1])=='return original(source_request, budget, progress)'
withnode.body=ast.parse('return original(request,budget,progress)').body;same(before_a,after_a)
before_m=parse(HERE/'stage_m_case.py');after_m=parse(ROOT/'v2_add_preflight/stage_m_case.py')
class UndoM(ast.NodeTransformer):
    def visit_Import(self,n):n.names=[v for v in n.names if v.name!='os'];return n
    def visit_FunctionDef(self,n):
        if n.name=='source_json_writer':return None
        return self.generic_visit(n)
    def visit_For(self,n):
        if (ast.unparse(n.target)=='mod' and ast.unparse(n.iter)=='modules.values()'
                and len(n.body)==1 and ast.unparse(n.body[0]).startswith("if hasattr(mod, '_write')")):return None
        return self.generic_visit(n)
same(before_m,UndoM().visit(after_m))
before_g=parse(HERE/'stage_optimization_gate.py');after_g=parse(ROOT/'v2_add_preflight/stage_optimization_gate.py')
old_helper=next(n for n in before_g.body if isinstance(n,ast.FunctionDef) and n.name=='replay_source_compatibility')
after_g.body=[copy.deepcopy(old_helper) if isinstance(n,ast.FunctionDef) and n.name=='replay_source_compatibility' else n for n in after_g.body]
for n in ast.walk(after_g):
    if isinstance(n,ast.Try):
        for i,part in enumerate(n.body):
            if isinstance(part,ast.Assign) and 'OFFICIAL_IO_REPAIR_20261023/SOURCE_COMPATIBILITY.json' in ast.unparse(part):
                assert ast.unparse(n.body[i+1]).startswith('if compatibility.exists():');del n.body[i:i+2];break
same(before_g,after_g)
old=read(HERE/'FROZEN_ADAPTER_SOURCE_SET.json')['source_files'];new=source_files()
a={v['path']:v for v in old};b={v['path']:v for v in new};assert a.keys()==b.keys()
changed=[p for p in a if a[p]!=b[p]]
assert sorted(Path(p).name for p in changed)==['stage_a_casefactory.py','stage_m_case.py','stage_optimization_gate.py']
for p in changed:
    saved=record(HERE/Path(p).name);assert (saved['sha256'],saved['bytes'])==(a[p]['sha256'],a[p]['bytes'])
budget_audit=read(H/'BOUND_JSON_REPAIR_20261023/SOURCE_COMPATIBILITY.json')
assert budget_audit['PASS'] and budget_audit['after_source_files']==old
assert budget_audit['budget_AST_after_removing_only_bound_telemetry_patch_equals_before']
atomic(HERE/'SOURCE_COMPATIBILITY.json',dict(PASS=True,before_source_files=old,
    compatible_previous_source_snapshots=[old,budget_audit['before_source_files']],after_source_files=new,
    budget_AST_after_removing_only_bound_telemetry_patch_equals_before=True,
    all_other_scientific_source_bytes_unchanged=True,
    A_prepare_AST_identical_after_removing_only_SOURCE_directory_routing=True,
    M_source_AST_identical_after_removing_only_Win32_JSON_writer_wrapper=True,
    gate_AST_identical_except_explicit_transitive_IO_provenance=True,
    exact_changed_paths=changed,old_reports_and_results_not_relabelled=True,
    current_source_real_numerical_canaries_still_required=True,
    audit_artifacts=[record(__file__),record(HERE/'FROZEN_ADAPTER_SOURCE_SET.json'),
        record(H/'BOUND_JSON_REPAIR_20261023/SOURCE_COMPATIBILITY.json'),
        *[record(HERE/Path(p).name) for p in changed],*[record(p) for p in changed]]))
frozen=read(HERE/'FROZEN_ADAPTER_SOURCE_SET.json');frozen['source_files']=new
frozen['official_IO_repair_audit']=record(HERE/'SOURCE_COMPATIBILITY.json')
atomic(H/'FROZEN_ADAPTER_SOURCE_SET.json',frozen)
print('OFFICIAL_IO_ONLY_AST_AND_ALL_OTHER_SOURCE_BYTES_PASS',len(new))
