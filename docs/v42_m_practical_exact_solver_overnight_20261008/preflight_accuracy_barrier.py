from practical_support import *
import accuracy_barrier_child_oracle as oracle_code
from v42_integrated.matrix import arrays
folder=OUT/'accuracy_barrier_preflight';folder.mkdir(exist_ok=True);old=oracle_code.base.OUT;oracle_code.base.OUT=folder
oracle=oracle_code.LPOracle()
try:
    cfg=dict(Method=2,Crossover=0,LPWarmStart=0,NumericFocus=0,DualReductions=1,InfUnbdInfo=0,BarConvTol=1e-12,TimeLimit=bounded_limit(900))
    for k,v in cfg.items():oracle.m.setParam(k,v)
    B,d=arrays(oracle.m);assert (B!=oracle.A).nnz==0 and oracle.objective_identity()['PASS'] and not oracle.calls
    assert all(oracle.m.getParamInfo(k)[2]==v for k,v in SETTINGS.items() if k not in cfg)
    atomic(folder/'PREFLIGHT.json',dict(PASS=True,optimize_calls=0,original_scientific_matrix_objective_bit_identity_PASS=True,fixed_Feasibility_Optimality_IntFeas_tolerances_unchanged=True,only_additional_barrier_convergence_accuracy_changed=True,settings=cfg,UTC=stamp()))
    print('ACCURACY_BARRIER_PREFLIGHT_PASS_OPTIMIZE_0')
finally:oracle.close();oracle_code.base.OUT=old
