"""Integer-valid SOC disjunction and actual fractional headroom counterexample."""
from itertools import product

import numpy as np
import pytest
from scipy import sparse

from v42_integration.m_engine import matrix_sha,domain_sha
from v42_integration.mess_s1_research import soc_route_hull_rows,cut_packet,full_vehicle_dw_plan,dw_pricing_scope_gate


def fixture():
    names=np.array([*(f"SOC[MESS01,{t}]" for t in range(97)),
        *(f"Pch[MESS01,A,{t}]" for t in range(96)),*(f"Pdis[MESS01,A,{t}]" for t in range(96)),
        *(f"arc[MESS01,{t}]" for t in range(96)),*(f"charge_mode[MESS01,{t}]" for t in range(96))])
    rr=[];cc=[];vv=[]
    for t in range(96):
        for j,w in ((t,-1.),(t+1,1.),(97+t,-.25),(193+t,.25),(289+t,1.)):
            rr.append(t);cc.append(j);vv.append(w)
    A=sparse.csr_matrix((vv,(rr,cc)),shape=(96,len(names)))
    d=dict(names=names,row_names=np.full(96,"energy_balance"),rhs=np.zeros(96),sense=np.full(96,"="),
        lower=np.r_[np.ones(97)*440.,np.zeros(384)],upper=np.r_[np.ones(97)*1080.,np.ones(192)*300.,np.ones(192)],
        types=np.r_[np.full(289,"C"),np.full(192,"B")])
    authority=dict(PASS=True,original_single_integer_path_theorem_verified=True,
        original_mode_and_connection_rows_exact=True,all_original_integer_routes_preserved=True,
        route_pool_restriction_added=False,physical_matrix_sha=matrix_sha(A),source_domain_sha=domain_sha(d))
    return A,d,authority


def test_soc_hull_preserves_both_original_integer_mode_route_disjunctions():
    A,d,authority=fixture()
    for E,C,D,T in product((440.,500.,1000.,1080.),(0.,150.,300.),(0.,150.,300.),(0.,1.)):
        if C and (D or T):continue
        after=E+.25*C-.25*D-T
        if not 440.<=after<=1080.:continue
        x=np.zeros(A.shape[1]);x[:97]=760.;x[0]=E;x[1]=after;x[97]=C;x[193]=D;x[289]=T
        diag=soc_route_hull_rows(A,d,x,source_integer_authority=authority)
        slot0=[r for r in diag["candidate_rows"] if r["slot"]==0]
        assert all(r["raw_root_violation"]<=0 for r in slot0)


def test_fractional_charge_discharge_restores_next_soc_but_violates_integer_headroom():
    A,d,authority=fixture();x=np.zeros(A.shape[1]);x[:97]=760.
    x[0]=1050.;x[1]=1050.;x[97]=150.;x[193]=150.
    assert float((A.getrow(0)@x).item())==0.
    diag=soc_route_hull_rows(A,d,x,source_integer_authority=authority)
    assert diag["robustly_violated_count"]==1
    assert diag["maximum_raw_root_violation"]==7.5
    C,cd=cut_packet(diag,len(x))
    assert C.shape==(1,len(x)) and float((C@x-cd["rhs"])[0])==7.5
    assert diag["original_4x24_Global_LB"] is None


def test_source_integer_route_authority_and_literal_energy_csr_are_required():
    A,d,authority=fixture();x=np.zeros(A.shape[1])
    with pytest.raises(ValueError,match="INTEGER_ROUTE_MODE_AUTHORITY_REQUIRED"):
        soc_route_hull_rows(A,d,x,source_integer_authority=dict(authority,PASS=False))
    changed=A.copy();changed.data[0]+=.1
    with pytest.raises(ValueError,match="LITERAL_SOURCE_MATRIX_DOMAIN_DRIFT"):
        soc_route_hull_rows(changed,d,x,source_integer_authority=authority)


def test_binary_mode_domain_is_checked_against_literal_source_not_only_authority_flag():
    A,d,authority=fixture();d["types"][385]="C"
    authority["source_domain_sha"]=domain_sha(d)
    with pytest.raises(ValueError,match="LITERAL_BINARY_MODE_UNIT_BOX_REQUIRED"):
        soc_route_hull_rows(A,d,np.zeros(A.shape[1]),source_integer_authority=authority)


def dw_fixture():
    _,d,_=fixture();d["names"]=np.r_[d["names"],[f"Q[MESS01,A,{t}]" for t in range(96)]]
    for key,values in (("types",np.full(96,"C")),("lower",np.full(96,-400.)),("upper",np.full(96,400.))):
        d[key]=np.r_[d[key],values]
    plan=full_vehicle_dw_plan(d,dict(reduced_case_sha="a"*64),["MESS01"])
    r=dict(source_identity=plan["source_identity"],source_domain_sha=plan["source_domain_sha"],
        joint_schedule_variable_families=["arc","SOC","charge_mode","Pch","Pdis","Q"],
        all_original_routes_preserved=True,finite_Beam_pool_restriction=False)
    return plan,{"MESS01":r}


def test_DW_full_schedule_scope_only_never_publishes_unpriced_restricted_master_bound():
    plan,receipts=dw_fixture()
    assert plan["route_only_columns_strengthen_original_network_flow"] is False
    gate=dw_pricing_scope_gate(plan,receipts,requested_scope="S1_REDUCED_ORIGINAL_FULL_DOMAIN")
    assert gate["can_publish_numeric_Global_LB"] is False and gate["Original_4x24_Global_LB"] is None


@pytest.mark.parametrize("mutation,match",[
    (dict(joint_schedule_variable_families=["arc"]),"PARTIAL_SCHEDULE"),
    (dict(finite_Beam_pool_restriction=True),"RESTRICTED_PRICING"),
    (dict(source_domain_sha="b"*64),"DOMAIN_DRIFT")])
def test_DW_route_only_restricted_pricing_and_cross_domain_receipts_are_rejected(mutation,match):
    plan,receipts=dw_fixture();receipts["MESS01"].update(mutation)
    with pytest.raises(ValueError,match=match):
        dw_pricing_scope_gate(plan,receipts,requested_scope="S1_REDUCED_ORIGINAL_FULL_DOMAIN")


def test_DW_all_active_pricing_is_required_and_S1_cannot_transfer_bounds_to_4x24():
    plan,receipts=dw_fixture()
    with pytest.raises(ValueError,match="ALL_ACTIVE_ORIGINAL_UNIT"):
        dw_pricing_scope_gate(plan,{},requested_scope="S1_REDUCED_ORIGINAL_FULL_DOMAIN")
    with pytest.raises(ValueError,match="CANNOT_TRANSFER"):
        dw_pricing_scope_gate(plan,receipts,requested_scope="ORIGINAL_4X24")
