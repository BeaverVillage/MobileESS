import sys
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v42_may_campaign_native90.preflight import native_zero
from v44_recovery_r018.thread_policy import numerical_threads
from v44_recovery_r018.a2_checkpoint import reconstruct
with native_zero() as denied,numerical_threads(1):
    reconstruct('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt001',
        sys.argv[1])
    assert not denied
