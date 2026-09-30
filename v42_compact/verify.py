from .common import *
def main():
    for row in read(OUT/'PR98_BYTE_SNAPSHOT.json'):require(sha(row['path'])==row['sha256'],'PRESERVATION:'+row['relative'])
    for name in ('SOURCE_MANIFEST.json','LOCAL_EVIDENCE_MANIFEST.json'):
        manifest=read(OUT/name)
        for row in manifest['files']+manifest.get('inherited_sources',[]):require(sha(row['path'])==row['sha256'],'HASH:'+row['path'])
    for name in ('SYNTHETIC_EQUIVALENCE.json','REAL_SUBSET_EQUIVALENCE.json','COMPACT_PATH_EQUIVALENCE_AUDIT.json','VERIFICATION.json'):
        require(read(OUT/name)['PASS'],'VERIFICATION:'+name)
    require(read(OUT/'VARIABLE_INDEX_SETS.json')['jobs']==1499,'ALL_JOBS')
    require(not read(OUT/'FINAL_FLAGS.json')['COMPLETE_OPTION_ENUMERATION_IN_COMPACT_MODEL'],'NO_COMPLETE_OPTION_PRODUCTION_PATH')
    require(not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),'NO_UNACCEPTED_KERNEL')
    print('PASS: preserved PR98, source/evidence hashes, equivalence, tests and acceptance gates')
if __name__=='__main__':main()
