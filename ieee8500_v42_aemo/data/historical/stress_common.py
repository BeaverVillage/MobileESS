import sys,json
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;ROOT=H.parent;PREV=ROOT/'IEEE8500_source_grid_compatibility_20260911'
sys.path.insert(0,str(PREV))
import screen_source_grid as base
from stress_control_telemetry import control_state
old=base.old;frozen=base.frozen;OLD=base.OLD;PCC=base.PCC
read,save,table,sha,record=base.read,base.save,base.table,base.sha,base.record
KEYS=base.KEYS;VIOLATIONS=base.VIOLATIONS;input_authorities=base.input_authorities;extrema_row=base.extrema_row
def overlay_path(source,vreg):return H/'overlays'/f'Source_{source:.4f}_Vreg_{vreg:.1f}.dss'
def case_folder(source,vreg,a):return H/'screen'/f'source_{source:.4f}'/f'vreg_{vreg:.1f}'/f'alpha_{a:.2f}'
def ranking_key(r):return (abs(r['max_phase_line_loading_pu']-.85),abs(r['vreg_V']-125.),abs(r['source_pu']-1.05),-r['alpha'])
def summarize(source,a,rows,elapsed):
    result=base.summarize(source,a,rows,elapsed);result['vreg_V']=rows[0]['vreg_V'];result['target_line_loading_pu']=.85;result['target_absolute_error_pu']=abs(result['max_phase_line_loading_pu']-.85);result['lexicographic_key']=list(ranking_key(result));return result
def check_freeze():
    mf=H/'PRE_EXECUTION_FREEZE_MANIFEST.json';assert sha(mf)==(H/'PRE_EXECUTION_FREEZE_MANIFEST.sha256').read_text().split()[0]
    for r in read(mf)['bound_files']:assert sha(Path(r['path']))==r['sha256'],r['path']
def allowed_audit(native,adapted,source,vreg):
    diffs=old.differences(native,adapted);regs={n for n in native if n.startswith('regcontrol.')};feed={'regcontrol.feeder_rega','regcontrol.feeder_regb','regcontrol.feeder_regc'};seen=set();src=[]
    assert len(regs)==12
    for r in diffs:
        n,k=r['element'],r['property'].lower()
        if n in regs:
            assert k=='vreg' and float(r['before'])==(126.5 if n in feed else 125.) and float(r['after'])==vreg;seen.add(n)
        elif n=='capacitor.capbank3':assert k in ['enabled','__element_enabled__']
        else:assert n=='vsource.source' and k=='pu' and float(r['before'])==1.05 and float(r['after'])==source;src.append(r)
    assert seen==(feed if vreg==125. else regs) and not adapted['capacitor.capbank3']['__element_enabled__'] and len(src)==1
    return dict(status='PASS',source_pu=source,vreg_V=vreg,regcontrol_count=12,exact_static_differences=diffs,native_config_sha256=frozen.digest(native),adapted_config_sha256=frozen.digest(adapted),allowed_static_changes='source pu, uniform forward Vreg, previously authorized CAPBank3 OFF only',all_other_properties_preserved=True,canonical_reproduction=False)
