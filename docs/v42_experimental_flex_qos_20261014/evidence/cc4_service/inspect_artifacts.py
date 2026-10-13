from pathlib import Path
import json
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
base=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
a=read(base/'A2/A_RESULT.json')
print(json.dumps(dict(a_keys=list(a),nominal_service_sample=list(a['CC4_service'].items())[:3],
    carry_sample=list(a['CC4_carryout'].items())[:3],
    reserve_keys=[k for k in a if 'reserve' in k or 'shortfall' in k],
    freeze_keys=list(read('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/SOURCE_FREEZE_DDAY_GRID_V5.json')),
    planning_keys=list(read(base/'PLANNING_FREEZE.json'))),ensure_ascii=False))
