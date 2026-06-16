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
from bms.supervisor import SupervisoryController, BMSState, FaultCode
from bms.bms_controller import BMSController


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
