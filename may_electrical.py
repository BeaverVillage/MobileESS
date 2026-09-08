"""Date-scoped May electrical binding; original numerical routines unchanged."""
from fast_prepare import *
import numpy as np

MAY_RUN=ROOT/'frozen_artifacts/v41r3_may'
MAY_OUT=OUT/'may_campaign'
CONFIGURED_DAY=None

def configure(day):
    global CONFIGURED_DAY
    assert day in [f'2025-05-{n:02}' for n in range(1,32)] and day!=DAY
    from dayahead.v41 import data,electrical
    if CONFIGURED_DAY is not None:
        assert CONFIGURED_DAY==day
        return electrical
    from dayahead.v41r2 import authority as r2
    from dayahead.v41r3 import authority as v3
    from dayahead.paper_analysis.storage import write_npz
    from dayahead.v40h.identity import bind,verify_bound_files
    data.RUNTIME=MAY_RUN;electrical.RUNTIME=MAY_RUN
    r2.DAY=day;r2.OUT=MAY_OUT/day
    v3.DAY=day;v3.SCALE=MAY_OUT/day
    original_scale=v3.scale_background
    def scale(background,stage):
        assert stage in ('DAYAHEAD','ACTUAL')
        path=v3.SCALE/'inputs'/f'ORIGINAL_{stage}_BACKGROUND.npz'
        keys=sorted(set().union(*(set(r) for r in background.gross_p_kw_96)))
        arrays=dict(bus_phase_keys=np.array([b+'::'+p for b,p in keys]))
        for name,field in [('gross_P_kw','gross_p_kw_96'),('gross_Q_kvar','gross_q_kvar_96'),('PV_P_kw','pv_generation_kw_96')]:
            arrays[name]=np.asarray([[r.get(k,0.) for k in keys] for r in getattr(background,field)])
        if path.exists():
            with np.load(path) as z:assert all(np.array_equal(z[k],v) for k,v in arrays.items()),'DAILY_BACKGROUND_INPUT_DRIFT'
        else:write_npz(path,**arrays)
        result=original_scale(background,stage)
        assert result.pv_generation_kw_96==background.pv_generation_kw_96
        return result
    v3.scale_background=scale
    original_identity=electrical.identity
    def identity(target):
        assert target==day
        old=original_identity(target)
        values=old['identity']['inputs'].copy()
        values['V41R3_MAY_DATE_BINDING']=dict(day=day,source=record(__file__),input_preparation=record(MAY_OUT/day/'INPUT_PREPARATION.json'),alpha_BG=1.6,unchanged_numerical_scaling_source=record(ROOT/'dayahead/v41r3/authority.py'),dynamic_bindings=['RUNTIME output path','per-day pre-AC B0 PCC path','per-day original background receipt path'],ML_calls=0)
        verify_bound_files(values)
        return bind('V41_ELECTRICAL_GENERATION_V1',values,tuple(values))
    electrical.identity=identity
    CONFIGURED_DAY=day
    return electrical

def main(day):
    gate=read(OUT/'V41R3_FAST_POWER_SCALE_FREEZE.json')
    assert gate['classification']=='FINAL_FOUR_METHOD_B1' and gate['May_launch_gate']=='PASS'
    electrical=configure(day)
    ctx=electrical.generate(day)
    print('MAY_ELECTRICAL_PASS',day,ctx.v41_electrical_identity,flush=True)
    ctx.electrical.voltage.close();ctx.electrical.current.close()

if __name__=='__main__':
    import sys
    main(sys.argv[1])
