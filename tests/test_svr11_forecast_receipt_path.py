"""Final Forecast source recheck must use the same exact contract as checked()."""
import ast
from pathlib import Path
import pytest
from v42_pr134_b1.common import read,record
from v42_voltage_control import forecast
from v42_voltage_control.authority import checked

def final_condition():
    node=next(n for n in ast.walk(ast.parse(Path(forecast.__file__).read_text()))
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require'
        and len(n.args)==2 and isinstance(n.args[1],ast.Constant)
        and n.args[1].value=='CAPCONTROL_SVR_FORECAST_SOURCE_OR_DECISION_MUTATED')
    return compile(ast.fix_missing_locations(ast.Expression(node.args[0])),'final_actual_guard','eval')

def passes(receipts):
    return eval(final_condition(),{'record':record,'Path':Path,'source_receipts':receipts,'sources':[]})

def test_real_historical_junction_same_SHA_and_bytes_is_accepted():
    source=Path(r'D:\v42_svr11_may_20261011_06\raw\2025-05-03\SOURCE_PROVENANCE.json')
    r=read(source)['daily_sources']['aemo_forecast.json']
    assert r['path']!=str(Path(r['path']).resolve()) and record(r['path'])!=r
    assert checked(r)==Path(r['path']).resolve() and passes([r])

@pytest.mark.parametrize('mutation',['sha256','bytes','path'])
def test_real_content_or_distinct_file_mutation_remains_rejected(tmp_path,mutation):
    p=tmp_path/'source.json';p.write_bytes(b'original');r=record(p)
    assert passes([r])
    if mutation=='sha256':r['sha256']='0'*64
    elif mutation=='bytes':r['bytes']+=1
    else:
        other=tmp_path/'different.json';other.write_bytes(b'changed');r['path']=str(other)
    assert not passes([r])

def test_reuse_review_is_limited_to_exact_final_path_guard():
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
    from reuse_svr11_completed import normalized_forecast_receipt_guard
    old=Path(r'D:\v42_svr11_epoch06_20261011\v42_voltage_control\forecast.py').read_text()
    new=Path(forecast.__file__).read_text()
    assert normalized_forecast_receipt_guard(old)==normalized_forecast_receipt_guard(new)
    assert normalized_forecast_receipt_guard(old)!=normalized_forecast_receipt_guard(new.replace('len(controls) == 96','len(controls) == 95'))
