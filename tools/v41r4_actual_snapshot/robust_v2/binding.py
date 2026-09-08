"""Namespace/bootstrap adapter. Sealed numerical and historical sources stay unchanged."""
import os, sys, json, hashlib
from pathlib import Path
sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RUN = ROOT / 'frozen_artifacts/v41r4_may/loop_wall_v4'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OUT / 'frozen_code'))
import common
common.OUT, common.ROOT, common.RUN = OUT, ROOT, RUN
from common import read, save, sha, digest, arrays

def verify_method():
    frozen = read(OUT / 'METHOD_FREEZE.json')
    for r in frozen['numerical_method_files']:
        assert sha(r['path']) == r['sha256'], ('FROZEN_METHOD_DRIFT', r['path'])
    assert sha(OUT / 'BATTERY_EFFICIENCY_AUTHORITY.json') == frozen['efficiency_authority_SHA']
    source=OUT/'METHOD_CODE_BINDING.json'
    if source.exists():
        for name,h in read(source)['files'].items():assert sha(OUT/name)==h,('FROZEN_ROBUST_CODE_DRIFT',name)
    binding = OUT / 'EXECUTION_BINDING.json'
    if binding.exists():
        for name, h in read(binding)['files'].items():
            assert sha(OUT / name) == h, ('EXECUTION_BINDING_DRIFT', name)
    return frozen
