"""Continue the same fresh1800s authorization; all earlier versions are immutable."""
from tools.adaptive_compact_joint import fresh_adapter as parent
from tools.adaptive_compact_joint.fresh_adapter import *
PILOT_DOCS=DOCS
DOCS=PILOT_DOCS/'v2_feedback'
DOCS.mkdir(parents=True,exist_ok=True)
v.DOCS=DOCS;r.DOCS=DOCS;r.BASELINE=DOCS/'PROTECTED_BASELINE.json';r.baseline.cache_clear()

def guard():
    parent.guard()
    if (DOCS/'PRESERVED_PILOT_FILES.json').exists():
        for rel,h in read(DOCS/'PRESERVED_PILOT_FILES.json').items():assert v.file_sha(ROOT/rel)==h,'PRIOR_PILOT_ARTIFACT_DRIFT:'+rel
    if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists():
        for rel,h in read(DOCS/'EXECUTED_SOURCE_HASHES.json').items():assert v.file_sha(ROOT/rel)==h,'CONTINUATION_SOURCE_DRIFT:'+rel

def configure():
    from tools.adaptive_compact_joint import fresh_worker,direct,beam
    from tools.minimax_beam1800 import grid
    fresh_worker.DOCS=DOCS;fresh_worker.guard=guard;direct.DOCS=DOCS
    beam.DOCS=DOCS;grid.DOCS=DOCS

def validate(raw,output,obj=None):return v.validate(Path(raw),solver_objective=obj,output=Path(output))
