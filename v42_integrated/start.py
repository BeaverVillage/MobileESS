"""Optional historical warm start; independent of historical certificate values."""
import math
import numpy as np
from .matrix import audit

PRIMARY=('arc','SOC','charge_mode','Pch','Pdis','Q','rho_max')

def reconstruct(A,d,source_names,source_values):
    values=dict(zip(map(str,source_names),map(float,source_values)))
    point=np.zeros(A.shape[1]);helpers=[]
    for j,name in enumerate(d['names']):
        if str(name).split('[',1)[0] in PRIMARY:
            if str(name) not in values:raise ValueError('PRIMARY_MAPPING_NOT_EXACT')
            point[j]=values[str(name)]
        else:helpers.append(j)
    pending=set(helpers);rules=[]
    for i,name in enumerate(d['row_names']):
        if '_binding' not in str(name):continue
        row=A[i];candidates=[int(j) for j in row.indices if int(j) in pending]
        if not candidates:continue
        target=max(candidates);pivot=dict(zip(row.indices,row.data))[target]
        if d['sense'][i]!='=' or pivot!=1. or any(j>target for j in row.indices):
            raise ValueError('NONTRIANGULAR_EXACT_HELPER')
        rules.append((target,i));pending.remove(target)
    if pending:raise ValueError('AUXILIARY_DEFINITION_INCOMPLETE')
    for target,i in sorted(rules):
        row=A[i];point[target]=math.fsum([float(d['rhs'][i])]+[-float(a)*point[j] for j,a in zip(row.indices,row.data) if j!=target])
    return point,audit(A,d,point,integral=True)

def compatible(new_anchor, old_anchor):
    if new_anchor['control_names']!=old_anchor['control_names']:return False
    columns=new_anchor['fixed_AIDC_control_columns']
    return np.array_equal(np.asarray(new_anchor['controls'])[:,columns],np.asarray(old_anchor['controls'])[:,columns])
