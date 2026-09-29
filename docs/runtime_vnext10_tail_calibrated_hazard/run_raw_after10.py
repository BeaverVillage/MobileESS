from common10 import *
import time,subprocess
while not (ROOT/'TRAINING_COMPLETED.json').exists():time.sleep(5)
with (ROOT/'evaluate_raw10.log').open('a',encoding='utf-8') as log:
    r=subprocess.run([sys.executable,'-u',str(ROOT/'evaluate_raw10.py')],stdout=log,stderr=subprocess.STDOUT)
raise SystemExit(r.returncode)
