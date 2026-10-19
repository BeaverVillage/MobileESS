from pathlib import Path
root=Path(__file__).resolve().parents[2]
for path in (root/'v44_recovery_r025b').glob('*.py'):
    text=path.read_text(encoding='utf-8').replace('R025B_NATIVE60_PHASE400_UB','R025B_NATIVE60_PHASE1000_UB')
    text=text.replace('Phase_I_native_ceiling=400.','Phase_I_native_ceiling=1000.').replace('Phase_I_native_seconds=400.','Phase_I_native_seconds=1000.')
    text=text.replace("Native_start=read(OPS/'R025_CURRENT_A2_STOPPED.json')['Native_account']['measured']","Native_start=read(OPS/'R025B_CURRENT_CONTINUATION.json')['inherited_Native_seconds']")
    text=text.replace('Native3600 Phase400','Native3600 Phase1000').replace('Native3600, Phase I cutoff400','Native3600, Phase I cutoff1000')
    path.write_text(text,encoding='utf-8')
for name in ('test_v44_recovery_r025b_bounded_policy.py','test_v44_recovery_r025b_ub_cache_owner.py'):
    path=root/'tests'/name;text=path.read_text(encoding='utf-8')
    text=text.replace('R025B_NATIVE60_PHASE400_UB','R025B_NATIVE60_PHASE1000_UB')
    if name.endswith('bounded_policy.py'):
        text=text.replace('399.','999.').replace('400.','1000.').replace('3200.','2600.')
        text=text.replace('b.native_used=999.;','b.native_used=999.;b.phase_native_used=999.;')
        text=text.replace('b.native_used=1000.;','b.native_used=1000.;b.phase_native_used=1000.;')
    path.write_text(text,encoding='utf-8')
print({'PASS':True,'Phase_I_limit':1000})
