"""Versioned worker: preserve V1 B0/B1/B2 producers; bind equivalent B3 A1."""
from fast_prepare import *
from v41r4_runtime import MAY_OUT
import sys

def main(day, phase):
    from dayahead.v40h.identity import verify_manifest
    release=read(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V2.json')
    assert release['status']=='FROZEN' and release['A1_own_budget_seconds']==1800
    verify_manifest(release['additional_source'])
    from v41r4_readback_v2 import install
    install()
    import v41r4_worker as original
    if phase.startswith('B3_'):
        from v41r4_b3_equivalent import configure
        original.configure=configure
    original.main(day,phase)

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
