"""New user-authorized execution; prior canary and pilot costs stay separate."""
from tools.adaptive_compact_joint import adapter as beta
from tools.adaptive_compact_joint.adapter import *
DOCS=ROOT/'docs/v42_b2_adaptive_compact_joint_fresh1800'
DOCS.mkdir(parents=True,exist_ok=True)
v.DOCS=DOCS;r.DOCS=DOCS;r.BASELINE=DOCS/'PROTECTED_BASELINE.json';r.baseline.cache_clear()

def guard():
    beta.guard()
    if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists():
        for rel,h in read(DOCS/'EXECUTED_SOURCE_HASHES.json').items():assert v.file_sha(ROOT/rel)==h,'FRESH_EXECUTION_SOURCE_DRIFT:'+rel

def configure_beam():
    from tools.adaptive_compact_joint import beam
    from tools.minimax_beam1800 import grid
    beam.DOCS=DOCS;grid.DOCS=DOCS

def validate(raw,output,objective=None):return v.validate(Path(raw),solver_objective=objective,output=Path(output))
