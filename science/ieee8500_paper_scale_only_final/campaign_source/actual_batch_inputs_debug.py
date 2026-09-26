"""Bulk native input setters; fresh contexts and causal solves remain unchanged."""
import numpy as np
import actual_electrical_speed as speed


class BatchInputEngine(speed.CachedMetadataEngine):
    def __init__(self, folder):
        super().__init__(folder)
        self.api = self.d._api_util
        self.lib = self.api.lib
        self.ffi = self.api.ffi
        classes = {name.lower(): i + 1 for i, name in enumerate(self.d.Basic.Classes())}
        def handles(cls, names):
            ptrs = [self.lib.Obj_GetHandleByName(self.api.ctx, classes[cls], n.encode()) for n in names]
            assert all(p != self.ffi.NULL for p in ptrs)
            return self.ffi.new('void*[]', ptrs), len(ptrs)
        self.load_batch = handles('load', [r['load'] for r in self.loads])
        self.pv_batch = handles('generator', [f'op8500_pv_{i:04d}' for i in range(len(self.loads))])
        self.base_pf = np.array([r['base_pf'] for r in self.loads])

    def set_values(self, batch, name, values):
        values = np.ascontiguousarray(values, dtype=np.float64)
        self.lib.Batch_Float64ArrayS(batch[0], batch[1], name, 0, self.ffi.from_buffer('double[]', values), 0)

    def get_values(self, batch, name):
        return self.api.get_float64_array(self.lib.Batch_GetFloat64S, batch[0], batch[1], name)

    def inputs(self, t, x=None):
        d = self.d
        factor = float(.552 * self.md[t])
        d.Solution.LoadMult(1.)
        d.Solution.Hour(t // 4)
        d.Solution.Seconds((t % 4) * 900)
        p, q = factor * self.P, factor * self.Q
        print("self.set_values(self.load_batch, b'kw', p)", flush=True)
        self.set_values(self.load_batch, b'kw', p)
        print("self.set_values(self.load_batch, b'kvar', q)", flush=True)
        self.set_values(self.load_batch, b'kvar', q)
        print("assert np.max(np.abs(self.get_values(self.load_batch, b'kw') - p)) < 1e-12", flush=True)
        assert np.max(np.abs(self.get_values(self.load_batch, b'kw') - p)) < 1e-12
        print("assert np.max(np.abs(self.get_values(self.load_batch, b'kvar') - q)) < 1e-12", flush=True)
        assert np.max(np.abs(self.get_values(self.load_batch, b'kvar') - q)) < 1e-12
        print("assert np.max(np.abs(self.get_values(self.load_batch, b'pf') - self.base_pf)) < 1e-12", flush=True)
        assert np.max(np.abs(self.get_values(self.load_batch, b'pf') - self.base_pf)) < 1e-12
        # Keep the original floating-point multiplication order.
        print('pv = .552 * self.ratio * self.P * self.mpv[t]', flush=True)
        pv = .552 * self.ratio * self.P * self.mpv[t]
        print('enabled = np.ascontiguousarray(pv > 0, dtype=np.int32)', flush=True)
        enabled = np.ascontiguousarray(pv > 0, dtype=np.int32)
        print("self.lib.Batch_Int32ArrayS(self.pv_batch[0], self.pv_batch[1], b'enabled', 0,", flush=True)
        self.lib.Batch_Int32ArrayS(self.pv_batch[0], self.pv_batch[1], b'enabled', 0,
                                  self.ffi.from_buffer('int32_t[]', enabled), 0)
        print('if enabled.all():', flush=True)
        if enabled.all():
            print("self.set_values(self.pv_batch, b'kw', pv)", flush=True)
            self.set_values(self.pv_batch, b'kw', pv)
            self.lib.Batch_Float64S(self.pv_batch[0], self.pv_batch[1], b'kvar', 0, 0., 0)
        elif enabled.any():
            for i in np.flatnonzero(enabled):
                d.Generators.Name(f'op8500_pv_{i:04d}')
                d.Generators.kW(float(pv[i]))
                d.Generators.kvar(0.)
        print('for j in range(12):', flush=True)
        for j in range(12):
            d.Loads.Name(f'op8500_aidc{j+1:02d}')
            d.Loads.kW(float(self.ap[t, j]))
            d.Loads.kvar(float(self.aq[t, j]))
        assert d.Error.Number() == 0
        base = np.r_[self.ap[t], np.zeros(48)]
        self.x = base.copy() if x is None else np.asarray(x).copy()
        print('self.controls(self.x)', flush=True)
        self.controls(self.x)


def install(enabled=True):
    speed.electrical.Engine = BatchInputEngine if enabled else speed.OriginalEngine
