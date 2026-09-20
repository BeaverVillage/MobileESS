"""Independent hidden Windows entry point; preserves the frozen Git runtime."""
import os,sys,runpy,json,ctypes,time
from pathlib import Path
R=Path(__file__).resolve().parent;W=R/'v41r4';sys.path.insert(0,str(W));os.chdir(W)
binding=json.loads((R/'manifests/codex_independent/RUNTIME_ENVIRONMENT.json').read_text(encoding='utf-8-sig'))
os.environ['PATH']=str(Path(binding['git_executable']).parent)+os.pathsep+os.environ.get('PATH','')
os.environ.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from v41r4_900_namespace import RUN,OUT
OUT.mkdir(parents=True,exist_ok=True)
from ctypes import wintypes
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetCurrentProcess.restype=wintypes.HANDLE
kernel.IsProcessInJob.argtypes=[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)]
member=wintypes.BOOL()
if not kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(member)):raise ctypes.WinError(ctypes.get_last_error())
assert not member.value,'CAMPAIGN_MUST_BE_OUTSIDE_CODEX_WINDOWS_JOBS'
(OUT/'CODEX_INDEPENDENCE.json').write_text(json.dumps(dict(status='PASS',pid=os.getpid(),parent_pid=os.getppid(),
    in_windows_job=False,at=time.time(),launch_method='WMI Win32_Process.Create',
    Codex_exit_does_not_stop_campaign=True),indent=2),encoding='utf-8')
sys.stdout=(OUT/f'SUPERVISOR_{os.getpid()}.log').open('a',encoding='utf-8',buffering=1)
sys.stderr=(OUT/f'SUPERVISOR_{os.getpid()}.err').open('a',encoding='utf-8',buffering=1)
from v41r4_900_campaign import main
main()
