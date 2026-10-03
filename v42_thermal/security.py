"""Independent raw-A security classification; no inherited current_pu trust."""
import numpy as np
from .authority import current_authority,denominators,arm_contract,require_certificate

def classify(raw,*,arm='B0'):
    names=raw['branch_names'];amps=np.asarray(raw['current_A']);v=np.asarray(raw['V_ACTUAL_AC']);kva=np.asarray(raw['transformer_kVA_pu'])
    limits=denominators(names);ratios=amps/limits
    if amps.ndim!=2 or amps.shape[1]!=len(names) or not np.isfinite(amps).all() or (amps<0).any() or not np.isfinite(v).all():raise ValueError('RAW_SECURITY_ARRAY_INVALID')
    tx=np.array([str(n).lower().startswith('transformer.') for n in names])
    if not np.isfinite(kva[:,tx]).all():raise ValueError('TRANSFORMER_KVA_ARRAY_INVALID')
    masks=dict(voltage=(v<.95)|(v>1.05),line_current=ratios[:,~tx]>1,
        transformer_current=ratios[:,tx]>1,transformer_kVA=kva[:,tx]>1)
    result=dict(**arm_contract(arm),converged=bool(np.all(raw['converged'])),
        cells={k:int(a.sum()) for k,a in masks.items()},days_with_violation={k:bool(a.any()) for k,a in masks.items()},
        max_transformer_current_pu=float(ratios[:,tx].max()),max_line_current_pu=float(ratios[:,~tx].max()))
    result['FULL_AC_SECURITY_PASS']=result['converged'] and not any(result['cells'].values())
    return result,ratios

def require_security_receipt(receipt):
    require_certificate(receipt)
    if receipt.get('FULL_AC_SECURITY_PASS') is not True or not receipt.get('converged') or any(receipt.get('cells',{}).get(k)!=0 for k in ('voltage','line_current','transformer_current','transformer_kVA')):
        raise ValueError('COMMON_FULL_AC_SECURITY_FAIL')
    return True
