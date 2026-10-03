"""Source values, raw classifications and actual hard-row authority regression."""
import copy
from types import SimpleNamespace
import math
import numpy as np
import pandas as pd
import pytest
from v42_thermal.common import *
from v42_thermal.authority import current_authority,denominators,checked_normal,require_certificate,arm_contract
from v42_thermal.planning import bind_coefficient,require_coefficient,normalized_response
from v42_thermal.security import classify,require_security_receipt

@pytest.mark.parametrize('index',range(120))
def test_all_phase_denominators_are_identical_compiled_sources(index):
    a=current_authority();p=a['Planning'][index];r=a['Actual'][index]
    assert p==r and r['new_denominator_A']==r['NormalAmps']>0
    assert math.isfinite(r['NormalAmps']) and r['parent_terminal']==1
    assert denominators([r['branch_phase']])[0]==r['NormalAmps']
    assert r['kVA']>0 and not r['CTPrim_used'] and not r['tap_used']

@pytest.mark.parametrize('value',[None,'',0,-1,float('nan'),float('inf')])
def test_invalid_normalamps_fails_instead_of_nameplate_fallback(value):
    with pytest.raises(ValueError,match='SOURCE_NORMALAMPS'):checked_normal(value,'invalid')

def test_reg1a_nameplate_normal_and_CT_are_distinct():
    r=next(r for r in current_authority()['rows'] if r['branch_phase']=='transformer.reg1a::A')
    assert r['NormalAmps']==pytest.approx(763.323673207438,abs=1e-12)
    assert r['old_denominator_A']==pytest.approx(693.9306120067617,abs=1e-12)
    assert r['old_denominator_A']==5000/(math.sqrt(3)*4.16)
    assert r['NormalAmps']!=700 and r['difference_percent']==pytest.approx(10)

@pytest.mark.parametrize('month,source,days',[('APRIL',APRIL,30),('MAY',MAY,31)])
def test_full_month_independent_reclassification_and_raw_SHA(month,source,days):
    result=read(OUT/(month+'_B0_CURRENT_RECLASSIFICATION.json'));assert result['days']==days
    counts={k:0 for k in ('voltage','line_current','transformer_current','transformer_kVA')};bad_days=0;maxpu=0
    audit=pd.read_csv(OUT/'TRANSFORMER_CURRENT_AUTHORITY_AUDIT.csv',float_precision='round_trip')
    limits=dict(zip(audit.branch_phase,audit.NormalAmps))
    lines=current_authority()['lines'];limits.update({r['branch_phase']:r['NormalAmps'] for r in lines})
    for d,r in enumerate(result['source_files'],1):
        assert sha(resolve(r))==r['sha256']
        with np.load(source/'BUNDLE'/day_folder(f'2025-{4 if month=="APRIL" else 5:02d}-{d:02d}')/'V_ACTUAL_AC.npz') as raw:
            names=list(map(str,raw['branch_names']));tx=np.array([n.startswith('transformer.') for n in names])
            ratio=raw['current_A']/np.array([limits[n] for n in names]);bad=ratio[:,tx]>1
            counts['transformer_current']+=int(bad.sum());bad_days+=bad.any();maxpu=max(maxpu,float(ratio[:,tx].max()))
            counts['voltage']+=int(((raw['V_ACTUAL_AC']<.95)|(raw['V_ACTUAL_AC']>1.05)).sum())
            counts['line_current']+=int((ratio[:,~tx]>1).sum())
            counts['transformer_kVA']+=int((raw['transformer_kVA_pu'][:,tx]>1).sum())
    assert result['cells']==counts and result['new_transformer_current_violation_days']==bad_days
    assert result['max_transformer_current_pu']==maxpu
    assert result['FULL_AC_SECURITY_PASS']==(not any(counts.values()) and result['converged'])
    assert result['new_AC_solves']==0

def test_old_May_12_cells_recomputed_from_amps():
    r=read(OUT/'MAY_B0_CURRENT_RECLASSIFICATION.json');ledger=pd.read_csv(OUT/'MAY_OLD_EXCEEDANCE_RECLASSIFICATION_LEDGER.csv',float_precision='round_trip')
    assert r['old_transformer_current_violation_cells']==12 and r['old_transformer_current_violation_days']==4
    assert len(ledger)==12 and ledger.branch_phase.unique().tolist()==['transformer.reg1a::A']
    assert np.array_equal(ledger.current_A.to_numpy()/ledger.new_limit_A.to_numpy(),ledger.new_current_pu.to_numpy())
    assert ledger.new_current_pu.max()==pytest.approx(1.0532829241698016/1.1)
    assert not ledger.new_violation.any()

def test_all_four_physics_and_failure_are_independent():
    a=current_authority();line=a['lines'][0]['branch_phase'];tx=a['rows'][0]['branch_phase'];limits=denominators([line,tx])
    raw=dict(branch_names=np.array([line,tx]),current_A=np.zeros((1,2)),V_ACTUAL_AC=np.array([[1.]]),
        transformer_kVA_pu=np.array([[np.nan,.1]]),converged=np.ones(1,bool))
    r,_=classify(raw);assert require_security_receipt(r)
    for kind in ('voltage','line_current','transformer_current','transformer_kVA'):
        changed={k:np.array(v,copy=True) for k,v in raw.items()}
        if kind=='voltage':changed['V_ACTUAL_AC'][0,0]=1.051
        elif kind=='transformer_kVA':changed['transformer_kVA_pu'][0,1]=1.01
        else:changed['current_A'][0,0 if kind=='line_current' else 1]=limits[0 if kind=='line_current' else 1]*1.001
        result,_=classify(changed);assert result['cells'][kind]==1 and not result['FULL_AC_SECURITY_PASS']
        with pytest.raises(ValueError,match='FULL_AC_SECURITY_FAIL'):require_security_receipt(result)

def test_exact_affine_columns_and_noncurrent_fields_are_preserved():
    r=read(OUT/'PLANNING_CURRENT_RESPONSE_RESCALE_RECEIPT.json')
    p=resolve(next(x for x in r['source_outputs'] if x['path'].endswith('V40I_PLANNING_ELECTRICAL_COEFFICIENTS.npz')))
    with np.load(p) as old,np.load(OUT/'PLANNING_CURRENT_RESPONSE_NORMALAMPS.npz') as new:
        mask=np.array([str(n).startswith('transformer.') for n in old['branch_names']]);factor=new['old_denominators_A']/new['current_denominators_A']
        for key in ('current_constant','current_matrix'):
            assert np.array_equal(new[key][...,~mask],old[key][...,~mask])
            assert np.array_equal(new[key][...,mask],old[key][...,mask]*factor[mask])
    assert r['voltage_flow_line_polygon_transformer_kVA_bit_identical'] and r['transformer_kVA_ratings_unchanged']

def small_response():
    a=current_authority();names=(a['lines'][0]['branch_phase'],'transformer.reg1a::A')
    c=SimpleNamespace(slot=0,control_names=('P',),coefficient_sha256='a'*64,voltage_constant=np.array([1.]),
        voltage_matrix=np.zeros((1,1)),branch_limits=np.array([100.,1666.6666666666667]),
        flow_p_constant=np.zeros(2),flow_q_constant=np.zeros(2),flow_p_matrix=np.zeros((2,1)),flow_q_matrix=np.zeros((2,1)),
        anchor=np.zeros(1),current_constant=np.array([.5,1.05]),current_matrix=np.array([[0.,.01]]),
        branch_names=names,transformer_ratings=(None,1666.6666666666667))
    return c,bind_coefficient(c,denominators(names,old=True))

def test_native_and_compressed_hard_rows_use_normalized_current():
    import gurobipy as gp
    from v42_native.grid import GridAuthority,add_grid
    from v42_native.voltage import Stage
    from v42_m1_sparse.grid import add_compressed
    old,c=small_response();authority=GridAuthority(*(['b'*64]*4),.912025,1.092025,True,Stage.M1,c.transformer_current_authority_sha256)
    assert require_coefficient(c,authority)
    for compressed in (False,True):
        model=gp.Model();model.Params.OutputFlag=0
        try:
            x=model.addVar(name='P');
            if compressed:add_compressed(model,[c],[[x]],authority,'M1-FCRA',[],[])
            else:add_grid(model,[c],[[x]],authority)
            model.update();row=next(r for r in model.getConstrs() if r.ConstrName=='transformer_current')
            expression=model.getRow(row)
            assert row.RHS==pytest.approx(1-c.current_constant[1])
            assert expression.getCoeff(0)==c.current_matrix[0,1]
        finally:model.dispose()
    with pytest.raises(ValueError,match='SUPERSEDED'):require_coefficient(old,authority)
    wrong=copy.copy(authority);object.__setattr__(wrong,'transformer_current_authority_sha256','0'*64)
    with pytest.raises(ValueError,match='GRID_CURRENT_AUTHORITY'):require_coefficient(c,wrong)

def test_old_M1_UB_LB_certificate_rejected_and_new_scope_NOT_RUN():
    impact=read(OUT/'M1_AUTHORITY_IMPACT.json');old=dict(UB=.5912812634331275,LB=.5722125039436496)
    with pytest.raises(ValueError,match='SUPERSEDED'):require_certificate(old)
    with pytest.raises(ValueError,match='SUPERSEDED'):require_certificate(dict(old,transformer_current_contract='NAMEPLATE',transformer_current_authority_sha256='a'*64))
    assert impact['old_M1_current_authority']=='SUPERSEDED' and not impact['old_UB_LB_gap_valid_for_new_model']
    flags=read(OUT/'FINAL_FLAGS.json')
    assert flags['M1']=='NOT_RUN' and flags['M1_RECALCULATION_REQUIRED'] and flags['PQ_repair']==flags['tuning']==0
    assert len({arm_contract(a)['transformer_current_authority_sha256'] for a in ('B0','B1','B2','B3')})==1

def test_live_branch_read_preserves_current_A_and_kVA_changes_only_ratio():
    from v42_regcontrol.authority import source,compile_verified
    m=source();odd,adapter,inventory=compile_verified()
    try:
        branches,_=m['oriented_branches'](odd)
        for b in branches:
            old=m['legacy_branch_measurement'](odd,b);new=m['branch_measurement'](odd,b)
            assert new[0]==old[0]
            if b.branch_id.startswith('transformer.'):
                assert new[2]==old[2] and new[1]==new[0]/denominators([f'{b.branch_id}::{b.phase}'])[0]
            else:assert new[:2]==old[:2] and math.isnan(new[2])
        assert m['inventory'](odd)==inventory
    finally:odd.Basic.ClearAll()

def test_thermal_supersession_is_sealed_and_rejects_unrelated_or_changed_code():
    from v42_thermal.supersession import assert_successor
    manifest=read(OUT/'AUTHORIZED_THERMAL_SUPERSESSION.json');r=manifest['files'][0]
    assert assert_successor(r['path'],r['current_sha256'],r['base_sha256'])
    assert not assert_successor('v42_final/Runtime.py','a'*64)
    with pytest.raises(AssertionError,match='UNSEALED'):assert_successor(r['path'],'0'*64)
    with pytest.raises(AssertionError,match='HISTORICAL'):assert_successor(r['path'],r['current_sha256'],'0'*64)
