"""
Tests for the reliability analysis notebook.

Groups:
  1. Config contract     — validates config cell output (fast)
  2. Stale symbol check  — ensures legacy symbols are gone (fast)
  3. Helper contracts    — tests pure helper functions (fast)
  4. Smoke test          — executes full notebook (slow)
"""

import math
import pytest
from testbook import testbook

NB_PATH = "archivist_reliability_analysis.ipynb"

# Cells to execute for config-level tests:
#   5  = imports/setup
#   6  = helper functions
#   7  = markdown heading (testbook skips markdown)
#   8  = unified config
#   9  = config display
CONFIG_CELLS = range(5, 10)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tb():
    """Shared testbook session with imports, helpers, and config executed."""
    with testbook(NB_PATH, execute=CONFIG_CELLS) as tb:
        yield tb


# ══════════════════════════════════════════════════════════════
# Group 1: Config contract
# ══════════════════════════════════════════════════════════════


def test_sensitivity_configs_structure(tb):
    """SENSITIVITY_CONFIGS is a non-empty list of dicts with required keys."""
    configs = tb.ref("SENSITIVITY_CONFIGS")
    assert isinstance(configs, list)
    assert len(configs) > 0
    required_keys = {"k", "n", "e", "e_actual", "l0"}
    for cfg in configs:
        assert isinstance(cfg, dict), f"Config is not a dict: {cfg}"
        assert set(cfg.keys()) == required_keys, (
            f"Keys mismatch: {set(cfg.keys())} != {required_keys}"
        )


def test_no_duplicate_configs(tb):
    """No duplicate (k, n, l0) tuples in the config grid."""
    configs = tb.ref("SENSITIVITY_CONFIGS")
    keys = [(c["k"], c["n"], c["l0"]) for c in configs]
    assert len(keys) == len(set(keys)), f"Duplicate configs found: {keys}"


def test_dimensions_valid(tb):
    """All configs satisfy k < n <= N_CEIL and k >= K_MIN."""
    configs = tb.ref("SENSITIVITY_CONFIGS")
    n_ceil = tb.ref("N_CEIL")
    k_min = tb.ref("K_MIN")
    for cfg in configs:
        assert cfg["k"] >= k_min, f"k={cfg['k']} < K_MIN={k_min}"
        assert cfg["k"] < cfg["n"], f"k={cfg['k']} >= n={cfg['n']}"
        assert cfg["n"] <= n_ceil, f"n={cfg['n']} > N_CEIL={n_ceil}"


def test_ceil_consistency(tb):
    """n >= ceil(k * e) and e_actual == n / k for every config."""
    configs = tb.ref("SENSITIVITY_CONFIGS")
    for cfg in configs:
        expected_n_min = math.ceil(cfg["k"] * cfg["e"])
        assert cfg["n"] >= expected_n_min, (
            f"n={cfg['n']} < ceil(k*e)={expected_n_min} for k={cfg['k']}, e={cfg['e']}"
        )
        assert abs(cfg["e_actual"] - cfg["n"] / cfg["k"]) < 1e-9, (
            f"e_actual={cfg['e_actual']} != n/k={cfg['n'] / cfg['k']}"
        )


def test_no_config_drift(tb):
    """Derived config values are identical to their sources."""
    tb.inject(
        """
_drift_results = {
    "ef_is_sef": EXPANSION_FACTORS is SENSITIVITY_EXPANSION_FACTORS,
    "r0_is_sl0": R0_VALUES is SENSITIVITY_L0_VALUES,
    "s3_eq_baseline": STUDY3_FIXED_MTTT_HOURS == BASELINE_MTTT,
    "mttt_study_eq_sweep": MTTT_STUDY_POINTS == list(MTTT_SWEEP),
    "mttr_study_eq_sweep": MTTR_STUDY_POINTS == list(MTTR_SWEEP),
}
"""
    )
    results = tb.ref("_drift_results")
    assert results["ef_is_sef"], (
        "EXPANSION_FACTORS is not SENSITIVITY_EXPANSION_FACTORS"
    )
    assert results["r0_is_sl0"], "R0_VALUES is not SENSITIVITY_L0_VALUES"
    assert results["s3_eq_baseline"], "STUDY3_FIXED_MTTT_HOURS != BASELINE_MTTT"
    assert results["mttt_study_eq_sweep"], "MTTT_STUDY_POINTS != list(MTTT_SWEEP)"
    assert results["mttr_study_eq_sweep"], "MTTR_STUDY_POINTS != list(MTTR_SWEEP)"


def test_standard_configs_valid(tb):
    """STANDARD_CONFIGS is non-empty and every element is in SENSITIVITY_CONFIGS."""
    tb.inject(
        """
_sc_valid = {
    "non_empty": len(STANDARD_CONFIGS) > 0,
    "all_in_grid": all(c in SENSITIVITY_CONFIGS for c in STANDARD_CONFIGS),
    "count": len(STANDARD_CONFIGS),
}
"""
    )
    result = tb.ref("_sc_valid")
    assert result["non_empty"], "STANDARD_CONFIGS is empty"
    assert result["all_in_grid"], (
        "STANDARD_CONFIGS contains entries not in SENSITIVITY_CONFIGS"
    )


def test_standard_configs_feasible(tb):
    """Each STANDARD_CONFIGS entry is feasible at all BETA_VALUES."""
    tb.inject(
        """
_feasibility = []
for _cfg in STANDARD_CONFIGS:
    for _beta in BETA_VALUES:
        _budget = effective_code_with_byzantine_budget(_cfg["k"], _cfg["n"], _beta)
        _feasibility.append({
            "cfg": (_cfg["k"], _cfg["n"], _cfg["l0"]),
            "beta": _beta,
            "feasible": _budget["feasible"],
            "remaining_parity": _budget["remaining_parity"],
            "l0": _cfg["l0"],
            "ok": _budget["feasible"] and _budget["remaining_parity"] >= _cfg["l0"],
        })
"""
    )
    results = tb.ref("_feasibility")
    for r in results:
        assert r["ok"], (
            f"Config {r['cfg']} infeasible at beta={r['beta']}: "
            f"feasible={r['feasible']}, remaining_parity={r['remaining_parity']}, l0={r['l0']}"
        )


# ══════════════════════════════════════════════════════════════
# Group 2: Stale symbol check
# ══════════════════════════════════════════════════════════════


def test_no_legacy_anchor_symbols(tb):
    """Legacy anchor-era symbols must not exist in the namespace."""
    tb.inject(
        """
_legacy_check = {
    name: name in dir()
    for name in [
        "ANCHOR_CONFIGS",
        "STUDY3_MTTT_BY_ANCHOR",
        "STANDARD_ANCHOR",
        "validate_study3_anchor_overrides",
        "study3_mttt_for_anchor",
    ]
}
"""
    )
    results = tb.ref("_legacy_check")
    for name, exists in results.items():
        assert not exists, f"Legacy symbol '{name}' still exists in notebook namespace"


def test_no_singular_standard_config(tb):
    """Only STANDARD_CONFIGS (plural) should exist, not STANDARD_CONFIG (singular)."""
    tb.inject(
        """
_naming_check = {
    "plural_exists": "STANDARD_CONFIGS" in dir(),
    "has_index_knob": "STANDARD_CONFIG_INDEX" in dir(),
    # STANDARD_CONFIG (singular, non-index) should not exist as a dict/list config object
    "singular_config_exists": (
        "STANDARD_CONFIG" in dir()
        and "STANDARD_CONFIG" != "STANDARD_CONFIG_INDEX"
        and "STANDARD_CONFIG" != "STANDARD_CONFIGS"
        and isinstance(globals().get("STANDARD_CONFIG"), (dict, list))
    ),
}
"""
    )
    result = tb.ref("_naming_check")
    assert result["plural_exists"], "STANDARD_CONFIGS not defined"
    assert result["has_index_knob"], "STANDARD_CONFIG_INDEX not defined"
    assert not result["singular_config_exists"], (
        "STANDARD_CONFIG (singular) still exists as a config object"
    )


# ══════════════════════════════════════════════════════════════
# Group 3: Helper function contracts
# ══════════════════════════════════════════════════════════════


def test_mttf_hours_from_afr_known_value(tb):
    """mttf_hours_from_afr with standard AFR produces expected result."""
    tb.inject(
        """
import numpy as _np
_mttf_result = mttf_hours_from_afr(0.0136)
_mttf_expected = 8760 / (-_np.log1p(-0.0136))
_mttf_close = bool(abs(_mttf_result - _mttf_expected) < 1e-6)
"""
    )
    assert tb.value("_mttf_close"), "mttf_hours_from_afr(0.0136) doesn't match expected"


def test_mttf_hours_from_afr_edge_cases(tb):
    """mttf_hours_from_afr rejects invalid AFR values."""
    tb.inject(
        """
_mttf_errors = {}
for _afr, _label in [(0, "zero"), (1, "one"), (-0.1, "negative"), (1.5, "gt_one")]:
    try:
        mttf_hours_from_afr(_afr)
        _mttf_errors[_label] = False
    except ValueError:
        _mttf_errors[_label] = True
"""
    )
    results = tb.ref("_mttf_errors")
    for label, raised in results.items():
        assert raised, f"mttf_hours_from_afr did not raise ValueError for {label}"


def test_effective_code_byzantine_budget(tb):
    """effective_code_with_byzantine_budget returns correct structure and values."""
    tb.inject(
        """
_budget = effective_code_with_byzantine_budget(10, 20, 0.1)
_budget_check = {
    "has_keys": all(k in _budget for k in ["k", "n", "parity_slots", "beta", "reserve_slots", "n_eff", "remaining_parity", "feasible"]),
    "k": _budget["k"],
    "n": _budget["n"],
    "parity": _budget["parity_slots"],
    "reserve": _budget["reserve_slots"],
    "n_eff": _budget["n_eff"],
    "remaining_parity": _budget["remaining_parity"],
    "feasible": _budget["feasible"],
}
"""
    )
    b = tb.ref("_budget_check")
    assert b["has_keys"], "Budget dict missing expected keys"
    assert b["k"] == 10
    assert b["n"] == 20
    assert b["parity"] == 10  # n - k
    assert b["reserve"] == 2  # ceil(0.1 * 20)
    assert b["n_eff"] == 18  # n - reserve
    assert b["remaining_parity"] == 8  # parity - reserve
    assert b["feasible"] is True


def test_beta_subplots_takes_explicit_param(tb):
    """beta_subplots requires beta_values as first positional arg."""
    tb.inject(
        """
import inspect as _inspect
_bs_sig = _inspect.signature(beta_subplots)
_bs_params = list(_bs_sig.parameters.keys())
_bs_first_param = _bs_params[0] if _bs_params else None
_bs_info = {
    "first_param": _bs_first_param,
    "has_no_default": bool(
        _bs_sig.parameters[_bs_first_param].default is _inspect.Parameter.empty
    ) if _bs_first_param else False,
}
"""
    )
    info = tb.ref("_bs_info")
    assert info["first_param"] == "beta_values", (
        "beta_subplots first param should be 'beta_values'"
    )
    assert info["has_no_default"], (
        "beta_subplots 'beta_values' should have no default (not use globals)"
    )


def test_add_loss_target_line_takes_explicit_param(tb):
    """add_loss_target_line requires target as explicit param with no default."""
    tb.inject(
        """
import inspect as _inspect
_alt_sig = _inspect.signature(add_loss_target_line)
_alt_params = list(_alt_sig.parameters.keys())
_alt_check = {
    "params": _alt_params,
    "target_no_default": (
        "target" in _alt_sig.parameters
        and _alt_sig.parameters["target"].default is _inspect.Parameter.empty
    ),
}
"""
    )
    result = tb.ref("_alt_check")
    assert result["params"] == ["ax", "target"], (
        f"add_loss_target_line params should be ['ax', 'target'], got {result['params']}"
    )
    assert result["target_no_default"], (
        "add_loss_target_line 'target' should have no default"
    )


# ══════════════════════════════════════════════════════════════
# Group 4: Smoke test (slow)
# ══════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_notebook_runs_end_to_end():
    """Execute all cells except expensive MC sims; fail on any error."""
    import json

    nb = json.load(open(NB_PATH))
    total = len(nb["cells"])

    # Find MC cells by content signature (only cell that calls both simulators)
    mc_cells = set()
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        if "simulate_discrete(" in src and "simulate_events(" in src:
            mc_cells.add(i)
            # Also skip the bar chart cell immediately after
            if i + 1 < total:
                mc_cells.add(i + 1)

    cells_to_run = [i for i in range(total) if i not in mc_cells]
    with testbook(NB_PATH, execute=cells_to_run, timeout=300) as tb:
        # If we get here, all cells executed without error.
        tb.inject("_smoke_ok = True")
        assert tb.ref("_smoke_ok")


# ══════════════════════════════════════════════════════════════
# Group 5: Numerical spot-checks
# ══════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def tb_with_model(tb):
    """Extend the config fixture by also executing the CTMC model cell."""
    # Cell 11 defines ctmc_model and model_fail_per_hour
    tb.execute_cell(11)
    return tb


def test_ctmc_model_known_output(tb_with_model):
    """model_fail_per_hour returns a sensible value for a known configuration."""
    tb_with_model.inject(
        """
_mfph = model_fail_per_hour(
    k=10, n=20, l0=1,
    mttt=24, mttf=BASE_MTTF_HOURS, mttr=24, beta=0.0
)
_model_check = {
    "positive": bool(_mfph > 0),
    "finite": bool(float('inf') > _mfph),
    "reasonable": bool(_mfph < 1),  # loss rate < 1/hour is physically sensible
    "value": float(_mfph),
}
"""
    )
    r = tb_with_model.ref("_model_check")
    assert r["positive"], f"Loss rate should be positive, got {r['value']}"
    assert r["finite"], "Loss rate should be finite"
    assert r["reasonable"], f"Loss rate {r['value']} implausibly high (>= 1/hour)"


def test_study1_baseline_meets_target(tb_with_model):
    """At least one (k, n) config achieves the durability target at beta=0."""
    tb_with_model.inject(
        """
import math as _math
_s1_found = False
for _ef in EXPANSION_FACTORS:
    for _l0v in R0_VALUES:
        for _K in range(K_MIN, K_MAX + 1):
            _N = _math.ceil(_K * _ef)
            if _N > N_CEIL:
                continue
            _budget = effective_code_with_byzantine_budget(_K, _N, 0.0)
            if not _budget["feasible"] or _budget["remaining_parity"] < _l0v:
                continue
            _lam = model_fail_per_hour(_K, _N, _l0v, BASELINE_MTTT, BASE_MTTF_HOURS, BASELINE_MTTR, beta=0.0) * 8760
            if _lam < TARGET_LAMBDA_LOSS_YEAR:
                _s1_found = True
                break
        if _s1_found:
            break
    if _s1_found:
        break
_s1_meets_target = bool(_s1_found)
"""
    )
    assert tb_with_model.value("_s1_meets_target"), (
        "No (k, n) config meets the durability target at beta=0 — "
        "Study 1 results would be empty"
    )


def test_audit_bridge_monotonic(tb_with_model):
    """Within a config+beta combo, more touches/day → lower lambda."""
    tb_with_model.inject(
        """
import math as _math
_mono_ok = True
_mono_detail = ""
_bridge_cfg = STANDARD_CONFIGS[0]
_bk, _bn, _bl0 = _bridge_cfg["k"], _bridge_cfg["n"], _bridge_cfg["l0"]
_budget = effective_code_with_byzantine_budget(_bk, _bn, 0.0)
_n_eff = _budget["n_eff"]
_plans = [
    max(1, _math.ceil(_n_eff / 4)),
    max(1, _math.ceil(_n_eff / 2)),
    _n_eff,
]
_lams = []
for _tpd in _plans:
    _mttt_eff = _n_eff / _tpd * 24
    _lam = model_fail_per_hour(_bk, _bn, _bl0, _mttt_eff, BASE_MTTF_HOURS, BASELINE_MTTR, beta=0.0) * 8760
    _lams.append(float(_lam))
# More touches → shorter MTTT → lower lambda
for _j in range(len(_lams) - 1):
    if _lams[_j] < _lams[_j + 1]:
        _mono_ok = False
        _mono_detail = f"lambda[{_j}]={_lams[_j]:.2e} < lambda[{_j+1}]={_lams[_j+1]:.2e}"
_mono_result = {"ok": bool(_mono_ok), "detail": _mono_detail, "lams": _lams}
"""
    )
    r = tb_with_model.ref("_mono_result")
    assert r["ok"], f"Audit bridge not monotonic: {r['detail']} (lambdas={r['lams']})"
