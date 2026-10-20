from pathlib import Path
ops=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY')
source=ops/'audit_active_revision_r006.py';target=ops/'audit_active_revision_r007.py'
assert not target.exists()
body=source.read_text(encoding='utf8')
assert body.count("'v44_recovery_r015')")==2
body=body.replace("'v44_recovery_r015')","'v44_recovery_r015','v44_recovery_r016')")
old="value['additional_performance_validation']=record(OPS/'R015_CHANGE_AND_VALIDATION.json')"
assert body.count(old)==1
body=body.replace(old,"value['additional_performance_validation']=record(OPS/('R016_CHANGE_AND_VALIDATION.json' if revision=='v44_recovery_r016' else 'R015_CHANGE_AND_VALIDATION.json'))\nif pending=='v44_recovery_r016':value['pending_performance_validation']=record(OPS/'R016_CHANGE_AND_VALIDATION.json')")
body=body.replace('ACTIVE_SOURCE_OS_C1_FRESH_AUDIT_AND_R015_SAFE_HANDOVER','ACTIVE_SOURCE_OS_C1_FRESH_AUDIT_AND_R016_SAFE_HANDOVER')
target.write_text(body,encoding='utf8')
