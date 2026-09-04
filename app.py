"""Streamlit front end for the Stock Valuation Engine."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_provider import CompanyData, demo_company_data, fetch_company_data
from valuation_engine import (
    CapitalStructure,
    ForecastAssumptions,
    WACCInputs,
    build_dcf,
    build_sensitivity_table,
    calculate_wacc,
    valuation_label,
)


st.set_page_config(
    page_title="EquityLens | Stock Valuation Engine",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(15,23,42,.96), rgba(30,41,59,.92));
        border: 1px solid rgba(148,163,184,.20); border-radius: 14px; padding: 16px;
    }
    [data-testid="stMetricLabel"] {color: #94a3b8;}
    .hero {padding: 0.5rem 0 1.2rem 0;}
    .eyebrow {color:#38bdf8; font-weight:700; letter-spacing:.12em; font-size:.78rem;}
    .hero h1 {font-size:2.45rem; margin:.25rem 0;}
    .hero p {color:#94a3b8; font-size:1.05rem; max-width:760px;}
    .valuation-card {border-radius:18px; padding:24px; border:1px solid rgba(148,163,184,.22);
        background:linear-gradient(135deg,rgba(15,23,42,.97),rgba(30,41,59,.9));}
    .small-note {color:#94a3b8; font-size:.84rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_company_data(ticker: str) -> CompanyData:
    return fetch_company_data(ticker)


def money(value: float, currency: str = "USD", decimals: int = 2) -> str:
    if not np.isfinite(value):
        return "N/A"
    symbol = "$" if currency in {"USD", "CAD", "AUD", "NZD"} else f"{currency} "
    return f"{symbol}{value:,.{decimals}f}"


def compact_money(value: float, currency: str = "USD") -> str:
    if not np.isfinite(value):
        return "N/A"
    absolute = abs(value)
    if absolute >= 1e12:
        return f"{currency} {value / 1e12:,.2f}T"
    if absolute >= 1e9:
        return f"{currency} {value / 1e9:,.2f}B"
    if absolute >= 1e6:
        return f"{currency} {value / 1e6:,.1f}M"
    return f"{currency} {value:,.0f}"


def format_table(frame: pd.DataFrame, currency: str) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if "Growth" in column or "Margin" in column or column == "Discount Factor":
            output[column] = output[column].map(lambda value: f"{value:.1%}" if pd.notna(value) else "—")
        elif pd.api.types.is_numeric_dtype(output[column]):
            output[column] = output[column].map(
                lambda value: compact_money(value, currency) if pd.notna(value) else "—"
            )
    return output


def export_workbook(
    company: CompanyData,
    assumptions: ForecastAssumptions,
    wacc_details: dict[str, float],
    forecast: pd.DataFrame,
    summary: dict[str, float],
    sensitivity: pd.DataFrame,
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Metric": list(summary.keys()),
                "Value": list(summary.values()),
            }
        ).to_excel(writer, sheet_name="Valuation Summary", index=False)
        company.historical.to_excel(writer, sheet_name="Historical Financials")
        forecast.to_excel(writer, sheet_name="DCF Forecast")
        sensitivity.to_excel(writer, sheet_name="Sensitivity")
        pd.DataFrame(
            list(asdict(assumptions).items()) + list(wacc_details.items()),
            columns=["Assumption", "Value"],
        ).to_excel(writer, sheet_name="Assumptions", index=False)
    return buffer.getvalue()


def manual_company_data() -> CompanyData:
    st.sidebar.markdown("#### Company inputs")
    company_name = st.sidebar.text_input("Company name", "Sample Company")
    ticker = st.sidebar.text_input("Ticker label", "DEMO").strip().upper() or "DEMO"
    currency = st.sidebar.selectbox("Currency", ["USD", "CAD", "EUR", "GBP"])
    current_price = st.sidebar.number_input("Current share price", min_value=0.01, value=100.0)
    revenue_m = st.sidebar.number_input("Latest revenue (millions)", min_value=1.0, value=10000.0)
    margin = st.sidebar.number_input("Latest EBITDA margin (%)", min_value=-50.0, max_value=90.0, value=25.0)
    fcf_m = st.sidebar.number_input("Latest FCF (millions)", value=1500.0)
    cash_m = st.sidebar.number_input("Cash (millions)", min_value=0.0, value=1000.0)
    debt_m = st.sidebar.number_input("Total debt (millions)", min_value=0.0, value=2000.0)
    shares_m = st.sidebar.number_input("Shares outstanding (millions)", min_value=0.01, value=100.0)
    beta = st.sidebar.number_input("Beta", min_value=0.0, max_value=4.0, value=1.0, step=0.05)

    latest_year = pd.Timestamp.today().year - 1
    historical = pd.DataFrame(
        {
            "Revenue": [revenue_m * 1e6],
            "Revenue Growth": [np.nan],
            "EBITDA": [revenue_m * 1e6 * margin / 100],
            "EBITDA Margin": [margin / 100],
            "Free Cash Flow": [fcf_m * 1e6],
        },
        index=[latest_year],
    )
    historical.index.name = "Fiscal Year"
    shares = shares_m * 1e6
    return CompanyData(
        ticker=ticker,
        company_name=company_name,
        sector="Manual input",
        currency=currency,
        current_price=current_price,
        market_cap=current_price * shares,
        beta=beta,
        cash=cash_m * 1e6,
        debt=debt_m * 1e6,
        shares_outstanding=shares,
        pre_tax_cost_of_debt=0.05,
        effective_tax_rate=0.21,
        risk_free_rate=0.0425,
        historical=historical,
        warnings=["Manual Input mode uses user-provided values rather than live market data."],
    )


st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">EQUITY RESEARCH TOOLKIT</div>
      <h1>EquityLens</h1>
      <p>A transparent stock valuation engine that turns financial statements and
      analyst assumptions into a five-year DCF, WACC build-up, and sensitivity analysis.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.title("Valuation setup")
mode = st.sidebar.radio(
    "Data source",
    ["Demo company", "Live ticker", "Manual input"],
    horizontal=True,
    help="Demo Company is self-contained; Live Ticker requests third-party market data.",
)

if mode == "Demo company":
    company = demo_company_data()
elif mode == "Live ticker":
    ticker = st.sidebar.text_input("Ticker", value="AAPL", help="Examples: AAPL, MSFT, NVDA, SHOP.TO")
    try:
        with st.spinner(f"Loading {ticker.upper()} financial statements…"):
            company = cached_company_data(ticker)
    except Exception as exc:
        st.error(str(exc))
        st.info("Try another ticker or select **Manual input** in the sidebar.")
        st.stop()
else:
    company = manual_company_data()

historical = company.historical.copy()
latest = historical.iloc[-1]
revenue_series = historical["Revenue"].dropna()
if len(revenue_series) >= 2 and revenue_series.iloc[0] > 0:
    years_between = max(len(revenue_series) - 1, 1)
    historical_cagr = (revenue_series.iloc[-1] / revenue_series.iloc[0]) ** (1 / years_between) - 1
else:
    historical_cagr = 0.08
historical_cagr = float(np.clip(historical_cagr, -0.05, 0.25))
latest_margin = float(latest.get("EBITDA Margin", 0.20))
if not np.isfinite(latest_margin):
    latest_margin = 0.20
latest_margin = float(np.clip(latest_margin, -0.20, 0.70))

st.sidebar.markdown("---")
st.sidebar.markdown("#### Market assumptions")
risk_free_rate = st.sidebar.number_input(
    "Risk-free rate (%)",
    min_value=0.0,
    max_value=15.0,
    value=float(company.risk_free_rate * 100),
    step=0.05,
) / 100
equity_risk_premium = st.sidebar.number_input(
    "Equity risk premium (%)", min_value=1.0, max_value=12.0, value=5.0, step=0.1
) / 100
beta = st.sidebar.number_input("Levered beta", min_value=0.0, max_value=4.0, value=float(company.beta), step=0.05)
pre_tax_cost_of_debt = st.sidebar.number_input(
    "Pre-tax cost of debt (%)",
    min_value=0.0,
    max_value=25.0,
    value=float(company.pre_tax_cost_of_debt * 100),
    step=0.1,
) / 100
tax_rate = st.sidebar.number_input(
    "Tax rate (%)", min_value=0.0, max_value=50.0, value=float(company.effective_tax_rate * 100), step=0.5
) / 100

try:
    wacc_details = calculate_wacc(
        WACCInputs(
            market_cap=company.market_cap,
            debt=company.debt,
            risk_free_rate=risk_free_rate,
            beta=beta,
            equity_risk_premium=equity_risk_premium,
            pre_tax_cost_of_debt=pre_tax_cost_of_debt,
            tax_rate=tax_rate,
        )
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.sidebar.markdown("---")
st.sidebar.markdown("#### Operating forecast")
growth_start = st.sidebar.number_input(
    "Year 1 revenue growth (%)", min_value=-50.0, max_value=100.0, value=round(historical_cagr * 100, 1), step=0.5
) / 100
growth_end = st.sidebar.number_input(
    "Year 5 revenue growth (%)", min_value=-20.0, max_value=50.0, value=4.0, step=0.5
) / 100
margin_start = st.sidebar.number_input(
    "Year 1 EBITDA margin (%)", min_value=-50.0, max_value=90.0, value=round(latest_margin * 100, 1), step=0.5
) / 100
margin_end = st.sidebar.number_input(
    "Year 5 EBITDA margin (%)", min_value=-50.0, max_value=90.0, value=round(latest_margin * 100, 1), step=0.5
) / 100
da_pct = st.sidebar.number_input("D&A as % of revenue", min_value=0.0, max_value=30.0, value=3.0, step=0.5) / 100
capex_pct = st.sidebar.number_input("CapEx as % of revenue", min_value=0.0, max_value=50.0, value=4.0, step=0.5) / 100
nwc_pct = st.sidebar.number_input(
    "NWC investment as % of incremental revenue", min_value=0.0, max_value=50.0, value=2.0, step=0.5
) / 100
terminal_growth = st.sidebar.number_input(
    "Terminal growth (%)", min_value=-2.0, max_value=8.0, value=2.5, step=0.1
) / 100

assumptions = ForecastAssumptions(
    revenue_growth_start=growth_start,
    revenue_growth_end=growth_end,
    ebitda_margin_start=margin_start,
    ebitda_margin_end=margin_end,
    da_as_revenue=da_pct,
    capex_as_revenue=capex_pct,
    nwc_as_incremental_revenue=nwc_pct,
    tax_rate=tax_rate,
    wacc=wacc_details["wacc"],
    terminal_growth=terminal_growth,
)
capital_structure = CapitalStructure(
    cash=company.cash,
    debt=company.debt,
    shares_outstanding=company.shares_outstanding,
    current_price=company.current_price,
)

try:
    forecast, summary = build_dcf(float(latest["Revenue"]), assumptions, capital_structure)
    sensitivity = build_sensitivity_table(float(latest["Revenue"]), assumptions, capital_structure)
except ValueError as exc:
    st.error(str(exc))
    st.info("Adjust the assumptions in the sidebar. In particular, WACC must exceed terminal growth.")
    st.stop()

for warning in company.warnings:
    st.warning(warning, icon="⚠️")

st.subheader(f"{company.company_name}  ·  {company.ticker}")
st.caption(f"{company.sector}  |  Reporting currency: {company.currency}  |  Annual financial statements")

metric_columns = st.columns(5)
metric_columns[0].metric("Current Price", money(company.current_price, company.currency))
metric_columns[1].metric("Implied Value", money(summary["implied_share_price"], company.currency))
metric_columns[2].metric("Upside / Downside", f"{summary['upside_downside']:+.1%}")
metric_columns[3].metric("WACC", f"{assumptions.wacc:.1%}")
metric_columns[4].metric("Enterprise Value", compact_money(summary["enterprise_value"], company.currency))

overview_tab, historical_tab, dcf_tab, sensitivity_tab = st.tabs(
    ["Valuation Summary", "Historical Performance", "DCF Model", "Sensitivity Analysis"]
)

with overview_tab:
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        label, color = valuation_label(summary["upside_downside"])
        direction = "upside" if summary["upside_downside"] >= 0 else "downside"
        st.markdown(
            f"""
            <div class="valuation-card">
              <div class="eyebrow" style="color:{color}">{label.upper()}</div>
              <h2 style="margin:.35rem 0">{money(summary['implied_share_price'], company.currency)}</h2>
              <p>The base-case DCF implies <strong>{abs(summary['upside_downside']):.1%} {direction}</strong>
              versus the current price of {money(company.current_price, company.currency)}.</p>
              <p class="small-note">This is a scenario-based model, not an investment recommendation.
              Change the operating and market assumptions in the sidebar to test the thesis.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("#### Valuation bridge")
        bridge = pd.DataFrame(
            {
                "Component": ["PV of forecast FCF", "PV of terminal value", "Cash", "Debt", "Equity value"],
                "Value": [
                    summary["pv_forecast_fcf"],
                    summary["pv_terminal_value"],
                    summary["cash"],
                    -summary["debt"],
                    summary["equity_value"],
                ],
            }
        )
        fig_bridge = go.Figure(
            go.Waterfall(
                x=bridge["Component"],
                y=bridge["Value"],
                measure=["relative", "relative", "relative", "relative", "total"],
                connector={"line": {"color": "#64748b"}},
                increasing={"marker": {"color": "#10b981"}},
                decreasing={"marker": {"color": "#ef4444"}},
                totals={"marker": {"color": "#38bdf8"}},
            )
        )
        fig_bridge.update_layout(yaxis_title=company.currency, height=390, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_bridge, width="stretch")
    with right:
        st.markdown("#### Base-case assumptions")
        assumption_table = pd.DataFrame(
            {
                "Assumption": [
                    "Year 1 revenue growth", "Year 5 revenue growth", "Year 1 EBITDA margin",
                    "Year 5 EBITDA margin", "Tax rate", "WACC", "Terminal growth",
                ],
                "Value": [
                    growth_start, growth_end, margin_start, margin_end, tax_rate,
                    assumptions.wacc, terminal_growth,
                ],
            }
        )
        assumption_table["Value"] = assumption_table["Value"].map(lambda value: f"{value:.1%}")
        st.dataframe(assumption_table, hide_index=True, width="stretch")
        st.markdown("#### Key model observations")
        st.write(
            f"- Terminal value contributes **{summary['terminal_value_share']:.1%}** of enterprise value."
        )
        st.write(
            f"- Revenue growth fades from **{growth_start:.1%}** to **{growth_end:.1%}** over five years."
        )
        margin_change = margin_end - margin_start
        margin_text = "expands" if margin_change >= 0 else "contracts"
        st.write(
            f"- EBITDA margin {margin_text} by **{abs(margin_change):.1%}** to **{margin_end:.1%}**."
        )

with historical_tab:
    if len(historical) == 1:
        st.info("Manual Input mode contains one historical period. Use Live Ticker mode for a multi-year trend.")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        fig_financials = go.Figure()
        fig_financials.add_bar(
            x=historical.index.astype(str), y=historical["Revenue"], name="Revenue", marker_color="#38bdf8"
        )
        fig_financials.add_bar(
            x=historical.index.astype(str), y=historical["Free Cash Flow"], name="Free Cash Flow", marker_color="#10b981"
        )
        fig_financials.update_layout(
            title="Revenue and Free Cash Flow", barmode="group", yaxis_title=company.currency, height=420
        )
        st.plotly_chart(fig_financials, width="stretch")
    with chart_right:
        fig_margin = go.Figure()
        fig_margin.add_scatter(
            x=historical.index.astype(str),
            y=historical["EBITDA Margin"],
            mode="lines+markers",
            name="EBITDA Margin",
            line=dict(color="#f59e0b", width=3),
        )
        fig_margin.update_layout(
            title="EBITDA Margin", yaxis_tickformat=".1%", yaxis_title="Margin", height=420
        )
        st.plotly_chart(fig_margin, width="stretch")
    st.markdown("#### Normalized annual financials")
    st.dataframe(format_table(historical, company.currency), width="stretch")

with dcf_tab:
    wacc_col, forecast_col = st.columns([0.36, 0.64], gap="large")
    with wacc_col:
        st.markdown("#### WACC build-up")
        wacc_table = pd.DataFrame(
            {
                "Component": [
                    "Risk-free rate", "Beta", "Equity risk premium", "Cost of equity",
                    "Pre-tax cost of debt", "After-tax cost of debt", "Equity weight", "Debt weight", "WACC",
                ],
                "Value": [
                    risk_free_rate, beta, equity_risk_premium, wacc_details["cost_of_equity"],
                    pre_tax_cost_of_debt, wacc_details["after_tax_cost_of_debt"],
                    wacc_details["equity_weight"], wacc_details["debt_weight"], wacc_details["wacc"],
                ],
            }
        )
        wacc_table["Value"] = [
            f"{value:.2f}" if component == "Beta" else f"{value:.1%}"
            for component, value in zip(wacc_table["Component"], wacc_table["Value"])
        ]
        st.dataframe(wacc_table, hide_index=True, width="stretch")
        st.latex(r"WACC = w_E(R_f + \beta \times ERP) + w_D R_D(1-T)")
        st.caption("Market-value capital weights are used. All assumptions can be edited in the sidebar.")
    with forecast_col:
        st.markdown("#### Five-year unlevered FCF forecast")
        fig_fcf = go.Figure()
        fig_fcf.add_bar(x=forecast.index, y=forecast["Unlevered FCF"], marker_color="#10b981", name="UFCF")
        fig_fcf.add_scatter(
            x=forecast.index,
            y=forecast["Revenue"],
            mode="lines+markers",
            line=dict(color="#38bdf8", width=3),
            name="Revenue",
        )
        fig_fcf.update_layout(yaxis_title=company.currency, height=360, legend_orientation="h")
        st.plotly_chart(fig_fcf, width="stretch")
    st.dataframe(format_table(forecast, company.currency), width="stretch")
    st.latex(r"UFCF = EBIT(1-T) + D\&A - CapEx - \Delta NWC")

with sensitivity_tab:
    st.markdown("#### Implied share price sensitivity")
    st.caption("Rows vary WACC; columns vary the perpetual terminal growth rate.")
    styled_sensitivity = sensitivity.style.format("{:.2f}").background_gradient(cmap="RdYlGn", axis=None)
    st.dataframe(styled_sensitivity, width="stretch")
    st.markdown("#### Interpretation")
    st.write(
        "A lower discount rate or higher terminal growth assumption increases modeled value. "
        "Use this table to show the valuation range instead of relying on one precise price target."
    )
    workbook = export_workbook(company, assumptions, wacc_details, forecast, summary, sensitivity)
    st.download_button(
        "Download valuation workbook",
        data=workbook,
        file_name=f"{company.ticker}_valuation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

st.markdown("---")
st.caption(
    "Data provided through Yahoo Finance via yfinance and may be delayed or incomplete. "
    "This educational tool is not investment advice. Always verify source filings before making decisions."
)
