"""Finite local execution pipeline for the active study, not a scheduled job."""
from pathlib import Path
import subprocess,sys,time,json
ROOT=Path(__file__).resolve().parent
def run(name,args):
    path=ROOT/(name+'.log')
    print('START',name,time.strftime('%Y-%m-%d %H:%M:%S'),flush=True)
    with path.open('x',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,'-X','utf8','-u',str(ROOT/'experiment.py')]+args,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
    if result.returncode:raise RuntimeError(name+' failed: '+path.read_text(encoding='utf-8')[-4000:])
    print('DONE',name,time.strftime('%Y-%m-%d %H:%M:%S'),flush=True)
def main():
    print('WAIT existing Stage1 development',flush=True)
    while 'PHASE_COMPLETE M0 development' not in (ROOT/'development.log').read_text(encoding='utf-8'):
        text=(ROOT/'development.log').read_text(encoding='utf-8')
        if 'Traceback (most recent call last)' in text:raise RuntimeError('Development failed')
        time.sleep(5)
    run('selection_freeze',['freeze'])
    run('evaluation',['evaluation'])
    run('stage2_development',['development','--stage2'])
    run('stage2_freeze',['freeze','--stage2'])
    run('stage2_evaluation',['evaluation','--stage2'])
    (ROOT/'ALL_MODEL_PHASES_COMPLETE.json').write_text(json.dumps(dict(complete=True,time=time.strftime('%Y-%m-%d %H:%M:%S')),indent=2),encoding='utf-8')
    print('ALL_MODEL_PHASES_COMPLETE',flush=True)
if __name__=='__main__':main()
