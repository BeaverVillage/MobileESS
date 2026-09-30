from .common import *

def main():
    for row in read(OUT/'PR97_BYTE_SNAPSHOT.json'):require(sha(row['path'])==row['sha256'],'PR97_PRESERVATION:'+row['relative'])
    for name in ('SOURCE_MANIFEST.json','LOCAL_EVIDENCE_MANIFEST.json'):
        for r in read(OUT/name)['files']:require(sha(r['path'])==r['sha256'],'SOURCE_HASH:'+r['path'])
    g=read(OUT/'A1_GENERATION_PROFILE_ACCELERATED.json')
    require(g['all_jobs_complete'] and g['jobs_complete']==1499 and g['total_seconds']<=600,'DOMAIN_TARGET')
    require(read(OUT/'A1_LEGACY_ACCELERATED_EQUIVALENCE.json')['missing_from_new']==0,'EXACT_DOMAIN_SET')
    require(read(OUT/'LIVE_TS_WINDOW_TRAIN_AUDIT.json')['valid_windows']==0,'LIVE_NO_FABRICATED_SOURCE')
    require(read(OUT/'VERIFICATION.json')['PASS'],'TESTS')
    require(not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),'NO_UNACCEPTED_RESPONSE_KERNEL')
    print('PASS: immutable PR97, sources, 1499 complete exact domains, tests and acceptance gates')

if __name__=='__main__':main()
