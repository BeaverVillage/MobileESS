"""Exact index-byte manifest and new-prefix scope, not Git text filters."""
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);out=root/'docs/v42_m1_certified_arc_lp_floor_and_threshold_cg'
records=json.loads((out/'SHA256_MANIFEST.json').read_text(encoding='utf8'))['files']
data=subprocess.run(['git','cat-file','--batch'],cwd=root,input=''.join(':'+r['path']+'\n' for r in records).encode(),capture_output=True,check=True).stdout
offset=0
for r in records:
    end=data.index(b'\n',offset);header=data[offset:end].split();assert header[1]==b'blob',(r,header)
    size=int(header[2]);start=end+1;value=data[start:start+size];offset=start+size+1
    assert hashlib.sha256(value).hexdigest()==r['sha256'],r['path']
assert offset==len(data)
paths=subprocess.run(['git','diff','--cached','--name-only','-z'],cwd=root,capture_output=True,check=True).stdout.decode().split('\0')
assert all(p.startswith(('v42_arc_floor/','tests/v42_arc_floor/','docs/v42_m1_certified_arc_lp_floor_and_threshold_cg/')) for p in paths if p)
for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=root,check=True)
print(json.dumps(dict(PASS=True,index_byte_matches=len(records))))
