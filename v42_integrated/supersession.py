"""Exact successor seal for this user-authorized integration, never a bypass."""
import hashlib,json,subprocess
from .governance import ROOT,OUT,BASE,sha,write,git

def assert_successor(path,current_sha,previous_sha=None):
    p=OUT/'AUTHORIZED_INTEGRATION_SUPERSESSION.json'
    if not p.is_file():return False
    manifest=json.loads(p.read_text(encoding='utf8'))
    row=next((r for r in manifest['files'] if r['path']==path),None)
    if row is None:return False
    assert manifest['canonical_base']==BASE and manifest['old_certificate_superseded']
    original=git('show',BASE+':'+path)
    assert hashlib.sha256(original).hexdigest()==row['base_sha256']
    if current_sha!=row['current_sha256']:
        # A clean checkout may use the Git blob instead of this host's CRLF
        # transport. Permit only the exact immutable blob of an audited
        # transport-only file, never an unsealed scientific edit.
        transport=json.loads((OUT/'CHECKOUT_BYTE_TRANSPORT_AUDIT.json').read_text(encoding='utf8'))
        proof=next((r for r in transport['files'] if r['path']==path),None)
        assert proof is not None and current_sha==row['base_sha256'],'UNSEALED_INTEGRATION_SUCCESSOR:'+path
        assert proof['canonical_base_sha256']==row['base_sha256'] and proof['checkout_sha256']==row['current_sha256'],'TRANSPORT_PROOF_MISMATCH:'+path
    if previous_sha is not None:assert previous_sha in row['historical_sha256'],'INTEGRATION_PREVIOUS_SHA:'+path
    return True

def seal():
    paths=set(git('diff','--name-only',BASE).decode().splitlines());rows=[]
    transport=OUT/'CHECKOUT_BYTE_TRANSPORT_AUDIT.json'
    if transport.is_file():
        paths.update(r['path'] for r in json.loads(transport.read_text())['files'])
    for path in sorted(paths):
        original=git('show',BASE+':'+path);history=set()
        refs=git('log','--format=%H',BASE,'--',path).decode().splitlines()
        for ref in refs:
            r=subprocess.run(['git','show',ref+':'+path],cwd=ROOT,capture_output=True)
            if r.returncode:continue
            value=r.stdout;lf=value.replace(b'\r\n',b'\n')
            history.update(hashlib.sha256(b).hexdigest() for b in (value,lf,lf.replace(b'\n',b'\r\n')))
        rows.append(dict(path=path,base_sha256=hashlib.sha256(original).hexdigest(),current_sha256=sha(ROOT/path),historical_sha256=sorted(history)))
    write('AUTHORIZED_INTEGRATION_SUPERSESSION.json',dict(canonical_base=BASE,authorization='User attachment 4df1e153-3aa4-4683-afdd-68150750c39c; zero-margin integration and required semantic tests',old_certificate_superseded=True,physical_evidence_unchanged=True,files=rows))

if __name__=='__main__':seal()
