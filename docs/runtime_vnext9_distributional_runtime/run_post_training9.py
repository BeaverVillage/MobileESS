"""Resume only new V9 stages; stop immediately on an error."""
from common9 import *
import subprocess,time
while not (ROOT/'TRAINING_COMPLETED.json').exists():time.sleep(5)
for name in ['evaluate9','finalize_model9']:
    with (ROOT/(name+'.log')).open('a',encoding='utf-8') as log:
        r=subprocess.run([sys.executable,'-u',str(ROOT/(name+'.py'))],stdout=log,stderr=subprocess.STDOUT)
    if r.returncode:raise SystemExit(name+' failed; inspect its log')
    print(now(),name,'COMPLETE',flush=True)
