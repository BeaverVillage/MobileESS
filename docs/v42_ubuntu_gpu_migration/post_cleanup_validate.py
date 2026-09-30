"""Linux restart validation; exact input/Git/research preservation and fresh solvers."""
import csv,json,hashlib,subprocess,os,time
from pathlib import Path
H=Path.home();W=H/'mobileess_worktrees';R=W/'root_lp_compression';O=R/'docs/v42_ubuntu_gpu_migration'
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args,label,cwd=R,env=None):
    with (O/(label+'.log')).open('w') as f:r=subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0,(label,r.returncode);return (O/(label+'.log')).read_text()[-1600:]
env=dict(os.environ,MOBILEESS_PATH_MAP=str(H/'mobileess_data/path_map.json'),PYTHONPATH=str(O)+':'+str(R))
cpu=str(H/'mobileess_envs/v42_cpu/bin/python');gpu=str(H/'mobileess_envs/v42_gpu/bin/python')
tests=run([cpu,'-m','pytest','-q','tests/test_v42_root.py','tests/test_v42_exact.py'],'POST_CLEANUP_BOUNDED_TESTS',env=env)
imports=run([cpu,str(O/'runtime_audit.py')],'POST_CLEANUP_IMPORT_AUDIT',env=env)
frozen=read(R/'docs/v42_root_lp_compression_a1/LEGACY_PRESERVATION_AUDIT.json')['files']
for root in (R,W/'pr102'):
    assert all(sha(root/x['path'])==x['sha256'] for x in frozen)
pr102_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=W/'pr102',text=True).strip()
assert pr102_head=='cd7e40762097b6c20303bd2238edf7ffeba87aa4'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=W/'pr102',text=True).strip()
data=list(csv.DictReader((O/'V42_DATA_MIGRATION_MANIFEST.csv').open()))
for row in data:
    p=Path(row['destination']);assert p.is_file() and sha(p)==row['sha256']
rows=list(csv.DictReader((O/'IEEE8500_FILE_MANIFEST.csv').open()));verified=set();start=time.perf_counter()
for i,row in enumerate(rows):
    p=Path(row['destination']);assert p.is_file() and p.stat().st_size==int(row['bytes'])
    if row['sha256'] not in verified:
        assert sha(p)==row['sha256'];verified.add(row['sha256'])
    if i%10000==0:print('POST_CLEANUP_IEEE',i,len(verified),flush=True)
for label,python,request in [('POST_CPU',cpu,'0'),('POST_GPU',gpu,'1')]:
    run([python,str(O/'gurobi_smoke.py'),str(O),label,request],label+'_stdout',env=env)
a=read(O/'SMOKE_POST_CPU.json');b=read(O/'SMOKE_POST_GPU.json')
gpu_pass=b['GPU_PDHG_log'] and b['GPU_model_log'] and not b['CPU_fallback'] and a['status']==b['status']==2 and abs(a['objective']-b['objective'])<1e-9
assert gpu_pass
result=dict(PASS=True,after_distro_terminate_and_restart=True,V42_PASS=True,GPU_PASS=gpu_pass,IEEE8500_PASS=True,PR102_head=pr102_head,frozen_source_files=len(frozen),immutable_inputs=len(data),IEEE8500_files=len(rows),IEEE8500_unique_SHA256=len(verified),IEEE8500_hash_seconds=time.perf_counter()-start,bounded_tests=tests,imports=imports,CPU=a,GPU=b,no_production_A1=True)
(O/'POST_CLEANUP_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print('POST_CLEANUP_PASS',flush=True)
