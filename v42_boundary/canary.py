import os
from .common import *
from v42_native.supervision import supervise

def main():
    os.environ['PYTHONUTF8']='1'
    require(read(OUT/'MAY01_RESOURCE_RECHECK.json')['PASS'],'RESOURCE_GATE')
    require(read(OUT/'A1_LEGACY_ACCELERATED_EQUIVALENCE.json')['PASS'],'EQUIVALENCE_GATE')
    require(read(GEN/'DOMAIN_COMPLETE.json')['all_jobs_complete'],'FULL_DOMAIN_GATE')
    candidate,receipt=supervise('A1','v42_native.boundary_model_worker:worker','v42_native.boundary_model_worker:validator',
        dict(sources=[rec(p) for p in (ROOT/'v42_boundary').glob('*.py')]),LOCAL/'A1_zero_rate_repair',seconds=600)
    dump('A1_SUPERVISOR_RECEIPT.json',receipt);print(receipt)
    if candidate is not None:raise RuntimeError('ACCEPTED_A1_CONTINUE_M1_A2_M2_REQUIRED')

if __name__=='__main__':main()
