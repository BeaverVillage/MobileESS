"""Read-only portable delivery audit; full refit/checkpoint audit is verify.py."""
from common import *
import tarfile

def main():
 m=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
 for r in m['files']:require(sha(ROOT/r['path'])==r['sha256'],'DELIVERY_DIGEST '+r['path'])
 count=0
 if (ROOT/'FIT_AUDIT_BUNDLE.tar.gz').exists():
  ledger=json.loads((ROOT/'FIT_AUDIT_BUNDLE_MEMBERS.json').read_text(encoding='utf-8'))
  require(sha(ROOT/'FIT_AUDIT_BUNDLE.tar.gz')==ledger['archive_sha256'],'BUNDLE_DIGEST')
  expected={r['path']:r for r in ledger['members']}
  with tarfile.open(ROOT/'FIT_AUDIT_BUNDLE.tar.gz','r:gz') as archive:
   for member in archive.getmembers():
    require(member.isfile() and member.name in expected and '..' not in Path(member.name).parts,'BUNDLE_MEMBER')
    content=archive.extractfile(member).read();require(hashlib.sha256(content).hexdigest()==expected[member.name]['sha256'],'MEMBER_DIGEST');count+=1
  require(count==len(expected),'MISSING_MEMBER')
 print('PORTABLE DELIVERY PASS',len(m['files']),'files;',count,'bundled fit records; checkpoint retraining not performed')

if __name__=='__main__':main()
