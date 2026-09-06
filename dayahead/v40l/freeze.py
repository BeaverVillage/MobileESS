import sys
from .common import *

def main():
    require_prereg();verify_k0()
    assert not (OUT/'CALIBRATION_ROWS.parquet').exists(),'CALIBRATION_ALREADY_OPENED'
    files=list((ROOT/'dayahead/v40l').glob('*.py'))+list((OUT/'models').glob('*.pkl'))
    files+=[K/'models/K0_FINAL.pkl',K/'models/FINAL_K4_INTERVAL_HAZARD.pkl',ROOT/'dayahead/v40k/models.py',ROOT/'dayahead/v40k/data.py',ROOT/'dayahead/v40k/common.py',ROOT/'dayahead/v40k/protocol.py']
    files=[p for p in files if p.name not in ['closeout.py']]
    write('V40L_PRECALIBRATION_EXECUTION_FREEZE.json',{'created_at':now(),'preregistration_commit':require_prereg(),'file_SHA':{p.relative_to(ROOT).as_posix():sha(p) for p in files},
      'CPU_only':True,'calibration_opened':False,'selection_opened':False,'shadow_opened':False,'visible_development_used_for_thresholds':False,'candidate_structure_changes':0,'K0_unchanged':True},immutable=True)
    print('PRECALIBRATION_FREEZE_READY',len(files),flush=True)
if __name__=='__main__':main()
