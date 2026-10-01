"""Full original-domain promotion requires every binary and independent physics."""
import numpy as np

def original_point(model,names,values):
    from v42_certificate.common import original_validation
    from v42_threshold.common import matrix_validation,axis
    from v42_threshold.validate import physical,grid
    inherited=original_validation(names,values)
    matrix=matrix_validation(model,values)
    fractionality=float(np.max(abs(values[axis()['original_types']=='B']-
        np.rint(values[axis()['original_types']=='B'])),initial=0))
    battery=physical(names,values);electrical,slots=grid(names,values)
    passed=bool(inherited['valid_new_UB'] and matrix['PASS'] and fractionality<=1e-7 and battery['PASS'] and electrical['PASS'])
    return dict(PASS=passed,inherited_original_validation=inherited,matrix=matrix,
        all_original_binary_max_fractionality=fractionality,physical=battery,grid=electrical,
        robust_voltage=[.955,1.045],full96=True,Actual_repair=False)
