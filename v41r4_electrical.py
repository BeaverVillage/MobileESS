"""Final 1.15 physics binding. No alpha search and no numerical-method changes."""
from fast_prepare import *
import numpy as np
import importlib, inspect, textwrap

MAY_RUN=ROOT/'frozen_artifacts/v41r4_may'
MAY_OUT=MAY_RUN/'audit'
CONFIGURED_DAY=None

def configure(day):
    global CONFIGURED_DAY
    assert day in [f'2025-05-{n:02}' for n in range(1,32)]
    from v41r4_io import install
    install()
    from dayahead.v41 import data,electrical
    if CONFIGURED_DAY is not None:
        assert CONFIGURED_DAY==day;return electrical
    from dayahead.v41r2 import authority as r2
    from dayahead.v41r3 import authority as v3
    from dayahead.paper_analysis.storage import write_npz
    from dayahead.v40h.identity import bind,verify_bound_files
    data.RUNTIME=RUN if day==DAY else ROOT/'frozen_artifacts/v41r3_may'
    electrical.RUNTIME=MAY_RUN
    r2.DAY=day;r2.OUT=MAY_OUT/day
    v3.DAY=day;v3.SCALE=MAY_OUT/day;v3.OUT=MAY_OUT
    # Preserve the exact scaler, changing only the now-final authority literal.
    source=inspect.getsource(v3.scale_background)
    assert source.count("authority['selected_alpha_BG']==1.6")==1
    source=source.replace("authority['selected_alpha_BG']==1.6","authority['selected_alpha_BG']==1.15")
    ns=dict(vars(v3));exec(compile(source,__file__+'::scale_background','exec'),ns)
    original_scale=ns['scale_background']
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
        assert result.evidence['alpha_BG']==1.15
        return result
    v3.scale_background=scale
    # Native Actual uses the same frozen settings and within-day sequential states.
    importlib.import_module('dayahead.v41r3.native_actual').OUT=MAY_OUT
    original_identity=electrical.identity
    def identity(target):
        assert target==day
        old=original_identity(target);values=old['identity']['inputs'].copy()
        values['V41R4_FINAL_DATE_BINDING']=dict(day=day,source=record(__file__),
            io_source=record(ROOT/'v41r4_io.py'),input_preparation=record(MAY_OUT/day/'INPUT_PREPARATION.json'),
            alpha_BG=1.15,scaler_source=record(ROOT/'dayahead/v41r3/authority.py'),
            scaler_change='Exact final-authority assertion 1.6 -> 1.15 only; P/Q multiplication unchanged',
            robust_scenarios=0,quantile_voltage_margin=0,forecast_error_correction=False,ML_calls=0)
        verify_bound_files(values)
        return bind('V41_ELECTRICAL_GENERATION_V1',values,tuple(values))
    electrical.identity=identity
    CONFIGURED_DAY=day
    return electrical

