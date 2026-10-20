from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025b
from v44.common import read,atomic
from v44_recovery_r025b.restore_active_checkpoint import adaptive_checkpoint
c=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
output=Path('D:/MobileESS_V44/development/r025b/current_continuation');p=read(output/'ADMISSION.json')
receipt,sources=adaptive_checkpoint(c/'2025-05-02/B3/attempt007',output)
p['adaptive_parent']=receipt;p['sources']=list({r['path']:r for r in p['sources']+sources}.values())
atomic(output/'ADMISSION.json',p);atomic(c/'AUTONOMOUS_RECOVERY/R025B_CURRENT_CONTINUATION.json',p)
print(dict(PASS=True,adaptive_parent=receipt['path']))
