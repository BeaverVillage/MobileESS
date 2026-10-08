"""One immutable wall deadline across every development and solve stage."""
import json
from datetime import datetime,timezone
from time import time
from .policy import OUT
from v42_a_stage_early.native import BudgetStop

def establish():
    p=OUT/'OVERNIGHT_START.json';p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():
        # Last observed clock before the newest instruction; intentionally
        # conservative because the message's exact receipt time is unavailable.
        start=datetime(2026,10,7,16,53,17,tzinfo=timezone.utc).timestamp()
        doc=dict(PASS=True,start_unix=start,deadline_unix=start+28800,budget_seconds=28800,
            start_UTC=datetime.fromtimestamp(start,timezone.utc).isoformat(),
            deadline_UTC=datetime.fromtimestamp(start+28800,timezone.utc).isoformat(),
            provenance='conservative last clock before overnight instruction; no exact message receipt timestamp available',
            immutable=True,budget_resets=0)
        with p.open('x',encoding='utf8') as f:json.dump(doc,f,indent=2);f.write('\n')
    return json.loads(p.read_text(encoding='utf8'))

class Budget:
    def __init__(self):self.record=establish();self.native_seconds=0.
    def remaining(self):
        value=self.record['deadline_unix']-time()
        if value<=0:raise BudgetStop('OVERNIGHT_IMMUTABLE_DEADLINE_REACHED')
        return value
    def charge(self,seconds):self.native_seconds+=seconds
    def accounted(self):return time()-self.record['start_unix']
