"""Compile the original per-object API loop without changing its call order."""
import sys, ctypes
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent/'ACTUAL_NATIVE_RUNTIME_20260922'))
from numba import njit
import dss_python_backend
import actual_electrical_speed as speed

DLL = ctypes.CDLL(str(Path(dss_python_backend.__file__).parent/'dss_capi.dll'))
def function(name, result, *args):
    fn = getattr(DLL, 'ctx_'+name)
    fn.restype = result
    fn.argtypes = list(args)
    return fn
ptr, dbl = ctypes.c_void_p, ctypes.c_double
load_name = function('Loads_Set_Name', None, ptr, ptr)
load_kw = function('Loads_Set_kW', None, ptr, dbl)
load_kvar = function('Loads_Set_kvar', None, ptr, dbl)
get_kw = function('Loads_Get_kW', dbl, ptr)
get_kvar = function('Loads_Get_kvar', dbl, ptr)
get_pf = function('Loads_Get_PF', dbl, ptr)
gen_name = function('Generators_Set_Name', None, ptr, ptr)
enabled = function('CktElement_Set_Enabled', None, ptr, ctypes.c_uint16)
gen_kw = function('Generators_Set_kW', None, ptr, dbl)
gen_kvar = function('Generators_Set_kvar', None, ptr, dbl)

@njit(fastmath=False)
def native_loop(ctx, names, pvnames, P, Q, PF, factor, ratio, solar, error):
    for i in range(len(P)):
        load_name(ctx, names[i]); assert error[0] == 0
        load_kw(ctx, factor*P[i]); assert error[0] == 0
        load_kvar(ctx, factor*Q[i]); assert error[0] == 0
        kw = get_kw(ctx); assert error[0] == 0
        assert abs(kw-factor*P[i]) < 1e-12
        kvar = get_kvar(ctx); assert error[0] == 0
        assert abs(kvar-factor*Q[i]) < 1e-12
        pf = get_pf(ctx); assert error[0] == 0
        assert abs(pf-PF[i]) < 1e-12
        gen_name(ctx, pvnames[i]); assert error[0] == 0
        val = .552*ratio*P[i]*solar
        enabled(ctx, val > 0); assert error[0] == 0
        if val > 0:
            gen_kw(ctx, val); assert error[0] == 0
            gen_kvar(ctx, 0.); assert error[0] == 0

class NativeInputEngine(speed.CachedMetadataEngine):
    def __init__(self, folder):
        super().__init__(folder)
        api = self.d._api_util
        ffi = api.ffi
        self.ctx = int(ffi.cast('uintptr_t', api.ctx))
        self.names_buffer = [ffi.new('char[]', r['load'].encode()) for r in self.loads]
        self.pvnames_buffer = [ffi.new('char[]', f'op8500_pv_{i:04d}'.encode()) for i in range(len(self.loads))]
        self.names = np.array([int(ffi.cast('uintptr_t', p)) for p in self.names_buffer], dtype=np.uintp)
        self.pvnames = np.array([int(ffi.cast('uintptr_t', p)) for p in self.pvnames_buffer], dtype=np.uintp)
        self.pf = np.array([r['base_pf'] for r in self.loads])
        self.error = np.frombuffer(ffi.buffer(self.d.Loads._errorPtr, 4), dtype=np.int32)

    def inputs(self, t, x=None):
        d = self.d
        factor = float(.552*self.md[t])
        d.Solution.LoadMult(1.)
        d.Solution.Hour(t//4)
        d.Solution.Seconds((t%4)*900)
        native_loop(self.ctx, self.names, self.pvnames, self.P, self.Q, self.pf,
                    factor, float(self.ratio), float(self.mpv[t]), self.error)
        for j in range(12):
            d.Loads.Name(f'op8500_aidc{j+1:02d}')
            d.Loads.kW(float(self.ap[t,j])); d.Loads.kvar(float(self.aq[t,j]))
        base = np.r_[self.ap[t], np.zeros(48)]
        self.x = base.copy() if x is None else np.asarray(x).copy()
        self.controls(self.x)

def install(enabled=True):
    speed.electrical.Engine = NativeInputEngine if enabled else speed.OriginalEngine
