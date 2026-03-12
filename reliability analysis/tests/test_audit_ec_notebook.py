"""
Tests for the audit EC commitment tradeoffs notebook.

Groups:
  1. Config contract          — validates constants from config cell (fast)
  2. Shared math functions    — required_touches, mttt_eff_hours, lambda_detect, reliability_detection_inputs (fast)
  3. amplify_alpha            — per-epoch alpha amplification (fast)
  4. merkle_q_det             — Merkle detection probability (fast)
  5. Touch-budget functions   — touches_per_epoch, detection_after_epochs, min_touches_per_epoch (fast)
  6. Regime plan functions    — merkle_plan, two_d_plan, hail_plan (fast)
  7. Stale symbol check       — ensures legacy symbols are gone (fast)
  8. Smoke test               — executes full notebook (slow)
"""

import math
import pytest
from testbook import testbook

NB_PATH = "archivist_audit_ec_commitment_tradeoffs.ipynb"

# Cell indices (0-based, testbook order):
#   3 = pip-install guard (needed for imports)
#   4 = imports (math, numpy, pandas, matplotlib) + constants
#   7 = core functions (required_touches, mttt_eff_hours, etc.)
#  12 = touch-budget functions (touches_per_epoch, detection_after_epochs, min_touches_per_epoch)
#  23 = amplify_alpha, merkle_q_det, and regime plan functions (merkle_plan, two_d_plan, hail_plan)
# NOTE: cell 23 has all helper and plan functions together, so both fixtures execute through it
CONFIG_CELLS = [3, 4, 7, 12, 23]
PLAN_CELLS = [3, 4, 7, 12, 23]


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tb():
    """Shared testbook session with config, core functions, and touch-budget executed."""
    with testbook(NB_PATH, execute=CONFIG_CELLS) as tb:
        yield tb


@pytest.fixture(scope="module")
def tb_plans():
    """Testbook session with regime plan functions also executed."""
    with testbook(NB_PATH, execute=PLAN_CELLS) as tb:
        yield tb


# ══════════════════════════════════════════════════════════════
# Group 1: Config contract
# ══════════════════════════════════════════════════════════════


def test_planning_target_delta(tb):
    """PLANNING_TARGET_DELTA == 1e-6."""
    assert tb.ref("PLANNING_TARGET_DELTA") == 1e-6


def test_archivist_target_q_det(tb):
    """ARCHIVIST_TARGET_Q_DET == 1 - 1e-6."""
    assert tb.ref("ARCHIVIST_TARGET_Q_DET") == pytest.approx(1 - 1e-6)


def test_audit_epoch_hours(tb):
    """AUDIT_EPOCH_HOURS == 24."""
    assert tb.ref("AUDIT_EPOCH_HOURS") == 24


def test_planning_target_epochs(tb):
    """PLANNING_TARGET_EPOCHS == 3."""
    assert tb.ref("PLANNING_TARGET_EPOCHS") == 3


def test_reliability_anchor_structure(tb):
    """RELIABILITY_ANCHOR is a dict with keys k, n, r0."""
    anchor = tb.ref("RELIABILITY_ANCHOR")
    assert isinstance(anchor, dict)
    assert {"k", "n", "r0"} <= set(anchor.keys())


def test_two_d_calibration_point_structure(tb):
    """TWO_D_CALIBRATION_POINT is a dict."""
    cal = tb.ref("TWO_D_CALIBRATION_POINT")
    assert isinstance(cal, dict)


# ══════════════════════════════════════════════════════════════
# Group 2: Shared math functions
# ══════════════════════════════════════════════════════════════


def test_required_touches_known_value(tb):
    """required_touches(0.5, 1e-6) == ceil(ln(1e-6)/ln(0.5))."""
    tb.inject("_rt_val = required_touches(0.5, 1e-6)")
    expected = math.ceil(math.log(1e-6) / math.log(0.5))
    assert tb.ref("_rt_val") == expected


def test_required_touches_monotone_alpha(tb):
    """Higher alpha (better detection) requires fewer touches."""
    tb.inject(
        """
_rt_mono_alpha = {
    "high": required_touches(0.9, 1e-6),
    "low":  required_touches(0.5, 1e-6),
}
"""
    )
    r = tb.ref("_rt_mono_alpha")
    assert r["high"] < r["low"], (
        f"required_touches(0.9) should be < required_touches(0.5), got {r}"
    )


def test_required_touches_monotone_delta(tb):
    """Smaller delta (tighter target) requires more touches."""
    tb.inject(
        """
_rt_mono_delta = {
    "tight": required_touches(0.5, 1e-9),
    "loose": required_touches(0.5, 1e-6),
}
"""
    )
    r = tb.ref("_rt_mono_delta")
    assert r["tight"] > r["loose"], (
        f"required_touches(delta=1e-9) should be > required_touches(delta=1e-6), got {r}"
    )


def test_mttt_eff_hours_full_coverage(tb):
    """mttt_eff_hours(20, 20, 24) == 24 (all slots covered each epoch)."""
    tb.inject("_mttt_full = mttt_eff_hours(20, 20, 24)")
    assert tb.ref("_mttt_full") == pytest.approx(24.0)


def test_mttt_eff_hours_half_coverage(tb):
    """mttt_eff_hours(20, 10, 24) == 48 (half slots per epoch)."""
    tb.inject("_mttt_half = mttt_eff_hours(20, 10, 24)")
    assert tb.ref("_mttt_half") == pytest.approx(48.0)


def test_mttt_eff_hours_single(tb):
    """mttt_eff_hours(1, 1, 24) == 24."""
    tb.inject("_mttt_single = mttt_eff_hours(1, 1, 24)")
    assert tb.ref("_mttt_single") == pytest.approx(24.0)


def test_lambda_detect_inverse_of_mttt(tb):
    """lambda_detect_from_sampling with q_det=1 == 1 / mttt_eff."""
    tb.inject("_lam_inv = lambda_detect_from_sampling(20, 10, 24, 1.0)")
    assert tb.ref("_lam_inv") == pytest.approx(1.0 / 48.0)


def test_lambda_detect_scales_with_q_det(tb):
    """lambda_detect_from_sampling scales linearly with q_det."""
    tb.inject("_lam_qdet = lambda_detect_from_sampling(20, 10, 24, 0.5)")
    assert tb.ref("_lam_qdet") == pytest.approx(0.5 / 48.0)


def test_reliability_detection_inputs_keys(tb):
    """reliability_detection_inputs returns dict with expected keys."""
    tb.inject("_rdi = reliability_detection_inputs(20, 10, 24, 1.0)")
    result = tb.ref("_rdi")
    assert isinstance(result, dict)
    assert "MTTT_eff_hours" in result
    assert "lambda_detect_per_hour" in result
    assert "MTTD_equiv_hours" in result


def test_reliability_detection_inputs_mttd_inverse(tb):
    """MTTD_equiv_hours == 1 / lambda_detect_per_hour."""
    tb.inject("_rdi2 = reliability_detection_inputs(20, 10, 24, 1.0)")
    result = tb.ref("_rdi2")
    assert result["MTTD_equiv_hours"] == pytest.approx(
        1.0 / result["lambda_detect_per_hour"]
    )


# ══════════════════════════════════════════════════════════════
# Group 3: amplify_alpha
# ══════════════════════════════════════════════════════════════


def test_amplify_alpha_identity(tb):
    """amplify_alpha(alpha, 1, 1) == alpha (no amplification)."""
    tb.inject("_amp_id = amplify_alpha(0.5, 1, 1)")
    assert tb.ref("_amp_id") == pytest.approx(0.5)


def test_amplify_alpha_two_nodes(tb):
    """amplify_alpha(0.5, 2, 1) == 1 - 0.5^2 == 0.75."""
    tb.inject("_amp_2n = amplify_alpha(0.5, 2, 1)")
    assert tb.ref("_amp_2n") == pytest.approx(0.75)


def test_amplify_alpha_two_rounds(tb):
    """amplify_alpha(0.5, 1, 2) == 0.75 (symmetric: m*r)."""
    tb.inject("_amp_2r = amplify_alpha(0.5, 1, 2)")
    assert tb.ref("_amp_2r") == pytest.approx(0.75)


def test_amplify_alpha_monotone(tb):
    """amplify_alpha(0.5, 4, 1) > amplify_alpha(0.5, 2, 1)."""
    tb.inject(
        """
_amp_mono = {
    "m4": amplify_alpha(0.5, 4, 1),
    "m2": amplify_alpha(0.5, 2, 1),
}
"""
    )
    r = tb.ref("_amp_mono")
    assert r["m4"] > r["m2"], (
        f"amplify_alpha(m=4) should be > amplify_alpha(m=2), got {r}"
    )


def test_amplify_alpha_bounds(tb):
    """amplify_alpha result is strictly between 0 and 1."""
    tb.inject("_amp_bounds = amplify_alpha(0.01, 5, 3)")
    val = tb.ref("_amp_bounds")
    assert val > 0
    assert val < 1


# ══════════════════════════════════════════════════════════════
# Group 4: merkle_q_det
# ══════════════════════════════════════════════════════════════


def test_merkle_q_det_single_round(tb):
    """merkle_q_det(0.5, 1) == 0.5 (single round, no amplification)."""
    tb.inject("_mqd1 = merkle_q_det(0.5, 1)")
    assert tb.ref("_mqd1") == pytest.approx(0.5)


def test_merkle_q_det_two_rounds(tb):
    """merkle_q_det(0.5, 2) == 0.75 (1 - 0.5^2)."""
    tb.inject("_mqd2 = merkle_q_det(0.5, 2)")
    assert tb.ref("_mqd2") == pytest.approx(0.75)


def test_merkle_q_det_three_rounds(tb):
    """merkle_q_det(0.9, 3) == 1 - 0.1^3 == 0.999."""
    tb.inject("_mqd3 = merkle_q_det(0.9, 3)")
    assert tb.ref("_mqd3") == pytest.approx(0.999)


# ══════════════════════════════════════════════════════════════
# Group 5: Touch-budget functions
# ══════════════════════════════════════════════════════════════


def test_touches_per_epoch_known_value(tb):
    """touches_per_epoch(10, 2, 3) == 60."""
    tb.inject("_tpe = touches_per_epoch(10, 2, 3)")
    assert tb.ref("_tpe") == 60


def test_detection_after_epochs_single(tb):
    """detection_after_epochs(0.5, 1, 1) == 0.5."""
    tb.inject("_dae1 = detection_after_epochs(0.5, 1, 1)")
    assert tb.ref("_dae1") == pytest.approx(0.5)


def test_detection_after_epochs_two_epochs(tb):
    """detection_after_epochs(0.5, 1, 2) == 0.75."""
    tb.inject("_dae2 = detection_after_epochs(0.5, 1, 2)")
    assert tb.ref("_dae2") == pytest.approx(0.75)


def test_min_touches_per_epoch_returns_tuple(tb):
    """min_touches_per_epoch returns a tuple (c_per_epoch, c_total)."""
    tb.inject(
        """
_mtp = min_touches_per_epoch(0.5, 1e-6, 3)
_mtp_c_total_expected = required_touches(0.5, 1e-6)
_mtp_check = {
    "is_tuple": isinstance(_mtp, tuple),
    "length": len(_mtp),
    "c_total_matches": _mtp[1] == _mtp_c_total_expected,
}
"""
    )
    r = tb.ref("_mtp_check")
    assert r["is_tuple"], "min_touches_per_epoch should return a tuple"
    assert r["length"] == 2, f"Expected 2-tuple, got length {r['length']}"
    assert r["c_total_matches"], "c_total should equal required_touches(alpha, delta)"


# ══════════════════════════════════════════════════════════════
# Group 6: Regime plan functions
# ══════════════════════════════════════════════════════════════


def test_merkle_plan_regime(tb_plans):
    """merkle_plan result has regime == 'Merkle'."""
    tb_plans.inject("_mp = merkle_plan(alpha=0.5, delta=1e-6, epoch_hours=24)")
    result = tb_plans.ref("_mp")
    assert result["regime"] == "Merkle"


def test_merkle_plan_mttt(tb_plans):
    """merkle_plan MTTT_eff_hours == 24 (single-slot)."""
    tb_plans.inject("_mp2 = merkle_plan(alpha=0.5, delta=1e-6, epoch_hours=24)")
    result = tb_plans.ref("_mp2")
    assert result["MTTT_eff_hours"] == pytest.approx(24.0)


def test_merkle_plan_lambda_consistency(tb_plans):
    """merkle_plan lambda_detect_per_hour == q_det / MTTT_eff_hours."""
    tb_plans.inject("_mp3 = merkle_plan(alpha=0.5, delta=1e-6, epoch_hours=24)")
    result = tb_plans.ref("_mp3")
    assert result["lambda_detect_per_hour"] == pytest.approx(
        result["q_det"] / result["MTTT_eff_hours"]
    )


def test_two_d_plan_regime(tb_plans):
    """two_d_plan result has regime == '2D EC'."""
    tb_plans.inject("_tdp = two_d_plan(epoch_hours=24)")
    result = tb_plans.ref("_tdp")
    assert result["regime"] == "2D EC"


def test_two_d_plan_mttt(tb_plans):
    """two_d_plan MTTT_eff_hours == 24."""
    tb_plans.inject("_tdp2 = two_d_plan(epoch_hours=24)")
    result = tb_plans.ref("_tdp2")
    assert result["MTTT_eff_hours"] == pytest.approx(24.0)


def test_two_d_plan_default_q_det(tb_plans):
    """two_d_plan default q_det == 1 - 1e-6."""
    tb_plans.inject("_tdp3 = two_d_plan(epoch_hours=24)")
    result = tb_plans.ref("_tdp3")
    assert result["q_det"] == pytest.approx(1 - 1e-6)


def test_two_d_plan_custom_q_det(tb_plans):
    """two_d_plan with q_det=0.99 returns q_det == 0.99."""
    tb_plans.inject("_tdp4 = two_d_plan(epoch_hours=24, q_det=0.99)")
    result = tb_plans.ref("_tdp4")
    assert result["q_det"] == pytest.approx(0.99)


def test_hail_plan_regime(tb_plans):
    """hail_plan result has regime == 'HAIL'."""
    tb_plans.inject(
        "_hp = hail_plan(alpha_base=0.5, m=2, r_nodes=3, n_slots=20, epoch_hours=24)"
    )
    result = tb_plans.ref("_hp")
    assert result["regime"] == "HAIL"


def test_hail_plan_q_det(tb_plans):
    """hail_plan q_det == amplify_alpha(0.5, 2, 3) == 1 - 0.5^(2*3)."""
    tb_plans.inject(
        "_hp2 = hail_plan(alpha_base=0.5, m=2, r_nodes=3, n_slots=20, epoch_hours=24)"
    )
    result = tb_plans.ref("_hp2")
    expected = 1 - 0.5 ** (2 * 3)
    assert result["q_det"] == pytest.approx(expected)


def test_hail_plan_mttt(tb_plans):
    """hail_plan MTTT_eff_hours == n_slots * epoch_hours / slots_per_epoch."""
    tb_plans.inject(
        "_hp3 = hail_plan(alpha_base=0.5, m=2, r_nodes=3, n_slots=20, epoch_hours=24)"
    )
    result = tb_plans.ref("_hp3")
    expected_mttt = 20 * 24.0 / result["slots_per_epoch"]
    assert result["MTTT_eff_hours"] == pytest.approx(expected_mttt)


def test_hail_plan_slots_feasible(tb_plans):
    """hail_plan slots_per_epoch <= n_slots."""
    tb_plans.inject(
        "_hp4 = hail_plan(alpha_base=0.5, m=2, r_nodes=3, n_slots=20, epoch_hours=24)"
    )
    result = tb_plans.ref("_hp4")
    assert result["slots_per_epoch"] <= 20


def test_hail_plan_infeasible_raises(tb_plans):
    """hail_plan raises ValueError when parameters are infeasible."""
    tb_plans.inject(
        """
_hail_infeasible_raised = False
try:
    hail_plan(alpha_base=0.001, m=1, r_nodes=1, n_slots=2, epoch_hours=24, target_epochs=1)
except ValueError:
    _hail_infeasible_raised = True
"""
    )
    assert tb_plans.ref("_hail_infeasible_raised"), (
        "hail_plan should raise ValueError for infeasible parameters"
    )


def test_all_plans_have_required_keys(tb_plans):
    """All three regime plans expose q_det, MTTT_eff_hours, lambda_detect_per_hour."""
    tb_plans.inject(
        """
_all_plans = [
    merkle_plan(alpha=0.5, delta=1e-6, epoch_hours=24),
    two_d_plan(epoch_hours=24),
    hail_plan(alpha_base=0.5, m=2, r_nodes=3, n_slots=20, epoch_hours=24),
]
_required_keys = ["q_det", "MTTT_eff_hours", "lambda_detect_per_hour"]
_plans_keys_ok = [all(k in p for k in _required_keys) for p in _all_plans]
"""
    )
    results = tb_plans.ref("_plans_keys_ok")
    for i, ok in enumerate(results):
        assert ok, f"Plan index {i} is missing one or more required keys"


def test_all_plans_lambda_consistency(tb_plans):
    """For all plans: lambda_detect_per_hour == q_det / MTTT_eff_hours."""
    tb_plans.inject(
        """
_lam_check_plans = [
    merkle_plan(alpha=0.5, delta=1e-6, epoch_hours=24),
    two_d_plan(epoch_hours=24),
    hail_plan(alpha_base=0.5, m=2, r_nodes=3, n_slots=20, epoch_hours=24),
]
_lam_consistent = [
    abs(p["lambda_detect_per_hour"] - p["q_det"] / p["MTTT_eff_hours"]) < 1e-12
    for p in _lam_check_plans
]
"""
    )
    results = tb_plans.ref("_lam_consistent")
    for i, ok in enumerate(results):
        assert ok, f"Plan index {i}: lambda_detect_per_hour != q_det / MTTT_eff_hours"


# ══════════════════════════════════════════════════════════════
# Group 7: Stale symbol check
# ══════════════════════════════════════════════════════════════


def test_no_legacy_audit_plan_symbol(tb_plans):
    """Legacy symbol 'audit_plan_from_target' must not exist in namespace."""
    tb_plans.inject("_has_old = 'audit_plan_from_target' in dir()")
    assert tb_plans.ref("_has_old") is False, (
        "Legacy symbol 'audit_plan_from_target' still exists in notebook namespace"
    )


# ══════════════════════════════════════════════════════════════
# Group 8: Smoke test (slow)
# ══════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_notebook_runs_end_to_end():
    """Execute all cells; fail on any exception."""
    import json

    nb = json.load(open(NB_PATH))
    total = len(nb["cells"])
    cells_to_run = list(range(total))
    with testbook(NB_PATH, execute=cells_to_run, timeout=120) as tb:
        tb.inject("_smoke_ok = True")
        assert tb.ref("_smoke_ok")
