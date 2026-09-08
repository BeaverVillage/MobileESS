"""Resume unchanged daily orchestration with the scoped B3 A1 worker."""
from fast_prepare import *
from v41r4_runtime import MAY_OUT
from v41r4_b3_equivalent import HELPERS, adapt
import v41r4_campaign as original

def release():
    from dayahead.v40h.identity import manifest,verify_manifest
    base=original.release()
    source=manifest([ROOT/p for p in HELPERS]+[ROOT/'dayahead/v40g_segments/coordination.py'],ROOT)
    path=MAY_OUT/'MAY_CAMPAIGN_RELEASE_V2.json'
    if path.exists():
        value=read(path);assert value['additional_source']==source
        verify_manifest(source);return value
    regression=MAY_OUT/'A1_regression/V41R4_A1_FOCUSED_REGRESSION.json'
    assert read(regression)['status']=='PASS'
    coordinator=MAY_OUT/'A1_regression/COORDINATOR_REGRESSION.json'
    assert read(coordinator)['status']=='PASS'
    assert read(coordinator)['source']==record(ROOT/'v41r4_b3_equivalent.py')
    readback=MAY_OUT/'readback_regression/READBACK_REGRESSION.json'
    assert read(readback)['status']=='PASS' and read(readback)['source']==record(ROOT/'v41r4_readback_v2.py')
    assert read(MAY_OUT/'gate_repair/GATE_REPAIR_VERIFICATION.json')['status']=='PASS'
    value=dict(base,version='V41R4_FINAL_115_B3_A1_B1_EQUIVALENT',
        previous_release=record(MAY_OUT/'MAY_CAMPAIGN_RELEASE.json'),additional_source=source,
        A1_own_budget_seconds=1800,B3_original_M1_MF_budget_seconds=1800,
        B3_total_budget_seconds=3600,regression=record(regression),coordinator_regression=record(coordinator),
        readback_regression=record(readback),
        budget_seconds_per_policy_day={'B0':1800,'B1':1800,'B2':1800,'B3':3600},
        change_scope='B3 A1 uses B1 full optimizer with fixed M1, independent 30 minutes',
        prior_B0_B1_B2_producers_unchanged=True)
    save(path,value);return value

def main():
    bound=adapt(original.main,[("str(ROOT/'v41r4_worker.py')","str(ROOT/'v41r4_worker_v2.py')")],dict(release=release))
    return bound()

if __name__=='__main__':main()
