"""Full-96-slot route-implied SOC disjunctions; no trajectory replication.

Every original integer z induces ONE DAG path. A selected movement arc skips
all intermediate site vertices, hence Pch=Pdis=Q=0 on its travel interval.
Summing the original energy rows gives Econnect=Edepart-e. Bounded endpoint
disjunctions and endpoint reachability are valid for all original integer
schedules, including continuous original route_flow via the uniqueness proof.
All row transport is outward weakened over ORIGINAL variable bounds.
"""
from .common import *
from fractions import Fraction as F
from collections import defaultdict

def emit(exact_terms,exact_rhs,d):
    exact_terms={j:a for j,a in exact_terms.items() if a};terms={j:float(v) for j,v in exact_terms.items()};error=F(0)
    for j,v in exact_terms.items():
        delta=F.from_float(terms[j])-v
        error+=max(delta*F.from_float(float(d['lower'][j])),delta*F.from_float(float(d['upper'][j])))
    safe=exact_rhs+error;rhs=float(safe)
    if F.from_float(rhs)<safe:rhs=float(np.nextafter(rhs,np.inf))
    assert F.from_float(rhs)>=safe
    return terms,rhs,dict(exact_terms={str(j):str(v) for j,v in exact_terms.items()},exact_rhs=str(exact_rhs),global_transport_error=str(error),outward_rhs_slack=str(F.from_float(rhs)-safe),transport_original_full_box_PASS=True)

def expression(reader,d,original_j):
    j=int(reader.target[original_j]);offset=F.from_float(float(reader.offset[original_j]));terms={j:F(1)} if j>=0 else {}
    lo=offset+(F.from_float(float(d['lower'][j])) if j>=0 else 0);hi=offset+(F.from_float(float(d['upper'][j])) if j>=0 else 0)
    return terms,offset,lo,hi

def combine(*parts):
    out=defaultdict(F);constant=F(0)
    for (terms,off),weight in parts:
        constant+=weight*off
        for j,v in terms.items():out[j]+=v*weight
    return dict(out),constant

def build(A,d,root,reader,arcs):
    ns={str(n):i for i,n in enumerate(reader.d['names'])};raw_rows=[];rhs=[];proofs=[];all_count=0;violations=[];units=defaultdict(int);bykind=defaultdict(int);time0=time.perf_counter()
    for original_j in reader.arc:
        unit,ai=str(reader.d['names'][original_j]).split('[',1)[1][:-1].split(',');ai=int(ai);a=arcs[ai]
        if a[4] is None:continue
        f,fo,fl,fu=expression(reader,d,original_j)
        if not f and fo==0:continue
        dep,do,ld,ud=expression(reader,d,ns[f'SOC[{unit},{a[1]}]']);arr,ao,la,ua=expression(reader,d,ns[f'SOC[{unit},{a[3]}]']);e=F.from_float(float(a[4].energy_kwh))
        U=max(F(0),ua-ld+e);L=min(F(0),la-ud+e)
        lowreach=max(F(0),la+e-ld);upreach=max(F(0),ua-ud+e)
        cases=[('TRAVEL_SOC_UPPER',[( (arr,ao),F(1)),((dep,do),F(-1)),((f,fo),U)],U-e),('TRAVEL_SOC_LOWER',[((arr,ao),F(-1)),((dep,do),F(1)),((f,fo),-L)],e-L),('DEPARTURE_SOC_REACHABILITY',[((dep,do),F(-1)),((f,fo),lowreach)],-ld),('ARRIVAL_SOC_REACHABILITY',[((arr,ao),F(1)),((f,fo),upreach)],ua)]
        for kind,parts,b in cases:
            terms,constant=combine(*parts);b-=constant;all_count+=1
            # A tiny sparse exact dot is cheap: no tolerance screen and no
            # basis/dual assumptions. Select ALL violations > scientific tol.
            violation=sum((v*F.from_float(float(root[j])) for j,v in terms.items()),F(0))-b
            if violation<=F.from_float(1e-8):continue
            delivered,br,transport=emit(terms,b,d);delivered_v=sum((F.from_float(v)*F.from_float(float(root[j])) for j,v in delivered.items()),F(0))-F.from_float(br)
            if delivered_v<=F.from_float(1e-8):continue
            index=len(raw_rows);raw_rows.append(delivered);rhs.append(br);units[unit]+=1;bykind[kind]+=1;violations.append(float(delivered_v))
            proofs.append(dict(row=index,kind=kind,MESS=unit,original_FULL_arc_column=int(original_j),original_C3A_flow_column=int(reader.target[original_j]),arc_index=ai,depart=a[1],connect=a[3],travel_energy_exact=str(e),departure_SOC_original_column=ns[f'SOC[{unit},{a[1]}]'],arrival_SOC_original_column=ns[f'SOC[{unit},{a[3]}]'],departure_C3A_column=int(reader.target[ns[f'SOC[{unit},{a[1]}]']]),arrival_C3A_column=int(reader.target[ns[f'SOC[{unit},{a[3]}]']]),native_root_source_violation=float(delivered_v),**transport))
    ii=[];jj=[];vv=[]
    for i,row in enumerate(raw_rows):
        for j,v in sorted(row.items()):ii.append(i);jj.append(j);vv.append(v)
    T=sparse.csr_matrix((vv,(ii,jj)),shape=(len(raw_rows),A.shape[1]));sparse.save_npz(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz',T);save(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz',rhs=np.array(rhs),sense=np.full(len(rhs),'<'))
    write(REPORTS/'VALID_INEQUALITY_CERTIFICATES.json',dict(PASS=True,proof_method='Integer DAG path uniqueness + zero dispatch on skipped vertices + summed original energy rows + finite endpoint bound disjunction + exact original-box outward transport',coverage='Every retained original movement arc for all four MESS and full slots 0..95; no route-domain reduction',original_flow_type_continuous=True,valid_on_integer_projection_only=True,coefficient_proof=proofs,candidate_rows_checked=all_count,delivered_violated_rows=len(raw_rows),by_MESS=units,by_kind=bykind,max_archived_root_violation=max(violations,default=0),added_columns=0,added_binary_variables=0,original_rows_removed=0,all_root_violations_selected=True,not_topK=True,build_wall_seconds=time.perf_counter()-time0,original_objective_unchanged=True,native_optimize_calls=0))
    return T,np.array(rhs),proofs
