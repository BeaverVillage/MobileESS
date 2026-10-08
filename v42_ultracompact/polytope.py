"""Exact stored rational H-polytopes and positive two-plane Farkas proofs."""
from fractions import Fraction as F
from itertools import combinations
def vertices(planes):
    out=set()
    for i,j in combinations(range(len(planes)),2):
        a,b,c=planes[i];d,e,f=planes[j];det=a*e-b*d
        if not det:continue
        x=(c*e-b*f)/det;y=(a*f-c*d)/det
        if all(p*x+q*y<=r for p,q,r in planes):out.add((x,y))
    return sorted(out)
def farkas(target,planes):
    a,b,c=target;best=None
    for i,j in combinations(range(len(planes)),2):
        p,q,r=planes[i];s,t,u=planes[j];det=p*t-q*s
        if not det:continue
        l=(a*t-b*s)/det;m=(p*b-q*a)/det
        if l<0 or m<0:continue
        bound=l*r+m*u
        if bound<=c and (best is None or bound<best[0]):best=(bound,i,j,l,m)
    return best
def minimal(planes):
    keep=list(range(len(planes)));removed={}
    for i in list(keep):
        others=[j for j in keep if j!=i];proof=farkas(planes[i],[planes[j] for j in others])
        if proof:
            bound,a,b,l,m=proof;removed[i]=dict(support=[others[a],others[b]],multipliers=[str(l),str(m)],slack=str(planes[i][2]-bound));keep.remove(i)
    # Rebuild every certificate solely from the final retained H representation.
    for i in removed:
        bound,a,b,l,m=farkas(planes[i],[planes[j] for j in keep]);removed[i]=dict(support=[keep[a],keep[b]],multipliers=[str(l),str(m)],slack=str(planes[i][2]-bound))
    return keep,removed
def down(x):
    import numpy as np
    v=float(x);return v if F(v)<=x else float(np.nextafter(v,-np.inf))
def up(x):
    import numpy as np
    v=float(x);return v if F(v)>=x else float(np.nextafter(v,np.inf))
