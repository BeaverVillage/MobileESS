"""Integer-valid hull and a fractional location/mode mechanism fixture."""
from fractions import Fraction
from itertools import product

import numpy as np
import pytest

from v42_integration.mess_mode_hull import aggregate_mode_hull_diagnostic, continuous_mode_reselection


def domain():
    return dict(names=np.array(["Pch[MESS01,A,1]","Pch[MESS01,B,1]",
        "Pdis[MESS01,A,1]","Pdis[MESS01,B,1]","charge_mode[MESS01,1]"]),
        lower=np.zeros(5),upper=np.array([300.,300.,300.,300.,1.]),
        types=np.array(["C","C","C","C","B"]))


def test_integer_valid_for_original_single_connected_location_mode_disjunction():
    d=domain()
    for location,mode,c,p in product((-1,0,1),(0,1),(0.,150.,300.),(0.,150.,300.)):
        x=np.zeros(5);x[4]=mode
        if location >= 0:
            x[location]=c*mode;x[2+location]=p*(1-mode)
        result=aggregate_mode_hull_diagnostic(d,300.,x)
        assert result["robustly_violated_count"]==0
    assert aggregate_mode_hull_diagnostic(d,300.)["root_point_observed"] is False


def test_fractional_two_location_mode_leakage_satisfies_original_site_limits_but_violates_hull():
    d=domain();x=np.array([150.,150.,150.,150.,.5])
    connection=np.array([.5,.5]);mode=.5
    assert np.all(x[:2] <= 300.*connection)
    assert np.all(x[2:4] <= 300.*connection)
    assert np.all(x[:2] <= 300.*mode)
    assert np.all(x[2:4] <= 300.*(1-mode))
    # Net P=0 and Q=0 satisfy every original PCS16 face at both locations.
    assert np.array_equal(x[2:4]-x[:2],np.zeros(2))
    # Original signed SOC balance retains round-trip losses instead of inventing
    # zero loss. A feasible wide SOC box accommodates this slot locally.
    alpha=Fraction(.25*.95);beta=Fraction(.25/.95)
    after=Fraction(760.)+alpha*Fraction(300.)-beta*Fraction(300.)
    assert Fraction(440.) <= after <= Fraction(1080.)
    result=aggregate_mode_hull_diagnostic(d,300.,x)
    assert result["robustly_violated_count"]==2
    assert [r["raw_violation"] for r in result["candidate_rows"]]==[150.,150.]
    assert result["actual_source_row_authority_independently_verified"] is False
    assert result["cuts_adopted"]==0 and result["strengthened_global_LB"] is None


def test_fractional_source_mode_designation_cannot_authorize_integer_cut():
    d=domain();d["types"][-1]="C"
    with pytest.raises(ValueError,match="BINARY_MODE_AUTHORITY_REQUIRED"):
        aggregate_mode_hull_diagnostic(d,300.,np.array([150.,150.,150.,150.,.5]))


def test_reselection_changes_only_free_mode_and_cannot_hide_over_limit_total_power():
    d=domain();d["objective"]=np.array([1.,0.,0.,0.,0.]);d["constant"]=np.array(0.)
    original=np.array([75.,75.,75.,75.,.25])
    x,receipt=continuous_mode_reselection(d,300.,original)
    assert np.array_equal(original,np.array([75.,75.,75.,75.,.25]))
    assert np.array_equal(x[:4],original[:4]) and x[-1]==.5
    assert aggregate_mode_hull_diagnostic(d,300.,x)["robustly_violated_count"]==0
    assert receipt["physical_integer_execution_claimed"] is False
    x,blocked=continuous_mode_reselection(d,300.,np.array([150.,150.,150.,150.,.5]))
    assert x is None and blocked["reason"]=="AGGREGATE_TOTAL_POWER_EXCEEDS_ORIGINAL_PMAX"


def test_one_kw_limit_discharging_mode_coefficient_is_not_a_power_coordinate():
    d=dict(names=np.array(["Pch[MESS01,A,0]","Pdis[MESS01,A,0]","charge_mode[MESS01,0]"]),
        lower=np.zeros(3),upper=np.ones(3),types=np.array(["C","C","B"]),
        objective=np.array([1.,0.,0.]),constant=np.array(0.))
    x,receipt=continuous_mode_reselection(d,1.,np.array([.2,.7,.5]))
    assert x is not None and .2 <= x[-1] <= .3
    assert aggregate_mode_hull_diagnostic(d,1.,x)["robustly_violated_count"]==0
