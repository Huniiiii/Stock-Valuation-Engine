# EquityLens — Stock Valuation Engine

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tests](https://github.com/Huniiiii/Stock-Valuation-Engine/actions/workflows/tests.yml/badge.svg)](https://github.com/Huniiiii/Stock-Valuation-Engine/actions/workflows/tests.yml)

**EquityLens** is an interactive equity-valuation application that converts public-company financial statements and analyst assumptions into a transparent five-year discounted cash flow model.

The project was built to demonstrate practical corporate-finance modeling, financial-statement analysis, Python engineering, and investment communication in one interview-ready application.

## What it does

- Imports annual financial statements from a public-company ticker
- Calculates historical revenue growth, EBITDA margin, and free cash flow
- Builds WACC using CAPM and market-value capital weights
- Forecasts revenue, EBITDA, NOPAT, CapEx, working-capital investment, and unlevered FCF
- Calculates enterprise value, equity value, implied share price, and upside/downside
- Generates a 5×5 WACC and terminal-growth sensitivity table
- Exports the full valuation to a multi-sheet Excel workbook
- Includes a self-contained fictional demo company and supports manual inputs as reliable fallbacks

## Valuation framework

### Weighted average cost of capital

```text
Cost of Equity = Risk-Free Rate + Beta × Equity Risk Premium
WACC = Equity Weight × Cost of Equity
     + Debt Weight × Pre-Tax Cost of Debt × (1 − Tax Rate)
```

### Unlevered free cash flow

```text
UFCF = EBIT × (1 − Tax Rate) + D&A − CapEx − Change in NWC
```

### Terminal value

```text
Terminal Value = Final-Year UFCF × (1 + g) / (WACC − g)
```

## Project structure

```text
Stock-Valuation-Engine/
├── app.py                       # Streamlit user interface and workbook export
├── data_provider.py             # Market-data download and normalization
├── valuation_engine.py          # Tested WACC, DCF, and sensitivity logic
├── tests/
│   └── test_valuation_engine.py
├── .streamlit/
│   └── config.toml              # App theme
├── requirements.txt
└── requirements-dev.txt
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Run the automated tests:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Deploy on Streamlit Community Cloud

1. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub.
2. Select **Create app** and choose this repository.
3. Set the branch to `main` and the main file path to `app.py`.
4. Click **Deploy**. No API key or Streamlit secret is required.

## Interview walkthrough

1. Open the self-contained demo company, then enter a familiar operating-company ticker such as `AAPL`, `MSFT`, or `NVDA` if live data is available.
2. Explain how the app normalizes financial statements and calculates historical operating metrics.
3. Walk through the CAPM-based WACC build-up.
4. Change revenue growth or EBITDA margin to demonstrate scenario analysis.
5. Use the sensitivity table to discuss valuation range and model risk rather than presenting one price target as certain.

## Important limitations

- Third-party market data can be delayed, incomplete, or classified differently from company filings.
- A traditional unlevered DCF is generally less appropriate for banks and insurers because debt is part of operations.
- The model uses simplified assumptions and is intended for education and portfolio demonstration—not investment advice.
- Source filings should be reviewed before relying on any valuation output.

## Security

This project requires no API key. `.env` files and `.streamlit/secrets.toml` are ignored so credentials cannot be committed accidentally.
