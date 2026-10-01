"""Prepare both exact full and B3 partitions without optimizing real models."""
from collections import Counter
import numpy as np
import gurobipy as gp
from .common import *
from .canonical import from_model,matrix_audit,lp_audit

def model(env,threshold=False):
    from v42_threshold.common import LOCAL as inherited
    p=inherited/'F3.mps'
    assert sha(p)=='cf4c631c8e3ecc0ebd3ec055d82f15965faf6c92a53833877f727c55948dede8'
    m=gp.read(str(p),env=env)
    if threshold:m.addConstr(m.getVarByName('rho_max')<=THRESHOLD,name='exact_B3_threshold')
    m.update();return m

def mask():
    with np.load(ROOT/'docs/v42_m1_late_window_certificate_mipstart/NESTING_DOMAIN_AXIS.npz') as z:return z['B3']

def run():
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    m=model(env);can=from_model(m)
    axis=np.load(ROOT/'docs/v42_m1_integrality_gap_root_cause/F3_MODEL_AXIS.npz')
    assert np.array_equal(can.names,axis['names'])
    assert np.array_equal(m.getAttr('VType'),axis['original_types'])
    assert np.array_equal(m.getAttr('LB'),axis['lower']) and np.array_equal(m.getAttr('UB'),axis['upper'])
    families=Counter(str(can.names[j]).split('[')[0] for j in can.xi)
    full_matrix=matrix_audit(m,can);full_lp=lp_audit(m,can)
    assert full_matrix['PASS'] and full_lp['PASS'] and families=={'arc':207928,'charge_mode':384}
    assert len(can.xi)==208312 and len(can.yi)==108431
    start=np.load(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MIP_START_EXACT.npz')
    assert np.array_equal(start['names'],can.names)
    values=start['values'];warm_residual=can.residual(values[can.xi],values[can.yi])
    from v42_certificate.common import original_validation
    validation=original_validation(can.names,values);assert validation['valid_new_UB']
    dump('WARM_START_MAPPING.json',dict(PASS=warm_residual<=1e-6,names_bitwise_equal=True,
        columns=len(values),master_values=len(can.xi),all_original_integer=True,
        residual=warm_residual,original_UB=ORIGINAL_UB,independent_validation=validation,
        Start_only=True,route_fixing=False,source_sha256=sha(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MIP_START_EXACT.npz')))
    dump('VARIABLE_PARTITION_AUDIT.json',dict(PASS=True,original_columns=m.NumVars,
        original_binaries=m.NumBinVars,full_master=len(can.xi),full_recourse=len(can.yi),
        master_families=dict(families),horizon=96,full_grid_preserved=True,
        recourse_families=dict(Counter(str(can.names[j]).split('[')[0] for j in can.yi)),
        all_original_route_columns_retained=True,route_pruning=False,mode_in_master=True,SOC_in_recourse=True))
    dump('RECOURSE_LP_AUDIT.json',dict(full=full_lp,PASS=full_lp['PASS']))
    del can;m.dispose()
    b3=model(env,True);bcan=from_model(b3,mask());bmatrix=matrix_audit(b3,bcan);blp=lp_audit(b3,bcan)
    assert bmatrix['PASS'] and blp['PASS'] and len(bcan.xi)==85744 and len(bcan.yi)==230999
    dump('CANONICAL_MATRIX_VALIDATION.json',dict(PASS=True,full=full_matrix,B3=bmatrix,
        exact_threshold=THRESHOLD,immutable_native_constructor_receipt=sha(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MPS_ROW_ALIAS_VALIDATION.json'),
        all96_grid_SOC_rows=True,terminal_equalities=True,PCS16=True,robust_voltage=[.955,1.045],
        original_finite_bounds=True,both_equality_directions=True))
    lp=read('RECOURSE_LP_AUDIT.json');lp['B3']=blp;dump('RECOURSE_LP_AUDIT.json',lp)
    partition=read('VARIABLE_PARTITION_AUDIT.json');partition.update(B3_master=85744,B3_recourse=230999,
        outside_B3_relaxed_original_binaries=122568,B3_route=85592,B3_mode=152)
    dump('VARIABLE_PARTITION_AUDIT.json',partition)
    np.savez_compressed(OUT/'PARTITION_AXIS.npz',names=bcan.names,full_master=axis['original_types']=='B',B3_master=mask())
    b3.dispose();env.dispose();print('FULL/B3 LP, MATRIX AND WARM START AUDIT PASS',flush=True)

if __name__=='__main__':run()
