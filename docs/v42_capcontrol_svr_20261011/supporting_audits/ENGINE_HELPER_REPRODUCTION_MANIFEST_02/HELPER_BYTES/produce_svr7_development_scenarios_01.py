"""Saved-topology DTO producer, no native compilation or solve."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,'D:/v42voltage')
from v42_voltage_control import siting,integration,authority
from v42_b3_joint.contracts import digest
from v42_pr134_b1.common import record
base=Path('D:/v42_voltage_control_development_20261011')
oldpath=base/'FROZEN_SVR4_INFRASTRUCTURE_03/SCENARIO.json'
ipath=base/'SVR_ORIGINAL_TOPOLOGY_INVENTORY.json'
old=json.loads(oldpath.read_text(encoding='utf8'))
inventory=json.loads(ipath.read_text(encoding='utf8'))
integration.validate_scenario(old)
source_before=authority.source_files()
output=base/'SVR7_DEVELOPMENT_SCENARIOS_01'
output.mkdir(exist_ok=False)
rows=[]
for alternative in ('BUS48','BUS50'):
    scenario=copy.deepcopy(old)
    scenario['svr']=siting.additive_svr7_contract(old['svr'],inventory,alternative=alternative)
    scenario['scenario_SHA']=digest(integration.scenario_identity(scenario))
    integration.validate_scenario(scenario)
    assert scenario['svr']['units'][:4]==old['svr']['units']
    path=output/('B_SVR7_'+alternative+'.json')
    with path.open('x',encoding='utf8') as f:
        json.dump(scenario,f,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    rows.append(dict(alternative=alternative,scenario=record(path),scenario_SHA=scenario['scenario_SHA'],units=[u['id'] for u in scenario['svr']['units']],status='DEVELOPMENT_NOT_FROZEN_NOT_CANARY',Native_optimizer_calls=0,OpenDSS_compile_calls=0,OpenDSS_solve_calls=0,actual96status='NOT_RUN'))
assert authority.source_files()==source_before
manifest=dict(schema='V42_ADDITIVE_SVR7_SAVED_TOPOLOGY_SCENARIO_PRODUCTION_V1',PASS=True,source_SHA=digest(source_before),original_SVR4_scenario=record(oldpath),original_inventory=record(ipath),preserved_SVR4_units_canonical_SHA=digest(old['svr']['units']),candidates=rows,selection='NOT_FROZEN',source_edits=0,Native_optimizer_calls=0,OpenDSS_compile_calls=0,OpenDSS_solve_calls=0)
with (output/'SCENARIO_PRODUCTION_RECEIPT.json').open('x',encoding='utf8') as f:
    json.dump(manifest,f,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
print(json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2))
