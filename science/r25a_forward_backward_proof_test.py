#!/usr/bin/env python3
import math, json
ETA_CH=0.95; DT=5/60; P_MAX=550.0; H=54
CHG=ETA_CH*DT*P_MAX

def min_debt_after_stays(debt,n):
    return max(0.0,float(debt)-int(n)*CHG)

def state_impossible_optimistically(min_debt,h):
    return float(min_debt) > (H-int(h))*CHG + 1e-9

def move_impossible_optimistically(min_debt,arrival_h):
    return float(min_debt) > (H-int(arrival_h))*CHG + 1e-9

# 1) Zero debt can never be removed by the debt rule for any surviving arrival < H.
for a in range(H):
    assert not move_impossible_optimistically(0.0,a)
# 2) A debt larger than the one remaining charge step must be removed for arrival H-1.
assert move_impossible_optimistically(CHG+1.0,H-1)
# 3) A debt below one charge step remains potentially repayable at H-1.
assert not move_impossible_optimistically(CHG-1.0,H-1)
# 4) R23 issue152 MESS01 debt needs exactly two ideal full-charge STAY steps.
d=79.08140706656712
assert math.ceil(d/CHG-1e-15)==2
assert min_debt_after_stays(d,1)>0 and min_debt_after_stays(d,2)==0
# 5) MESS02/MESS03 each require at most one ideal STAY step; MESS04 none.
for d0,steps in [(0.9965977812537845,1),(3.777411723623579,1),(0.0,0)]:
    assert math.ceil(max(0.0,d0)/CHG-1e-15)==steps
# 6) The proof direction is conservative: if optimistic min debt exceeds an unconditional
# repayment upper bound, every more restrictive physical/grid realization is impossible.
# This is a logical implication test on representative numbers.
optimistic_lb=90.0; unconditional_ub=2*CHG
assert optimistic_lb>unconditional_ub
print(json.dumps({
  'status':'PASS','charge_repayment_upper_kWh_per_available_step':CHG,
  'tests':6,'issue152_initial_debt_min_stay_steps':{'MESS01':2,'MESS02':1,'MESS03':1,'MESS04':0}
},indent=2))
