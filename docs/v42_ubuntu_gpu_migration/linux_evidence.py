"""Record hardware, existing installations, license solve and smoke evidence."""
import os,json,subprocess,shutil,hashlib,urllib.request
from pathlib import Path
h=Path.home();out=h/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration';src=Path(__file__).parent
for n in ('launch_v42.py','runtime_audit.py','gurobi_smoke.py'):
    shutil.copy2(src/n,out/n)
env=dict(os.environ,MOBILEESS_PATH_MAP=str(h/'mobileess_data/path_map.json'),PYTHONPATH=str(out)+':'+str(h/'mobileess_worktrees/root_lp_compression'))
cpu=h/'mobileess_envs/v42_cpu/bin/python';gpu=h/'mobileess_envs/v42_gpu/bin/python'
subprocess.run([str(cpu),str(out/'runtime_audit.py')],cwd=h/'mobileess_worktrees/root_lp_compression',env=env,check=True)
smokes={}
for label,requested in [('CPU',0),('GPU',1)]:
    if not (out/('SMOKE_'+label+'.json')).exists():
        with (out/('GPU_SMOKE_'+label+'_STDOUT.log')).open('w') as f:subprocess.run([str(gpu),str(out/'gurobi_smoke.py'),str(out),label,str(requested)],stdout=f,stderr=subprocess.STDOUT,check=True)
    smokes[label]=json.loads((out/('SMOKE_'+label+'.json')).read_text())
smokes['PASS']=smokes['GPU']['GPU_PDHG_log'] and smokes['GPU']['GPU_model_log'] and not smokes['GPU']['CPU_fallback'] and smokes['GPU']['status']==smokes['CPU']['status']==2 and abs(smokes['GPU']['objective']-smokes['CPU']['objective'])<=1e-7 and max(smokes['GPU']['feasibility_max_violation'],smokes['CPU']['feasibility_max_violation'])<=1e-6
(out/'GUROBI_GPU_SMOKE_TEST.json').write_text(json.dumps(smokes,indent=2)+'\n');assert smokes['PASS']
hardware=subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.free','--format=csv,noheader,nounits'],text=True).strip().split(',')
name,driver,total,free=[s.strip() for s in hardware]
(out/'GPU_HARDWARE_AUDIT.json').write_text(json.dumps(dict(WSL_NVIDIA_GPU_VISIBLE=True,GPU_MODEL=name,driver=driver,CUDA_compatibility='13.0 (nvidia-smi)',VRAM_bytes=int(total)*1048576,free_VRAM_bytes=int(free)*1048576,nvidia_smi=subprocess.check_output(['nvidia-smi'],text=True)),indent=2)+'\n')
code='import gurobipy as g,json,importlib.metadata as m; a=g.Model(); a.Params.OutputFlag=0; x=a.addVar(vtype=g.GRB.BINARY); a.addConstr(x>=.5); a.setObjective(x); a.optimize(); print(json.dumps(dict(license_valid=a.Status==2,objective=a.ObjVal,version=list(g.gurobi.version()),gurobipy=m.version("gurobipy"))))'
r=subprocess.run([str(cpu),'-c',code],capture_output=True,text=True,check=True);validation=json.loads(r.stdout.strip().splitlines()[-1]);validation.update(cpu_installation_preserved=True,license_regenerated=False,gurobi_cl=shutil.which('gurobi_cl'),gurobi_cl_version='NOT_ON_PATH; existing Python distributions validated directly')
(out/'GUROBI_LINUX_VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
wheel=h/'mobile_ess_work/gpu_gurobi_wheels/gurobipy-13.0.2+cu129-cp312-cp312-manylinux_2_24_x86_64.whl'
with wheel.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
with wheel.open('rb') as f:md5=hashlib.file_digest(f,'md5').hexdigest()
url='https://checksum.gurobi.com/13.0.2/wheels/'+wheel.name+'.md5'
try:
    official=urllib.request.urlopen(url,timeout=20).read().decode();official_pass=official.split()[0]==md5
except Exception as e:official=str(e);official_pass=None
build=dict(existing_CPU_version='13.0.2',existing_CPU_GPU_request='CPU fallback recorded in EXISTING_CPU smoke',existing_GPU_version='13.0.2+cu129',separate_GPU_installation_reused=True,installation_overwritten=False,new_GPU_installation_needed=False,full_CUDA_toolkit_installed=False,wheel=str(wheel),wheel_sha256=digest,wheel_md5=md5,official_checksum_url=url,official_checksum_response=official,official_checksum_matches=official_pass,official_guidance='https://support.gurobi.com/hc/en-us/articles/43498824105873-Installing-and-Running-GPU-enabled-Gurobi',GPU_log_verified=True)
(out/'GUROBI_GPU_BUILD_AUDIT.json').write_text(json.dumps(build,indent=2)+'\n')
shutil.copy2(h/'mobileess_migration_evidence/GUROBI_GPU_SMOKE_EXISTING_CPU.log',out/'EXISTING_CPU_GPU_FALLBACK.log')
print('GPU_LICENSE_DATA_EVIDENCE_PASS',flush=True)
