import pytest
import math
from types import SimpleNamespace

from pfr.power import H100UtilizationPowerCurve
from pfr.runtime import MESS_IDS, _GurobiSensitivityProjector, _nominal_mess_dispatch
from pfr.safety import ExactAcResult
from pfr.slow_fast import FastControl, FastLayerState


def dispatch(*, energy, transit=(), enabled=True, charge=0.0, discharge=0.0):
    return _nominal_mess_dispatch(
        energy_kwh={mid: float(energy) for mid in MESS_IDS},
        in_transit={mid: mid in transit for mid in MESS_IDS},
        energy_enabled=enabled,
        plan=SimpleNamespace(
            coarse_charging_kw={mid: (float(charge),) for mid in MESS_IDS},
            coarse_discharging_kw={mid: (float(discharge),) for mid in MESS_IDS},
        ),
        plan_age_steps=0,
    )


def test_nominal_dispatch_follows_frozen_slow_plan_not_price():
    charge, discharge = dispatch(energy=760.0, charge=125.0)

    assert set(charge.values()) == {125.0}
    assert set(discharge.values()) == {0.0}


def test_plan_charge_is_clipped_by_physical_capacity():
    charge, discharge = dispatch(energy=1079.0, charge=550.0)

    assert all(value == pytest.approx(1.0 / (0.95 * (5.0 / 60.0))) for value in charge.values())
    assert set(discharge.values()) == {0.0}


def test_planned_discharge_cannot_cross_protected_floor():
    charge, discharge = dispatch(energy=441.0, discharge=550.0)

    assert set(charge.values()) == {0.0}
    assert all(value == pytest.approx(1.0 * 0.95 / (5.0 / 60.0)) for value in discharge.values())

    _, at_floor = dispatch(energy=440.0, discharge=550.0)
    assert set(at_floor.values()) == {0.0}


def test_disabled_or_in_transit_storage_has_no_nominal_dispatch():
    disabled_charge, disabled_discharge = dispatch(energy=600.0, enabled=False, charge=100.0)
    transit_charge, transit_discharge = dispatch(energy=600.0, transit=MESS_IDS, charge=100.0)

    assert set(disabled_charge.values()) == set(disabled_discharge.values()) == {0.0}
    assert set(transit_charge.values()) == set(transit_discharge.values()) == {0.0}


class CoupledPqVerifier:
    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        net_p = sum(
            control.mess_discharge_kw[mid] - control.mess_charge_kw[mid]
            for mid in MESS_IDS
        )
        active_fraction = (net_p + 200.0) / 2400.0
        q_fraction = sum(control.mess_q_kvar.values()) / (4.0 * 700.0)
        vmin = 0.96 + 0.01 * active_fraction + 0.02 * q_fraction
        vmax = 1.04 + 0.02 * active_fraction + 0.08 * q_fraction
        line = 1.12 - 0.20 * active_fraction
        passed = 0.95 <= vmin <= vmax <= 1.05 and line <= 1.0
        return ExactAcResult(
            passed,
            "PASS" if passed else "VIOLATION",
            True,
            True,
            vmin,
            vmax,
            line,
            0.8,
            0 if passed else 1,
        )


class MultiTrustRegionPqVerifier:
    """Feasibility requires several improving P/Q trust-region steps."""

    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        net_p = sum(
            control.mess_discharge_kw[mid] - control.mess_charge_kw[mid]
            for mid in MESS_IDS
        )
        net_q = sum(control.mess_q_kvar.values())
        vmin = 0.97 + net_q / 100000.0
        vmax = 1.04 + net_p / 40000.0 + net_q / 20000.0
        line = 1.30 - net_p / 7000.0
        passed = 0.95 <= vmin <= vmax <= 1.05 and line <= 1.0
        return ExactAcResult(
            passed,
            "PASS" if passed else "VIOLATION",
            True,
            True,
            vmin,
            vmax,
            line,
            0.8,
            0 if passed else 1,
        )


class PairwiseQVerifier:
    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        left = control.mess_q_kvar["MESS01"] / 700.0
        right = -control.mess_q_kvar["MESS02"] / 700.0
        vmin = 0.949 + 0.008 * left - 0.004 * right
        vmax = 1.051 + 0.004 * left - 0.008 * right
        passed = 0.95 <= vmin <= vmax <= 1.05
        return ExactAcResult(
            passed,
            "PASS" if passed else "VIOLATION",
            True,
            True,
            vmin,
            vmax,
            0.5,
            0.5,
            0 if passed else 1,
        )


class FleetQVerifier:
    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        fleet_support = sum(control.mess_q_kvar.values()) / 700.0
        vmin = 0.949 + 0.001 * fleet_support
        vmax = 1.04
        passed = 0.95 <= vmin <= vmax <= 1.05
        return ExactAcResult(
            passed,
            "PASS" if passed else "VIOLATION",
            True,
            True,
            vmin,
            vmax,
            0.5,
            0.5,
            0 if passed else 1,
        )


class ActiveSensitivityVerifier:
    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        support = control.mess_discharge_kw["MESS03"] - control.mess_charge_kw["MESS03"]
        vmin = 0.949 + 0.00001 * support
        vmax = 1.04
        passed = 0.95 <= vmin <= vmax <= 1.05
        return ExactAcResult(
            passed,
            "PASS" if passed else "VIOLATION",
            True,
            True,
            vmin,
            vmax,
            0.5,
            0.5,
            0 if passed else 1,
        )


class SafeStressVerifier:
    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        p = sum(
            control.mess_discharge_kw[mid] - control.mess_charge_kw[mid]
            for mid in MESS_IDS
        )
        q = sum(control.mess_q_kvar.values())
        vmax = (
            1.03
            + abs(p - 200.0) / 100000.0
            + abs(q + 120.0) / 100000.0
        )
        return ExactAcResult(
            True,
            "PASS",
            True,
            True,
            0.98,
            vmax,
            0.5,
            0.5,
            0,
        )


def test_recovery_fallback_keeps_transit_mess_disconnected() -> None:
    verifier = SimpleNamespace(mess_in_transit=(False, False, False, True))
    projector = _GurobiSensitivityProjector(
        verifier,
        allow_mess=True,
        carried_energy_debt_kwh={mid: 1.0 for mid in MESS_IDS},
        minimum_recovery_charge_kw={mid: 125.0 for mid in MESS_IDS},
    )
    nominal = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )

    fallback = projector._null_or_minimum_recovery_control(nominal)

    assert fallback.mess_charge_kw["MESS04"] == 0.0
    assert fallback.mess_discharge_kw["MESS04"] == 0.0
    assert fallback.mess_q_kvar["MESS04"] == 0.0
    assert all(
        fallback.mess_charge_kw[mid] == 125.0 for mid in MESS_IDS[:3]
    )
    assert projector._recovery_compliant(fallback)

    invalid_transit_dispatch = FastControl(
        {**fallback.mess_charge_kw, "MESS04": 1.0},
        dict(fallback.mess_discharge_kw),
        dict(fallback.mess_q_kvar),
        {},
        {},
    )
    assert not projector._recovery_compliant(invalid_transit_dispatch)


def test_projector_combines_active_relief_with_location_sensitive_q():
    nominal = FastControl(
        {mid: 50.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    projector = _GurobiSensitivityProjector(CoupledPqVerifier(), allow_mess=True)

    candidate = projector.project(
        nominal=nominal,
        state=state,
        slow_plan=SimpleNamespace(fingerprint="fixed-plan"),
    )
    exact = projector.verifier.verify_fresh(
        control=candidate.control,
        state=state,
        slow_plan=SimpleNamespace(fingerprint="fixed-plan"),
    )

    assert exact.passed
    assert sum(candidate.control.mess_q_kvar.values()) < 0.0
    assert any("joint_pq_trust_region_qcp" in row for row in projector.trace)
    assert not any(
        row.get("solver", {}).get("status")
        == "FRESH_OPENDSS_PASSING_ACTIVE_COORDINATE_Q_SEARCH"
        for row in projector.trace
    )


def test_safe_h0_action_uses_local_pq_model_and_exact_admission():
    nominal = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    projector = _GurobiSensitivityProjector(
        SafeStressVerifier(),
        allow_mess=True,
        improve_safe_operating_point=True,
        refresh_local_pq_model=True,
    )

    candidate = projector.project(
        nominal=nominal,
        state=state,
        slow_plan=SimpleNamespace(fingerprint="fixed-plan"),
    )

    assert projector.local_pq_surrogate is not None
    assert candidate.objective_projected <= candidate.objective_nominal
    assert any(
        row.get("status") == "H0_EXACT_BENEFIT_ADMISSION"
        for row in projector.trace
    )


def test_joint_projection_restores_feasibility_across_multiple_trust_regions():
    nominal = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    verifier = MultiTrustRegionPqVerifier()
    projector = _GurobiSensitivityProjector(verifier, allow_mess=True)
    slow_plan = SimpleNamespace(fingerprint="fixed-plan")

    candidate = projector.project(
        nominal=nominal,
        state=state,
        slow_plan=slow_plan,
    )
    exact = verifier.verify_fresh(
        control=candidate.control,
        state=state,
        slow_plan=slow_plan,
    )

    assert exact.passed
    joint_rows = [
        row["joint_pq_trust_region_qcp"]
        for row in projector.trace
        if "joint_pq_trust_region_qcp" in row
    ]
    assert len(joint_rows) >= 4
    assert any(
        row["predicted_elastic_residual"]["line"] > 0.0
        for row in joint_rows[:-1]
    )
    assert all(
        row["fresh_exact_violation_score_after"]
        < row["fresh_exact_violation_score_before"]
        for row in joint_rows
        if not row["passed"]
    )


def test_projector_blend_enforces_strict_p550_s700_boundary():
    base = FastControl(
        {mid: 54.225320409655794 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    target = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 550.0 for mid in MESS_IDS},
        {mid: 700.0 for mid in MESS_IDS},
        {},
        {},
    )

    combined = _GurobiSensitivityProjector._combine(base, target, base, 1.0, 0.0)

    for mid in MESS_IDS:
        net_p = combined.mess_discharge_kw[mid] - combined.mess_charge_kw[mid]
        assert abs(net_p) <= 550.0
        assert math.hypot(net_p, combined.mess_q_kvar[mid]) <= 700.0
        assert not (combined.mess_charge_kw[mid] > 0.0 and combined.mess_discharge_kw[mid] > 0.0)


def test_pairwise_q_search_closes_opposing_voltage_axes():
    control = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    verifier = PairwiseQVerifier()
    projector = _GurobiSensitivityProjector(verifier, allow_mess=True)
    slow_plan = SimpleNamespace(fingerprint="fixed-plan")
    exact = verifier.verify_fresh(control=control, state=state, slow_plan=slow_plan)

    result = projector._pairwise_q_step(control, state, slow_plan, exact)

    assert result is not None
    assert result[1].passed
    assert result[2]["status"] == "FRESH_OPENDSS_PAIRWISE_Q_SEARCH"


def test_continuous_q_sensitivity_qp_closes_between_coarse_grid_points():
    control = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    verifier = PairwiseQVerifier()
    projector = _GurobiSensitivityProjector(verifier, allow_mess=True)
    slow_plan = SimpleNamespace(fingerprint="fixed-plan")
    exact = verifier.verify_fresh(control=control, state=state, slow_plan=slow_plan)

    result = projector._sensitivity_qp_step(control, state, slow_plan, exact)

    assert result is not None
    assert result[1].passed
    assert result[2]["status"] == "FRESH_OPENDSS_CONTINUOUS_Q_SENSITIVITY_QP"
    assert result[2]["integer_variables"] == 0


def test_continuous_active_sensitivity_qp_selects_effective_pcc():
    control = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    verifier = ActiveSensitivityVerifier()
    projector = _GurobiSensitivityProjector(verifier, allow_mess=True)
    slow_plan = SimpleNamespace(fingerprint="fixed-plan")
    exact = verifier.verify_fresh(control=control, state=state, slow_plan=slow_plan)

    result = projector._active_sensitivity_qp_step(control, state, slow_plan, exact)

    assert result is not None
    assert result[1].passed
    assert result[0].mess_discharge_kw["MESS03"] > 0.0
    assert result[2]["status"] == "FRESH_OPENDSS_CONTINUOUS_P_SENSITIVITY_QP"
    assert result[2]["integer_variables"] == 0


def test_fleet_q_search_closes_multi_pcc_voltage_support():
    control = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    verifier = FleetQVerifier()
    projector = _GurobiSensitivityProjector(verifier, allow_mess=True)
    slow_plan = SimpleNamespace(fingerprint="fixed-plan")
    exact = verifier.verify_fresh(control=control, state=state, slow_plan=slow_plan)

    result = projector._fleet_q_step(control, state, slow_plan, exact)

    assert result is not None
    assert result[1].passed
    assert result[2]["status"] == "FRESH_OPENDSS_FLEET_Q_SEARCH"


def test_overvoltage_target_increases_compute_within_gpu_and_kva_limits():
    job = SimpleNamespace(
        lifecycle="RUNNING",
        destination_idc="IDC01",
        source=SimpleNamespace(
            requested_gpu=8,
            deadline_step=12,
            cpu_request_share_kw=2.0,
        ),
    )
    verifier = SimpleNamespace(
        mess_in_transit=(False, False, False, False),
        jobs={"job": job},
        power_curve=H100UtilizationPowerCurve(
            (0.0, 1.0), (0.1, 0.65), "a" * 64, ("b" * 64,)
        ),
    )
    control = FastControl(
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {"job": 0.1},
        {},
    )
    state = FastLayerState(
        0,
        {mid: 760.0 / 1080.0 for mid in MESS_IDS},
        {"job": 8.0},
    )
    projector = _GurobiSensitivityProjector(
        verifier,
        allow_mess=False,
        allow_compute=True,
        compute_site_capacity={"IDC01": 4.0},
    )
    high_voltage = ExactAcResult(
        False, "VOLTAGE_HIGH", True, True, 0.98, 1.051, 0.5, 0.5, 1
    )

    _, voltage_target = projector._targets(control, state, high_voltage)

    assert voltage_target.job_compute_rate_fraction["job"] > 0.1
    assert voltage_target.job_compute_rate_fraction["job"] == pytest.approx(0.5)
