"""Canonical launcher: Linux native worktree, data, Python and path table."""
import os,sys
from pathlib import Path
h=Path.home();args=sys.argv[1:];gpu='--gpu' in args;base='--pr102' in args
args=[a for a in args if a not in ('--gpu','--pr102')]
work=h/'mobileess_worktrees'/('pr102' if base else 'root_lp_compression')
support=h/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration'
assert not str(work).startswith('/mnt/')
os.chdir(work)
env=dict(os.environ,MOBILEESS_PATH_MAP=str(h/'mobileess_data/path_map.json'),PYTHONPATH=str(support)+':'+str(work),PYTHONUTF8='1')
python=h/'mobileess_envs'/('v42_gpu' if gpu else 'v42_cpu')/'bin/python'
os.execve(str(python),[str(python)]+args,env)
