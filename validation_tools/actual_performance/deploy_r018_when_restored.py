"""Deploy only after the owned Native0 restorer exits successfully."""
from pathlib import Path
import sys,os,subprocess,psutil,shutil
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
root=Path('D:/v44_may01_07_prepare_20261016')
destination=sys.argv[1]
with Path(destination+'.log').open('ab') as log:
    process=subprocess.Popen([sys.executable,'-X','utf8','-u','validation_tools/actual_performance/reconstruct_may02_b3.py',destination],
        cwd=root,env=dict(os.environ,PYTHONUTF8='1'),stdout=log,stderr=log,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('OWNED_NATIVE0_RESTORER_PID',process.pid,flush=True)
    code=process.wait(timeout=2400)
if code!=0:raise RuntimeError('NATIVE0_RECONSTRUCTION_NOT_SUCCESSFUL:'+str(code))
print('NATIVE0_RESTORATION_EXIT_ZERO',flush=True)
commands=[
    [sys.executable,'-X','utf8','validation_tools/actual_performance/seal_r018.py'],
    [shutil.which('pwsh') or 'powershell.exe','-NoProfile','-File','validation_tools/actual_performance/register_r018_task.ps1'],
    [sys.executable,'-X','utf8','validation_tools/actual_performance/arm_r018.py'],
]
for command in commands:
    value=subprocess.run(command,cwd=root,env=dict(os.environ,PYTHONUTF8='1'),capture_output=True,text=True,encoding='utf8',
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print(value.stdout,flush=True)
    if value.returncode:
        print(value.stderr,flush=True);raise RuntimeError('RECOVERY_DEPLOYMENT_STEP_FAILED:'+str(command))
print('R018_ARMED',flush=True)
