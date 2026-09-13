import ctypes,json,time
from pathlib import Path
import psutil
H=Path(__file__).parent
target=50600
p=psutil.Process(target)
assert 'production_campaign_v2.py' in ' '.join(p.cmdline())
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.FreeConsole()
if not k.AttachConsole(target):
    raise ctypes.WinError(ctypes.get_last_error())
k.SetConsoleCtrlHandler(None,True)
buf=(ctypes.c_uint32*32)()
n=k.GetConsoleProcessList(buf,32)
members=list(buf[:n])
assert set(members)<={target,psutil.Process().pid},members
receipt={'target_pid':target,'console_members':members,'method':'Windows CTRL_C_EVENT -> Python KeyboardInterrupt -> campaign exception/finally cleanup','requested_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
receipt['signal_sent']=bool(k.GenerateConsoleCtrlEvent(0,0))
time.sleep(1)
k.FreeConsole()
try:p.wait(timeout=40);receipt['exited']=True
except psutil.TimeoutExpired:receipt['exited']=False
(H/'GRACEFUL_STOP_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))
