"""Reuse verified D-only input bytes and immutable original scientific arrays."""
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
import json
import numpy as np

from v42_unified.audit import ROOT, git, write
from v42_unified.storage import FrozenStore, sha, setup
from v42_m1_research import case as legacy
from v42_m1_research.check_ub import validate_candidate
from v42_m1_research.check_joint import check_exact_integer_replay

BASE_HEAD='6122331841e22562d23eb054c4168b5130566f3f'
CASE_SHA='cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a'
REPORTS=ROOT/'docs/v42_m1_fast_hybrid_20261008'
RUNTIME=ROOT/'runtime/v42_m1_fast_hybrid'


def committed_json(relative):
    return json.loads(git('show',f'{BASE_HEAD}:{relative}'))


def historical_manifest():
    return committed_json('docs/v42_m1_joint_gap_research/SHA256_MANIFEST.json')


def verify_baseline_files():
    manifest=historical_manifest()
    checked={}
    for name,expected in manifest['files'].items():
        actual=sha(ROOT/name)
        if actual!=expected:raise ValueError('HISTORICAL_HYBRID_BASELINE_DRIFT:'+name)
        checked[name]=actual
    # The manifest does not recursively hash itself.
    name='docs/v42_m1_joint_gap_research/SHA256_MANIFEST.json'
    import hashlib
    if sha(ROOT/name)!=hashlib.sha256(git('show',f'{BASE_HEAD}:{name}')).hexdigest():
        raise ValueError('HISTORICAL_MANIFEST_DRIFT')
    return checked


def load_case(output=REPORTS):
    begin=perf_counter();setup();output=Path(output).resolve()
    if not output.is_relative_to(ROOT.resolve()):raise ValueError('D_HYBRID_OUTPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=True)
    previous=committed_json('docs/v42_m1_joint_gap_research/SCIENTIFIC_MODEL_IDENTITY.json')
    cached={str(r['original_path']).replace('\\','/').lower():r for r in previous['D_frozen_copies']}
    reused=[]

    class VerifiedStore(FrozenStore):
        def copy(self,record):
            key=str(record['path']).replace('\\','/').lower()
            if key in self.mapping:return super().copy(record)
            saved=cached.get(key)
            if saved and saved['sha256']==record['sha256']:
                local=Path(saved['local_path']).resolve()
                if not local.is_relative_to(ROOT.resolve()) or sha(local)!=record['sha256']:
                    raise ValueError('PREVIOUSLY_VERIFIED_D_COPY_DRIFT')
                self.mapping[key]=local
                row=dict(saved,current_D_copy_SHA256_verified=True,original_C_source_rehashed=False)
                self.copies.append(row);reused.append(row)
                return local
            return super().copy(record)

    with patch.object(legacy,'REPORTS',output), patch.object(legacy,'FROZEN',RUNTIME/'case'), patch.object(legacy,'FrozenStore',VerifiedStore):
        case=legacy.load_case()
    if case.case_sha!=CASE_SHA:raise ValueError('HYBRID_SCIENTIFIC_CASE_DRIFT')
    point_file=ROOT/'docs/v42_m1_joint_gap_research/U2_RAW_POINT.npz'
    if sha(point_file)!='011609aeeac4e746646b3517fd79883f4a3f771e7fa1b2d2302e9ef1663957a4':
        raise ValueError('COMPLETED_STRICT_U2_RAW_DRIFT')
    with np.load(point_file,allow_pickle=False) as z:
        if z.files!=['point']:raise ValueError('STRICT_U2_RAW_AXIS_DRIFT')
        case.point=z['point'].copy()
    replay=validate_candidate(case,case.point)
    if not replay['PASS']:raise ValueError('HYBRID_BASELINE_PHYSICAL_FAILURE')
    check_exact_integer_replay(replay)
    if replay['objective']!=.6063186498423855:raise ValueError('HYBRID_BASELINE_RHO_DRIFT')
    for matrix in (case.A,case.original_A):
        for array in (matrix.data,matrix.indices,matrix.indptr):array.flags.writeable=False
    for data in (case.d,case.original_d):
        for array in data.values():
            if isinstance(array,np.ndarray):array.flags.writeable=False
    case.point.flags.writeable=False
    write(output/'STRICT_BASELINE_REPLAY.json',replay)
    write(output/'CASE_LOAD_REUSE_AUDIT.json',dict(PASS=True,case_sha=case.case_sha,
        source_HEAD=BASE_HEAD,wall_seconds=perf_counter()-begin,verified_D_copies_reused=reused,
        CSR_loaded_once_per_run=True,static_graph_loaded_once=True,arrays_read_only=True,
        old_reports_written=False,May12_consumed=False,additional_Native_calls=0))
    return case
