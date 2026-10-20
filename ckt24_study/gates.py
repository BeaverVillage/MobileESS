"""Closed admission contract. No production dispatcher is imported."""
REQUIRED=('Original Network','Traffic','Spatial','Site Counts','PCC','MESS8','AIDC',
          'Baseline AC','MESS Sensitivity','AIDC Sensitivity','Model Identity','Source')

def admit(gates,day):
    if day!='2025-05-01':raise ValueError('MAY01_ONLY')
    failed=[name for name in REQUIRED if gates.get(name,{}).get('status')!='PASS']
    if failed:raise RuntimeError('PRE_SOLVER_GATES_NOT_PASSED:'+','.join(failed))
    return dict(allowed=True,day=day,arms=['B0','B1','B2','B3'],
                new_Ckt24_A1_required=True,legacy_IEEE123_A1_UB_LB_checkpoint_reuse=False)
