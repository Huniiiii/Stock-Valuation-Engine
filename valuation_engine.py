"""Core financial-modeling functions for the Stock Valuation Engine.

The functions in this module are deliberately independent from Streamlit so the
valuation logic can be tested, reused in notebooks, or connected to a different
front end later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastAssumptions:
    """User-controlled assumptions used in the five-year DCF."""

    forecast_years: int = 5
    revenue_growth_start: float = 0.08
    revenue_growth_end: float = 0.04
    ebitda_margin_start: float = 0.25
    ebitda_margin_end: float = 0.27
    da_as_revenue: float = 0.03
    capex_as_revenue: float = 0.04
    nwc_as_incremental_revenue: float = 0.02
    tax_rate: float = 0.21
    wacc: float = 0.09
    terminal_growth: float = 0.025


@dataclass(frozen=True)
class CapitalStructure:
    """Balance-sheet and market inputs required to bridge EV to equity value."""

    cash: float
    debt: float
    shares_outstanding: float
    current_price: float


@dataclass(frozen=True)
class WACCInputs:
    """Inputs to the capital asset pricing model and after-tax cost of debt."""

    market_cap: float
    debt: float
    risk_free_rate: float
    beta: float
    equity_risk_premium: float
    pre_tax_cost_of_debt: float
    tax_rate: float


def calculate_wacc(inputs: WACCInputs) -> dict[str, float]:
    """Calculate WACC and return its components.

    All rate inputs use decimals (for example, 0.045 means 4.5%). If a company
    has no debt, its WACC is equal to its CAPM-derived cost of equity.
    """

    equity = max(float(inputs.market_cap), 0.0)
    debt = max(float(inputs.debt), 0.0)
    total_capital = equity + debt
    if total_capital <= 0:
        raise ValueError("Market capitalization plus debt must be positive.")

    cost_of_equity = inputs.risk_free_rate + inputs.beta * inputs.equity_risk_premium
    after_tax_cost_of_debt = inputs.pre_tax_cost_of_debt * (1.0 - inputs.tax_rate)
    equity_weight = equity / total_capital
    debt_weight = debt / total_capital
    wacc = equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt

    return {
        "cost_of_equity": cost_of_equity,
        "after_tax_cost_of_debt": after_tax_cost_of_debt,
        "equity_weight": equity_weight,
        "debt_weight": debt_weight,
        "wacc": wacc,
    }


def build_dcf(
    base_revenue: float,
    assumptions: ForecastAssumptions,
    capital_structure: CapitalStructure,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build an unlevered five-year DCF using a perpetual-growth terminal value."""

    if base_revenue <= 0:
        raise ValueError("Base revenue must be positive.")
    if assumptions.forecast_years < 1:
        raise ValueError("Forecast years must be at least one.")
    if assumptions.wacc <= assumptions.terminal_growth:
        raise ValueError("WACC must be greater than the terminal growth rate.")
    if capital_structure.shares_outstanding <= 0:
        raise ValueError("Shares outstanding must be positive.")

    years = np.arange(1, assumptions.forecast_years + 1)
    growth_rates = np.linspace(
        assumptions.revenue_growth_start,
        assumptions.revenue_growth_end,
        assumptions.forecast_years,
    )
    margins = np.linspace(
        assumptions.ebitda_margin_start,
        assumptions.ebitda_margin_end,
        assumptions.forecast_years,
    )

    revenues: list[float] = []
    previous_revenue = float(base_revenue)
    for growth in growth_rates:
        revenue = previous_revenue * (1.0 + growth)
        revenues.append(revenue)
        previous_revenue = revenue

    revenue_array = np.asarray(revenues)
    prior_revenues = np.r_[base_revenue, revenue_array[:-1]]
    ebitda = revenue_array * margins
    depreciation = revenue_array * assumptions.da_as_revenue
    ebit = ebitda - depreciation
    nopat = ebit * (1.0 - assumptions.tax_rate)
    capex = revenue_array * assumptions.capex_as_revenue
    change_nwc = np.maximum(revenue_array - prior_revenues, 0.0) * assumptions.nwc_as_incremental_revenue
    unlevered_fcf = nopat + depreciation - capex - change_nwc
    discount_factors = 1.0 / np.power(1.0 + assumptions.wacc, years)
    pv_fcf = unlevered_fcf * discount_factors

    terminal_value = (
        unlevered_fcf[-1]
        * (1.0 + assumptions.terminal_growth)
        / (assumptions.wacc - assumptions.terminal_growth)
    )
    pv_terminal_value = terminal_value * discount_factors[-1]
    enterprise_value = float(pv_fcf.sum() + pv_terminal_value)
    equity_value = enterprise_value + capital_structure.cash - capital_structure.debt
    implied_share_price = equity_value / capital_structure.shares_outstanding
    upside_downside = (
        implied_share_price / capital_structure.current_price - 1.0
        if capital_structure.current_price > 0
        else np.nan
    )

    forecast = pd.DataFrame(
        {
            "Year": [f"Year {year}" for year in years],
            "Revenue Growth": growth_rates,
            "Revenue": revenue_array,
            "EBITDA Margin": margins,
            "EBITDA": ebitda,
            "D&A": depreciation,
            "EBIT": ebit,
            "NOPAT": nopat,
            "CapEx": capex,
            "Change in NWC": change_nwc,
            "Unlevered FCF": unlevered_fcf,
            "Discount Factor": discount_factors,
            "PV of FCF": pv_fcf,
        }
    ).set_index("Year")

    summary = {
        "pv_forecast_fcf": float(pv_fcf.sum()),
        "terminal_value": float(terminal_value),
        "pv_terminal_value": float(pv_terminal_value),
        "enterprise_value": enterprise_value,
        "cash": float(capital_structure.cash),
        "debt": float(capital_structure.debt),
        "equity_value": float(equity_value),
        "shares_outstanding": float(capital_structure.shares_outstanding),
        "implied_share_price": float(implied_share_price),
        "current_price": float(capital_structure.current_price),
        "upside_downside": float(upside_downside),
        "terminal_value_share": float(pv_terminal_value / enterprise_value)
        if enterprise_value
        else np.nan,
    }
    return forecast, summary


def build_sensitivity_table(
    base_revenue: float,
    assumptions: ForecastAssumptions,
    capital_structure: CapitalStructure,
    wacc_step: float = 0.01,
    growth_step: float = 0.005,
) -> pd.DataFrame:
    """Calculate implied share prices across WACC and terminal-growth cases."""

    wacc_values = assumptions.wacc + np.arange(-2, 3) * wacc_step
    growth_values = assumptions.terminal_growth + np.arange(-2, 3) * growth_step
    table = pd.DataFrame(
        index=[f"{rate:.1%}" for rate in wacc_values],
        columns=[f"{rate:.1%}" for rate in growth_values],
        dtype=float,
    )
    table.index.name = "WACC / Terminal Growth"

    for wacc in wacc_values:
        for growth in growth_values:
            if wacc <= growth:
                value = np.nan
            else:
                case = ForecastAssumptions(
                    **{
                        **asdict(assumptions),
                        "wacc": float(wacc),
                        "terminal_growth": float(growth),
                    }
                )
                _, summary = build_dcf(base_revenue, case, capital_structure)
                value = summary["implied_share_price"]
            table.loc[f"{wacc:.1%}", f"{growth:.1%}"] = value
    return table


def valuation_label(upside_downside: float) -> tuple[str, str]:
    """Return a neutral valuation label and display color."""

    if not np.isfinite(upside_downside):
        return "Price comparison unavailable", "#94a3b8"
    if upside_downside >= 0.10:
        return "Potentially undervalued", "#10b981"
    if upside_downside <= -0.10:
        return "Potentially overvalued", "#ef4444"
    return "Near modeled fair value", "#f59e0b"

