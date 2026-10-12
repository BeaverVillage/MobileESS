"""Finite fleet-count disjunction and fleet/window boolean-product RLT.

All source coefficients are copied, signed, or multiplied by exact integers.
Selector copies prevent rounding from coalescing a source coefficient and RHS.
"""
from common import *
from array import array

def select_block(A,d,units,start,end,grid):
    metadata=[info(n) for n in d['names']];selected=set()
    for j,(family,unit,t,args) in enumerate(metadata):
        if unit in units and t is not None and ((family=='SOC' and start<=t<=end) or (family!='SOC' and start<=t<end)):
            selected.add(j)
    rows=set(map(int,grid));physics={'PCS16','flow','connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge','energy_balance'}
    electrical={'injection_P_binding','injection_Q_binding','response_line_P_binding','response_line_Q_binding','response_line_correction_binding','response_transformer_P_binding','response_transformer_Q_binding'}
    for i,name in enumerate(d['row_names']):
        family=str(name).split('[')[0]
        if family not in physics|electrical|{'node_activity_link'}:continue
        cols=A.indices[A.indptr[i]:A.indptr[i+1]]
        if family in electrical:
            ts={metadata[j][2] for j in cols if metadata[j][2] is not None}
            if ts and min(ts)>=start and max(ts)<end:rows.add(i)
        elif family=='energy_balance':
            soc=[metadata[j] for j in cols if metadata[j][0]=='SOC' and metadata[j][1] in units]
            if soc and start<max(m[2] for m in soc)<=end:rows.add(i)
        elif any(int(j) in selected for j in cols):rows.add(i)
    routes={int(j) for i in rows for j in A.indices[A.indptr[i]:A.indptr[i+1]] if metadata[j][0]=='route_flow'}
    # Include the actual flow equations incident to copied travel-energy arcs.
    for i in np.flatnonzero(d['row_names']=='flow'):
        cols=A.indices[A.indptr[i]:A.indptr[i+1]]
        if any(int(j) in routes for j in cols):rows.add(int(i))
    rows=np.array(sorted(rows),dtype=np.int64);columns=np.unique(A[rows].indices)
    return rows,columns

class Rows:
    def __init__(self,n):self.n=n;self.rr=array('i');self.cc=array('i');self.vv=array('d');self.rhs=[];self.sense=[];self.groups=[]
    def row(self,terms,sense='=',rhs=0):
        i=len(self.rhs);self.rhs.append(float(rhs));self.sense.append(sense)
        ids=[int(j) for j,v in terms if v]
        assert len(ids)==len(set(ids)),'COEFFICIENT_SUMMATION_REQUIRES_EXACT_ROUNDING_PROOF'
        for j,v in terms:
            if v:self.rr.append(i);self.cc.append(int(j));self.vv.append(float(v))
    def group(self,kind,begin,**data):self.groups.append(dict(kind=kind,begin=begin,end=len(self.rhs),**data))
    def matrix(self):return sparse.coo_matrix((np.asarray(self.vv),(np.asarray(self.rr),np.asarray(self.cc))),shape=(len(self.rhs),self.n)).tocsr()

def augment_data(d,names,lower,upper,rows):
    n=len(names);return dict(d,names=np.r_[d['names'],np.asarray(names)],lower=np.r_[d['lower'],lower],upper=np.r_[d['upper'],upper],types=np.r_[d['types'],np.full(n,'C')],objective=np.r_[d['objective'],np.zeros(n)],rhs=np.r_[d['rhs'],rows.rhs],sense=np.r_[d['sense'],rows.sense],row_names=np.r_[d['row_names'],[f'joint_exact[{i}]' for i in range(len(rows.rhs))]])

def count_ef(A,d,I,J,groups):
    n=A.shape[1];N=len(J);K=len(groups);words=list(itertools.product(range(len(groups[0])+1),repeat=K));states=len(words)
    assert all(len(g)==len(groups[0]) for g in groups)
    index={int(j):i for i,j in enumerate(J)};assert all(int(j) in index and d['types'][j]=='B' for g in groups for j in g)
    total=n+states*N+states;builder=Rows(total);S=A[I].tocsr();lams=n+states*N+np.arange(states)
    names=[f'fleet_count_y[{s},{int(j)}]' for s in range(states) for j in J]+[f'fleet_count_lambda[{s}]' for s in range(states)]
    lower=np.r_[np.tile(np.minimum(0,d['lower'][J]),states),np.zeros(states)];upper=np.r_[np.tile(np.maximum(0,d['upper'][J]),states),np.ones(states)]
    for s,word in enumerate(words):
        lam=int(lams[s]);offset=n+s*N;begin=len(builder.rhs)
        for pos,i in enumerate(I):
            cols=S.indices[S.indptr[pos]:S.indptr[pos+1]];vals=S.data[S.indptr[pos]:S.indptr[pos+1]]
            builder.row([(offset+index[int(j)],v) for j,v in zip(cols,vals)]+[(lam,-d['rhs'][i])],str(d['sense'][i]))
        builder.group('homogeneous_original_rows',begin,state=s)
        begin=len(builder.rhs)
        for q,j in enumerate(J):
            builder.row([(offset+q,1),(lam,-d['lower'][j])],'>')
            builder.row([(offset+q,1),(lam,-d['upper'][j])],'<')
        builder.group('perspective_bounds',begin,state=s)
        begin=len(builder.rhs)
        for t,g in enumerate(groups):builder.row([(offset+index[int(j)],1) for j in g]+[(lam,-word[t])])
        builder.group('complete_count_word',begin,state=s)
    begin=len(builder.rhs);builder.row([(int(j),1) for j in lams],rhs=1)
    for q,j in enumerate(J):builder.row([(int(j),1)]+[(n+s*N+q,-1) for s in range(states)])
    builder.group('recombination',begin)
    B=builder.matrix();e=augment_data(d,names,lower,upper,builder)
    spec=dict(kind='COMPLETE_FLEET_COUNT_WINDOW_DISJUNCTION',original_columns=n,source_rows=I.tolist(),source_columns=J.tolist(),groups=groups,words=words,states=states,rows=builder.groups,integer_projection_unchanged=True,complete_integer_fleet_hull_claimed=False,binary_aggregation='The TOTAL selected-site occupancy across both units and all four slots is disjunctively integral; no individual-slot count or full fleet integer hull is claimed; other binaries stay original in MILP and relaxed in the root LP')
    return B,e,spec

def rlt_ef(A,d,I,J,selectors):
    n=A.shape[1];N=len(J);K=len(selectors);idx={int(j):q for q,j in enumerate(J)};assert all(j in idx and d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1 for j in selectors)
    total=n+K*N+K;builder=Rows(total);S=A[I].tocsr();lams=n+K*N+np.arange(K)
    names=[f'fleet_rlt_y[{b},{int(j)}]' for b in selectors for j in J]+[f'fleet_rlt_selector[{b}]' for b in selectors]
    lower=np.r_[np.tile(np.minimum(0,d['lower'][J]),K),np.zeros(K)];upper=np.r_[np.tile(np.maximum(0,d['upper'][J]),K),np.ones(K)]
    for s,b in enumerate(selectors):
        offset=n+s*N;lam=int(lams[s]);begin=len(builder.rhs);builder.row([(lam,1),(b,-1)])
        builder.group('selector_identity',begin,selector=s)
        begin=len(builder.rhs)
        for pos,i in enumerate(I):
            cols=S.indices[S.indptr[pos]:S.indptr[pos+1]];vals=S.data[S.indptr[pos]:S.indptr[pos+1]];sense=str(d['sense'][i])
            builder.row([(offset+idx[int(j)],v) for j,v in zip(cols,vals)]+[(lam,-d['rhs'][i])],sense)
            if sense!='=':builder.row([(int(j),v) for j,v in zip(cols,vals)]+[(offset+idx[int(j)],-v) for j,v in zip(cols,vals)]+[(lam,d['rhs'][i])],sense,d['rhs'][i])
        builder.group('boolean_times_original_rows',begin,selector=s)
        begin=len(builder.rhs)
        for q,j in enumerate(J):
            y=offset+q;lo,hi=d['lower'][j],d['upper'][j]
            builder.row([(y,1),(lam,-lo)],'>');builder.row([(y,1),(lam,-hi)],'<')
            builder.row([(int(j),1),(y,-1),(lam,lo)],'>',lo);builder.row([(int(j),1),(y,-1),(lam,hi)],'<',hi)
        builder.row([(offset+idx[b],1),(b,-1)])
        builder.group('boolean_product_bounds',begin,selector=s)
    begin=len(builder.rhs)
    for s,b in enumerate(selectors):
        for t,c in enumerate(selectors[:s]):builder.row([(n+s*N+idx[c],1),(n+t*N+idx[b],-1)])
    builder.group('joint_fleet_time_product_symmetry',begin)
    B=builder.matrix();e=augment_data(d,names,lower,upper,builder)
    spec=dict(kind='FLEET_WINDOW_GRID_SOC_BOOLEAN_RLT',original_columns=n,source_rows=I.tolist(),source_columns=J.tolist(),selectors=selectors,selector_original_names=[str(d['names'][j]) for j in selectors],rows=builder.groups,integer_projection_unchanged=True,complete_integer_fleet_hull_claimed=False,joint_products='Shared symmetric products across every chosen unit/time location and mode selector; every retained physical/grid row is multiplied by b and 1-b')
    return B,e,spec

def lift(spec,x):
    J=np.asarray(spec['source_columns']);n=spec['original_columns'];assert len(x)==n
    if spec['kind'].startswith('COMPLETE'):
        word=tuple(int(sum(x[j] for j in group)) for group in spec['groups']);states=[tuple(w) for w in spec['words']];s=states.index(word)
        weights=np.zeros(len(states));weights[s]=1;y=np.zeros((len(states),len(J)));y[s]=x[J]
    else:
        weights=x[np.asarray(spec['selectors'])];assert np.all((weights==0)|(weights==1));y=weights[:,None]*x[J]
    return np.r_[x,y.ravel(),weights]

def build_candidate(label):
    r=read(OUT/'ROOT_WINDOW_SELECTION.json');A,d,_=load();start,end=r['window']['start'],r['window']['end_exclusive'];names={str(n):j for j,n in enumerate(d['names'])}
    units=r['selected_units'] if label=='A' else r['all_units'];I,J=select_block(A,d,units,start,end,r['selected_grid_rows'])
    if label=='A':
        groups=[[names[f"node_activity[{u},{r['site']},{t}]"] for u in units for t in range(start,end)]]
        J=np.union1d(J,np.array(groups).ravel());forecast=dict(states=9,added_columns=9*(len(J)+1),selected_rows=len(I),selected_columns=len(J),aggregation='Total selected-site occupancy across BOTH units and ALL four slots',full_slotwise_count_hull_claimed=False)
    else:
        t=max(range(start,end),key=lambda slot:sum(abs(g['ROOT_Pi']) for g in r['grid_rows'] if g['slot']==slot))
        selectors=[names[f'charge_mode[{u},{start}]'] for u in units]+[names[f"node_activity[{u},{r['site']},{t}]"] for u in units]
        J=np.union1d(J,selectors);forecast=dict(selectors=len(selectors),added_columns=len(selectors)*(len(J)+1),selected_rows=len(I),selected_columns=len(J))
    atomic(OUT/f'{label}_SIZE_FORECAST.json',forecast)
    assert forecast['added_columns']<=300000,'REGISTERED_REPRESENTATION_SIZE_LIMIT_NOT_A_SCIENTIFIC_DOMAIN_RESTRICTION'
    B,e,spec=count_ef(A,d,I,J,groups) if label=='A' else rlt_ef(A,d,I,J,selectors)
    assert B.nnz<=15000000 and B.shape[0]<=1500000,'REGISTERED_EXPLICIT_FORMULATION_SIZE_LIMIT'
    sparse.save_npz(OUT/f'{label}_ADDED_MATRIX.npz',B);np.savez_compressed(OUT/f'{label}_DATA.npz',**e);atomic(OUT/f'{label}_SPEC.json',spec)
    census=dict(PASS=True,label=label,units=units,start=start,end_exclusive=end,original_rows=A.shape[0],original_columns=A.shape[1],original_nnz=A.nnz,added_rows=B.shape[0],added_columns=B.shape[1]-A.shape[1],added_nnz=B.nnz,source_row_families=__import__('collections').Counter(str(d['row_names'][i]).split('[')[0] for i in I),full_matrix_rows=A.shape[0]+B.shape[0],full_matrix_columns=B.shape[1],all_new_bounds_finite=bool(np.isfinite(e['lower']).all() and np.isfinite(e['upper']).all()),source_rows_SHA256=hashlib.sha256(I.tobytes()).hexdigest(),matrix_SHA256=sha(OUT/f'{label}_ADDED_MATRIX.npz'),data_SHA256=sha(OUT/f'{label}_DATA.npz'),spec_SHA256=sha(OUT/f'{label}_SPEC.json'),root_TimeLimit=600)
    atomic(OUT/f'{label}_MODEL_CENSUS.json',census);print(json.dumps(clean(census)),flush=True)
    return B,e,spec
if __name__=='__main__':build_candidate(sys.argv[1])
