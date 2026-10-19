from pathlib import Path
ops=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY')
source=ops/'collect_watchdog.py';target=ops/'collect_watchdog_r016.py'
assert not target.exists()
body=source.read_text(encoding='utf8')
start=body.index('# Select the proven active handover revision')
end=body.index('from v44.locks',start)
body=body[:start]+'''import importlib
_ops=Path(__file__).parent
_revision=read(_ops/'CURRENT_HANDOFF.json')['active_revision']
if _revision not in ('v44_recovery_r015','v44_recovery_r016'):
    raise PermissionError('EXPLICIT_SUPPORTED_ACTIVE_RECOVERY_REQUIRED')
_module=importlib.import_module(_revision+'.operations')
root,OPS,PERMIT,validate,latest,states=(_module.CAMPAIGN,_module.OPS,_module.PERMIT,_module.validate,_module.latest,_module.states)
'''+body[end:]
old="auto['next_run_KST']=datetime.fromtimestamp(auto['next_run_at']/1000,timezone(timedelta(hours=9))).isoformat()"
assert body.count(old)==1
body=body.replace(old,"auto['next_run_KST']=None if auto['next_run_at'] is None else datetime.fromtimestamp(auto['next_run_at']/1000,timezone(timedelta(hours=9))).isoformat()")
body=body.replace("schema='V44_30MIN_WATCHDOG_R002'","schema='V44_30MIN_WATCHDOG_R016'")
target.write_text(body,encoding='utf8')
auditor=ops/'audit_active_revision_r007.py'
text=auditor.read_text(encoding='utf8').replace('Collector legacy r006 metadata preserved; active policy crosschecked against live coordinator identity and immutable validate().','Collector receipt metadata preserved; active policy crosschecked against live coordinator identity and immutable validate().')
auditor.write_text(text,encoding='utf8')
