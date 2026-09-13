"""Wait for existing B2 writer, then archive/extract. Never invokes scientific work."""
import json,time,subprocess,sys,hashlib,ctypes,datetime,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent
LIVE=Path(r'D:\ChatGPT\Mobile ESS 2\IEEE8500_B2_actual_availability_gating_20260912_r3')
NODE=Path(r'C:\Users\kjw39\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
def save(name,x):(HERE/name).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def alive(pid):
 k=ctypes.windll.kernel32;k.OpenProcess.restype=ctypes.c_void_p
 h=k.OpenProcess(0x100000,False,pid)
 if not h:return False
 try:return k.WaitForSingleObject(ctypes.c_void_p(h),0)==258
 finally:k.CloseHandle(ctypes.c_void_p(h))
def main():
 assert not (HERE/'PIPELINE_STARTED.json').exists(),'No duplicate export pipeline'
 names=['finish_when_ready.py','archive_all.py','extract.py','build_csv.mjs','package_csv.py']
 freeze={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in names}
 save('PIPELINE_STARTED.json',{'pid':__import__('os').getpid(),'source_B2_pid':55228,'script_sha256':freeze,'scientific_execution_count':0})
 while True:
  s=json.loads((LIVE/'STATUS.json').read_text(encoding='utf-8'));running=alive(55228)
  save('EXPORT_STATUS.json',{'stage':'WAITING_FOR_EXISTING_B2_ACTUAL','B2_status':s,'B2_process_alive':running,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  if not running:
   if s.get('status') not in ('PASS','FAIL_CLOSE'):raise RuntimeError('B2 process ended without terminal evidence; no result regeneration allowed')
   break
  time.sleep(30)
 for n,sha in freeze.items():assert hashlib.sha256((HERE/n).read_bytes()).hexdigest()==sha,n
 for args in [[sys.executable,'-B',str(HERE/'archive_all.py')]]:
  subprocess.run(args,cwd=HERE,check=True)
 idx=json.loads((HERE/'ARCHIVE_READY.json').read_text(encoding='utf-8'))
 subprocess.run([sys.executable,'-B',str(HERE/'extract.py'),idx['archive_path']],cwd=HERE,check=True)
 subprocess.run([str(NODE),str(HERE/'build_csv.mjs')],cwd=HERE,check=True)
 subprocess.run([sys.executable,'-B',str(HERE/'package_csv.py')],cwd=HERE,check=True)
 save('EXPORT_STATUS.json',{'stage':'COMPLETE','result':json.loads((HERE/'FINAL_EXPORT_VERIFICATION.json').read_text(encoding='utf-8'))})
if __name__=='__main__':
 try:main()
 except BaseException as e:save('EXPORT_STATUS.json',{'stage':'EXPORT_FAIL_CLOSE','error':repr(e),'traceback':traceback.format_exc()});raise
