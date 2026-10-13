"""Reuse audited predecessor functions; isolate all new output writes."""
from tools.global_local_multistart1800.adapter import *
ROOT=Path(__file__).resolve().parents[2]
OLD_ROOT=Path('D:/v42_b2_global_local_multistart_dual1800_20261013')
OLD_DOCS=OLD_ROOT/'docs/v42_b2_global_local_multistart_dual1800'
DOCS=ROOT/'docs/v42_b2_adaptive_compact_joint'
v.DOCS=DOCS;r.DOCS=DOCS;r.BASELINE=DOCS/'PROTECTED_BASELINE.json';g.DOCS=DOCS

def guard():
    for rel,digest in read(DOCS/'PRESERVED_JOINT_FILES.json').items():
        assert v.file_sha(OLD_ROOT/rel)==digest,'PRESERVED_CANARY_DRIFT:'+rel
    if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists():
        for rel,digest in read(DOCS/'EXECUTED_SOURCE_HASHES.json').items():
            assert v.file_sha(ROOT/rel)==digest,'NEW_EXECUTION_SOURCE_DRIFT:'+rel

def replay(raw,out,obj=None):
    return v.validate(Path(raw),solver_objective=obj,output=Path(out))
