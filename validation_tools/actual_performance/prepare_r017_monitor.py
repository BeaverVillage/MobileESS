"""New read-only collectors; preserve every previous collector and receipt."""
from pathlib import Path
import sys
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44_recovery_r017.operations import OPS

source=(OPS/'collect_watchdog_r016.py').read_text(encoding='utf8')
source=source.replace("('v44_recovery_r015','v44_recovery_r016')","('v44_recovery_r015','v44_recovery_r016','v44_recovery_r017')")
source=source.replace("schema='V44_30MIN_WATCHDOG_R016'","schema='V44_30MIN_WATCHDOG_R017'")
target=OPS/'collect_watchdog_r017.py';assert not target.exists();target.write_text(source,encoding='utf8',newline='\n')

source=(OPS/'audit_active_revision_r007.py').read_text(encoding='utf8')
source=source.replace("'v44_recovery_r016')","'v44_recovery_r016','v44_recovery_r017')")
source=source.replace("lease=read(ROOT/'COORDINATOR_LEASE.json');process=psutil.Process(lease['pid'])\nassert abs(process.create_time()-lease['process_created'])<.001\nmanual_entry='v44_recovery_r015_user_actual_r001' in process.cmdline()",
"from v44.locks import alive\nlease=read(ROOT/'COORDINATOR_LEASE.json');process=psutil.Process(lease['pid']) if alive(lease) else None\ncommand=process.cmdline() if process is not None else []\nif process is None:assert handoff.get('pending_revision'),'NO_LIVE_OWNER_OR_AUTHORIZED_PENDING_HANDOVER'\nmanual_entry='v44_recovery_r015_user_actual_r001' in command")
source=source.replace("else:\n    assert revision+'.operations' in process.cmdline()","elif process is not None:\n    assert revision+'.operations' in command")
source=source.replace('actual_coordinator_command=process.cmdline()','actual_coordinator_command=command,coordinator_alive=process is not None')
source=source.replace("value['additional_performance_validation']=record(OPS/('R016_CHANGE_AND_VALIDATION.json' if revision=='v44_recovery_r016' else 'R015_CHANGE_AND_VALIDATION.json'))",
"value['additional_performance_validation']=record(OPS/(revision.rsplit('_',1)[1].upper()+'_CHANGE_AND_VALIDATION.json'))")
source=source.replace("if pending=='v44_recovery_r016':value['pending_performance_validation']=record(OPS/'R016_CHANGE_AND_VALIDATION.json')",
"if pending:value['pending_performance_validation']=record(OPS/(pending.rsplit('_',1)[1].upper()+'_CHANGE_AND_VALIDATION.json'))")
source=source.replace('ACTIVE_SOURCE_OS_C1_FRESH_AUDIT_AND_R016_SAFE_HANDOVER','ACTIVE_SOURCE_OS_C1_FRESH_AUDIT_AND_R017_SAFE_HANDOVER')
target=OPS/'audit_active_revision_r008.py';assert not target.exists();target.write_text(source,encoding='utf8',newline='\n')
compile(source,str(target),'exec')
print('R017_MONITOR_TOOLS_CREATED')
