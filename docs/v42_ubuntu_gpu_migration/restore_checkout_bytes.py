"""Restore only Git checkout line endings when hash proves exact frozen bytes."""
from pathlib import Path
import json,hashlib,subprocess
H=Path.home();R=H/'mobileess_worktrees/pr102';O=H/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration'
a=json.loads((O.parent/'v42_root_lp_compression_a1/LEGACY_PRESERVATION_AUDIT.json').read_text());fixed=[]
for row in a['files']:
    p=R/row['path'];b=p.read_bytes()
    if hashlib.sha256(b).hexdigest()==row['sha256']:continue
    corrected=b.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    if hashlib.sha256(corrected).hexdigest()!=row['sha256']:raise RuntimeError('NON_EOL_DRIFT:'+row['path'])
    p.write_bytes(corrected);fixed.append(row['path'])
(O/'PR102_CHECKOUT_BYTE_RESTORATION.json').write_text(json.dumps(dict(files=fixed,method='Only LF-to-CRLF checkout translation whose SHA256 exactly equals frozen Windows authority; no scientific/source text changes',PASS=True),indent=2)+'\n')
print('RESTORED_EXACT_CHECKOUT_BYTES',fixed)
print(subprocess.check_output(['git','status','--short'],cwd=R,text=True))
