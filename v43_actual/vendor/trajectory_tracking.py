from copy import deepcopy
from pathlib import Path
import math
import json
import numpy as np
from .actual import _require_public_metadata
from .policy import digest
from .reservation_state import union_job_segments


def require_tracking_public(value):
    _require_public_metadata(value)
    if isinstance(value,dict):
        if {'future_job_uid','future_unknown_uids','actual_duration_seconds','completion_time'} & value.keys():
            raise ValueError('PRIVATE_REALIZATION_IN_TRACKING_METADATA')
        for child in value.values(): require_tracking_public(child)
    elif isinstance(value,(list,tuple)):
        for child in value: require_tracking_public(child)


def service_integral(sites, segments, begin):
    """GPU occupancy averaged over each 900s slot; sum/4 is nominal GPUh."""
    out = np.zeros((96, len(sites)))
    for seg in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
        site = seg['resource'][4:]
        a, b = seg['begin']-begin, seg['end']-begin
        for t in range(max(0, int(a//900)), min(96, int(math.ceil(b/900)))):
            overlap = max(0., min(b, (t+1)*900)-max(a, t*900))
            out[t, sites.index(site)] += seg['quantity']*overlap/900
    return out


class TrackingReference:
    def __init__(self, known, unknown, it, p, q, *, sites, begin, commands, identity):
        self.sites = tuple(sites); self.begin = float(begin)
        self._commands = deepcopy(commands); self.identity = deepcopy(identity)
        self.arrays = {}
        for name, value in dict(G_Known_Plan=known, G_Unknown_Q50_Plan=unknown,
                                IT_Plan=it, PCC_P_Plan=p, PCC_Q_Plan=q).items():
            a = np.array(value, dtype=float, copy=True)
            if a.shape != (96, len(sites)) or not np.isfinite(a).all():
                raise ValueError('TRACKING_REFERENCE_FULL96_FINITE_AXIS')
            if name.startswith('G_') and np.any(a < 0):
                raise ValueError('NONNEGATIVE_GPU_TARGET')
            a.setflags(write=False); self.arrays[name] = a
        total = self.arrays['G_Known_Plan'] + self.arrays['G_Unknown_Q50_Plan']
        total.setflags(write=False); self.arrays['G_Total_Plan'] = total
        self.sha = self._digest()

    @property
    def commands(self): return deepcopy(self._commands)

    def _digest(self):
        return digest(dict(arrays={k:a.tolist() for k,a in self.arrays.items()},
                           commands=self._commands, sites=self.sites, begin=self.begin,
                           identity=self.identity))

    def require_immutable(self):
        if self._digest() != self.sha: raise ValueError('PLANNING_TARGET_SHA_DRIFT')

    def save(self, path):
        self.require_immutable()
        extras={}
        for name in ('CC4_Q50','CC4_Q90','Timing_CDF_Q10','Timing_CDF_Q90'):
            if name in self.identity: extras[name]=np.asarray(self.identity[name],float)
        np.savez_compressed(Path(path), **self.arrays, sites=np.asarray(self.sites),
                            begin_seconds=self.begin, target_sha=self.sha,**extras,
                            Known_UID_Schedule_JSON=json.dumps(self._commands,sort_keys=True),
                            Nominal_Service_Carry_JSON=json.dumps({k:self.identity[k] for k in
                                ('CC4_service','CC4_carryout') if k in self.identity},sort_keys=True))
