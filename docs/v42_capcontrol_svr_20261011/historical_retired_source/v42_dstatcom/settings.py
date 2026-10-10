"""Frozen engineering assumptions for independent local D-STATCOM control."""
from dataclasses import asdict, dataclass
import math

VERSION = 'V42_DSTATCOM_TAP_AWARE_NETWORK_FEEDBACK_SETTINGS_V3'


@dataclass(frozen=True)
class ControllerSettings:
    deadband_lower_pu: float = .975
    deadband_upper_pu: float = 1.025
    supply_saturation_pu: float = .955
    absorb_saturation_pu: float = 1.045
    droop_saturation_fraction_of_phase_rating: float = .90
    hysteresis_release_width_pu: float = .0005
    damping: float = .025
    ramp_fraction_of_phase_rating_per_second: float = .10
    feedback_step_seconds: float = 1.0
    maximum_feedback_iterations: int = 300
    q_convergence_kvar: float = .05
    voltage_convergence_pu: float = 1e-5
    stable_iterations_required: int = 3
    operating_kva_fraction: float = .90
    operating_current_fraction: float = .95
    converter_standby_loss_fraction: float = .002
    converter_full_output_variable_loss_fraction: float = .012
    coupling_transformer_kva_factor: float = 1.10
    coupling_transformer_xhl_percent: float = 2.0
    coupling_transformer_winding_r_percent: float = .25
    coupling_transformer_no_load_loss_percent: float = .10
    coupling_transformer_magnetizing_current_percent: float = .10
    actual_voltage_min_pu: float = .95
    actual_voltage_max_pu: float = 1.05
    numerical_power_readback_tolerance_kva: float = 1e-4
    network_feedback_probe_kvar: float = 2.5
    network_feedback_max_step_kvar: float = 10.
    network_feedback_min_step_kvar: float = .3125
    network_feedback_voltage_target_margin_pu: float = .002
    network_feedback_relative_improvement: float = .0001

    def __post_init__(self):
        values = asdict(self)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values.values()):
            raise ValueError('DSTATCOM_FINITE_NUMERIC_SETTINGS_REQUIRED')
        if self.actual_voltage_min_pu != .95 or self.actual_voltage_max_pu != 1.05:
            raise ValueError('DSTATCOM_ORIGINAL_VOLTAGE_BAND_REQUIRED')
        if not (self.actual_voltage_min_pu <= self.supply_saturation_pu < self.deadband_lower_pu
                < 1 < self.deadband_upper_pu < self.absorb_saturation_pu <= self.actual_voltage_max_pu):
            raise ValueError('DSTATCOM_ORDERED_DROOP_AND_ORIGINAL_ACTUAL_BAND_REQUIRED')
        if not (0 < self.damping <= .5 and 0 < self.operating_kva_fraction < 1
                and 0 < self.operating_current_fraction < 1):
            raise ValueError('DSTATCOM_DAMPING_AND_OPERATING_RESERVE_REQUIRED')
        if not (0 < self.droop_saturation_fraction_of_phase_rating <= self.operating_kva_fraction
                and 0 < self.hysteresis_release_width_pu < min(1-self.deadband_lower_pu,self.deadband_upper_pu-1)):
            raise ValueError('DSTATCOM_BOUNDED_DROOP_TARGET_AND_SCHMITT_HYSTERESIS_REQUIRED')
        if not (0 < self.ramp_fraction_of_phase_rating_per_second <= 1 and self.feedback_step_seconds > 0
                and self.q_convergence_kvar > 0 and self.voltage_convergence_pu > 0):
            raise ValueError('DSTATCOM_POSITIVE_RAMP_AND_CONVERGENCE_SETTINGS_REQUIRED')
        if not (0<self.network_feedback_min_step_kvar<=self.network_feedback_probe_kvar
                <=self.network_feedback_max_step_kvar and 0<self.network_feedback_voltage_target_margin_pu<.01
                and 0<self.network_feedback_relative_improvement<.01):
            raise ValueError('DSTATCOM_FINITE_NETWORK_FEEDBACK_STEP_AND_SAFETY_CONTRACT_REQUIRED')
        if (type(self.maximum_feedback_iterations) is not int or not 1 <= self.maximum_feedback_iterations <= 300
                or type(self.stable_iterations_required) is not int or not 2 <= self.stable_iterations_required <= 10):
            raise ValueError('DSTATCOM_BOUNDED_FEEDBACK_ITERATIONS_REQUIRED')
        if not (0 < self.converter_standby_loss_fraction < .05
                and 0 <= self.converter_full_output_variable_loss_fraction < .05
                and self.coupling_transformer_kva_factor >= 1.05
                and self.coupling_transformer_xhl_percent > 0
                and self.coupling_transformer_winding_r_percent > 0
                and self.coupling_transformer_no_load_loss_percent > 0
                and self.coupling_transformer_magnetizing_current_percent >= 0):
            raise ValueError('DSTATCOM_EXPLICIT_NONZERO_LOSS_AND_IMPEDANCE_ASSUMPTIONS_REQUIRED')

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        value.pop('version', None)
        return cls(**value)

    def to_dict(self):
        return dict(version=VERSION, **asdict(self))

    def engineering_assumptions(self):
        return dict(status='ENGINEERING_DESIGN_ASSUMPTIONS_NOT_PROCURED_PRODUCT_SPECIFICATIONS',
            independent_phase_topology='Three physically distinct grounded single-phase converter modules; no assumed independent control of a three-wire inverter',
            coupling_transformer='Dedicated grounded-wye single-phase isolation bank at the actual PCC; existing service transformer remains in net-flow path',
            voltage_base='All single-phase kV values are coil/line-neutral; three-phase PCC inventory supplies actual line-neutral base',
            converter_losses='Positive constant-power loss Loads: standby fraction of phase kVA plus variable fraction times squared Q utilization',
            transformer_losses='OpenDSS winding resistances, no-load loss and magnetizing branch explicitly modeled; no original equipment rating changed',
            ramp_time='feedback_step_seconds bounds converter command slew only. Original STATIC control queues may advance delays internally; this is not validated physical regulator timing',
            active_controller='Tap-aware present-fullnetwork causal feedback; no Actual OPF/MILP/future inputs. Real Q trial and Q-only rollback retain endogenous original tap history',
            superseded_V2_droop='Local .18 saturation-fraction gain law is an unexecuted superseded reference and is not called by the public autonomous controller',
            hysteresis='Original V1 local deadband retained; Tap-aware supervisor holds actual applied Q after fullnetwork safety, and reenters only for present network violation. Mode is bounded supply/absorb command state, without an integral accumulator',
            anti_windup='No integral accumulator. Persistent Q state tracks only the capacity/ramp-limited command; no hidden unsaturated request accumulates',
            grounding='Solid ground reference at each single-phase winding neutral; neutral current equals phase current and each isolated module neutral requires full current rating',
            hardware_certification='Steady-state design model only; harmonic, protection, fault-duty, transient stability and procurement approval remain outside this power-flow validation')

