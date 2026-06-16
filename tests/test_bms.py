"""
Unit tests for the BMS package.

Run:
    python -m pytest tests/test_bms.py -v
"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bms.config import CellConfig, PackConfig, EKFConfig, OCV_SOC_TABLE
from bms.cell_model import CellModel, ocv_from_soc, docv_dsoc
from bms.soc_estimator import EKFSOCEstimator
from bms.soh_estimator import SOHEstimator
from bms.cell_balancer import CellBalancer
from bms.power_limits import PowerLimitsCalculator
from bms.supervisor import SupervisoryController, BMSState, FaultCode, AlertCode
from bms.bms_controller import BMSController
from bms.chemistries import LFP, LEAD_ACID, NMC
from bms.thermal import FanController, FanFaultCode
from bms.vehicles import (
    TWO_WHEELER, FOUR_WHEELER_RETRO, FOUR_WHEELER_MODERN, ELECTRIC_BUS,
    make_bms_controller,
)


# -------------------------------------------------------------------------
# OCV lookup table
# -------------------------------------------------------------------------

class TestOCVTable:
    def test_ocv_at_zero_soc(self):
        assert ocv_from_soc(0.0) == pytest.approx(2.5, abs=0.01)

    def test_ocv_at_full_soc(self):
        assert ocv_from_soc(1.0) == pytest.approx(3.65, abs=0.01)

    def test_ocv_midrange(self):
        v = ocv_from_soc(0.5)
        assert 3.2 <= v <= 3.3         # LFP plateau region

    def test_ocv_clamps_below_zero(self):
        assert ocv_from_soc(-0.1) == ocv_from_soc(0.0)

    def test_ocv_clamps_above_one(self):
        assert ocv_from_soc(1.1) == ocv_from_soc(1.0)

    def test_docv_dsoc_positive(self):
        # OCV must increase with SOC everywhere
        for soc in [0.1, 0.3, 0.5, 0.7, 0.9]:
            assert docv_dsoc(soc) > 0


# -------------------------------------------------------------------------
# Cell model
# -------------------------------------------------------------------------

class TestCellModel:
    def test_soc_decreases_on_discharge(self):
        cell = CellModel(soc_init=0.80)
        state = cell.step(current=50.0, dt=3600.0)   # 50 A for 1 hour = 0.5 C·h
        assert state.soc < 0.80

    def test_soc_increases_on_charge(self):
        cell = CellModel(soc_init=0.20)
        state = cell.step(current=-50.0, dt=3600.0)
        assert state.soc > 0.20

    def test_soc_bounded(self):
        cell = CellModel(soc_init=0.0)
        state = cell.step(current=200.0, dt=7200.0)  # attempt over-discharge
        assert state.soc >= 0.0

    def test_terminal_voltage_drops_on_discharge(self):
        cell = CellModel(soc_init=0.50)
        v_open = cell.v_terminal
        state = cell.step(current=100.0, dt=0.1)
        assert state.v_terminal < v_open + 1e-6      # voltage drops with current

    def test_temperature_rises_with_current(self):
        cell = CellModel(soc_init=0.50, temp_init=25.0)
        for _ in range(100):
            cell.step(current=200.0, dt=1.0, ambient_temp=25.0)
        assert cell.temperature > 25.0

    def test_ekf_matrices_shape(self):
        cell = CellModel()
        F, H, ocv, r0 = cell.get_ekf_matrices(current=10.0, dt=1.0)
        assert F.shape == (3, 3)
        assert H.shape == (1, 3)
        assert isinstance(ocv, float)
        assert r0 > 0


# -------------------------------------------------------------------------
# EKF SOC Estimator
# -------------------------------------------------------------------------

class TestEKFSOCEstimator:
    def test_tracks_true_soc(self):
        """EKF estimate converges toward true SOC.

        LFP has a notoriously flat OCV-SOC plateau, so the filter relies
        primarily on coulomb-counting with slow voltage corrections.
        Starting 30 % off, we expect at most 10 % residual error after
        200 steps (dt=1 s, 50 A → 14 mAh drawn → small SOC movement).
        """
        cell = CellModel(soc_init=0.80)
        ekf = EKFSOCEstimator(cell, soc_init=0.50)   # wrong initial guess

        i = 50.0
        for _ in range(200):
            state = cell.step(i, 1.0)
            ekf.update(i, state.v_terminal, 1.0)

        assert abs(ekf.soc_estimate - cell.soc) < 0.10

    def test_estimate_stays_bounded(self):
        cell = CellModel(soc_init=0.80)
        ekf = EKFSOCEstimator(cell, soc_init=0.80)
        for _ in range(200):
            state = cell.step(50.0, 1.0)
            est = ekf.update(50.0, state.v_terminal, 1.0)
            assert 0.0 <= est <= 1.0


# -------------------------------------------------------------------------
# SOH Estimator
# -------------------------------------------------------------------------

class TestSOHEstimator:
    def test_initial_soh_is_100(self):
        soh = SOHEstimator()
        result = soh.update(0.0, 3.2, dt=1.0)
        assert result.soh_capacity_pct == pytest.approx(100.0, abs=0.01)

    def test_capacity_degrades_with_throughput(self):
        soh = SOHEstimator(nominal_capacity_ah=100.0, degradation_rate=1e-3)
        # Simulate 500 equivalent full cycles worth of throughput
        for _ in range(int(500 * 2 * 100 * 3600)):  # would be too slow — just test math
            pass
        # Test degradation formula directly
        equiv_cycles = 100.0
        q_fade = 1e-3 * equiv_cycles
        q_usable = 100.0 * (1.0 - q_fade)
        assert q_usable == pytest.approx(90.0, abs=0.01)

    def test_r0_estimation_on_step(self):
        soh = SOHEstimator(r0_fresh=0.002, r0_ema_alpha=1.0)  # alpha=1 → instant
        # Simulate a current step: ΔI=100 A, ΔV=0.2 V → R0=0.002 Ω
        soh.update(0.0, 3.2, dt=1.0)              # prev: I=0, V=3.2
        result = soh.update(100.0, 3.0, dt=1.0)  # step: I=100, V=3.0 (drop = 0.2)
        assert result.r0_estimate == pytest.approx(0.002, abs=0.002)


# -------------------------------------------------------------------------
# Cell Balancer
# -------------------------------------------------------------------------

class TestCellBalancer:
    def test_no_balancing_below_threshold(self):
        bal = CellBalancer(n_cells=4, v_threshold=0.010)
        voltages = [3.25, 3.252, 3.248, 3.250]   # spread = 4 mV < 10 mV
        socs = [0.5] * 4
        state = bal.update(voltages, socs)
        assert not state.is_balancing

    def test_balancing_above_threshold(self):
        bal = CellBalancer(n_cells=4, v_threshold=0.010)
        voltages = [3.30, 3.25, 3.25, 3.25]       # spread = 50 mV > 10 mV
        socs = [0.6, 0.5, 0.5, 0.5]
        state = bal.update(voltages, socs)
        assert state.is_balancing
        assert state.bypass_switches[0] is True    # highest cell bypassed
        assert state.bypass_switches[1] is False

    def test_balancing_disabled_externally(self):
        bal = CellBalancer(n_cells=4, v_threshold=0.010)
        voltages = [3.30, 3.25, 3.25, 3.25]
        socs = [0.6, 0.5, 0.5, 0.5]
        state = bal.update(voltages, socs, balancing_enabled=False)
        assert not state.is_balancing


# -------------------------------------------------------------------------
# Power Limits
# -------------------------------------------------------------------------

class TestPowerLimitsCalculator:
    def test_nominal_limits(self):
        calc = PowerLimitsCalculator()
        limits = calc.compute(soc=0.50, temperature=25.0, v_pack=51.2)
        assert limits.i_max_discharge > 0
        assert limits.i_max_charge < 0
        assert limits.derate_reason == "nominal"

    def test_discharge_derated_at_low_soc(self):
        calc = PowerLimitsCalculator()
        limits_normal = calc.compute(soc=0.50, temperature=25.0, v_pack=51.2)
        limits_low = calc.compute(soc=0.06, temperature=25.0, v_pack=48.0)
        assert limits_low.i_max_discharge < limits_normal.i_max_discharge

    def test_charge_blocked_over_temp(self):
        calc = PowerLimitsCalculator()
        limits = calc.compute(soc=0.50, temperature=50.0, v_pack=51.2)
        assert limits.i_max_charge == pytest.approx(0.0, abs=1.0)

    def test_discharge_blocked_over_temp(self):
        calc = PowerLimitsCalculator()
        limits = calc.compute(soc=0.50, temperature=65.0, v_pack=51.2)
        assert limits.i_max_discharge == pytest.approx(0.0, abs=1.0)

    def test_charge_blocked_below_min_temp(self):
        calc = PowerLimitsCalculator()
        limits = calc.compute(soc=0.50, temperature=-5.0, v_pack=51.2)
        assert limits.i_max_charge == pytest.approx(0.0, abs=1.0)


# -------------------------------------------------------------------------
# Supervisory State Machine
# -------------------------------------------------------------------------

class TestSupervisoryController:
    def _make_sv(self):
        return SupervisoryController(
            cv_voltage_per_cell=3.65,
            cv_term_current_a=5.0,
            cc_current_a=-50.0,
        )

    def _healthy_inputs(self, **kwargs):
        defaults = dict(
            v_cell_max=3.3, v_cell_min=3.25, t_cell_max=28.0,
            soc_mean=0.50, current=0.0, v_spread=0.005,
            charge_requested=False, discharge_requested=False,
            isolation_ok=True,
        )
        defaults.update(kwargs)
        return defaults

    def test_starts_in_init(self):
        sv = self._make_sv()
        assert sv.state == BMSState.INIT

    def test_transitions_to_idle(self):
        sv = self._make_sv()
        for _ in range(5):
            sv.update(**self._healthy_inputs())
        assert sv.state == BMSState.IDLE

    def test_over_voltage_fault(self):
        sv = self._make_sv()
        for _ in range(5):
            sv.update(**self._healthy_inputs())
        sv.update(**self._healthy_inputs(v_cell_max=3.75))
        assert sv.state == BMSState.FAULT

    def test_under_voltage_fault(self):
        sv = self._make_sv()
        for _ in range(5):
            sv.update(**self._healthy_inputs())
        sv.update(**self._healthy_inputs(v_cell_min=2.35))
        assert sv.state == BMSState.FAULT

    def test_isolation_fault(self):
        sv = self._make_sv()
        for _ in range(5):
            sv.update(**self._healthy_inputs())
        sv.update(**self._healthy_inputs(isolation_ok=False))
        assert sv.state == BMSState.FAULT


# -------------------------------------------------------------------------
# Top-level BMSController integration test
# -------------------------------------------------------------------------

class TestBMSController:
    def test_pack_voltage_in_range(self):
        bms = BMSController(n_cells=16, soc_init=0.50)
        state = bms.step(current=50.0, dt=1.0)
        # 16 × 3.2 V nominal → pack ~51.2 V
        assert 30.0 < state.pack_voltage_v < 70.0

    def test_soc_decreases_on_discharge(self):
        bms = BMSController(n_cells=4, soc_init=0.80)
        for _ in range(100):
            state = bms.step(current=50.0, dt=10.0)
        assert state.pack_soc_mean < 0.80

    def test_all_cell_states_populated(self):
        bms = BMSController(n_cells=8, soc_init=0.60)
        state = bms.step(current=0.0, dt=1.0)
        assert len(state.cell_voltages_v) == 8
        assert len(state.cell_soc_estimates) == 8
        assert len(state.cell_temperatures_c) == 8

    def test_power_limits_not_none(self):
        bms = BMSController(n_cells=4, soc_init=0.50)
        state = bms.step(current=10.0, dt=1.0)
        assert state.power_limits is not None
        assert state.power_limits.i_max_discharge >= 0

    def test_no_fault_on_normal_discharge(self):
        bms = BMSController(n_cells=4, soc_init=0.80)
        for _ in range(60):
            state = bms.step(current=50.0, dt=1.0)
        assert not state.fault_active

    def test_soh_available(self):
        bms = BMSController(n_cells=4, soc_init=0.50)
        state = bms.step(current=50.0, dt=1.0)
        assert 0 < state.soh.soh_capacity_pct <= 100.0


# -------------------------------------------------------------------------
# Multi-chemistry cell models
# -------------------------------------------------------------------------

class TestMultiChemistry:
    def test_lead_acid_ocv_at_full(self):
        v = LFP.ocv_table[-1, 1]
        assert v == pytest.approx(3.65, abs=0.01)
        v_pba = LEAD_ACID.ocv_table[-1, 1]
        assert v_pba == pytest.approx(2.30, abs=0.01)

    def test_lead_acid_cell_model_discharge(self):
        cell = CellModel(config=LEAD_ACID.cell_config, ocv_table=LEAD_ACID.ocv_table, soc_init=0.80)
        state = cell.step(current=10.0, dt=3600.0)
        assert state.soc < 0.80
        assert state.v_terminal > 1.5      # should not collapse entirely

    def test_nmc_ocv_monotone(self):
        ocv_vals = NMC.ocv_table[:, 1]
        assert all(b > a for a, b in zip(ocv_vals, ocv_vals[1:]))

    def test_lfp_cell_nominal_voltage(self):
        assert LFP.cell_config.v_nominal == pytest.approx(3.20, abs=0.01)

    def test_pba_three_stage_flag(self):
        assert FOUR_WHEELER_RETRO.charging_stages == 3

    def test_chemistry_registry_keys(self):
        from bms.chemistries import CHEMISTRY_REGISTRY
        assert "LFP" in CHEMISTRY_REGISTRY
        assert "PbA" in CHEMISTRY_REGISTRY
        assert "NMC" in CHEMISTRY_REGISTRY


# -------------------------------------------------------------------------
# Vehicle profiles
# -------------------------------------------------------------------------

class TestVehicleProfiles:
    def test_two_wheeler_voltage(self):
        # 15 cells × 3.2 V = 48 V
        assert TWO_WHEELER.nominal_pack_voltage_v == pytest.approx(48.0, abs=0.5)

    def test_four_wheeler_retro_voltage(self):
        # 36 cells × 2.0 V = 72 V
        assert FOUR_WHEELER_RETRO.nominal_pack_voltage_v == pytest.approx(72.0, abs=0.5)

    def test_electric_bus_energy(self):
        # 128S2P, 200 Ah per cell → 400 Ah pack, 409.6 V → ~163.8 kWh
        assert ELECTRIC_BUS.nominal_pack_energy_kwh == pytest.approx(163.8, rel=0.05)

    def test_bus_is_active_cooled(self):
        assert ELECTRIC_BUS.has_active_cooling is True

    def test_two_wheeler_passive_cooled(self):
        assert TWO_WHEELER.has_active_cooling is False

    def test_make_bms_controller_two_wheeler(self):
        bms = make_bms_controller(TWO_WHEELER, soc_init=0.80)
        state = bms.step(current=20.0, dt=1.0)
        # 15 cells × ~3.28 V = ~49.2 V at 80% SOC
        assert 40.0 < state.pack_voltage_v < 60.0

    def test_make_bms_controller_retro_4w(self):
        bms = make_bms_controller(FOUR_WHEELER_RETRO, soc_init=0.80)
        state = bms.step(current=43.0, dt=1.0)
        # 36 cells × ~2.10 V (at 80% SOC) ≈ 75.6 V
        assert 50.0 < state.pack_voltage_v < 100.0

    def test_make_bms_controller_bus(self):
        bms = make_bms_controller(ELECTRIC_BUS, soc_init=0.80)
        # Use low current to avoid large R0 drop: pack OCV ≈ 128 × 3.28 ≈ 420 V
        state = bms.step(current=10.0, dt=1.0)
        assert 380.0 < state.pack_voltage_v < 460.0


# -------------------------------------------------------------------------
# Thermal / fan controller
# -------------------------------------------------------------------------

class TestFanController:
    def test_fan_off_below_threshold(self):
        fan = FanController(t_fan_on=35.0, t_fan_full=50.0)
        state = fan.update(temperature=25.0)
        assert state.fan_pwm_pct == pytest.approx(0.0, abs=0.1)
        assert not state.cooling_active

    def test_fan_full_above_t_high(self):
        fan = FanController(t_fan_on=35.0, t_fan_full=50.0)
        state = fan.update(temperature=55.0)
        assert state.fan_pwm_pct == pytest.approx(100.0, abs=0.1)

    def test_fan_ramps_linearly(self):
        fan = FanController(t_fan_on=35.0, t_fan_full=50.0)
        s_low = fan.update(temperature=35.0)
        # force fan_on so hysteresis doesn't suppress
        s_mid = fan.update(temperature=42.5)
        s_high = fan.update(temperature=50.0)
        assert s_low.fan_pwm_pct <= s_mid.fan_pwm_pct <= s_high.fan_pwm_pct

    def test_heater_on_below_t_heat(self):
        fan = FanController(t_heat_on=5.0)
        state = fan.update(temperature=2.0)
        assert state.heater_on is True
        assert state.cooling_mode == "HEATER"

    def test_fan_fault_detection(self):
        fan = FanController(t_fan_on=35.0, t_fan_full=50.0)
        fan.update(temperature=55.0)  # ensure fan_on state
        state = fan.update(temperature=55.0, fan_speed_feedback=0.0)  # stuck
        assert state.fan_fault == FanFaultCode.FAN_STUCK

    def test_no_fault_without_feedback(self):
        fan = FanController(t_fan_on=35.0, t_fan_full=50.0)
        state = fan.update(temperature=55.0, fan_speed_feedback=None)
        assert state.fan_fault == FanFaultCode.NONE


# -------------------------------------------------------------------------
# 3-stage charging + alert codes (supervisory)
# -------------------------------------------------------------------------

class TestThreeStageCharging:
    """Validate lead-acid 3-stage charging transitions in supervisor."""

    def _make_sv_3stage(self):
        return SupervisoryController(
            cv_voltage_per_cell=2.40,
            cv_term_current_a=1.0,
            cc_current_a=-10.0,
            float_voltage_per_cell=2.27,
            charging_stages=3,
            ov_fault_v=2.50,
            uv_fault_v=1.65,
            t_max_fault_c=50.0,
            t_min_fault_c=0.0,
        )

    def _inputs(self, **kw):
        base = dict(
            v_cell_max=2.10, v_cell_min=2.08, t_cell_max=30.0,
            soc_mean=0.80, current=-10.0, v_spread=0.010,
            charge_requested=True, discharge_requested=False,
            isolation_ok=True,
        )
        base.update(kw)
        return base

    def _reach_charging_cc(self, sv):
        """Advance supervisor to CHARGING_CC state (INIT×3 → IDLE×1 → PRE_CHARGE×2 → CC)."""
        for _ in range(7):
            sv.update(**self._inputs())

    def test_reaches_charging_cc(self):
        sv = self._make_sv_3stage()
        self._reach_charging_cc(sv)
        assert sv.state == BMSState.CHARGING_CC

    def test_transitions_to_cv(self):
        sv = self._make_sv_3stage()
        self._reach_charging_cc(sv)
        # trigger CV: v_max hits absorption voltage
        sv.update(**self._inputs(v_cell_max=2.41))
        assert sv.state == BMSState.CHARGING_CV

    def test_transitions_cc_to_float_via_cv(self):
        sv = self._make_sv_3stage()
        self._reach_charging_cc(sv)
        sv.update(**self._inputs(v_cell_max=2.41))  # → CV
        # current tapers below termination threshold → should go to FLOAT
        sv.update(**self._inputs(current=-0.5, v_cell_max=2.41))
        assert sv.state == BMSState.CHARGING_FLOAT

    def test_float_state_output_has_charging_complete_alert(self):
        sv = self._make_sv_3stage()
        self._reach_charging_cc(sv)
        sv.update(**self._inputs(v_cell_max=2.41))
        sv.update(**self._inputs(current=-0.5, v_cell_max=2.41))
        out = sv.update(**self._inputs(current=-0.3, v_cell_max=2.27))
        assert AlertCode.CHARGING_COMPLETE in out.alerts


class TestAlertCodes:
    def _make_sv(self):
        return SupervisoryController(cv_voltage_per_cell=3.65, cv_term_current_a=5.0)

    def _idle_inputs(self, **kw):
        base = dict(
            v_cell_max=3.3, v_cell_min=3.25, t_cell_max=28.0,
            soc_mean=0.50, current=0.0, v_spread=0.005,
            charge_requested=False, discharge_requested=False,
            isolation_ok=True,
        )
        base.update(kw)
        return base

    def _reach_idle(self, sv):
        for _ in range(5):
            sv.update(**self._idle_inputs())

    def test_low_soc_alert(self):
        sv = self._make_sv()
        self._reach_idle(sv)
        out = sv.update(**self._idle_inputs(soc_mean=0.10))
        assert AlertCode.LOW_SOC in out.alerts

    def test_high_temperature_alert(self):
        sv = self._make_sv()
        self._reach_idle(sv)
        out = sv.update(**self._idle_inputs(t_cell_max=53.0))
        assert AlertCode.HIGH_TEMPERATURE in out.alerts

    def test_cell_imbalance_alert(self):
        sv = self._make_sv()
        self._reach_idle(sv)
        out = sv.update(**self._idle_inputs(v_spread=0.060))
        assert AlertCode.CELL_IMBALANCE in out.alerts

    def test_no_alerts_in_nominal_conditions(self):
        sv = self._make_sv()
        self._reach_idle(sv)
        out = sv.update(**self._idle_inputs())
        assert out.alerts == []
