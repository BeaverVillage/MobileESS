"""Read live monitor and original A2 evidence without changing campaign state."""
from pathlib import Path
from fractions import Fraction
import sys,json,urllib.request
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,atomic,now
base=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt001/A2')
stage=read(base/'NATIVE_RUNTIME_LEDGER.json');trace=read(base/'OUTPUT/PHASE_I_TRACE.json')
with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=15) as response:status=json.load(response)
out=Path('D:/MobileESS_V44/development/monitor_phi_display_20261017');out.mkdir(exist_ok=True)
atomic(out/'LIVE_BEFORE.json',status)
last=trace['trajectory'][-1]
print(json.dumps(dict(UTC=now(),last_Phase_I=last,exact_fraction_decimal=float(Fraction(last['exact_Phi'])),
    Native_seconds=stage.get('measured_Native_Runtime'),Native_cap=stage.get('Native_ceiling_seconds'),
    inflight=stage.get('inflight'),monitor={k:v for k,v in status.items() if k in ('stage','status','build','phase','worker','run_id')},
    evidence_directory=str(out)),ensure_ascii=False))
