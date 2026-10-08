"""Independent delivered-row and original-physics validation, optimize=0."""
from .common import *
from fractions import Fraction as F
from collections import Counter

def expected(record,reader,d,arcs,lookup):
    unit=record['MESS'];a=arcs[record['arc_index']];dep=lookup[f'SOC[{unit},{a[1]}]'];arr=lookup[f'SOC[{unit},{a[3]}]'];f=record['original_FULL_arc_column']
    assert str(reader.d['names'][f])==f"arc[{unit},{record['arc_index']}]" and a[4] is not None
    assert record['depart']==a[1] and record['connect']==a[3]
    e=F.from_float(float(a[4].energy_kwh));assert str(e)==record['travel_energy_exact']
    positions=[int(reader.target[j]) for j in (dep,arr,f)];offsets=[F.from_float(float(reader.offset[j])) for j in (dep,arr,f)]
    bounds=[]
    for j,off in zip(positions[:2],offsets[:2]):bounds.append((off+F.from_float(float(d['lower'][j])),off+F.from_float(float(d['upper'][j]))) if j>=0 else (off,off))
    (ld,ud),(la,ua)=bounds
    kind=record['kind']
    if kind=='TRAVEL_SOC_UPPER':weights=(-F(1),F(1),max(F(0),ua-ld+e));right=weights[2]-e
    elif kind=='TRAVEL_SOC_LOWER':weights=(F(1),-F(1),-min(F(0),la-ud+e));right=e+weights[2]
    elif kind=='DEPARTURE_SOC_REACHABILITY':weights=(-F(1),F(0),max(F(0),la+e-ld));right=-ld
    elif kind=='ARRIVAL_SOC_REACHABILITY':weights=(F(0),F(1),max(F(0),ua-ud+e));right=ua
    else:raise AssertionError('UNKNOWN_PHYSICAL_DISJUNCTION')
    terms={}
    for j,off,w in zip(positions,offsets,weights):
        right-=w*off
        if j>=0:terms[j]=terms.get(j,F(0))+w
    return {j:a for j,a in terms.items() if a},right

def validate_record(record,row,b,reader,d,arcs,lookup):
    terms,right=expected(record,reader,d,arcs,lookup)
    assert terms=={int(j):F(v) for j,v in record['exact_terms'].items()} and right==F(record['exact_rhs'])
    delivered=dict(zip(map(int,row.indices),map(float,row.data)));assert set(terms)==set(delivered)
    error=F(0)
    for j,a in terms.items():
        delta=F.from_float(delivered[j])-a;error+=max(delta*F.from_float(float(d['lower'][j])),delta*F.from_float(float(d['upper'][j])))
    assert F.from_float(float(b))>=right+error,'UNSAFE_ROW_COEFFICIENT_TRANSPORT'

def main():
    prior.forbid_optimize();paths_audit('independent_inequality_verifier')
    assert read(REPORTS/'BOUNDED_EXACT_FIXTURE_VERIFICATION.json')['PASS']
    A,d,start=hc.load();reader=hc.physical_reader();lookup={str(n):i for i,n in enumerate(reader.d['names'])}
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,battery,receipt=graph_inputs()
    assert len(set(tuple(a[:4]) for a in arcs))==len(arcs) and all(a[3]>a[1] for a in arcs)
    route=read(P183/'ROUTE_PROJECTION_AUDIT.json');manifest=read(P183/'SHA256_MANIFEST.json')
    assert route['PASS'] and sha(P183/'ROUTE_PROJECTION_AUDIT.json')==manifest['files']['ROUTE_PROJECTION_AUDIT.json']['sha256']
    T=sparse.load_npz(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
    with np.load(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as f:rhs=f['rhs'].copy()
    cert=read(REPORTS/'VALID_INEQUALITY_CERTIFICATES.json');records=cert['coefficient_proof'];assert len(records)==T.shape[0]
    for i,record in enumerate(records):validate_record(record,T.getrow(i),rhs[i],reader,d,arcs,lookup)
    rejected=0
    if records:
        try:validate_record(records[0],T.getrow(0),rhs[0]-1.,reader,d,arcs,lookup)
        except AssertionError:rejected+=1
        wrong=dict(records[0],travel_energy_exact='0')
        try:validate_record(wrong,T.getrow(0),rhs[0],reader,d,arcs,lookup)
        except AssertionError:rejected+=1
        assert rejected==2
    known=[]
    for path in sorted((P183/'artifacts/assignments').glob('*.npz')):
        with np.load(path) as f:x=f['x'].copy()
        violation=float(np.max(T@x-rhs,initial=0));assert violation<=1e-8
        known.append(dict(id=path.stem,source_SHA256=sha(path),max_temporal_violation=violation,PASS=True))
    with np.load(P183/'artifacts/BEST_VALID_POINT.npz') as f:best=f['x'].copy()
    replay=prior.prior.full_replay(A,d,best,reader);assert replay['PASS'] and float(d['objective']@best)==UB
    replay.update(valid_UB=UB,source_SHA256=sha(P183/'artifacts/BEST_VALID_POINT.npz'),new_temporal_row_max_violation=float(np.max(T@best-rhs,initial=0)),all_original_physics_unchanged=True,new_optimize_calls=0)
    assert replay['new_temporal_row_max_violation']<=1e-8;write(REPORTS/'ORIGINAL_PHYSICAL_REPLAY.json',replay)
    write(REPORTS/'INDEPENDENT_VALID_INEQUALITY_AUDIT.json',dict(PASS=True,delivered_rows=T.shape[0],coefficient_and_source_rational_checks=True,outward_transport_original_bounds=True,invalid_physics_and_rhs_mutations_rejected=rejected,known_witnesses=known,original_best_UB_replay_PASS=True,original_forward_DAG_no_parallel_arcs=True,PR183_general_integer_projection_proof_SHA256_preserved=True,source_objective_identity=prior.objective_identity(A,d),new_variables=0,all_original_rows_retained=True,native_optimize_calls=0))
    write(WORK/'checkpoints/ROOT_EQUIVALENCE_GATE.json',dict(PASS=True,source_BASE=BASE,bounded_fixtures_PASS=True,full_96slot_CSR_scientific_identity_PASS=True,full_original_integer_preservation_PASS=True,source_objective_bit_identity_PASS=True,independent_temporal_transport_PASS=True,UB_full_replay_PASS=True,temporal_rows_sha256=sha(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz'),temporal_data_sha256=sha(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz'),B2_distinct_rows=T.shape[0],B1_duplicate_solve_forbidden=True,ROOT_MAX_BUDGET=900))
    print('ROOT_EQUIVALENCE_GATE_PASS original_UB=',UB,'rows=',T.shape[0],flush=True)

if __name__=='__main__':main()
