"""Exhaustive exact rational polytope vertices, no native optimize calls."""
from fractions import Fraction as F
from itertools import combinations,product

def solve(a,b):
    a=[list(map(F,row))+[F(y)] for row,y in zip(a,b)];n=len(a)
    for j in range(n):
        k=next((k for k in range(j,n) if a[k][j]),None)
        if k is None:return None
        a[j],a[k]=a[k],a[j];d=a[j][j];a[j]=[v/d for v in a[j]]
        for k in range(n):
            if k!=j:
                d=a[k][j];a[k]=[v-d*w for v,w in zip(a[k],a[j])]
    return tuple(row[-1] for row in a)

def vertices(n,rows):
    eq=[(a,b) for a,s,b in rows if s=='='];ineq=[(a,b) for a,s,b in rows if s=='<'];result=set()
    basis=[]
    for a,b in eq:
        row=list(map(F,a))+[F(b)]
        for j,previous in basis:
            scale=row[j];row=[x-scale*y for x,y in zip(row,previous)]
        j=next((i for i in range(n) if row[i]),None)
        if j is None:
            if row[-1]:return []
        else:
            scale=row[j];row=[x/scale for x in row];basis.append((j,row));basis.sort(key=lambda x:x[0])
    eq=[(r[:-1],r[-1]) for j,r in basis]
    for chosen in combinations(ineq,n-len(eq)):
        v=solve([a for a,b in eq+list(chosen)],[b for a,b in eq+list(chosen)])
        if v is not None and all(sum(F(c)*x for c,x in zip(a,v))==b if s=='=' else sum(F(c)*x for c,x in zip(a,v))<=b for a,s,b in rows):result.add(v)
    return sorted(result)

def bounds(n,upper):
    return [(tuple(-int(i==j) for i in range(n)),'<',0) for j in range(n)]+[(tuple(int(i==j) for i in range(n)),'<',F(u)) for j,u in enumerate(upper)]

def cases():
    # Each block retains all vertices for each integral route/mode assignment,
    # including continuous faces. PCS fixture uses every facet of this fixture.
    return [
        ('route_split',2,[1,1],[0,1],[([1,1],'=',1),([-2,0],'<',-1)],[1,0],1),
        ('charge_mode',3,[1,1,1],[0],[([-1,1,0],'<',0),([1,0,1],'<',1),([0,1,-1],'=',0)],[0,-1,-1],1),
        ('SOC_travel_energy',3,[1,F(1,2),1],[0],[([1,-1,1],'=',1),([0,0,1],'=',1)],[0,-1,0],1),
        ('PCS',3,[1,1,1],[0],[([-1,1,0],'<',0),([1,0,1],'<',1),([0,1,1],'<',1),([0,1,-1],'<',1),([0,-1,1],'<',1),([0,-1,-1],'<',1)],[0,-1,-1],1),
        ('grid_coupling',1,[1],[0],[([-2],'<',-1)],[1],1),
        ('terminal_SOC',2,[1,1],[0],[([1,1],'=',1),([0,-1],'<',F(-3,4))],[-1,0],1),
        ('multi_MESS_coupling',1,[1],[0],[([-2],'<',-1)],[1],2),
    ]

def run():
    result=[]
    for name,n,upper,ints,local,cost,blocks in cases():
        lr=bounds(n,upper)+[(tuple(a),s,F(b)) for a,s,b in local]
        arc=vertices(n,lr);iv=[]
        for values in product((0,1),repeat=len(ints)):
            extra=[(tuple(int(i==j) for i in range(n)),'=',F(v)) for j,v in zip(ints,values)]
            iv+=vertices(n,lr+extra)
        iv=sorted(set(iv));assert arc and iv
        # Original joint LP/MILP: shared rho >= sum cost*x; finite shared bound.
        N=n*blocks+1;joint=bounds(N,upper*blocks+[4])
        for m in range(blocks):
            for a,s,b in local:joint.append((tuple([0]*(n*m)+list(a)+[0]*(n*(blocks-m-1)+1)),s,F(b)))
        offset=blocks if any(c<0 for c in cost) else 0
        joint.append((tuple(cost*blocks+[-1]),'<',-offset))
        av=vertices(N,joint);za=min(x[-1] for x in av)
        zv=[]
        for values in product((0,1),repeat=len(ints)*blocks):
            indices=[m*n+j for m in range(blocks) for j in ints]
            extra=[(tuple(int(i==j) for i in range(N)),'=',F(v)) for j,v in zip(indices,values)]
            zv+=vertices(N,joint+extra)
        zi=min(x[-1] for x in zv)
        # Full DW LP: all enumerated continuous vertices, every convexity row,
        # exactly the same original shared rho and coupling coefficient.
        K=len(iv);D=K*blocks+1;dw=bounds(D,[1]*(D-1)+[4])
        for m in range(blocks):dw.append((tuple(int(m*K<=i<(m+1)*K) for i in range(D)),'=',1))
        projected=[sum(F(c)*x for c,x in zip(cost,v)) for v in iv]
        dw.append((tuple(projected*blocks+[-1]),'<',-offset));dv=vertices(D,dw);zd=min(x[-1] for x in dv)
        # Integer master chooses one local vertex per block; rho stays continuous.
        zdi=min(max(F(0),offset+sum(projected[j] for j in js)) for js in product(range(K),repeat=blocks))
        assert za<=zd<=zi and zdi==zi
        result.append(dict(fixture=name,blocks=blocks,all_local_integer_assignments=2**len(ints),all_integer_face_vertices=K,arc_vertices=len(av),DW_vertices=len(dv),z_arc_LP=str(za),z_DW_LP=str(zd),z_original_integer=str(zi),z_DW_integer=str(zdi),PASS=True,rows=[dict(a=list(map(str,a)),sense=s,rhs=str(b)) for a,s,b in lr],local_vertices=[[str(x) for x in v] for v in iv],coupling='sum cost*x - rho <= -offset',offset=offset,cost=list(map(str,cost))))
    return dict(PASS=True,method='Exact Fraction Gaussian elimination of every active-row combination and every binary assignment; full continuous-face vertex enumeration, no native solver, no sampled vertices.',native_optimize_calls=0,fixtures=result,scope='Small independent bounded fixtures; inclusion theorem and actual full-scale matrix audit provide the full-domain proof, these fixtures are regression checks.')
