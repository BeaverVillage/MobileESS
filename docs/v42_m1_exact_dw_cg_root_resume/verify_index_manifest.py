import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);out=root/'docs/v42_m1_exact_dw_cg_root_resume'
records=json.loads((out/'CORRECTION_SHA256_MANIFEST.json').read_text(encoding='utf8'))['files']
payload=''.join(':'+r['path']+'\n' for r in records).encode()
data=subprocess.run(['git','cat-file','--batch'],cwd=root,input=payload,capture_output=True,check=True).stdout
offset=0
for record in records:
    end=data.index(b'\n',offset);header=data[offset:end].split();assert header[1]==b'blob',(record,header)
    size=int(header[2]);start=end+1;value=data[start:start+size];offset=start+size+1
    assert hashlib.sha256(value).hexdigest()==record['sha256'],record['path']
assert offset==len(data)
staged=subprocess.run(['git','diff','--cached','--name-only','-z'],cwd=root,capture_output=True,check=True).stdout.decode().split('\0')
actual={p for p in staged if p}
assert all(p.startswith(('v42_dw_resume/','tests/v42_dw_resume/','docs/v42_m1_exact_dw_cg_root_resume/')) for p in actual),actual
for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=root,check=True)
print(json.dumps(dict(PASS=True,manifest_index_byte_matches=len(records),staged_paths=len(actual),manifest_SHA=hashlib.sha256((out/'CORRECTION_SHA256_MANIFEST.json').read_bytes()).hexdigest())))
