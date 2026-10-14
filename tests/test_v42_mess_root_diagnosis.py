"""Raw scope, family fixation, fractional coupling and nested time regressions."""
import numpy as np
import pytest
from scipy import sparse

from v42_integration.m_engine import domain_sha,vector_sha
from v42_integration.mess_root_diagnosis import root_diagnosis,fixation_overlay,solver_phase_receipt


def fixture():
    names=np.array(["arc[M,0]","arc[M,1]","charge_mode[M,0]","Pch[M,A,0]","Pdis[M,A,0]","Q[M,A,0]","SOC[M,0]","SOC[M,1]","rho_max"])
    a=np.zeros((7,len(names)));a[0,:2]=1;a[1,[6,7,3,4]]=[-1,1,-.25,.25]
    a[2,[3,4,5,8]]=[.001,-.002,.0003,-1]
    a[3,[3,0]]=[1,-300];a[4,[4,0]]=[1,-300];a[5,[3,2]]=[1,-300];a[6,[4,2]]=[1,300]
    d=dict(names=names,row_names=np.array(["flow","energy_balance","line_thermal_face[0,L,A]","connected_Pch","connected_Pdis","no_simultaneous_charge","no_simultaneous_discharge"]),
        rhs=np.array([1,0,-.7,0,0,0,300]),sense=np.array(["=","=","<","<","<","<","<"]),
        lower=np.array([0,0,0,0,0,-400,440,440,0.]),upper=np.array([1,1,1,300,300,400,1080,1080,1.]),
        types=np.array(["B","B","B",*("C" for _ in range(6))]),objective=np.r_[np.zeros(8),1.],constant=np.array(0.))
    integer=np.array([1,0,1,0,0,0,760,760,.7]);root=np.array([.5,.5,.5,100,100,50,760,760,.615])
    battery=dict(minimum=440.,maximum=1080.,eta_charge=1.,eta_discharge=1.,dt_hours=.25)
    return sparse.csr_matrix(a),d,integer,root,battery


def test_actual_fractional_route_mode_power_and_critical_signed_Q_remain_coupled():
    A,d,integer,x,b=fixture();sha=vector_sha(x)
    r=root_diagnosis(A,d,x,arcs=[("A",0,"A",1,0.),("B",0,"B",1,0.)],arc_columns={"M":{0:0,1:1}},
        units=["M"],sites=["A","B"],battery=b,integer_point=integer)
    assert r["fractional_route_Arcs"]==2 and r["fractional_Mode"]==1
    assert r["multiple_location_vehicle_slots"]==1 and r["simultaneous_charge_discharge_vehicle_slots"]==1
    assert r["maximum_SOC_recurrence_residual"]==0
    q=[v for v in r["critical_rows"][0]["signed_P_Q_terms"] if v["name"].startswith("Q[")][0]
    assert q["normalized_contribution"]==pytest.approx(.015)
    assert r["Original_4x24_Global_LB"] is None and vector_sha(x)==sha


@pytest.mark.parametrize("experiment,families,count",[("S1-A",[],0),("S1-B",["arc"],2),("S1-C",["charge_mode"],1),("S1-D",["arc","charge_mode"],3)])
def test_fixation_is_a_verified_single_pattern_overlay_never_global_LB(experiment,families,count):
    A,d,integer,_,_=fixture();before=domain_sha(d)
    evaluated,overlay,r=fixation_overlay(A,d,integer,experiment=experiment,source_identity={"case_sha":"a"*64})
    assert r["fixed_original_families"]==families and r["fixed_columns"]==count
    assert np.all(evaluated["types"]=="C")
    assert np.array_equal(evaluated["lower"][overlay["indices"]],integer[overlay["indices"]])
    assert r["can_publish_original_S1_Global_LB"] is False and r["can_publish_original_4x24_Global_LB"] is False
    assert domain_sha(d)==before and np.array_equal(evaluated["objective"],d["objective"])


def test_fractional_or_infeasible_pattern_cannot_seed_fixed_route_mode_diagnostics():
    A,d,integer,root,_=fixture()
    for x in (root,integer+np.array([0,0,0,400,0,0,0,0,0])):
        with pytest.raises(ValueError,match="ORIGINAL_FULL_INTEGER_PATTERN"):
            fixation_overlay(A,d,x,experiment="S1-D",source_identity={})


@pytest.mark.parametrize("barrier",["Barrier performed 14 iterations in 23.49 seconds","Barrier solved model in 40 iterations and 23.49 seconds"])
def test_barrier_completion_time_is_cumulative_and_no_solver_subphase_sum_is_fabricated(barrier):
    log="Presolve time: 6.96s\nPresolve time: 4.76s\n"+barrier+"\nCrossover time: 6.52 seconds\nRoot relaxation: objective 0.609, 4611 iterations, 17.69 seconds\nExplored 1 nodes"
    r=solver_phase_receipt(log,native_runtime=40.174,build_wall=3.94)
    assert r["Presolve_reported_seconds"]==[6.96,4.76]
    assert r["Barrier_completion_cumulative_Native_seconds"]==[23.49]
    assert r["exclusive_Root_barrier_duration"] is None and r["exclusive_B_and_B_duration"] is None
