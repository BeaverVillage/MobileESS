"""Preflight the registered cold node LP using original source arrays; solve=0."""
from practical_support import *
import cold_barrier_child_oracle as oracle_code
from v42_integrated.matrix import arrays
from fractions import Fraction as F

def run():
    folder=OUT/'cold_barrier_preflight';folder.mkdir(exist_ok=True);old=oracle_code.OUT;oracle_code.OUT=folder
    oracle=oracle_code.LPOracle()
    try:
        checkpoint=read(OUT/'external_production/OPEN_CHECKPOINT.json')['state'];j=checkpoint['nodes']['0']['children'][0];node=checkpoint['nodes'][str(j)]
        e=dict(oracle.d,types=np.full(oracle.A.shape[1],'C'),lower=oracle.d['lower'].copy(),upper=oracle.d['upper'].copy())
        for col,value in node['fixings']:e['lower'][col]=e['upper'][col]=value
        m=oracle.m;m.setAttr('LB',oracle.variables,e['lower'].tolist());m.setAttr('UB',oracle.variables,e['upper'].tolist());m.update()
        cfg=dict(Method=2,Crossover=0,LPWarmStart=0,NumericFocus=0,DualReductions=1,InfUnbdInfo=0,TimeLimit=bounded_limit(900))
        for k,v in cfg.items():m.setParam(k,v)
        B,transport=arrays(m);assert (B!=oracle.A).nnz==0 and all(np.array_equal(e[k],transport[k]) for k in e)
        assert oracle.objective_identity()['PASS'] and not oracle.calls
        assert all(m.getParamInfo(k)[2]==v for k,v in SETTINGS.items() if k not in cfg)
        core=oracle_code.core;bb=core.ExactBB(oracle.identity,str(F.from_float(.5687116104049206)),str(F.from_float(.6306505800203936)),dict(fixture=True));root=bb.select();bb.begin(root)
        r=dict(identity=oracle.identity,fixing_hash=root['fixing_hash'],proof_checked=True,LP_status='OPTIMAL',certified_LB='1/2',optimal_LP_certificate_PASS=True,exact_infeasibility_PASS=False,branch_variable=node['branch_variable'],branch_is_original_binary=True,raw_fractional_branch_value=.49990505638503346,witness=None)
        bb.apply(0,r);before=bb.audit();child=bb.select();bb.begin(child);bb.apply(child['id'],dict(r,fixing_hash=child['fixing_hash'],LP_status='UNRESOLVED',native_status=3,certified_LB=None,optimal_LP_certificate_PASS=False,branch_variable=None));after=bb.audit()
        assert after['OPEN']==[1,2] and before['global_OPEN_min_LB_exact']==after['global_OPEN_min_LB_exact'] and bb.select()['id']==2
        atomic(folder/'PREFLIGHT.json',dict(PASS=True,optimize_calls=0,actual_original_matrix_transport_identical=True,original_objective_bit_identity_PASS=True,only_original_binary_bound_fixed=True,settings=cfg,all_other_fixed_settings_PASS=True,crossover_disabled_no_basis_claim=True,native_infeasible_without_exact_ray_kept_OPEN=True,both_children_preserved=True,unresolved_first_child_does_not_block_sibling=True,UTC=stamp()))
        print('COLD_BARRIER_PREFLIGHT_PASS_OPTIMIZE_0')
    finally:oracle.close();oracle_code.OUT=old
if __name__=='__main__':run()
