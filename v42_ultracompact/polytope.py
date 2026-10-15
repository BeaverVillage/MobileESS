"""Exact stored rational H-polytopes and positive two-plane Farkas proofs."""
from fractions import Fraction as F
from itertools import combinations
from functools import lru_cache
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
@lru_cache(maxsize=16384)
def _bounds(numerator,denominator):
    import numpy as np
    x=F(numerator,denominator);v=float(x);stored=F(v)
    return (v if stored<=x else float(np.nextafter(v,-np.inf)),
            v if stored>=x else float(np.nextafter(v,np.inf)))

def down(x):
    return _bounds(x.numerator,x.denominator)[0]

def up(x):
    return _bounds(x.numerator,x.denominator)[1]
