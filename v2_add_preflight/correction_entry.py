"""Supported correction CLI with full frozen-input closure before any cache reuse.

Historical screen/pilot/results modules are retained byte-for-byte for provenance;
the correction workflow must use this entry point and separate output namespaces.
"""
import sys
from pathlib import Path
from .audit import ROOT,read,sha
from .correction import OUT,put

def closure():
    baseline=read(OUT/'PRESERVATION_BASELINE.json')
    mismatches=[p for p,h in baseline['tracked_sha256'].items() if sha((ROOT/p).read_bytes())!=h]
    if mismatches:raise RuntimeError('Frozen V2_add source/input/config closure changed; cache reuse blocked: '+','.join(mismatches))
    return dict(PASS=True,baseline_HEAD=baseline['PR236_HEAD'],verified_frozen_files=len(baseline['tracked_sha256']),
        coverage='All148 prior tracked source/config/input/PV roster/PV rule/MV design/initial states/route authority receipts and historical results',
        numerical_arrays='Case receipts separately bind final electrical arrays, BG arrays, controls, code and dispatch delta bytes',
        production_source_receipts='Existing r043/PR197/199/200/235 SHA certifications reused; no restoration or rerun of historical59 checks',
        failed_case_reuse='No complete matching receipt or any mismatched artifact SHA => no reuse',
        cache_contract='This full closure gate runs before and after the supported CLI stage; any input change requires a new explicit evidence namespace')

def main():
    before=closure();put('FULL_INPUT_CLOSURE_CERTIFICATION.json',before)
    mode=sys.argv[1]
    if mode!='audit':
        if mode in ('anchors','extension','temporal','legacy_remaining'):
            from . import correction_time100 as driver
            driver.anchors() if mode=='anchors' else driver.stage(mode)
        elif mode=='legacy_pilots':
            from .correction_old_pilots import main as run
            run()
        elif mode=='charge_spread':
            from .correction_charge_spread import main as run
            run()
        elif mode=='svr':
            config=sys.argv[2]
            if config=='S0':
                from .correction_svr_run import main as run
            elif config=='S1_03':
                from .correction_svr_implicit import main as run
            elif config in ('S1_06','S1_12'):
                from .correction_svr_busnames import main as run
            else:raise ValueError('Frozen configurations: S0, S1_03, S1_06, S1_12')
            run(config)
        elif mode=='peak31':
            from .correction_peak31 import main as run
            run()
        else:raise ValueError('Supported stages: audit, anchors, extension, temporal, legacy_remaining, legacy_pilots, charge_spread')
    after=closure();assert after==before;put('FULL_INPUT_CLOSURE_CERTIFICATION.json',after)
    print('FULL FROZEN INPUT CLOSURE PASS',after['verified_frozen_files'],flush=True)

if __name__=='__main__':main()
