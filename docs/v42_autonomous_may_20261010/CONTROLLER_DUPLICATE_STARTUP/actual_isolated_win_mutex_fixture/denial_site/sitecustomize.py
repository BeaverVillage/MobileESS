import gurobipy as gp
from pathlib import Path
import json
def denied(*args,**kwargs):
    Path('D:\\v42_controller_duplicate_startup_repair_20261010_01\\pytest_full\\test_actual_windows_owned_supe0\\CHILD_NATIVE_ENTRY_ATTEMPTS.json').write_text('DENIED ENTRY',encoding='utf-8')
    raise AssertionError('ISOLATED_CHILD_NATIVE_MODEL_ENTRY_DENIED')
gp.Model.__init__=denied
gp.Model.optimize=denied
Path('D:\\v42_controller_duplicate_startup_repair_20261010_01\\pytest_full\\test_actual_windows_owned_supe0\\CHILD_NATIVE_DENIAL_INSTALLED.json').write_text(json.dumps({'Model_init_denied':True,'Model_optimize_denied':True}),encoding='utf-8')
