"""One immutable scientific case and exact transport to the original matrix."""
from dataclasses import dataclass
import hashlib
import json
import pickle
from pathlib import Path
import numpy as np
from scipy import sparse
from v42_unified.audit import ROOT, M_HEAD, C3_HEAD, A_HEAD, git, write
from v42_unified.storage import FrozenStore, sha, setup
from v42_unified.replay import pinned
from v42_unified.mess_replay import graph_from_bundle
from v42_native.contracts import digest

REPORTS = ROOT/'docs/v42_m1_joint_gap_research'
FROZEN = ROOT/'runtime/v42_m1_joint_gap_research/case'


def committed_file(path, head=M_HEAD):
    if Path(path).is_absolute() or '..' in Path(path).parts:raise ValueError('COMMITTED_RELATIVE_PATH_REQUIRED')
    raw=git('show',f'{head}:{path}')
    target=FROZEN/path
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.read_bytes()!=raw:
        raise ValueError('COMPLETED_CASE_BLOB_DRIFT:'+path)
    if not target.exists():target.write_bytes(raw)
    return target,dict(path=path,head=head,sha256=hashlib.sha256(raw).hexdigest(),local_path=str(target))


def npz_data(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}


@dataclass
class ResearchCase:
    A: object
    d: dict
    original_A: object
    original_d: dict
    point: object
    graph: tuple
    case_sha: str
    identity: dict
    retained_columns: object
    aliases: list

    def lift(self,point):
        point=np.asarray(point)
        if point.shape!=(self.A.shape[1],):raise ValueError('C3A_POINT_AXIS_DRIFT')
        x=np.zeros(self.identity['C1_columns']);x[self.retained_columns]=point
        defined=set(map(int,self.retained_columns))
        for row in reversed(self.aliases):
            j=row['column']
            if j in defined:raise ValueError('DUPLICATE_C1_ALIAS')
            x[j]=row['constant']
            for k,w in row['terms'].items():
                if int(k) not in defined or w!=1.:raise ValueError('UNPROVEN_C1_ALIAS')
                x[j]+=w*x[int(k)]
            defined.add(j)
        if len(defined)!=len(x):raise ValueError('INCOMPLETE_C1_POINT_TRANSPORT')
        return x[:self.original_A.shape[1]].copy()


def load_case():
    setup();REPORTS.mkdir(parents=True,exist_ok=True)
    out=ROOT/'docs/v42_m1_ultracompact_exact_20261006'
    parent=ROOT/'docs/v42_m1_supercompact_exact_20261006'
    for path in ('v42_native/mess.py','v42_bootstrap/m1.py',
                 'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz',
                 'docs/v42_m1_supercompact_exact_20261006/C2_ELIMINATION_CERTIFICATES.json',
                 'docs/v42_m1_supercompact_exact_20261006/C1_DATA.npz'):
        if sha(ROOT/path)!=hashlib.sha256(git('show',f'{M_HEAD}:{path}')).hexdigest():
            raise ValueError('M_COMPLETED_SOURCE_TRANSPORT_DRIFT:'+path)
    authority=pinned(out/'ULTRACOMPACT_CURRENT_AUTHORITY_M1.json',M_HEAD)
    for key,name in (('selected_matrix_SHA256','C3A_A.npz'),('selected_data_SHA256','C3A_DATA.npz'),('selected_start_SHA256','C3A_VALID_START.npz')):
        if sha(out/name)!=authority[key]:raise ValueError('C3A_SCIENTIFIC_HASH_DRIFT')
    A=sparse.load_npz(out/'C3A_A.npz');d=npz_data(out/'C3A_DATA.npz')
    receipts=[]
    best_path,row=committed_file('docs/v42_m1_route_mode_benders_20261008/artifacts/BEST_VALID_POINT.npz');receipts.append(row)
    for name in ('VALID_UB_CHANGE.json','FINAL_VALIDATION.json','BEST_FULL_REPLAY.json'):
        _,row=committed_file('docs/v42_m1_route_mode_benders_20261008/'+name);receipts.append(row)
    with np.load(best_path,allow_pickle=False) as z:
        if z.files!=['x']:raise ValueError('BEST_C3A_POINT_NOT_FOUND')
        point=z['x'].copy()
    if point.shape!=(A.shape[1],):raise ValueError('BEST_C3A_POINT_DIMENSION_DRIFT')
    freeze=pinned(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')
    store=FrozenStore()
    source='C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL'
    source_data=store.copy(dict(path=source+'/DATA.pkl',sha256=freeze['source_data_sha256']))
    with source_data.open('rb') as stream:data=pickle.load(stream)
    bundle=data[0];store.copy(bundle['route_table'])
    graph=graph_from_bundle(store.operational_view(bundle))
    original=pinned(parent/'CURRENT_ORIGINAL_MODEL_CENSUS.json',M_HEAD)['identity']
    original_A_path=store.copy(dict(path=source+'/FULL_A.npz',sha256=original['matrix_sha256']))
    original_data_path=store.copy(dict(path=source+'/FULL_DATA.npz',sha256=original['data_sha256']))
    full_A=sparse.load_npz(original_A_path);full_d=npz_data(original_data_path)
    cols=npz_data(parent/'C2_RETAINED_AXES.npz')['columns']
    aliases=json.loads((parent/'C2_ELIMINATION_CERTIFICATES.json').read_text(encoding='utf8'))
    C1_columns=len(npz_data(parent/'C1_DATA.npz')['names'])
    facts=dict(schema='V42_M1_RESEARCH_CASE_V1',day=bundle['day'],jobs=len(data[1]),units=len(graph[1]),slots=96,
        services=len(graph[0]),binary=int(np.count_nonzero(d['types']!='C')),objective='min rho_max',
        scientific_C3A_head=C3_HEAD,completed_M_head=M_HEAD,integrated_A_head=A_HEAD,
        C3A_matrix_sha256=authority['selected_matrix_SHA256'],C3A_data_sha256=authority['selected_data_SHA256'],
        original_matrix_sha256=original['matrix_sha256'],original_data_sha256=original['data_sha256'],
        frozen_bundle_sha256=freeze['source_data_sha256'],route_table_sha256=bundle['route_table']['sha256'],
        C3A_start_sha256=authority['selected_start_SHA256'],C1_columns=C1_columns,
        alias_sha256=sha(parent/'C2_ELIMINATION_CERTIFICATES.json'),retained_columns_sha256=sha(parent/'C2_RETAINED_AXES.npz'),
        common_physics_sha256={p:sha(ROOT/p) for p in ('v42_native/mess.py','v42_bootstrap/m1.py')})
    if (facts['day'],facts['jobs'],facts['units'],facts['slots'],facts['binary'],facts['services'])!=('2025-05-01',1499,4,96,9322,24):raise ValueError('MAY01_C3A_CASE_REQUIRED')
    case_sha=digest(facts)
    identity=dict(PASS=True,case_sha=case_sha,**facts,committed_best_UB_sources=receipts,
        D_frozen_copies=store.copies,May12_input_consumed=False,source_files_modified=False,
        C3A_dimensions=list(A.shape),original_dimensions=list(full_A.shape),C3A_nnz=A.nnz,
        original_AIDC_anchor_preserved=True,normalamps_authority='0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51')
    write(REPORTS/'SCIENTIFIC_MODEL_IDENTITY.json',identity)
    return ResearchCase(A,d,full_A,full_d,point,graph,case_sha,identity,cols,aliases)
