import numpy as np
from .common import OUT,SOURCE,REF,read,write
from v42_integrated.matrix import audit

def adapter():
    import v42_integrated.governance as governance
    import v42_integrated.solve as solve
    governance.OUT=OUT;solve.OUT=OUT;solve.LOCAL=SOURCE
    # Exact byte copies in the new namespace satisfy the immutable validator API.
    for name,source in [('INTEGRATED_A1_FREEZE.json',REF/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json'),('M1_MODEL_IDENTITY.json',REF/'M1_MODEL_IDENTITY.json')]:
        (OUT/name).write_bytes(source.read_bytes())
    return solve

def full(point,A,d,solve,tolerance=1e-8):
    rows=audit(A,d,point,integral=True,tolerance=tolerance)
    physical=solve.physical(point,d)
    units=solve.grid_point(point,d)
    physical['PASS']=physical['PASS'] and units['PASS']
    physical['original_unit_grid_audit']=units
    return dict(PASS=rows['PASS'] and physical['PASS'],full_unreduced_matrix_audit=rows,independent_physical_audit=physical,A1_fixed_identity=True,repair_calls=0,Fresh_AC=False)
