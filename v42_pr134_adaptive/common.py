from pathlib import Path
import pickle
from v42_pr134_b1.common import read,sha,digest,record,atomic,table,now,SETTINGS
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_b1_adaptive_prescreening_rescue_20261007'
PRIOR=ROOT/'docs/v42_b1_may17_may19_repair_20261007'
SOURCE=Path('C:/v42_b1_may17_may19_repair_20261007')
CASE=Path('C:/v42_b1_adaptive_prescreening_rescue_20261007')
PRODUCTION=Path('C:/v42_pr134_sc_execution_20261007')
DAYS=('2025-05-17','2025-05-19')
BASE='fe0f5cf253bb08e3f96fe1e2c0af677e8b541144'
def label(day):return 'MAY'+day[-2:]
def write(name,value):atomic(OUT/name,value)
def load(day):
    with (SOURCE/day/'DATA.pkl').open('rb') as f:return pickle.load(f)
