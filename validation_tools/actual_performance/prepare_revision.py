"""Create a separate r016 package; never edit the running sealed r015."""
from pathlib import Path

root=Path('D:/v44_may01_07_prepare_20261016')
source=root/'v44_recovery_r015';target=root/'v44_recovery_r016'
assert target.parent.resolve()==root.resolve() and not target.exists()
target.mkdir()
for path in source.glob('*.py'):
    body=path.read_text(encoding='utf8').replace('r015','r016').replace('R015','R016')
    (target/path.name).write_text(body,encoding='utf8')
(target/'b3_copy.py').write_bytes((root/'v44_actual_performance/memo_copy.py').read_bytes())
path=target/'current_ac_performance.py';body=path.read_text(encoding='utf8')
old="    if getattr(oracle,'arm',None)=='B1':\n        from .physical_copy import clone_physical as deepcopy\n"
assert body.count(old)==1
body=body.replace(old,old+"    elif getattr(oracle,'arm',None)=='B3':\n        from .b3_copy import clone_physical as deepcopy\n")
old="                stack.enter_context(patch.object(ac,'deepcopy',clone_physical))\n"
assert body.count(old)==1
body=body.replace(old,old+"            elif oracle is not None and getattr(oracle,'arm',None)=='B3':\n                from .b3_copy import clone_physical as b3_clone\n                stack.enter_context(patch.object(ac,'deepcopy',b3_clone))\n")
body=body.replace("if request['arm'] not in ('B1','B3'):return False","if request['arm'] not in ('B0','B1','B3'):return False")
old="        if not require_policy(oracle) or getattr(oracle,'_independent_fresh',False):return original(oracle,rows)"
new="""        if not require_policy(oracle):return original(oracle,rows)
        if getattr(oracle,'_independent_fresh',False):
            from .fresh_performance import live_fresh_scope
            with live_fresh_scope(oracle):return original(oracle,rows)"""
assert body.count(old)==1;body=body.replace(old,new)
path.write_text(body,encoding='utf8')
path=target/'operations.py';body=path.read_text(encoding='utf8')
body=body.replace("performance_scope='SUBSEQUENT_B1_B3_ONLY_PROTECT_CURRENT_MAY01_B1'","performance_scope='B0_B1_B3_AFTER_CURRENT_MAY01_B3_ATTEMPT003_ENTIRE_CASE_FINISHES'")
body=body.replace("Independent_Fresh='FULL_ORIGINAL_PATH_FAST_SCOPE_BYPASSED'","Independent_Fresh='FULL_INDEPENDENT_MEASUREMENTS_LIVE_PROPERTY_READS_PURE_EXPECTED_COPY_NO_HISTORY_OR_BANK_REUSE'")
body=body.replace("physical_copy='B1_ONLY_EXACT_BUILTIN_GRAPH_CLONE_PRESERVE_ALIAS_CYCLE_CUSTOM_DEEPCOPY_FALLBACK_B3_RETAINS_R009_COPY'","physical_copy='B1_UNCHANGED_R015_GRAPH_CLONE_B3_VERIFIED_C_PICKLE_GRAPH_CLONE_CUSTOM_DEEPCOPY_FALLBACK'")
body=body.replace("user_instruction='Keep current May01 B1 unchanged to completion; accelerate subsequent B1/B3 Actual with live ordinal property reads; preserve every physics check, TIME solve, Raw and budgets; retain validated A2 cache recovery'","user_instruction='Apply r016 improvements to B0, B1 and B3 after current May01 B3 attempt003 Actual and independent Fresh naturally finish. Preserve every physical solve and complete independent Fresh measurement, Raw bytes, source identities, constraints, objectives, tolerances and Native budgets.'")
path.write_text(body,encoding='utf8')
for path in (root/'tests').glob('test_v44_recovery_r015*.py'):
    name=path.name.replace('r015','r016');dest=path.with_name(name);assert not dest.exists()
    dest.write_text(path.read_text(encoding='utf8').replace('r015','r016').replace('R015','R016'),encoding='utf8')
print('Created',target,'and ported regression tests')
