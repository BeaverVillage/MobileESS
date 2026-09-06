import sys,json,pathlib,pytest
repo=pathlib.Path(r'C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt')
base=pathlib.Path.cwd(); out=repo/'dayahead/artifacts/v40i_authority_electrical_closure/prechange_tests'
sys.path.insert(0,str(base))
class SameExistingFixtures:
 def pytest_collection_modifyitems(self,items):
  for item in items:
   m=item.module
   if hasattr(m,'REPO'):m.REPO=repo
   if hasattr(m,'audit') and hasattr(m.audit,'REPO'):m.audit.REPO=repo
 def pytest_sessionfinish(self,session,exitstatus):
  (out/'same_fixture_import_proof.json').write_text(json.dumps({'baseline_source_root':str(base),'fixture_root':str(repo),'I_imports':[k for k in sys.modules if k.startswith('dayahead.v40i')],'source_files':{k:getattr(v,'__file__',None) for k,v in sys.modules.items() if k.startswith(('dayahead.v39e','dayahead.tools.audit_v39h'))}},indent=2),encoding='utf-8')
nodes=['tests/dayahead/test_v39h_terminal_audit.py::TerminalAuditTests::test_gate_live_hold_and_unaffected',
 'tests/dayahead/test_v39h_production_refreeze.py::SelectiveTests::test_frozen_production_loader_consumes_repaired_schedule',
 'tests/dayahead/test_v39h_production_refreeze.py::SelectiveTests::test_may01_05_exact_result_reuse_and_immutable_files']
raise SystemExit(pytest.main(nodes+['-q','--tb=short','--junitxml='+str(out/'same_preexisting_fixtures.xml')],plugins=[SameExistingFixtures()]))

