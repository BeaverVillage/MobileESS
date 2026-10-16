"""Compare actual original integer FULL captures across scientific Sources.

Proves exact row/column permutation equivalence, including original domains,
all objective layers, named global roles, UID expressions and runtime counts.
Also exercises the actual 4,800-tail lift. Never optimizes a model.
"""
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '1'
import argparse
from fractions import Fraction
import gc
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sys
from time import perf_counter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration.table_v_dw import _row_signatures
from v42_integration.m_engine import file_record


def load(path):
    with gzip.open(path, 'rb') as stream:
        return pickle.load(stream)


def expression_terms(expression):
    if expression[0] == 'v': return Fraction(0), {int(expression[1]): Fraction(1)}
    if expression[0] == 'c': return Fraction(float(expression[1])), {}
    if expression[0] != 'e': raise ValueError('UNKNOWN_PRIMITIVE_EXPRESSION')
    terms = {}
    for j,c in zip(expression[2],expression[3]):
        j=int(j);terms[j]=terms.get(j,Fraction(0))+Fraction(float(c))
    return Fraction(float(expression[1])), {j:c for j,c in terms.items() if c}


def column_mapping(before, after):
    a, b = before['original_descriptor'], after['original_descriptor']
    left, right = before['original'], after['original']
    mapping = {}
    def bind(i, j):
        i, j = int(i), int(j)
        if i in mapping and mapping[i] != j: raise ValueError('CONFLICTING_SEMANTIC_COLUMN_ROLES')
        mapping[i] = j
    def pair(e, f):
        if e[0] == f[0] == 'v': bind(e[1], f[1])
        elif e[0] == f[0] == 'e':
            if e[1] != f[1] or not np.array_equal(e[3], f[3]): raise ValueError('PRIMITIVE_COEFFICIENT_DRIFT')
            for i,j in zip(e[2],f[2]): bind(i,j)
        elif e[0] == f[0] == 'c' and e == f: pass
        else: raise ValueError('PRIMITIVE_ROLE_DRIFT')
    if set(a['globals']) != set(b['globals']): raise ValueError('NAMED_GLOBAL_SET_DRIFT')
    for name, i in a['globals'].items(): bind(i,b['globals'][name])
    # Remaining global prefix columns are checked with the entire matrix and
    # with all control/known/risk/objective expressions below. No coefficient
    # is changed to make this candidate permutation pass.
    unit_columns = [j for u in a['units'] for items in u['v'].values()
                    for e in items.values() for j in expression_terms(e)[1]]
    prefix = min(unit_columns)
    for j in range(prefix):
        if j not in mapping: bind(j,j)
    targets = {u['id']:u for u in b['units']}
    if len(targets) != len(b['units']) or {u['id'] for u in a['units']} != set(targets):
        raise ValueError('ORIGINAL_UID_IDENTITY_DRIFT')
    for unit in a['units']:
        target = targets[unit['id']]
        for key in ('uid', 'optional'):
            if unit.get(key) != target.get(key): raise ValueError('UID_SCIENTIFIC_ROLE_DRIFT')
        if set(unit['v']) != set(target['v']): raise ValueError('UID_FAMILY_DRIFT')
        for family, items in unit['v'].items():
            if set(items) != set(target['v'][family]): raise ValueError('UID_CHOICE_DOMAIN_DRIFT')
            for key,e in items.items(): pair(e,target['v'][family][key])
    def runtime_roles(capture):
        result = {}
        for (key,site,end),column in capture['original_runtime_bindings'].items():
            members = tuple(sorted(map(str,capture['data'][7]['classes'][key])))
            role = (members,site,end)
            if role in result: raise ValueError('DUPLICATE_ORIGINAL_RUNTIME_ROLE')
            result[role] = column
        return result
    old_runtime, new_runtime = runtime_roles(before), runtime_roles(after)
    if set(old_runtime) != set(new_runtime): raise ValueError('ORIGINAL_RUNTIME_DOMAIN_DRIFT')
    for role,column in old_runtime.items(): bind(column,new_runtime[role])
    columns = left.matrix.shape[1]
    if left.matrix.shape != right.matrix.shape or set(mapping) != set(range(columns)) or len(set(mapping.values())) != columns:
        missing = sorted(set(range(columns))-set(mapping))
        raise ValueError('FULL_COLUMN_BIJECTION_REQUIRED:'+str(missing[:20]))
    permutation = np.asarray([mapping[j] for j in range(columns)], dtype=np.int64)
    def same_expression(e,f):
        constant, terms = expression_terms(e); other_constant, other = expression_terms(f)
        if constant != other_constant or {int(permutation[j]):c for j,c in terms.items()} != other:
            raise ValueError('SEMANTIC_EXPRESSION_DRIFT_AFTER_PERMUTATION')
    for key in ('known','risk'):
        if set(a[key]) != set(b[key]): raise ValueError('SCIENTIFIC_ROLE_SET_DRIFT')
        for role,e in a[key].items(): same_expression(e,b[key][role])
    if len(a['controls']) != len(b['controls']): raise ValueError('CONTROL_GROUP_DRIFT')
    for es,fs in zip(a['controls'],b['controls']):
        if len(es) != len(fs): raise ValueError('CONTROL_DOMAIN_DRIFT')
        for e,f in zip(es,fs): same_expression(e,f)
    if [n for n,e in a['levels']] != [n for n,e in b['levels']]: raise ValueError('LEX_OBJECTIVE_ROLE_DRIFT')
    for (_,e),(_,f) in zip(a['levels'],b['levels']): same_expression(e,f)
    return permutation, dict(global_prefix=prefix,UIDs=len(targets),runtime_auxiliaries=len(old_runtime))


def audit(old, new, output):
    import gurobipy as gp
    def forbidden(*args, **kwargs): raise AssertionError('NATIVE0_ENTRYPOINT_FORBIDDEN')
    for name in ('optimize','presolve','computeIIS','feasRelax','feasRelaxS'): setattr(gp.Model,name,forbidden)
    output = Path(output); output.mkdir(parents=True,exist_ok=False); started=perf_counter()
    old_path = Path(old)/'B1/A1/DW/FULL_CAPTURE/ORIGINAL_FULL_CAPTURE.pkl.gz'
    new_path = Path(new)/'B1/A1/DW/FULL_CAPTURE/ORIGINAL_FULL_CAPTURE.pkl.gz'
    records=[]
    for folder,path in ((Path(old),old_path),(Path(new),new_path)):
        receipt=json.loads((path.parent/'ORIGINAL_FULL_CAPTURE_RECEIPT.json').read_text(encoding='utf8'))
        record=file_record(path)
        if receipt.get('PASS') is not True or record != receipt.get('capture'):
            raise ValueError('ACTUAL_ORIGINAL_CAPTURE_RECEIPT_BYTES_REQUIRED')
        records.append(record)
    print('LOAD_ORIGINAL_CAPTURES',flush=True)
    before,after=load(old_path),load(new_path)
    for folder,capture in ((Path(old),before),(Path(new),after)):
        metadata=json.loads((folder/'ORIGINAL_FULL_INTEGER_NATIVE0.json').read_text(encoding='utf8'))
        if capture['native_binding'] != metadata['native_binding']:
            raise ValueError('ACTUAL_ORIGINAL_NATIVE_READBACK_BINDING_REQUIRED')
    permutation,counts=column_mapping(before,after)
    a,b=before['original'],after['original']
    for field in ('lower','upper','vtypes'):
        if not np.array_equal(getattr(a,field),getattr(b,field)[permutation]): raise ValueError('ORIGINAL_DOMAIN_DRIFT:'+field)
    if [o.name for o in a.objectives] != [o.name for o in b.objectives]: raise ValueError('ORIGINAL_OBJECTIVE_LAYERS_DRIFT')
    for x,y in zip(a.objectives,b.objectives):
        if x.constant != y.constant or {int(permutation[j]):c for j,c in x.coefficients().items()} != y.coefficients():
            raise ValueError('ORIGINAL_OBJECTIVE_DRIFT:'+x.name)
    print('COMPARE_ALL_ORIGINAL_ROWS',a.matrix.shape,flush=True)
    signatures=_row_signatures(a,permutation)
    other=_row_signatures(b)
    if signatures != other:
        raise ValueError('ORIGINAL_ROW_MULTISET_DRIFT:'+str(dict(old_only=sum((signatures-other).values()),new_only=sum((other-signatures).values()))))
    np.savez_compressed(output/'ORIGINAL_COLUMN_PERMUTATION.npz',old_to_new=permutation)
    proof=dict(status='PASS',scope='EXACT_ORIGINAL_INTEGER_FULL_ACROSS_SOURCES_NOT_FEASIBILITY',Native_calls=0,
        rows=a.matrix.shape[0],columns=a.matrix.shape[1],NNZ=a.matrix.nnz,
        original_captures=records,
        original_fingerprints=[a.fingerprint(),b.fingerprint()],
        permutation_sha=hashlib.sha256(permutation.astype('<i8').tobytes()).hexdigest(),
        moved_columns=int(np.count_nonzero(permutation!=np.arange(len(permutation)))),
        exact_row_multiset_including_duplicates_senses_rhs=True,all_domains_integrality_objectives_exact=True,
        semantic_controls_UIDs_known_risk_levels_preserved=True,**counts)
    del before,after,a,b,signatures,other,permutation;gc.collect()
    print('EXERCISE_ACTUAL_P1_TAIL_LIFT',flush=True)
    capture=load(Path(new)/'B1/A1/DW/FULL_CAPTURE/FULL_DW_CAPTURE.pkl.gz')
    from v42_integration.table_v_p1_tails import project,lift
    source=capture['projected'];rowmap={int(row):i for i,row in enumerate(capture['runtime_projection']['retained_original_rows'])}
    protected={rowmap[int(i)] for i in capture['coupling_rows'].values()}
    projected,descriptor,tail,rows,columns=project(source,capture['descriptor'],protected_rows=protected)
    saved=json.loads((Path(new)/'B1/A1/DW/P1_NEUTRAL_TAIL_PROJECTION.json').read_text(encoding='utf8'))
    if tail != saved: raise ValueError('ACTUAL_SAVED_TAIL_PROOF_DRIFT')
    point=np.maximum(projected.lower,np.minimum(projected.upper,np.zeros(len(projected.lower))))
    if not np.all(np.isfinite(point)): raise ValueError('FINITE_BOX_POINT_REQUIRED')
    restored=lift(source,point,tail)
    if not np.array_equal(restored[columns],point) or not np.all(restored>=source.lower) or not np.all(restored<=source.upper):
        raise ValueError('ACTUAL_TAIL_LIFT_BOX_OR_RETAINED_POINT_DRIFT')
    for entry in tail['entries']:
        i=entry['row'];lo,hi=source.matrix.indptr[i:i+2]
        lhs=sum((Fraction(float(c))*Fraction(float(restored[j])) for j,c in zip(source.matrix.indices[lo:hi],source.matrix.data[lo:hi])),Fraction(0))
        if lhs<Fraction(float(source.rhs[i])): raise ValueError('EXACT_ACTUAL_TAIL_ROW_VIOLATION')
    proof['actual_tail_lift']=dict(PASS=True,removed_rows_verified=len(tail['entries']),all_boxes_preserved=True,
        retained_point_unchanged=True,exact_rational_removed_row_replay=True,
        scope='BOUNDED_DIAGNOSTIC_POINT_LIFT_NOT_FULL_FEASIBILITY_OR_UB')
    proof['wall_seconds']=perf_counter()-started
    (output/'RESULT.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--old',type=Path,required=True)
    parser.add_argument('--new',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();audit(args.old,args.new,args.output)
