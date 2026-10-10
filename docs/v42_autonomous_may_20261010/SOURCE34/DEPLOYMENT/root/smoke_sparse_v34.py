"""Import and hash the immutable checkout without constructing a model."""
import json,sys
from pathlib import Path
sys.path.insert(0,'D:/v42run34')
import gurobipy as gp
from unittest.mock import patch
CODE=Path('D:/v42run34');ROOT=Path('D:/v42_may_restart_20261010_02')
attempts=[];original_optimize=gp.Model.optimize
class ForbiddenModel:
    optimize=original_optimize
    def __init__(self,*args,**kwargs):
        attempts.append(dict(args=repr(args),kwargs=repr(kwargs)))
        raise AssertionError('SPARSE_SOURCE34_REAL_MODEL_FORBIDDEN')
with patch.object(gp,'Model',ForbiddenModel):
    from v42_autonomous_b2 import worker,pricing_cache,rmp_presolve,f1_basis
    from v42_b2_seed_recovery_v19.common import read,record,digest,atomic,now
    modules=(worker,pricing_cache,rmp_presolve,f1_basis)
    for module in modules:assert Path(module.__file__).resolve().is_relative_to(CODE)
    execution=worker.sources();assert len(execution)==98
    template=read(ROOT/'autonomous/V34_VALIDATION_BINDING_TEMPLATE.json')
    assert digest(execution)==template['repair_source_SHA']
    for field in ('source_files','original_source_files','sparse_required_additional_assets'):
        for row in template[field]:
            relative=Path(row['path']).relative_to(Path('D:/MobileESS_v42_autonomous'))
            actual=record(CODE/relative)
            assert (actual['sha256'],actual['bytes'])==(row['sha256'],row['bytes'])
assert not attempts
target=ROOT/'autonomous/V34_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json';assert not target.exists()
atomic(target,dict(PASS=True,UTC=now(),schema='V42_SOURCE34_SPARSE_NATIVE_DENIED_IMPORT_SMOKE',
    code_root=str(CODE),execution_SHA=digest(execution),execution_source_count=98,
    original_scientific_source_count=1007,additional_asset_count=5,
    imported_modules=[record(module.__file__) for module in modules],
    real_model_constructor_attempts=attempts,model_constructions=0,Native_optimize_calls=0,
    validation_template=record(ROOT/'autonomous/V34_VALIDATION_BINDING_TEMPLATE.json'),
    diagnostic_deny_class_is_not_production_raw_model_provenance=True,
    actual_sealed_request_factories_still_required=True,source_script=record(__file__)))
print(json.dumps(dict(PASS=True,receipt=record(target)),ensure_ascii=False))
