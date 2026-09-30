"""Add matching official CLI separately when only Python Gurobi was installed."""
import urllib.request,hashlib,tarfile,json,subprocess,shutil,os
from pathlib import Path
h=Path.home();base=h/'mobileess_tools/gurobi_cli';base.mkdir(parents=True,exist_ok=True)
archive=base/'gurobi13.0.2_linux64.tar.gz';url='https://packages.gurobi.com/13.0/'+archive.name
checksum_url='https://checksum.gurobi.com/13.0.2/'+archive.name+'.md5'
expected=urllib.request.urlopen(checksum_url,timeout=30).read().decode().split()[0]
if not archive.exists():urllib.request.urlretrieve(url,archive)
with archive.open('rb') as f:actual=hashlib.file_digest(f,'md5').hexdigest()
assert expected==actual
cl=base/'gurobi1302/linux64/bin/gurobi_cl'
if not cl.exists():
    with tarfile.open(archive) as t:t.extractall(base,filter='data')
env=dict(os.environ,GUROBI_HOME=str(cl.parents[1]),LD_LIBRARY_PATH=str(cl.parents[1]/'lib'))
version=subprocess.check_output([str(cl),'--version'],text=True,env=env)
lp=base/'CPU_LICENSE_SMOKE.lp';lp.write_text('Minimize\n obj: x\nSubject To\n c: x >= 1\nBounds\n x >= 0\nEnd\n')
solve=subprocess.run([str(cl),str(lp)],cwd=base,capture_output=True,text=True,env=env)
wrapper=h/'.local/bin/gurobi_cl';wrapper.parent.mkdir(exist_ok=True)
body='#!/usr/bin/python3\n# MobileESS matching CLI only; no Python/GPU environment mutation.\nimport os,sys\nenv=dict(os.environ,GUROBI_HOME='+repr(str(cl.parents[1]))+',LD_LIBRARY_PATH='+repr(str(cl.parents[1]/'lib'))+')\nos.execve('+repr(str(cl))+',['+repr(str(cl))+']+sys.argv[1:],env)\n'
if not wrapper.exists():wrapper.write_text(body);wrapper.chmod(0o755)
elif wrapper.read_text()!=body:raise RuntimeError('EXISTING_CLI_WRAPPER_DO_NOT_OVERWRITE')
out=h/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration';v=json.loads((out/'GUROBI_LINUX_VALIDATION.json').read_text());v.update(gurobi_cl=str(cl),gurobi_cl_version=version.strip(),gurobi_cl_solve_returncode=solve.returncode,matching_official_CLI_added_separately=True,CLI_package_url=url,CLI_package_md5=actual,CLI_checksum_url=checksum_url)
(out/'GUROBI_CLI_CPU_SMOKE.log').write_text(solve.stdout+solve.stderr);(out/'GUROBI_LINUX_VALIDATION.json').write_text(json.dumps(v,indent=2)+'\n');print(version.strip(),'LICENSE_SOLVE_RETURN',solve.returncode);assert solve.returncode==0
