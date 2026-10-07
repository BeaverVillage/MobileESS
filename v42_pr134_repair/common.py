from pathlib import Path
from v42_pr134_b1.common import read,sha,digest,record,atomic,table,clean,now,BASE,SETTINGS,BUDGET
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_b1_may17_may19_repair_20261007'
CASE=Path('C:/v42_b1_may17_may19_repair_20261007')
PRODUCTION=Path('C:/v42_pr134_sc_execution_20261007')
DAYS=('2025-05-17','2025-05-19')
def failed(day):
    if day not in DAYS:raise PermissionError('MAY17_MAY19_SCOPE_ONLY')
    return PRODUCTION/'stages'/day/'A1'/'1'/'output'
def label(day):return 'MAY'+day[-2:]
def write(name,value):atomic(OUT/name,value)
