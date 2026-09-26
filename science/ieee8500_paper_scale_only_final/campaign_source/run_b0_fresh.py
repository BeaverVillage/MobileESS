"""Independent 96-slot B0 Fresh replay before opening B2."""
from bootstrap import *


def main():
    assert read(H/'B0/COMPLETE.json')['status']=='PASS'
    with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:pcc=z['pcc'].copy()
    result=exact(pcc,(),H/'B0/Fresh')
    assert result['status']=='PASS'
    baseline=read(H/'B0/DA_exact/AC_VALIDATION.json')
    assert all(abs(result['metrics'][key]-baseline['metrics'][key])<1e-8 for key in baseline['metrics'])
    save(H/'B0/FRESH_GATE.json',dict(status='PASS',report=record(H/'B0/Fresh/AC_VALIDATION.json'),
         independent_full_96_slot_replay=True))
    print('B0_FRESH_PASS',result['metrics']['max_phase_line_loading_pu'],flush=True)


if __name__=='__main__':main()
