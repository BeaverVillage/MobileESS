"""Inherited exact integer Z definition, with independently checked lift."""
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import Objective,integer_objective_proof

def define(snapshot,name):
    proof=integer_objective_proof(snapshot,name);o=snapshot.objective(name);co=o.coefficients();n=snapshot.matrix.shape[1]
    if o.constant<0 or any(c<0 or snapshot.lower[j]<0 for j,c in co.items()):raise ValueError('NONNEGATIVE_INTEGER_OBJECTIVE_REQUIRED')
    row=sp.csr_matrix(([-float(v) for v in co.values()]+[1.],([0]*(len(co)+1),list(co)+[n])),shape=(1,n+1))
    A=sp.vstack((sp.hstack((snapshot.matrix,sp.csr_matrix((snapshot.matrix.shape[0],1))),format='csr'),row),format='csr')
    objectives=tuple(Objective(name,((n,Fraction(1)),),0) if v.name==name else v for v in snapshot.objectives)
    result=replace(snapshot,matrix=A,lower=np.append(snapshot.lower,0),upper=np.append(snapshot.upper,np.inf),vtypes=np.append(snapshot.vtypes,'I'),
        senses=np.append(snapshot.senses,'='),rhs=np.append(snapshot.rhs,float(o.constant)),objectives=objectives).require()
    return result,dict(PASS=True,component=name,original_integrality=proof,original_columns=n,Z_column=n,
        defining_row=snapshot.matrix.shape[0],original_objective_constant=str(o.constant),same_LP_projection=True,
        same_integer_schedules=True,same_original_objective_values=True,unique_lift='Z=original integer affine objective',
        artificial_variable=False,original_rows_boxes_types_unchanged=True)

def fix_case(snapshot,Z,value):
    if type(value) is not int:raise ValueError('EXACT_INTEGER_CASE_REQUIRED')
    lower=snapshot.lower.copy();upper=snapshot.upper.copy();lower[Z]=value;upper[Z]=value
    return replace(snapshot,lower=lower,upper=upper).require()
