"""Verify exact Git index bytes, including append-only artifact scope."""
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);out=root/'docs/v42_m1_dw_certified_dual_bound'
records=json.loads((out/'SHA256_MANIFEST.json').read_text(encoding='utf8'))['files']
data=subprocess.run(['git','cat-file','--batch'],cwd=root,input=''.join(':'+r['path']+'\n' for r in records).encode(),capture_output=True,check=True).stdout
offset=0
for record in records:
    end=data.index(b'\n',offset);header=data[offset:end].split();assert header[1]==b'blob',(record,header)
    size=int(header[2]);start=end+1;value=data[start:start+size];offset=start+size+1
    assert hashlib.sha256(value).hexdigest()==record['sha256'],record['path']
assert offset==len(data)
paths=subprocess.run(['git','diff','--cached','--name-only','-z'],cwd=root,capture_output=True,check=True).stdout.decode().split('\0');staged=[p for p in paths if p]
assert all(p.startswith(('v42_dw_bound/','tests/v42_dw_bound/','docs/v42_m1_dw_certified_dual_bound/')) for p in staged)
for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=root,check=True)
print(json.dumps(dict(PASS=True,index_byte_matches=len(records),staged_paths=len(staged),manifest_SHA=hashlib.sha256((out/'SHA256_MANIFEST.json').read_bytes()).hexdigest())))
