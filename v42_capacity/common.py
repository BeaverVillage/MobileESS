from pathlib import Path
from v42_april_port.audit import read, record, sha, write, table

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_april_b0_capacity_queue_voltage_calibration'
PRIOR=ROOT/'docs/v42_april_modelable_population_b0'
BASE='81118271a837648da13146fb6ffdc8e3de8d95ab'

def resolve(source):
    p=Path(source['path'])
    candidates=[p]
    text=str(p).replace('\\','/')
    for prefix,replacement in [('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2','D:/ChatGPT/Mobile ESS 2'),
                               ('C:/codex_mobileess_workspace','D:/codex_mobileess_workspace')]:
        if text.startswith(prefix): candidates.append(Path(replacement+text[len(prefix):]))
    for candidate in candidates:
        if candidate.is_file() and sha(candidate)==source['sha256']: return candidate
    raise ValueError('EXACT_SOURCE_UNAVAILABLE:'+str(p))

def day_folder(day): return 'DAY_'+day.replace('-','')
