from pathlib import Path
import sys
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44_recovery_r018.operations import OPS
for old,new in [('collect_watchdog_r017.py','collect_watchdog_r018.py'),('audit_active_revision_r008.py','audit_active_revision_r009.py')]:
    source=(OPS/old).read_text(encoding='utf8')
    source=source.replace("'v44_recovery_r017')","'v44_recovery_r017','v44_recovery_r018')")
    source=source.replace('V44_30MIN_WATCHDOG_R017','V44_30MIN_WATCHDOG_R018')
    source=source.replace('AND_R017_SAFE_HANDOVER','AND_R018_CHECKPOINT_RECOVERY')
    target=OPS/new;assert not target.exists();target.write_text(source,encoding='utf8',newline='\n')
    compile(source,str(target),'exec')
print('R018_COLLECTOR_AND_AUDITOR_READY')
