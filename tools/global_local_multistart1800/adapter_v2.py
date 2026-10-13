"""Separate serialization-corrected version; V1 source and ledger stay immutable."""
from tools.global_local_multistart1800.adapter import *
V1_DOCS=DOCS
DOCS=V1_DOCS/'v2'
v.DOCS=DOCS;r.DOCS=DOCS;r.BASELINE=DOCS/'PROTECTED_BASELINE.json';r.baseline.cache_clear();g.DOCS=DOCS
def guard():
    for path,digest in read(DOCS/'EXECUTED_SOURCE_HASHES.json').items():assert v.file_sha(ROOT/path)==digest,'SOURCE_POLICY_V2_DRIFT:'+path
