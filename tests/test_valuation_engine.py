import math

import numpy as np

from valuation_engine import (
    CapitalStructure,
    ForecastAssumptions,
    WACCInputs,
    build_dcf,
    build_sensitivity_table,
    calculate_wacc,
    valuation_label,
)


def test_wacc_matches_manual_calculation():
    inputs = WACCInputs(
        market_cap=800,
        debt=200,
        risk_free_rate=0.04,
        beta=1.2,
        equity_risk_premium=0.05,
        pre_tax_cost_of_debt=0.06,
        tax_rate=0.25,
    )
    result = calculate_wacc(inputs)
    expected = 0.8 * (0.04 + 1.2 * 0.05) + 0.2 * 0.06 * (1 - 0.25)
    assert math.isclose(result["wacc"], expected)
    assert math.isclose(result["equity_weight"] + result["debt_weight"], 1.0)


def test_dcf_bridge_and_price_are_internally_consistent():
    assumptions = ForecastAssumptions(
        revenue_growth_start=0.10,
        revenue_growth_end=0.05,
        ebitda_margin_start=0.25,
        ebitda_margin_end=0.27,
        wacc=0.09,
        terminal_growth=0.025,
    )
    capital = CapitalStructure(cash=100, debt=200, shares_outstanding=50, current_price=20)
    forecast, summary = build_dcf(1_000, assumptions, capital)

    assert len(forecast) == 5
    assert (forecast["Unlevered FCF"] > 0).all()
    assert math.isclose(
        summary["enterprise_value"] + capital.cash - capital.debt,
        summary["equity_value"],
    )
    assert math.isclose(
        summary["equity_value"] / capital.shares_outstanding,
        summary["implied_share_price"],
    )


def test_sensitivity_behaves_directionally():
    assumptions = ForecastAssumptions(wacc=0.09, terminal_growth=0.025)
    capital = CapitalStructure(cash=100, debt=200, shares_outstanding=50, current_price=20)
    table = build_sensitivity_table(1_000, assumptions, capital)

    assert table.shape == (5, 5)
    assert table.iloc[0, 2] > table.iloc[-1, 2]
    assert table.iloc[2, -1] > table.iloc[2, 0]
    assert not np.isnan(table.iloc[2, 2])


def test_invalid_terminal_spread_is_rejected():
    assumptions = ForecastAssumptions(wacc=0.03, terminal_growth=0.03)
    capital = CapitalStructure(cash=0, debt=0, shares_outstanding=10, current_price=10)
    try:
        build_dcf(100, assumptions, capital)
    except ValueError as exc:
        assert "WACC" in str(exc)
    else:
        raise AssertionError("Expected a ValueError when WACC is not above terminal growth")


def test_valuation_labels():
    assert valuation_label(0.25)[0] == "Potentially undervalued"
    assert valuation_label(-0.25)[0] == "Potentially overvalued"
    assert valuation_label(0.03)[0] == "Near modeled fair value"

