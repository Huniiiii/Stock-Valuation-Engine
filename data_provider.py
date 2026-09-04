"""Financial data retrieval and normalization for the Streamlit application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class CompanyData:
    ticker: str
    company_name: str
    sector: str
    currency: str
    current_price: float
    market_cap: float
    beta: float
    cash: float
    debt: float
    shares_outstanding: float
    pre_tax_cost_of_debt: float
    effective_tax_rate: float
    risk_free_rate: float
    historical: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def demo_company_data() -> CompanyData:
    """Return a self-contained illustrative company for reliable demonstrations."""

    revenue = np.array([12.5, 16.2, 21.4, 29.8, 41.7]) * 1e9
    margins = np.array([0.24, 0.26, 0.25, 0.29, 0.34])
    historical = pd.DataFrame(
        {
            "Revenue": revenue,
            "Revenue Growth": pd.Series(revenue).pct_change().to_numpy(),
            "EBITDA": revenue * margins,
            "EBITDA Margin": margins,
            "Free Cash Flow": np.array([1.8, 2.6, 3.4, 5.3, 8.7]) * 1e9,
        },
        index=[2021, 2022, 2023, 2024, 2025],
    )
    historical.index.name = "Fiscal Year"
    current_price = 400.0
    shares = 500e6
    return CompanyData(
        ticker="NSTC",
        company_name="NorthStar Compute (Illustrative)",
        sector="Semiconductors",
        currency="USD",
        current_price=current_price,
        market_cap=current_price * shares,
        beta=1.25,
        cash=5.5e9,
        debt=3.0e9,
        shares_outstanding=shares,
        pre_tax_cost_of_debt=0.052,
        effective_tax_rate=0.21,
        risk_free_rate=0.0425,
        historical=historical,
        warnings=[
            "Demo Company uses fictional illustrative data so the model remains available when live data is rate-limited."
        ],
    )


def _first_row(frame: pd.DataFrame, names: Iterable[str]) -> pd.Series:
    """Return the first available statement row, or an empty float series."""

    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    for name in names:
        if name in frame.index:
            values = pd.to_numeric(frame.loc[name], errors="coerce")
            if isinstance(values, pd.DataFrame):
                values = values.iloc[0]
            return values.astype(float)
    return pd.Series(index=frame.columns, dtype=float)


def _latest(series: pd.Series, default: float = 0.0) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.iloc[0]) if not values.empty else float(default)


def _safe_info(stock: yf.Ticker) -> dict:
    try:
        return stock.info or {}
    except Exception:
        return {}


def _safe_fast_info(stock: yf.Ticker) -> dict:
    try:
        return dict(stock.fast_info)
    except Exception:
        return {}


def _latest_market_price(stock: yf.Ticker, fast_info: dict, info: dict) -> float:
    try:
        history = stock.history(period="5d", auto_adjust=False)
        close = pd.to_numeric(history.get("Close"), errors="coerce").dropna()
        if not close.empty:
            return float(close.iloc[-1])
    except Exception:
        pass
    return float(fast_info.get("last_price") or info.get("currentPrice") or 0.0)


def _risk_free_rate() -> float:
    """Use the US 10-year Treasury proxy; fall back to 4.25%."""

    try:
        history = yf.Ticker("^TNX").history(period="5d", auto_adjust=False)
        close = pd.to_numeric(history.get("Close"), errors="coerce").dropna()
        if not close.empty:
            return float(close.iloc[-1]) / 100.0
    except Exception:
        pass
    return 0.0425


def fetch_company_data(ticker: str) -> CompanyData:
    """Download and normalize annual financials for a public-company ticker."""

    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Enter a ticker symbol.")

    stock = yf.Ticker(symbol)
    try:
        income = stock.financials
        balance = stock.balance_sheet
        cashflow = stock.cashflow
    except Exception as exc:
        raise ValueError(f"Financial statements could not be downloaded for {symbol}.") from exc

    if income is None or income.empty:
        raise ValueError(
            f"No annual financial statements were returned for {symbol}. "
            "Check the ticker or use Manual Input mode."
        )

    info = _safe_info(stock)
    fast_info = _safe_fast_info(stock)
    warnings: list[str] = []

    revenue = _first_row(income, ["Total Revenue", "Operating Revenue"])
    ebitda = _first_row(income, ["EBITDA", "Normalized EBITDA"])
    ebit = _first_row(income, ["EBIT", "Operating Income"])
    depreciation = _first_row(
        cashflow,
        ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
    )
    if ebitda.dropna().empty and not ebit.dropna().empty:
        ebitda = ebit.add(depreciation.reindex(ebit.index, fill_value=0.0), fill_value=0.0)
        warnings.append("EBITDA was approximated as EBIT plus D&A.")

    free_cash_flow = _first_row(cashflow, ["Free Cash Flow"])
    operating_cash_flow = _first_row(
        cashflow,
        ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    )
    capex = _first_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])
    if free_cash_flow.dropna().empty:
        free_cash_flow = operating_cash_flow.add(capex, fill_value=np.nan)
        warnings.append("Free cash flow was calculated as operating cash flow plus CapEx.")

    all_columns = sorted(
        {column for series in [revenue, ebitda, free_cash_flow] for column in series.index},
        reverse=False,
    )
    historical = pd.DataFrame(index=all_columns)
    historical["Revenue"] = revenue.reindex(all_columns)
    historical["Revenue Growth"] = historical["Revenue"].pct_change()
    historical["EBITDA"] = ebitda.reindex(all_columns)
    historical["EBITDA Margin"] = historical["EBITDA"] / historical["Revenue"]
    historical["Free Cash Flow"] = free_cash_flow.reindex(all_columns)
    historical = historical.dropna(subset=["Revenue"]).tail(5)
    historical.index = [pd.Timestamp(column).year for column in historical.index]
    historical.index.name = "Fiscal Year"

    if historical.empty:
        raise ValueError(f"Revenue history is unavailable for {symbol}.")

    cash = _latest(
        _first_row(
            balance,
            [
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Short Term Investments",
                "Cash And Cash Equivalents",
            ],
        )
    )
    debt = _latest(_first_row(balance, ["Total Debt"]))
    shares = _latest(
        _first_row(balance, ["Ordinary Shares Number", "Share Issued"]),
        default=float(fast_info.get("shares") or info.get("sharesOutstanding") or 0.0),
    )
    current_price = _latest_market_price(stock, fast_info, info)
    market_cap = float(
        fast_info.get("market_cap")
        or info.get("marketCap")
        or (current_price * shares if current_price and shares else 0.0)
    )
    beta = float(info.get("beta") or 1.0)

    interest_expense = abs(
        _latest(
            _first_row(
                income,
                ["Interest Expense", "Interest Expense Non Operating"],
            )
        )
    )
    pre_tax_cost_of_debt = np.clip(interest_expense / debt, 0.0, 0.20) if debt else 0.0

    tax_provision = _latest(_first_row(income, ["Tax Provision"]))
    pretax_income = _latest(_first_row(income, ["Pretax Income"]), default=np.nan)
    if np.isfinite(pretax_income) and pretax_income > 0:
        effective_tax_rate = float(np.clip(tax_provision / pretax_income, 0.0, 0.40))
    else:
        effective_tax_rate = 0.21

    if shares <= 0:
        warnings.append("Shares outstanding were unavailable; please verify the estimate.")
    if info.get("sector") == "Financial Services":
        warnings.append(
            "Traditional unlevered DCF is less suitable for banks and insurers because debt is operational."
        )

    return CompanyData(
        ticker=symbol,
        company_name=str(info.get("longName") or info.get("shortName") or symbol),
        sector=str(info.get("sector") or "Not available"),
        currency=str(fast_info.get("currency") or info.get("currency") or "USD"),
        current_price=current_price,
        market_cap=market_cap,
        beta=beta,
        cash=cash,
        debt=debt,
        shares_outstanding=shares,
        pre_tax_cost_of_debt=float(pre_tax_cost_of_debt),
        effective_tax_rate=effective_tax_rate,
        risk_free_rate=_risk_free_rate(),
        historical=historical,
        warnings=warnings,
    )
