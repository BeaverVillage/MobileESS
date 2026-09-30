"""Read-only frozen evidence verification. Never reruns an optimizer or ML."""
from .common import *

def main():
    for name in ('SOURCE_MANIFEST.json','LOCAL_EVIDENCE_MANIFEST.json'):
        for r in read(OUT/name)['files']:
            require(sha(r['path'])==r['sha256'],'SOURCE_HASH:'+r['path'])
    for r in read(OUT/'LEGACY_PRESERVATION_AUDIT.json')['files']:
        require(sha(ROOT/r['path'])==r['sha256'],'LEGACY_HASH:'+r['path'])
    prereg=read(OUT/'PREREGISTRATION.json')
    require(prereg['minimum_conditional_N']==100 and prereg['envelope_quantiles']==[.1,.9],'PREREGISTERED_PARAMETERS')
    require(prereg['capacity_GPU']==780 and prereg['gamma90']==2.423057443558147,'FROZEN_CAPACITY_GAMMA')
    require(sha(OUT/'PREREGISTRATION.json')==read(OUT/'TS_HIERARCHICAL_BACKOFF_AUTHORITY.json')['preregistration']['sha256'],'PREREGISTRATION_DRIFT')
    flags=read(OUT/'FINAL_FLAGS.json')
    require(not any(flags[k] for k in flags if k.startswith('NEW_') and k.endswith('_TRAINED')),'NO_NEW_ML')
    require(not flags['FINAL_RESPONSE_KERNEL_FROZEN'] and not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),'NO_UNACCEPTED_KERNEL')
    require(read(OUT/'VERIFICATION.json')['PASS'],'TEST_VERIFICATION')
    print('PASS: source hashes, all PR96 files, preregistration, no-ML and acceptance gates')

if __name__=='__main__':main()
