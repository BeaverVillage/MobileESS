from pathlib import Path
import os
CODE=Path(__file__).resolve().parent
REPO=CODE.parent
ROOT=Path(os.environ.get('V44_ITERATION2_RUNTIME','D:/MobileESS_V44/runtime/V44_iteration2'))
DOC=ROOT/'DOCUMENTS';OPS=ROOT/'OPERATIONS'
SOURCE=Path(os.environ.get('V44_ITERATION2_SOURCE','D:/v44_r022_rowgen_20261017'))
PROFILE=Path('D:/v44_mess825_20261022')
B2_HOME=Path('D:/v44_b2_iofix_r2_20261022')
B2_ROOT=Path('D:/MobileESS_V44/runtime/equipment_versions/V44_R043_MESS_TX825_THERMAL_V1/campaign007_may22_31_B2_fixedB3_followup')
OLD=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1')
DAYS=tuple(f'2025-05-{n:02d}' for n in range(1,32))
STAGES=('M2','A3','M3','A4','M4')
CORE_STAGE={s:('A2' if s.startswith('A') else 'M2') for s in STAGES}
PARENT={'M2':'A2','A3':'M2','M3':'A3','A4':'M3','M4':'A4'}
EQUIPMENT='V44_R043_MESS_TX825_THERMAL_V1'
FLEET=('MESS01','MESS02','MESS03','MESS04')
LOCKS=tuple(map(Path,('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock',
 'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_1.lock',
 'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_2.lock',
 'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_3.lock',
 'D:/V42_UNIFIED_HEAVY_WORKER.lock','D:/MobileESS_V43/runtime/V43_HEAVY_WORKER.lock')))

def campaign(day):
 n=int(day[-2:])
 return OLD/('campaign004' if n<=7 else 'campaign005_may08_14' if n<=14 else 'campaign006_may15_21' if n<=21 else 'campaign007_may22_31')

def band(stage):
 if stage in ('M1','M2','M3'):return (.955,1.045)
 if stage in ('M4','ACTUAL','FRESH'):return (.95,1.05)
 raise ValueError('No M voltage policy for '+stage)
