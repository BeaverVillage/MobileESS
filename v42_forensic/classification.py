"""Preregistered evidence gates; absence of bound movement is not negative."""
from .common import F3,UB

def classify(arms,best_ub):
    gain=max(a['LB_gain'] for a in arms);ubgain=UB-best_ub
    active=next(a for a in arms if a['name']=='R_ACTIVE');buffer=next(a for a in arms if a['name']=='R_BUFFER')
    allnegative=all(a['negative_certificate'] for a in arms)
    if gain>=.001 and ubgain>=.005:label='CASE_C_MIXED'
    elif gain>=.01 and ubgain<.005:label='CASE_A_LB_DOMINATED'
    elif allnegative and ubgain>=.005:label='CASE_B_UB_DOMINATED'
    elif active['negative_certificate'] and buffer['negative_certificate'] and ubgain<.005:label='CASE_D_GLOBAL_BROADER_COUPLING'
    else:label='CASE_E_INCONCLUSIVE'
    return dict(ROOT_CAUSE_CLASS=label,max_partial_LB_gain=gain,UB_gain=ubgain,required_negative_certificates_available=allnegative,
        LB_WEAKNESS_MATERIAL=gain>=.001,INCUMBENT_QUALITY_MATERIAL=ubgain>=.005,
        no_improvement_does_not_prove_incumbent_globally_good=True,unchanged_BestBd_is_not_negative_evidence=True)
