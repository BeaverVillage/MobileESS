"""Launch Linux-native PR102 diagnostic only after test and GPU smoke gates."""
import os,sys,subprocess,shutil,json
from pathlib import Path
H=Path.home();root=H/'mobileess_worktrees/root_lp_compression';out=root/'docs/v42_ubuntu_gpu_migration'
assert json.loads((out/'UBUNTU_V42_VALIDATION.json').read_text())['PASS']
assert json.loads((H/'mobileess_migration_evidence/SMOKE_GPU.json').read_text())['GPU_PDHG_log']
source=Path(__file__).with_name('pr102_gpu_root.py');shutil.copy2(source,out/source.name)
env=dict(os.environ,MOBILEESS_PATH_MAP=str(H/'mobileess_data/path_map.json'),PYTHONPATH=str(out)+':'+str(H/'mobileess_worktrees/pr102'))
subprocess.run([str(H/'mobileess_envs/v42_gpu/bin/python'),'-u',str(out/source.name)],cwd=H/'mobileess_worktrees/pr102',env=env,check=True)
