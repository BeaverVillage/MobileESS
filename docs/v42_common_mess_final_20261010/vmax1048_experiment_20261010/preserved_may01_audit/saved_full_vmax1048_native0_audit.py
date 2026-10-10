"""Independent preserved FULL coefficient experiment; Native optimize calls 0.

This diagnoses the supplied cap on original May01 FULL bytes. The actual fresh
build/Compact/C3A gate is separately emitted by the diagnostic worker.
"""
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys
import numpy as np
from scipy import sparse
import gurobipy as gp

sys.path.insert(0,r'D:\v42vmax1048')
from v42_common_mess.planning_policy import specification,_full_voltage_audit,_same_csr,_equal

OUT=Path(__file__).resolve().parent
BASE=Path(r'D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01\output')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def record(path):
    path=Path(path).resolve()
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
def arrays(path):
    with np.load(path,allow_pickle=False) as data:return {k:data[k].copy() for k in data.files}
def domain_sha(d):
    h=hashlib.sha256()
    for key in sorted(d):
        value=np.asarray(d[key]);h.update(key.encode());h.update(value.dtype.str.encode())
        h.update(np.asarray(value.shape,dtype='<i8').tobytes());h.update(value.tobytes())
    return h.hexdigest()

prior=read(OUT/'B2_MAY01_VOLTAGE_AUDIT.json')
receipts=[]
for r in prior['sources']:
    now=record(r['path'])
    assert now['sha256']==r['sha256'] and now['bytes']==r['bytes'],'PRESERVED_SOURCE_BYTES_DRIFT:'+r['path']
    # The D: input mirror contains junctions to its pinned C: source archive.
    assert Path(now['path']).resolve()==Path(r['path']).resolve()
    receipts.append(now)
original_A=sparse.load_npz(BASE/'FULL_A.npz').tocsr()
original_d=arrays(BASE/'FULL_DATA.npz')
identity=read(BASE/'SCIENTIFIC_CASE_IDENTITY.json')
assert domain_sha(original_d)==identity['original_domain_sha']
candidate_d={k:v.copy() for k,v in original_d.items()}
policy=specification()
mask=np.array([str(n).startswith('voltage_upper[') for n in original_d['row_names']])
assert mask.sum()==96*386
candidate_d['rhs'][mask]+=policy['Planning_upper_squared']-policy['baseline_Planning_upper_squared']
native=read(r'D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B2\2025-05-01\NATIVE_INPUT.json')
coeff_path=native['grid_outputs']['planning_coefficients']['path'].replace('C:','D:',1)
coeff_archive=arrays(coeff_path)
fixed=read(BASE/'FIXED_AIDC_ANCHOR.json')
coeff=tuple(SimpleNamespace(control_names=fixed['control_names'],voltage_constant=coeff_archive['voltage_constant'][t],
    voltage_matrix=coeff_archive['voltage_matrix'][t]) for t in range(96))
case=SimpleNamespace(original_A=original_A,original_d=candidate_d,coefficients=coeff,anchor=fixed)
rowaudit=_full_voltage_audit(case,policy);rowaudit.pop('row_indices')

m=gp.Model('PRESERVED_MAY01_FULL_1048_NATIVE0_READBACK')
try:
    m.Params.OutputFlag=0;m.Params.Threads=1
    variables=m.addMVar(original_A.shape[1],lb=candidate_d['lower'],ub=candidate_d['upper'],
        vtype=candidate_d['types'],obj=candidate_d['objective'])
    variables.VarName=candidate_d['names'].tolist();m.ObjCon=float(candidate_d['constant'])
    constraints=m.addMConstr(original_A,variables,candidate_d['sense'],candidate_d['rhs'])
    constraints.ConstrName=candidate_d['row_names'].tolist();m.update()
    matrix=m.getA().tocsr()
    checks=dict(FULL_native_CSR_exact=_same_csr(matrix,original_A),
        FULL_native_RHS_exact=_equal(np.asarray(m.getAttr('RHS')),candidate_d['rhs']),
        FULL_native_sense_exact=_equal(np.asarray(m.getAttr('Sense')),candidate_d['sense']),
        FULL_native_types_exact=_equal(np.asarray(m.getAttr('VType')),candidate_d['types']),
        FULL_native_lower_exact=_equal(np.asarray(m.getAttr('LB')),candidate_d['lower']),
        FULL_native_upper_exact=_equal(np.asarray(m.getAttr('UB')),candidate_d['upper']),
        FULL_native_objective_exact=_equal(np.asarray(m.getAttr('Obj')),candidate_d['objective'])
            and m.ObjCon==float(candidate_d['constant']),
        preserved_FULL_nonupper_RHS_byte_equal=_equal(candidate_d['rhs'][~mask],original_d['rhs'][~mask]),
        preserved_FULL_all_other_metadata_byte_equal=all(_equal(candidate_d[k],original_d[k]) for k in original_d if k!='rhs'))
    assert all(checks.values()),checks
    native_readback=dict(rows=m.NumConstrs,columns=m.NumVars,checks=checks)
finally:m.dispose()

point=arrays(BASE/'BEST_STRICT_UB_POINT.npz')['point']
axes=arrays(BASE/'CURRENT_C2_AXES.npz')
aliases=read(BASE/'CURRENT_C2_ALIASES.json')
lifted=np.zeros(identity['transport']['compact_columns']);lifted[axes['columns']]=point
for definition in reversed(aliases):
    lifted[definition['column']]=definition['constant']+sum(w*lifted[int(j)] for j,w in definition['terms'].items())
original_point=lifted[:len(original_d['names'])]
assert np.array_equal(original_point[original_d['types']!='C'],np.rint(original_point[original_d['types']!='C']))
violation=original_A[mask]@original_point-candidate_d['rhs'][mask]
assert violation.max()>1e-8
for r in receipts:assert record(r['path'])==r
report=dict(schema='V42_MAY01_PRESERVED_FULL_1048_NATIVE0_COEFFICIENT_AUDIT_V1',
    generated_UTC=datetime.now(timezone.utc).isoformat(),PASS=True,diagnostic_only=True,
    Native_optimize_calls=0,OpenDSS_solve_calls=0,original_point_mutation_count=0,original_source_mutation_count=0,
    original_case_SHA=identity['case_sha'],original_SourceSHA=prior['source_SHA'],
    original_domain_SHA=identity['original_domain_sha'],candidate_FULL_domain_SHA=domain_sha(candidate_d),
    coefficient_matrix_SHA_unchanged=identity['original_matrix_sha'],policy=policy,
    coverage='Independent exact original FULL snapshot with only user-authorized voltage-upper RHS shift, read back from actual Gurobi without optimize. Fresh source rebuild/Compact/C3A independent gate is still required from actual diagnostic worker.',
    changed_upper_rows=int(mask.sum()),lower_rows_unchanged=int(sum(str(n).startswith('voltage_lower[') for n in original_d['row_names'])),
    all_nonupper_RHS_byte_equal=True,all_other_column_row_metadata_byte_equal=True,
    Native_full_readback=native_readback,original_coefficient_voltage_audit=rowaudit,
    old_strict_point_under_new_FULL_upper_violation_count=int((violation>1e-8).sum()),
    old_strict_point_under_new_FULL_upper_max_violation_squared_pu=float(violation.max()),
    old_point_feasibility_not_reused=True,sources=receipts)
path=OUT/'B2_MAY01_SAVED_FULL_VMAX1048_NATIVE0_MODEL_AUDIT.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(receipt=record(path),PASS=True,Native_optimize_calls=0,
    native_readback=native_readback,changed_upper_rows=int(mask.sum()),
    old_point_violation_count=report['old_strict_point_under_new_FULL_upper_violation_count'],
    old_point_max_violation_squared_pu=report['old_strict_point_under_new_FULL_upper_max_violation_squared_pu']),indent=2))
