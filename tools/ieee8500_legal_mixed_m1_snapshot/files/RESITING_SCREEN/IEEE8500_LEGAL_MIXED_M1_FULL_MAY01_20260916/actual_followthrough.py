"""Wait for existing DA/Fresh supervisor, then run frozen Actual serially."""
import os,sys,json,time,subprocess,traceback
from pathlib import Path
H=Path(__file__).absolute().parent
assert str(H).isascii()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(v):
    p=H/'ACTUAL_FOLLOWTHROUGH_STATUS.json'; q=p.with_suffix('.writing')
    q.write_text(json.dumps(dict(updated_unix=time.time(),supervisor_pid=os.getpid(),**v),indent=2),encoding='utf-8'); os.replace(q,p)
def main():
    assert read(H/'ACTUAL_AUTHORIZATION.json')['authorized']
    import psutil
    previous=H/'ACTUAL_FOLLOWTHROUGH_STATUS.json'
    if previous.exists():
        old=read(previous)
        assert not psutil.pid_exists(old['supervisor_pid']), 'ALREADY_RUNNING'
    while True:
        s=read(H/'SUPERVISOR_STATUS.json')
        if s['status']=='COMPLETE':break
        if s['status']=='PAUSED_USER':save(dict(status='PAUSED_USER'));return
        save(dict(status='WAITING_DA_FRESH',DA_status=s['status'],DA_stage=s.get('stage'),workers=1,threads=4))
        time.sleep(30)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',TMP=str(H/'tmp'),TEMP=str(H/'tmp'))
    log=H/f'Actual_production_{time.time_ns()}.log'
    with log.open('x',encoding='utf-8') as f:
        child=subprocess.Popen([sys.executable,'-B','-u',str(H/'actual_campaign.py')],cwd=H,env=env,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        save(dict(status='RUNNING',stage='ACTUAL_B0_B1_B2_B3',worker_pid=child.pid,log=str(log),workers=1,threads=4))
        code=child.wait()
    assert code==0, ('ACTUAL_FAILED',code,str(log))
    assert (H/'Actual/CAMPAIGN_COMPLETE.json').exists()
    save(dict(status='COMPLETE',result=str(H/'Actual/CAMPAIGN_COMPLETE.json')))
if __name__=='__main__':
    try:main()
    except BaseException as e:save(dict(status='FAILED',error=repr(e),traceback=traceback.format_exc()));raise
