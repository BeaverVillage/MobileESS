"""Measured incumbent P/Q reference, with inherited PCS/SOC route lookahead."""
from tools.adaptive_compact_joint.adapter import *
from tools.minimax_beam1800.grid import Minimax

class AdaptiveMinimax(Minimax):
    def __init__(self,case,point,context):
        super().__init__(case,point,context)
        original=case.lift(point);values=dict(zip(map(str,case.original_d['names']),map(float,original)))
        self.measured=np.zeros((4,self.m))
        for ui,u in enumerate(self.units):
            for si,s in enumerate(self.sites):
                for ri,row in enumerate(self.rows):
                    for fi,f in enumerate(('Pch','Pdis','Q')):
                        self.measured[ui,ri]+=self.coeff[ui,si,ri,fi]*values.get(f'{f}[{u},{s},{row["slot"]}]',0.)
        self.legacy_base_support=self.base_support.copy()
        # Partial labels now compare alternatives to actual optimized service,
        # rather than replacing unchanged vehicles by a guessed schedule.
        self.base_support=self.measured.copy()

    def peak(self,paths):
        vector=self.base.copy();rebound=np.zeros(self.m);unresolved=0.
        for ui,u in enumerate(self.units):
            path=paths[u]
            if path==self.baseline_paths[u]:vector+=self.measured[ui]
            else:
                vector+=self.path_vector(u,path);_,extra,missing,_=self.path_cache[u,tuple(path)]
                rebound+=extra;unresolved+=missing
        return float(np.max(vector+rebound)+1e-4*unresolved),vector.tolist(),rebound.tolist()
