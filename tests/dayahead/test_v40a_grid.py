from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import gurobipy as gp
import pytest
from dayahead.v28r2.electrical_subproblem import SlotCoefficients
from dayahead.v40a.grid import add_grid,evaluate_grid
from dayahead.v40a.feedback import authorized_options


def coefficient():
    # One line, one transformer: the actual inherited affine/polygon type.
    return SlotCoefficients(slot=0,control_names=tuple(['aidc_load_kw[AIDC01]','mess_p_kw[STA01]']),
        branch_names=('line.test::a','transformer.test::a'),anchor=np.zeros(2),
        voltage_constant=np.ones(1),voltage_matrix=np.array([[-.001],[.001]]),
        current_constant=np.array([.1,.1]),current_matrix=np.array([[.01,.01],[-.01,-.01]]),
        flow_p_constant=np.array([1.,1.]),flow_q_constant=np.zeros(2),
        flow_p_matrix=np.array([[1.,-1.],[1.,-1.]]),flow_q_matrix=np.zeros((2,2)),
        branch_limits=(10.,10.),transformer_ratings=(None,10.),coefficient_sha256='a'*64)


def solve_with_mess(mess):
    m=gp.Model();m.Params.OutputFlag=0
    p=m.addVar(lb=2,ub=2);rho,rows=add_grid(m,[coefficient()],[[p,mess]])
    m.setObjective(rho);m.optimize()
    assert m.Status==gp.GRB.OPTIMAL
    result=rho.X;m.dispose();return result,rows


def test_frozen_m1_p_directly_changes_planning_objective():
    without,rows=solve_with_mess(0);with_mess,_=solve_with_mess(1)
    assert with_mess<without
    assert all(rows[k]>0 for k in ('voltage','line_current','transformer_current','transformer_kva'))


def test_grid_reports_actual_critical_state():
    c=coefficient();r=evaluate_grid([c],[[2,1]],['bus.1'])
    assert r['critical_line']=='line.test::a' and r['critical_slot']==0
    assert r['status']=='PASS'


def test_a1_running_fixed_under_user_confirmed_policy():
    row=dict(state_at_issue='RUNNING',AIDC_site='AIDC01',start_slot=0,end_slot=20)
    assert authorized_options(row,None)==[('AIDC01',0)]


def test_a1_terminal_job_frozen():
    row=dict(state_at_issue='PENDING',AIDC_site='UNASSIGNED',start_slot=125,end_slot=130)
    assert authorized_options(row,None)==[('UNASSIGNED',125)]


def test_a1_no_new_latest_start_rule():
    cap=SimpleNamespace(aidc_ids=('AIDC01',),site_capacity={'AIDC01':64},eligible_racks=lambda *a:True)
    row=dict(job_uid='a',state_at_issue='PENDING',AIDC_site='AIDC01',start_slot=110,end_slot=114,
             requested_GPU=4,safe_duration_slots=4,eligible_standby=True,RSP_start_slot=110,RW_completion_slot=150)
    options=authorized_options(row,cap)
    assert min(s for _,s in options)==110 and max(s for _,s in options)==116
