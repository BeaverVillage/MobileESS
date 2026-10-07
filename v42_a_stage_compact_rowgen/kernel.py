"""Exact count-scaled perspective kernel plus one column per frozen path.

The retained sum kernel is essential: concrete vertices alone do not preserve
the original native LP's fractional WAN directions. Identical optional lanes
project exactly by their sum. Its rational inverse splits the sum equally.

For cardinality N, residual mass k and path counts mu satisfy k+sum(mu)=N.
A*z <= (b/N)*k, L/N*k <= z <= U/N*k; every path contributes B*p/N*mu.
All compiled coefficients must have EXACT binary64 representations. Normalized
lambda=mu/N is a mathematical identity; no rounded 1/N enters the matrix.
Forward lifting z+sum(p/N*mu) lies in the original sum kernel. The inverse
chooses mu=0,k=N and retains z, so ALL original fractional directions survive.
"""
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_early.candidate import exact_coupling
from .projection import exact_replay

def binary64(value):
    value=Fraction(value);f=float(value)
    if Fraction(f)!=value:raise ValueError('COMPACT_NONEXACT_BINARY64_COEFFICIENT:'+str(value))
    return f

def perspective(snapshot,B,points,N):
    count=len(points);width=snapshot.matrix.shape[1];k=width;mu=width+1
    for p in points:
        if not exact_replay(snapshot,p)['PASS']:raise ValueError('CONCRETE_ENDPOINT_NOT_EXACT_NATIVE_FEASIBLE')
    rhs_job=np.asarray([binary64(Fraction(float(v))/N) for v in snapshot.rhs])
    A=sp.hstack((snapshot.matrix,sp.csr_matrix(-rhs_job.reshape(-1,1)),sp.csr_matrix((len(rhs_job),count))),format='csr')
    rows=[A];senses=list(snapshot.senses);rhs=[0.]*A.shape[0]
    ri=[];cj=[];vv=[];bound_senses=[]
    for j,(lo,hi) in enumerate(zip(snapshot.lower,snapshot.upper)):
        for bound,sense in ((lo,'>'),(hi,'<')):
            if abs(bound)>=1e100 or bound==0:continue
            i=len(bound_senses);bound_senses.append(sense)
            ri.extend((i,i));cj.extend((j,k));vv.extend((1.,-binary64(Fraction(float(bound))/N)))
    if bound_senses:
        rows.append(sp.csr_matrix((vv,(ri,cj)),shape=(len(bound_senses),width+1+count)))
        senses.extend(bound_senses);rhs.extend([0.]*len(bound_senses))
    rows.append(sp.csr_matrix(([1.]*(count+1),([0]*(count+1),list(range(k,width+1+count)))),shape=(1,width+1+count)))
    senses.append('=');rhs.append(float(N))
    C=[]
    for p in points:
        exact=exact_coupling(B,p)
        C.append(sp.csr_matrix(([binary64(v/N) for i,v in sorted(exact.items())],([i for i,v in sorted(exact.items())],[0]*len(exact))),shape=(B.shape[0],1)))
    coupling=sp.hstack([B,sp.csr_matrix((B.shape[0],1)),*C],format='csr')
    objectives=[]
    for obj in snapshot.objectives:
        terms=list(obj.terms)
        for i,p in enumerate(points):
            value=sum((c*Fraction(float(p[j])) for j,c in obj.coefficients().items()),Fraction(0))/N
            if value:terms.append((mu+i,Fraction(binary64(value))))
        objectives.append(replace(obj,terms=tuple(terms)))
    extended=replace(snapshot,matrix=sp.vstack(rows,format='csr'),lower=np.r_[np.minimum(0,snapshot.lower),np.zeros(1+count)],
        upper=np.r_[np.maximum(0,snapshot.upper),np.full(1+count,float(N))],senses=np.asarray(senses),rhs=np.asarray(rhs),
        vtypes=np.full(width+1+count,'C'),objectives=tuple(objectives)).require()
    return extended,coupling,dict(kernel_columns=width,residual_mass_column=k,compact_path_columns=tuple(range(mu,mu+count)),
        cardinality=N,normalized_lambda='mu/N (exact rational; no rounded reciprocal compiled)',
        all_compiled_coefficients_exact_binary64=True,retains_all_native_fractional_directions=True)

def rational_lift(point,points,N):
    width=len(points[0]);result=[Fraction(float(v)) for v in point[:width]]
    for i,p in enumerate(points):
        mass=Fraction(float(point[width+1+i]))
        for j,v in enumerate(p):
            if v:result[j]+=Fraction(float(v))*mass/N
    return result
