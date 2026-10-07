from pathlib import Path
from v42_pr134_b1.common import read,sha,digest,record,atomic,table,now,process,SETTINGS,BUDGET,CHECKER
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_b1_may19_prescreening_rescue_20261007'
CASE=Path('C:/v42_b1_may19_prescreening_rescue_20261007')
BASE='d9b32354128484fe381703958579d4cb118fa99e'
DAY='2025-05-19'
OLD=Path('C:/v42_b1_adaptive_prescreening_rescue_20261007')/DAY
START=OLD/'S2_EXACT_SUPPORT_BATCH'
SUPPORT=OLD/'S2_SUPPORT_SECOND_BATCH'
POOL=ROOT/'docs/v42_b1_adaptive_prescreening_rescue_20261007/MAY19_OMITTED_OPTION_UNIVERSE.csv'
PRODUCTION=Path('C:/v42_pr134_sc_execution_20261007')
LP_SETTINGS=dict(SETTINGS,Method=2,Crossover=0,TimeLimit=600.)
MIP_SETTINGS=dict(SETTINGS,TimeLimit=600.)
SHELLS=[dict(name='S_A',kind='SAME_SITE',batch=16),dict(name='S_B',kind='SAME_SITE',batch=32),
        dict(name='S_C',kind='PRESTART_SITE',batch=64),dict(name='S_D',kind='MIGRATION',batch=128)]
def write(name,v):atomic(OUT/name,v)
def other_heavy():
    import psutil
    keys=('v42_pr134_b1.worker','v42_pr134_adaptive.solve_snapshot','v42_pr134_adaptive.capacity_master',
          'v42_pr134_adaptive.minimum_probe','v42_pr134_may19.solve','v42_pr134_may19.production')
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==psutil.Process().pid:continue
        if str(p.info['name']).lower().startswith('python') and any(k in ' '.join(p.info['cmdline'] or []) for k in keys):
            raise PermissionError('OTHER_HEAVY_OPTIMIZER:'+str(p.pid))
