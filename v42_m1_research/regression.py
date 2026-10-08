"""Replay integration receipts into new research outputs; preserve old evidence."""
from time import perf_counter
from unittest.mock import patch
from .case import REPORTS
from v42_unified.audit import write

def run():
    from v42_unified import mess_replay, replay, delivery
    target=REPORTS/'INTEGRATION_REGRESSION'
    target.mkdir(parents=True,exist_ok=True)
    start=perf_counter()
    with patch.object(mess_replay,'REPORTS',target), patch.object(replay,'REPORTS',target):
        m=mess_replay.run()
        a,handoff,payload=replay.aidc_replay()
    preserved=delivery.verify_preservation()
    result=dict(PASS=bool(m['PASS'] and a['PASS'] and preserved['PASS']),
        native_optimize_calls=0, original_integration_receipts_overwritten=False,
        historical_May01_replay=m, May12_P1_only_replay=a,
        source_preservation=preserved,wall_seconds=perf_counter()-start,
        May01_result_transferred_to_May12=False)
    write(REPORTS/'INTEGRATION_REGRESSION.json',result)
    print('INTEGRATION_REGRESSION',result['PASS'],result['wall_seconds'])
    return result

if __name__=='__main__':run()
