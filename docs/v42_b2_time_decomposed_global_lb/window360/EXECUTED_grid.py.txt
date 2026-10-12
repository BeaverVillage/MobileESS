"""Exact per-slot original security authority without a FULL CSR/model build.

The frozen NPZ members are streamed to temporary NPY files and memory-mapped.
Only requested original security rows and their recursive equality-helper
closure are copied. All original binary64 numbers are exact dyadic Fractions.
No Gurobi import, FULL CSR construction, or Optimize call occurs here.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path
import argparse
import gc
import gzip
import hashlib
import json
import math
import re
import shutil
import tempfile
import time
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SAVED = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
SOURCE = '497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
PARENT = '40ab888b884255e76fd6c89fd01933570b60c242'
FAMILIES = ('line_thermal_face', 'transformer_kVA', 'NormalAmps', 'voltage_upper', 'voltage_lower')
PHYSICAL = re.compile(r'(Pch|Pdis|Q)\[(MESS\d\d),([^,]+),(\d+)\]')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    path = Path(path)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.gz':
        # mtime=0 produces reproducible proof files.
        with path.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as stream:
                stream.write((json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode())
    else:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _row_sha(i, name, sense, rhs, terms):
    return canonical_sha(dict(original_row=int(i), name=name, sense=sense,
        rhs_hex=float(rhs).hex(), terms=[[int(j), float(v).hex()] for j,v in terms]))


def _upward(value):
    ans = float(value)
    require(math.isfinite(ans), 'NONFINITE_NATIVE_RHS')
    if F(ans) < value:
        ans = float(np.nextafter(ans, np.inf))
    return ans


class SelectiveAuthority:
    """Read-only row accessor over streamed frozen arrays, not a CSR object."""
    def __init__(self):
        self.started = time.perf_counter()
        self.tmp = tempfile.TemporaryDirectory(prefix='v42_time_grid_')
        self.maps = {}
        self.records = {}
        inherited = read(ROOT/'docs/v42_physical_global_lb_pilot/NATIVE0.json')
        require(inherited['PASS'] and inherited['base_commit'] == SOURCE and inherited['case_sha'] == CASE,
                'INHERITED_SOURCE_AUTHORITY')
        identity = read(SAVED/'SCIENTIFIC_CASE_IDENTITY.json')
        require(identity['case_sha'] == CASE and identity['original_matrix_sha'] == inherited['original_matrix_sha']
                and identity['original_domain_sha'] == inherited['original_domain_sha'], 'CASE_MATRIX_DOMAIN_IDENTITY')
        for source in ('FULL_A.npz', 'FULL_DATA.npz'):
            p = SAVED/source
            got = sha(p)
            require(got == inherited['source_records'][str(p)], 'FROZEN_SOURCE_SHA:'+source)
            self.records[str(p)] = got
            folder = Path(self.tmp.name)/source
            folder.mkdir()
            with zipfile.ZipFile(p) as z:
                for member in z.infolist():
                    require(Path(member.filename).name == member.filename and member.filename.endswith('.npy'), 'NPZ_MEMBER_PATH')
                    target = folder/member.filename
                    with z.open(member) as src, target.open('wb') as dst:
                        shutil.copyfileobj(src, dst, 1024*1024)
                    self.maps[member.filename[:-4]] = np.load(target, mmap_mode='r', allow_pickle=False)
        require(bytes(self.maps['format']) == b'csr', 'STORED_MATRIX_FORMAT')
        self.shape = tuple(int(v) for v in self.maps['shape'])
        require(self.shape == (1130336,344967), 'SOURCE_FULL_DIMENSIONS')
        require(len(self.maps['names']) == self.shape[1] and len(self.maps['row_names']) == self.shape[0], 'SOURCE_AXES')
        objective = self.maps['objective']
        obj_columns = np.flatnonzero(objective)
        require(len(obj_columns)==1 and str(self.maps['names'][obj_columns[0]])=='rho_max'
                and float(objective[obj_columns[0]])==1. and float(self.maps['constant'])==0., 'SOURCE_RHO_OBJECTIVE')
        self.rho = int(obj_columns[0])
        require(float(self.maps['lower'][self.rho])==0. and float(self.maps['upper'][self.rho])==1., 'SOURCE_RHO_BOUNDS')
        self.helper_defs = {}
        self.security_by_slot = defaultdict(list)
        for i, n in enumerate(self.maps['row_names']):
            name = str(n)
            family = name.split('[',1)[0]
            if family in FAMILIES:
                slot = int(name.split('[',1)[1].split(',',1)[0])
                self.security_by_slot[slot].append(i)
            if (family.startswith(('response_','injection_')) and family.endswith('_binding')):
                require(str(self.maps['sense'][i])=='=', 'HELPER_NOT_EQUALITY')
                terms = self.terms(i)
                pivots = [j for j,w in terms if w==1. and str(self.maps['names'][j]).split('[',1)[0]+'_binding'==family]
                require(len(pivots)==1 and pivots[0] not in self.helper_defs, 'HELPER_PIVOT_UNIQUE')
                self.helper_defs[pivots[0]]=i
        self.cache = {}
        self.raw_cache = {}

    def terms(self, i):
        lo,hi = (int(v) for v in self.maps['indptr'][i:i+2])
        return [(int(j),float(c)) for j,c in zip(self.maps['indices'][lo:hi],self.maps['data'][lo:hi])]

    def raw(self, i):
        if i not in self.raw_cache:
            terms = self.terms(i)
            name,sense,rhs = str(self.maps['row_names'][i]),str(self.maps['sense'][i]),float(self.maps['rhs'][i])
            self.raw_cache[i] = dict(original_row=i,name=name,sense=sense,rhs_hex=rhs.hex(),
                terms=[[j,c.hex()] for j,c in terms],source_row_sha256=_row_sha(i,name,sense,rhs,terms))
        return self.raw_cache[i]

    def expand(self, j, visiting=None):
        if j not in self.helper_defs:
            return F(0), {j:F(1)}, set()
        if j in self.cache:
            return self.cache[j]
        visiting = set() if visiting is None else visiting
        require(j not in visiting, 'SOURCE_HELPER_CYCLE')
        visiting.add(j)
        i=self.helper_defs[j]
        constant, terms, used = F(float(self.maps['rhs'][i])),defaultdict(F),{i}
        for k,v in self.terms(i):
            if k==j:
                continue
            c0,pieces,deps=self.expand(k,visiting)
            coefficient=-F(v)
            constant += coefficient*c0
            for q,c in pieces.items():
                terms[q] += coefficient*c
            used.update(deps)
        visiting.remove(j)
        result=constant,{q:c for q,c in terms.items() if c},used
        self.cache[j]=result
        return result

    def project(self,i,slot):
        sense=str(self.maps['sense'][i])
        require(sense in ('<','>'),'SECURITY_SENSE')
        sign=F(1) if sense=='<' else F(-1)
        constant,terms,used=F(0),defaultdict(F),set()
        for j,v in self.terms(i):
            c0,pieces,deps=self.expand(j)
            coefficient=sign*F(v)
            constant += coefficient*c0
            for k,c in pieces.items():
                terms[k] += coefficient*c
            used.update(deps)
        exact={j:c for j,c in terms.items() if c}
        rhs=sign*F(float(self.maps['rhs'][i]))-constant
        leaves={}
        cross_time=[]
        for j,c in exact.items():
            name=str(self.maps['names'][j])
            if name=='rho_max':
                leaves[name]=c
                continue
            match=PHYSICAL.fullmatch(name)
            require(match is not None,'SECURITY_RESIDUAL_NONPHYSICAL:'+name)
            if int(match.group(4))!=slot:
                cross_time.append(name)
            leaves[name]=c
        require(not cross_time,'SECURITY_CROSS_TIME_UNPROJECTABLE:'+','.join(cross_time))
        error,native=F(0),{}
        for j,c in exact.items():
            lo,hi=float(self.maps['lower'][j]),float(self.maps['upper'][j])
            require(math.isfinite(lo) and math.isfinite(hi),'OUTWARD_FINITE_SOURCE_BOX')
            f=float(c)
            require(math.isfinite(f) and f!=0.,'NATIVE_COEFFICIENT_UNDER_OR_OVERFLOW')
            error += max((F(f)-c)*F(lo),(F(f)-c)*F(hi))
            native[str(self.maps['names'][j])]=f
        native_rhs=_upward(rhs+error)
        original=self.raw(i)
        return dict(name=original['name'], original_row=i, original_sense=sense,
            original_rhs_hex=original['rhs_hex'],source_row_sha256=original['source_row_sha256'],
            sense='<',rhs=str(rhs),coeff={n:str(v) for n,v in sorted(leaves.items())},
            native_rhs=native_rhs,native_coeff=dict(sorted(native.items())),
            rounding_error=str(error),rhs_outward_extra=str(F(native_rhs)-rhs-error),
            eliminated_constant=str(constant),helper_rows=sorted(used),
            time_coupling_audit=dict(requested_slot=slot,nonrho_leaf_slots=[slot] if len(leaves)>('rho_max' in leaves) else [],cross_time_leaves=[]))

    def slot(self,slot):
        require(slot in self.security_by_slot,'SLOT_SECURITY_MISSING')
        rows=[]
        for i in self.security_by_slot[slot]:
            rows.append(self.project(i,slot))
        ids=set(self.security_by_slot[slot])
        helper_ids={i for row in rows for i in row['helper_rows']}
        all_ids=ids|helper_ids
        raw_rows=[self.raw(i) for i in sorted(all_ids)]
        cols={j for row in raw_rows for j,_ in row['terms']}
        axis={str(j):dict(name=str(self.maps['names'][j]),lower_hex=float(self.maps['lower'][j]).hex(),
            upper_hex=float(self.maps['upper'][j]).hex(),type=str(self.maps['types'][j]),objective_hex=float(self.maps['objective'][j]).hex())
            for j in sorted(cols)}
        leaves={name for row in rows for name in row['coeff']}
        ids_by_name={str(self.maps['names'][j]):j for j in cols}
        bounds={name:dict(lower=float(self.maps['lower'][ids_by_name[name]]),upper=float(self.maps['upper'][ids_by_name[name]]),
            lower_hex=float(self.maps['lower'][ids_by_name[name]]).hex(),upper_hex=float(self.maps['upper'][ids_by_name[name]]).hex(),
            original_column=ids_by_name[name]) for name in sorted(leaves)}
        raw_packet=dict(schema='V42_TIME_GRID_RAW_CLOSURE_V1',source=SOURCE,case_sha=CASE,slot=slot,
            original_full_shape=list(self.shape),source_files=self.records,columns=axis,rows=raw_rows,
            original_security_rows=sorted(ids),helper_rows=sorted(helper_ids),
            no_FULL_CSR_constructed=True,no_solver_model_constructed=True,Native_optimize_calls=0)
        exact_packet=dict(schema='V42_TIME_GRID_EXACT_V1',source=SOURCE,case_sha=CASE,parent=PARENT,slot=slot,
            source_files=self.records,rows=rows,source_leaf_bounds=bounds,
            original_full_shape=list(self.shape),original_grid_family_counts=dict(Counter(r['name'].split('[',1)[0] for r in rows)),
            rows_count=len(rows),nnz=sum(len(r['coeff']) for r in rows),helper_rows_count=len(helper_ids),
            rho_contract=dict(name='rho_max',original_column=self.rho,lower=0.,upper=1.,objective=1.,objective_constant=0.),
            helper_time_coupling_audit=dict(PASS=True,all_projected_nonrho_leaves_in_selected_slot=True,cross_time_rows=[],omitted_original_security_rows=[]),
            coefficient_authority='Frozen FULL stored binary64 interpreted exactly as Fractions; equality-helper recursive elimination',
            outward_rounding='ceil_binary64(rhs_exact + sum_j max((native_c-exact_c)*source_lb,(native_c-exact_c)*source_ub))',
            includes_all_original_slot_security_families=True,Native_optimize_calls=0,FULL_CSR_constructed=False)
        return exact_packet,raw_packet

    def close(self):
        self.cache.clear();self.raw_cache.clear()
        for arr in self.maps.values():
            mmap=getattr(arr,'_mmap',None)
            if mmap is not None:
                mmap.close()
        self.maps.clear()
        gc.collect()
        self.tmp.cleanup()


def build_slots(slots,out):
    """Save independent exact and original raw closure evidence for each slot."""
    started=time.perf_counter()
    out=Path(out)
    require(len(slots)==len(set(slots)) and all(0<=t<96 for t in slots),'REQUESTED_SLOTS')
    authority=SelectiveAuthority()
    results=[]
    try:
        for slot in slots:
            exact,raw=authority.slot(slot)
            p=out/f'slot{slot:02d}'
            p.mkdir(parents=True,exist_ok=True)
            write(p/'GRID_EXACT.json.gz',exact)
            write(p/'GRID_RAW_CLOSURE.json.gz',raw)
            report=dict(PASS=True,slot=slot,source=SOURCE,case_sha=CASE,parent=PARENT,
                rows=exact['rows_count'],nnz=exact['nnz'],family_counts=exact['original_grid_family_counts'],
                helper_rows=exact['helper_rows_count'],leaf_columns=len(exact['source_leaf_bounds']),
                helper_time_coupling_audit=exact['helper_time_coupling_audit'],source_files=authority.records,
                rho_contract=exact['rho_contract'],Native_optimize_calls=0,FULL_CSR_constructed=False,
                original_full_model_reconstructed=False,
                evidence={name:sha(p/name) for name in ['GRID_EXACT.json.gz','GRID_RAW_CLOSURE.json.gz']})
            write(p/'GRID_AUTHORITY.json',report)
            results.append(report)
    finally:
        authority.close()
    write(out/'GRID_EXTRACTION.json',dict(PASS=True,slots=slots,slot_results=results,
        wall_seconds=time.perf_counter()-started,Native_optimize_calls=0,FULL_CSR_constructed=False,
        temp_NPY_memmaps_removed=True,code_sha256=sha(__file__)))
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--slots',type=int,nargs='+',default=[75,82,94])
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build_slots(args.slots,args.out)))
