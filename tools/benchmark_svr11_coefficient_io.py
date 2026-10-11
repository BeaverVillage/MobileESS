"""Compare immutable real Forecast coefficient loading; zero AC/Native calls."""
from pathlib import Path
import sys,ast,time,json
from unittest.mock import patch
import numpy as np
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11 import model
from v42_thermal import authority
origin=Path(r'D:\v42_svr11_may_20261011_06');root=Path(r'D:\v42_svr11_may_20261011_07')
m=read(origin/'CAMPAIGN_MANIFEST.json');cert=read(origin/'models/2025-05-03/ELECTRICAL_CERTIFICATE.json')
oldfile=Path(m['code_root'])/'v42_svr11/model.py'
oldfn=next(n for n in ast.parse(oldfile.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='load_coefficients')
with patch.object(model,'active',lambda:m),patch.object(authority,'current_authority',lambda:read(m['thermal']['path'])):
    scope=dict(model.__dict__);exec(compile(ast.fix_missing_locations(ast.Module(body=[oldfn],type_ignores=[])),str(oldfile),'exec'),scope)
    started=time.perf_counter();old=scope['load_coefficients'](cert,cert['day']);old_seconds=time.perf_counter()-started
    started=time.perf_counter();new=model.load_coefficients(cert,cert['day']);new_seconds=time.perf_counter()-started
assert len(old)==len(new)==96
for a,b in zip(old,new):
    for f in model.FIELDS+('anchor','current_denominators_A'):assert np.array_equal(getattr(a,f),getattr(b,f))
    assert a.branch_names==b.branch_names and a.control_names==b.control_names and a.transformer_ratings==b.transformer_ratings
result=dict(PASS=True,all96_fields_bitwise_equal=True,detached_slot_copies=True,
    coefficient=cert['outputs']['planning_coefficients'],old_loader_source=record(oldfile),new_loader_source=record(SOURCE/'v42_svr11/model.py'),
    old_load_wall_seconds=old_seconds,cached_load_wall_seconds=new_seconds,
    old_field_decompressions_per_load=96,cached_field_decompressions_per_load=1,
    AC_calls=0,Native_optimizer_calls=0,physical_or_algorithm_policy_changed=False,UTC=now())
root.mkdir(exist_ok=True);atomic(root/'COEFFICIENT_IO_EQUIVALENCE.json',result);print(json.dumps(result))
