"""Cache immutable feeder metadata; preserve every physical clean-prefix solve."""
import json,time,hashlib
from pathlib import Path
import numpy as np
import electrical_engine as electrical

OriginalEngine=electrical.Engine
METADATA=None
COUNTS=dict(cold_metadata_builds=0,cached_metadata_builds=0)
FIELDS=('native','loads','ax','nodes','P','Q','md','mpv','ratio','ap','aq','inv','adapted','services','tolerance')


class CachedMetadataEngine(OriginalEngine):
    def __init__(self,folder):
        global METADATA
        folder=Path(folder)
        if METADATA is None:
            super().__init__(folder)
            METADATA={name:getattr(self,name) for name in FIELDS}
            COUNTS['cold_metadata_builds']+=1
            return
        # No DSS context/solution, voltage, tap, capacitor or control-queue state
        # is cached. Every trial compiles and solves its full causal prefix.
        self.d=d=electrical.remapped_engine(folder)
        for name,value in METADATA.items():setattr(self,name,value)
        d.Text.Command(f'Redirect "{electrical.s.overlay_path(1.04,123.5)}"')
        resources=electrical.s.frozen.add_resources(d,self.loads,self.ratio,self.inv)
        electrical.save(folder/'RESOURCE_BINDING.json',dict(PV_ratio=self.ratio,
            resource_text_sha256=hashlib.sha256(resources.encode()).hexdigest()))
        by={(r['PCC_role'],r['location_id']):r for r in self.inv}
        for sid in self.services:
            location='A'+sid if sid.startswith('IDC') else sid;r=by['MESS',location]
            d.Text.Command(f'New Load.np8500_mess_{sid.lower()} phases=3 bus1={r["PCC_bus"]}.1.2.3 conn=wye kv=0.48 kW=0 kvar=0 Model=1 Vminpu=0.85 Vmaxpu=1.15 Status=Fixed')
        assert d.Circuit.NumBuses()==4912 and d.Circuit.NumNodes()==8639 and d.Transformers.Count()==1226
        assert d.Solution.Convergence()==self.tolerance
        COUNTS['cached_metadata_builds']+=1


def install(enabled=True):
    electrical.Engine=CachedMetadataEngine if enabled else OriginalEngine


def electrical_key(data,t,qtrial):
    # Match Electrical.apply's additions and order exactly, including co-location.
    services=[f'IDC{i:02}' for i in range(1,13)]+[f'STA{i:02}' for i in range(1,13)]
    aggregate=np.zeros(24,dtype=float)
    for j,s in enumerate(data['locations'][t]):
        if data['connected'][t,j]:aggregate[services.index(s)]+=qtrial[j]
    return aggregate.tobytes()


def original_continuous(fn,*args):
    install(False)
    try:return fn(*args)
    finally:install(True)
