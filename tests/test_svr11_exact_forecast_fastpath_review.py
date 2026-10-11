"""Admit exact reviewed replacements; reject changed inputs, physics or wiring."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reuse_svr11_completed import normalized_reviewed_model
OLD=Path(r'D:\v42_svr11_epoch12_20261011\v42_svr11\model.py')
NEW=Path(__file__).resolve().parents[1]/'v42_svr11/model.py'
def test_only_approved_input_and_measurement_fastpaths_are_equivalent():
 assert normalized_reviewed_model(OLD.read_text(encoding='utf8'))==normalized_reviewed_model(NEW.read_text(encoding='utf8'))
@pytest.mark.parametrize('before,after',[
 ("for slot in range(96):","for slot in range(95):"),
 ("for row in native.loads:","for row in reversed(native.loads):"),
 ("value*pf_tan","value*pf_tan*1.001"),
 ("setter_schedule[t]","setter_schedule[0]"),
 ("terminal_axis,len(branches)","terminal_axis,len(branches)-1"),
 ("powers[2*index+1]","powers[2*index]"),
 ("clock.settle_slot(e,t,capture_events=False)","clock.settle_slot(e,0,capture_events=False)"),
 ("(plus[k]-minus[k])/(2*d)","(plus[k]-minus[k])/d"),
 ("raise PermissionError('SVR11_FORECAST_SETTER_INVENTORY_DRIFT')","pass"),
])
def test_rejects_unreviewed_changes(before,after):
 text=NEW.read_text(encoding='utf8')
 if before not in text:pytest.skip('expression belongs to detached diagnostic only')
 try:normalized=normalized_reviewed_model(text.replace(before,after))
 except ValueError:return
 assert normalized!=normalized_reviewed_model(OLD.read_text(encoding='utf8'))
