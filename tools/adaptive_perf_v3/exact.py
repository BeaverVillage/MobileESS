"""Exact integer original alias operator and dynamic links, independently derived."""
from scipy import sparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.proof import inverse
def alias_operator(case,route):
    expand=inverse(case);position={j:i for i,j in enumerate(route)};position_set=set(position);rows=[];cols=[];coeff=[];constant=[];axes=[]
    for j,name in enumerate(map(str,case.original_d['names'])):
        family=name.split('[',1)[0]
        if family not in ('arc','node_activity'):continue
        fields=name.split('[',1)[1][:-1].split(',');offset,terms=expand(j)
        assert offset.denominator==1 and set(terms)<=position_set
        assert all(value.denominator==1 for value in terms.values())
        row=len(axes);axes.append((j,family,fields));constant.append(int(offset))
        for col,value in terms.items():rows.append(row);cols.append(position[col]);coeff.append(int(value))
        assert abs(int(offset))+sum(abs(int(value)) for value in terms.values())<2**62
    M=sparse.csr_matrix((np.asarray(coeff,dtype=np.int64),(rows,cols)),shape=(len(axes),len(route)))
    return M,np.asarray(constant,dtype=np.int64),axes

def independent_links(case,spec,route,operator):
    graph=Graph(case);names=list(map(str,case.d['names']));M,constant,axes=operator;L=spec['lambda_count']
    values=np.zeros((len(route),L),dtype=np.int64);routeunits=[]
    for j in route:routeunits.append(names[j].split('[',1)[1].split(',')[0])
    for col,entry in enumerate(spec['lambda_axis']):
        u=entry['unit'];path=entry['path'];arcs=set(path);vertices={graph.arcs[k][:2] for k in path}|{(graph.arcs[path[-1]][2],96)}
        graph.validate(u,path)
        for k,j in enumerate(route):
            if routeunits[k]!=u:continue
            family,fields=names[j].split('[',1);axis=fields[:-1].split(',')
            values[k,col]=int(int(axis[1]) in arcs) if family=='route_flow' else int((axis[1],int(axis[2])) in vertices)
        selected=[i for i,(j,family,fields) in enumerate(axes) if fields[0]==u]
        actual=np.asarray(M[selected]@values[:,col]).ravel()+constant[selected]
        expected=np.asarray([int(int(axes[i][2][1]) in arcs) if axes[i][1]=='arc' else int((axes[i][2][1],int(axes[i][2][2])) in vertices) for i in selected])
        assert np.array_equal(actual,expected)
        original=np.asarray([axes[i][0] for i in selected]);assert np.all(expected>=case.original_d['lower'][original]) and np.all(expected<=case.original_d['upper'][original])
    lower=case.d['lower'].copy();upper=case.d['upper'].copy();rr=[];cc=[];vv=[];vary=[]
    for row,u in enumerate(sorted(spec['pools'])):
        for col,a in enumerate(spec['lambda_axis']):
            if a['unit']==u:rr.append(row);cc.append(354277+col);vv.append(1.)
    for k,j in enumerate(route):
        columns=[col for col,a in enumerate(spec['lambda_axis']) if a['unit']==routeunits[k]];vrow=values[k,columns]
        lower[j]=vrow.min();upper[j]=vrow.max()
        if lower[j]==upper[j]:continue
        row=4+len(vary);vary.append(j);rr.append(row);cc.append(j);vv.append(1.)
        for col in columns:
            if values[k,col]:rr.append(row);cc.append(354277+col);vv.append(-1.)
    A=sparse.csr_matrix((vv,(rr,cc)),shape=(4+len(vary),354277+L));rhs=np.r_[np.ones(4),np.zeros(len(vary))]
    # Builder's row order follows grouped unit coordinates; derive that order explicitly.
    unit_for={j:u for j,u in zip(route,routeunits)}
    expected_order=sorted(vary,key=lambda j:(unit_for[j],j));positions={j:i for i,j in enumerate(vary)}
    A=A[[0,1,2,3]+[4+positions[j] for j in expected_order]]
    assert expected_order==spec['varying_route_columns']
    signature=hashlib.sha256()
    for value in (lower,upper):signature.update(value.tobytes())
    signature.update(v.matrix_sha(A).encode());signature.update(rhs.tobytes())
    center=v.load_point(spec['center_raw']['path']);assert v.vector_sha(center)==spec['center_vector_SHA']
    assert np.array_equal(A@np.r_[center,spec['lambda_Start']],rhs)
    return A,signature.hexdigest()
