"""Byte preservation of inherited Git blobs and staged evidence artifacts."""
from .common import *

PREFIXES=('docs/v42_m1_root_pathology_diagnostics/','v42_root_diagnostics/')
EXCLUDED={'docs/v42_m1_root_pathology_diagnostics/STAGED_BYTE_AUDIT.json','docs/v42_m1_root_pathology_diagnostics/SHA256_MANIFEST.json'}

def check(include_self=False):
    freeze_check();assert preserve()==2536
    names=git('diff','--cached','--name-only',BASE).splitlines()
    assert all(n.startswith(PREFIXES) for n in names),names
    checked=[]
    for name in names:
        if name in EXCLUDED and not include_self:continue
        blob=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest()==sha(ROOT/name),name
        checked.append(name)
    subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
    if include_self:
        manifest=read('SHA256_MANIFEST.json')
        assert all(sha(ROOT/n)==s for n,s in manifest['files'].items())
        print('FINAL_STAGED_BYTES_AND_MANIFEST_PASS',len(checked),flush=True)
    else:
        dump('STAGED_BYTE_AUDIT.json',dict(PASS=True,exact_base=BASE,utc=stamp(),
            inherited_physical_files_unchanged=2536,inherited_Git_blob_changes=0,
            new_staged_blob_physical_byte_identical_count=len(checked),checked_paths=checked,
            recursive_self_reference_exclusions=sorted(EXCLUDED),
            excluded_files_validation='After this receipt and refreshed manifest are staged, include_self=True independently checks both index byte identities and every manifest entry.',
            git_diff_cached_check_PASS=True))

if __name__=='__main__':check(include_self='--include-self' in os.sys.argv)
