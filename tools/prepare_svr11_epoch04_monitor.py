"""Prepare corrected-historical evidence and official pending successor ledger."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.controller import initial
root=Path(r'D:\v42_svr11_may_20261011_04');old=Path(r'D:\v42_svr11_may_20261011_02')
m=read(root/'CAMPAIGN_MANIFEST.json')
if not (root/'CAMPAIGN_LEDGER.json').exists():
    atomic(root/'CAMPAIGN_LEDGER.json',dict(initial(),status='WAITING_PREDECESSOR_DRAIN',source_SHA=m['execution_SHA'],UTC=now()))
proof=old/'NORMALAMPS_FOUR_DAY_REASSESSMENT.json';p=read(proof)
assert p['all_four_contract_reassessment_PASS']
atomic(root/'NORMALAMPS_CLASSIFICATION_CORRECTION.json',dict(schema='SVR11_IMMUTABLE_CLASSIFICATION_CORRECTION_V1',
    corrected_historical_dates={r['day']:'PASS' for r in p['dates']},
    measurement_Source_SHA=read(old/'CAMPAIGN_MANIFEST.json')['execution_SHA'],classifier_Source_SHA=m['execution_SHA'],
    original_transformer_current_authority=m['original_transformer_current_authority'],complete_96_slot_independent_reassessment=record(proof),
    new_epoch_official_results_promoted=False,old_results_and_ledger_preserved=True,UTC=now()))
