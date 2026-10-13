"""Separate development tree; predecessor implementation is read-only."""
import sys,time,gc,hashlib,json
from pathlib import Path
PREVIOUS_ROOT=Path('D:/v42_b2_adaptive_compact_joint_20261013')
sys.path.insert(0,str(PREVIOUS_ROOT))
from tools.adaptive_compact_joint import resume_adapter as previous
from tools.adaptive_compact_joint.resume_adapter import *
DEVELOPMENT_ROOT=Path(__file__).resolve().parents[2]
PREVIOUS_DOCS=previous.DOCS
DOCS=DEVELOPMENT_ROOT/'docs/v42_b2_adaptive_perf_v3'
DOCS.mkdir(parents=True,exist_ok=True)

def configure():
    previous.configure()
    from tools.adaptive_compact_joint import beam,direct,fresh_worker
    from tools.minimax_beam1800 import grid
    beam.DOCS=DOCS;direct.DOCS=DOCS;grid.DOCS=DOCS;fresh_worker.DOCS=DOCS
    r.DOCS=DOCS;r.BASELINE=DOCS/'PROTECTED_BASELINE.json';r.baseline.cache_clear();v.DOCS=DOCS

def guard():
    if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists():
        for path,digest in read(DOCS/'EXECUTED_SOURCE_HASHES.json').items():assert v.file_sha(path)==digest,'V3_SOURCE_POLICY_DRIFT:'+path

def full_guard():previous.guard();guard()

class Timing:
    def __init__(self):self.started=time.perf_counter();self.parts={};self.stack=[]
    def stage(self,name):
        owner=self
        class Stage:
            def __enter__(self):self.began=time.perf_counter();return self
            def __exit__(self,*exc):owner.parts[name]=owner.parts.get(name,0.)+time.perf_counter()-self.began
        return Stage()
    def receipt(self):
        wall=time.perf_counter()-self.started;measured=sum(self.parts.values())
        assert measured<=wall+.01
        return dict(parts=self.parts,total_wall=wall,other_control_and_IO_wall=wall-measured,accounting_residual=0.,disjoint_stage_timings=True)
