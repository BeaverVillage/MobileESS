"""Independent AST audit; never rewrites historical validation provenance."""
import ast,copy,json,sys
from pathlib import Path
HERE=Path(__file__).parent
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT))
from v2_add_preflight.stage_common import read,record
from v2_add_preflight.stage_campaign import source_files
from v2_add_preflight.prestart_execution import atomic

def equivalent_budget():
    before=ast.parse((HERE/'stage_budget.before.py').read_text(encoding='utf8'))
    after=ast.parse((ROOT/'v2_add_preflight/stage_budget.py').read_text(encoding='utf8'))
    class Undo(ast.NodeTransformer):
        def visit_Import(self,node):
            node.names=[v for v in node.names if v.name!='math'];return node
        def visit_ImportFrom(self,node):
            if node.module=='v42_may_campaign_native90.budget' and node.names[0].name=='DateBudget':
                # a_budget already had this import before the repair.
                if self.inside_scope:return None
            return node
        inside_scope=False
        def visit_FunctionDef(self,node):
            if node.name in ('persistable_bound_diagnostics','persist_date'):return None
            old=self.inside_scope
            if node.name=='scope':self.inside_scope=True
            self.generic_visit(node);self.inside_scope=old;return node
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name) and t.id=='original_date' for t in node.targets):return None
            return self.generic_visit(node)
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='persistable_bound_diagnostics':return None
            return self.generic_visit(node)
        def visit_With(self,node):
            node.items=[v for v in node.items if not (isinstance(v.context_expr,ast.Call) and ast.unparse(v.context_expr)=="patch.object(DateBudget, 'persist', persist_date)")]
            return self.generic_visit(node)
    assert ast.dump(before,include_attributes=False)==ast.dump(Undo().visit(after),include_attributes=False),'NON_TELEMETRY_BUDGET_CHANGE'

def equivalent_gate():
    before=ast.parse((HERE/'stage_optimization_gate.before.py').read_text(encoding='utf8'))
    after=ast.parse((ROOT/'v2_add_preflight/stage_optimization_gate.py').read_text(encoding='utf8'))
    class Undo(ast.NodeTransformer):
        def visit_FunctionDef(self,node):
            if node.name=='replay_source_compatibility':return None
            return self.generic_visit(node)
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name) and t.id=='compatibility' for t in node.targets):return None
            return self.generic_visit(node)
        def visit_If(self,node):
            if ast.unparse(node.test)=='compatibility.exists()':return None
            if ast.unparse(node.test)=='not replay_source_compatibility(value, entered, work)':
                node.test=ast.parse("value.get('validation_source_files')!=entered or value.get('validation_source_snapshot_unchanged') is not True",mode='eval').body
            return self.generic_visit(node)
    assert ast.dump(before,include_attributes=False)==ast.dump(Undo().visit(after),include_attributes=False),'UNEXPECTED_GATE_CHANGE'

if __name__=='__main__':
    equivalent_budget();equivalent_gate()
    previous=read(HERE/'FROZEN_ADAPTER_SOURCE_SET.json')['source_files'];current=source_files()
    a={v['path']:v for v in previous};b={v['path']:v for v in current}
    assert a.keys()==b.keys(),'SOURCE_PATH_SET_CHANGED'
    changed=[p for p in a if a[p]!=b[p]]
    assert sorted(Path(p).name for p in changed)==['stage_budget.py','stage_optimization_gate.py']
    for name in ('stage_budget','stage_optimization_gate'):
        expected=next(v for v in previous if Path(v['path']).name==name+'.py')
        raw=record(HERE/(name+'.before.py'))
        assert (raw['sha256'],raw['bytes'])==(expected['sha256'],expected['bytes'])
    result=dict(PASS=True,before_source_files=previous,after_source_files=current,
        budget_AST_after_removing_only_bound_telemetry_patch_equals_before=True,
        gate_AST_after_removing_only_explicit_compatibility_check_equals_before=True,
        all_other_scientific_source_bytes_unchanged=True,
        exact_changed_paths=changed,
        diagnostic_only_change='Nonfinite Native_BestBd -> null plus original diagnostic spelling; Runtime untouched',
        old_replay_reports_not_rewritten=True,current_source_real_numerical_canaries_still_required=True,
        audit_artifacts=[record(__file__),record(HERE/'stage_budget.before.py'),record(HERE/'stage_optimization_gate.before.py'),
                         record(HERE/'FROZEN_ADAPTER_SOURCE_SET.json'),*[record(p) for p in changed]])
    atomic(HERE/'SOURCE_COMPATIBILITY.json',result)
    frozen=read(HERE/'FROZEN_ADAPTER_SOURCE_SET.json');frozen['source_files']=current
    frozen['IO_only_repair_audit']=record(HERE/'SOURCE_COMPATIBILITY.json')
    atomic(HERE.parent/'FROZEN_ADAPTER_SOURCE_SET.json',frozen)
    print('AST_AUDIT_PASS',len(current),'UNCHANGED_SCIENTIFIC_MODEL; TWO_AUDITED_IO_AND_PROOF_MODULES')
