from pathlib import Path
from v42_april_port.audit import read,record,write,table,sha
from v42_capacity.common import resolve,day_folder
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_transformer_normalamps_contract'
BASE='e0cdb0d8037bfe17b76e1eb95367bf93b3a0d255'
MAY=ROOT/'docs/v42_may_b0_zero_margin_holdout'
APRIL=ROOT/'docs/v42_actual_autonomous_regcontrol_fixed_cap'
SCHEMA='V42_TRANSFORMER_NORMALAMPS_CURRENT_V1'

def csv(name,rows):table(OUT,name,rows,list(rows[0]))
