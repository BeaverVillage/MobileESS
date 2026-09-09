from mission_health import *
from fast_prepare import record
assert not any((RUN/f'2025-05-{n:02}'/'B3/dayahead/DAYAHEAD_STARTED.json').exists() for n in range(1,32))
write(OUT/'TERMINAL_A1_RETRACTION.json',dict(status='RETRACTED_BEFORE_ANY_B3_EXECUTION',
    authority='Latest user clarification: final B1 reuse A0 -> M1 -> A1 -> MF',
    unused_patch=str(ROOT/'mission_coordination.py'),active_dispatch=record(ROOT/'mission_worker.py'),
    scientific_producer_changes=0,B3_jobs_affected=0,MF_enabled=True,at=time.time()))
print('MF_RETAINED_TERMINAL_PATCH_NOT_USED')
