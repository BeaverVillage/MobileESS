"""Baseline and successor contracts, without production optimization."""
import os,sys,json,subprocess,shutil,hashlib,importlib.metadata as md
from pathlib import Path
H=Path.home();W=H/'mobileess_worktrees';ROOT=W/'root_lp_compression';OUT=ROOT/'docs/v42_ubuntu_gpu_migration'
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
cfg=H/'mobileess_data/path_map.json';mapping=json.loads(cfg.read_text())
integrity=json.loads((ROOT/'v42_final/runtime_bundle/INTEGRITY.json').read_text())
for row in integrity['inference_source_extraction']:
    dest=ROOT/'v42_final/inference'/row['path'].replace('\\','/').split('/')[-1]
    assert sha(dest)==row['sha256'];mapping[row['path'].replace('\\','/')]=str(dest)
cfg.write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(Path(__file__).with_name('sitecustomize.py'),OUT/'sitecustomize.py')
env=dict(os.environ,MOBILEESS_PATH_MAP=str(cfg),PYTHONPATH=str(OUT)+':'+str(ROOT))
cpu=H/'mobileess_envs/v42_cpu/bin/python';gpu=H/'mobileess_envs/v42_gpu/bin/python'
result={}
code='from v42_boundary.boundaries import load_native; from v42_temporal.native import load_power; b,j,*_=load_native(); print("NATIVE_JOBS",len(j)); c,p,*_=load_power(b); print("POWER",len(p)); from v42_final.runtime import FrozenQ50; FrozenQ50(); print("PROVIDER_READY")'
with (OUT/'UBUNTU_IMPORT.log').open('w') as f:r=subprocess.run([str(cpu),'-c',code],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
result['import_pass']=r.returncode==0
print('IMPORT',r.returncode,flush=True)
if r.returncode:print((OUT/'UBUNTU_IMPORT.log').read_text());sys.exit(1)
for kind,path in [('PR102',W/'pr102'),('WIP',ROOT)]:
    this_env=dict(env,PYTHONPATH=str(OUT)+':'+str(path))
    # The inference basename references point to identical WIP-vendored sources.
    with (OUT/('TEST_'+kind+'.log')).open('w') as f:
        r=subprocess.run([str(cpu),'-m','pytest','-q','tests'],cwd=path,env=this_env,stdout=f,stderr=subprocess.STDOUT)
    result[kind+'_tests_pass']=r.returncode==0;result[kind+'_test_summary']=(OUT/('TEST_'+kind+'.log')).read_text()[-1800:]
    print('TEST',kind,r.returncode,flush=True)
result['PASS']=all(result[k] for k in ('import_pass','PR102_tests_pass','WIP_tests_pass'))
(OUT/'UBUNTU_V42_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
names=['numpy','scipy','pandas','gurobipy','dss-python','opendssdirect.py','pytest','psutil','pyarrow','lightgbm']
with (OUT/'UBUNTU_ENVIRONMENT_MANIFEST.txt').open('w') as f:
    for python in (cpu,gpu):
        f.write('\nENVIRONMENT '+str(python)+'\n')
        subprocess.run([str(python),'--version'],stdout=f,stderr=subprocess.STDOUT)
        subprocess.run([str(python),'-m','pip','freeze'],stdout=f,stderr=subprocess.STDOUT)
print(json.dumps(result))
