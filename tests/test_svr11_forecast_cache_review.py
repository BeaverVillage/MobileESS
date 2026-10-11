"""Reuse admits only this exact input cache and rejects changed physical math."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reuse_svr11_completed import normalized_reviewed_model

OLD=Path(r'D:\v42_svr11_epoch09_20261011\v42_svr11\model.py')
NEW=Path(__file__).resolve().parents[1]/'v42_svr11/model.py'

def test_equivalent_cache_has_identical_reviewed_model_ast():
    assert normalized_reviewed_model(OLD.read_text())==normalized_reviewed_model(NEW.read_text())

@pytest.mark.parametrize('before,after',[
    ('_set_load(engine,name,p,q)','_set_load(engine,name,p*1.01,q)'),
    ('background.gross_q_kvar_96[t]','background.gross_q_kvar_96[0]'),
    ('for row in native.loads:', 'for row in reversed(native.loads):'),
    ('totals_by_slot=_forecast_native_totals(native,bg)', 'totals_by_slot=_forecast_native_totals(native,actual)'),
    ('_apply_forecast_native(e,native,totals_by_slot,t)', '_apply_forecast_native(e,native,totals_by_slot,0)'),
])
def test_rejects_altered_cache_values_order_or_forecast_source(before,after):
    text=NEW.read_text();assert before in text
    with pytest.raises(ValueError,match='REUSE_UNREVIEWED_FORECAST_CACHE'):
        normalized_reviewed_model(text.replace(before,after))

@pytest.mark.parametrize('before,after',[
    ('(plus[k]-minus[k])/(2*d)','(plus[k]-minus[k])/d'),
    ('clock.settle_slot(e,t,capture_events=False)','clock.settle_slot(e,0,capture_events=False)'),
    ('original._set_slot(e,{**ad,\'loads\':[]},bg,p,t)', 'original._set_slot(e,{**ad,\'loads\':[]},bg,p,0)'),
])
def test_rejects_changed_sensitivity_clock_and_other_setters(before,after):
    text=NEW.read_text();assert before in text
    assert normalized_reviewed_model(text.replace(before,after))!=normalized_reviewed_model(OLD.read_text())
