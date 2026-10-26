# Project synopsis - technical draft

HCLTech Career Shaper | Project 25 | Individual project | Academic year 2025-26

**Learner, roll number, college, mentor and submission date:** to be completed by the learner in the original submission template. This draft stores no personal data.

## 1. Problem statement

Learners and virtual portfolio analysts need a safe way to examine how stock prices, order fees, account value and historical risk interact. Raw OHLCV data, especially a short or inconsistent dataset, cannot by itself show reliable P&L or fair strategy results. Portfolio Lab cleans the source, persists virtual orders, and presents transparent analytics without connecting to a broker.

## 2. Proposed solution and approach

A five-page Streamlit application provides a virtual INR portfolio, trade validation, risk analytics, technical signals, a backtest and a next-day direction classifier. SQLite stores stocks, prices, portfolios, transactions and signals. pandas and NumPy clean and analyse the data; yfinance optionally supplies a five-year stock and NIFTY 50 cache; scikit-learn evaluates an ML model using a chronological split. Docker Compose packages the application for a local demonstration.

## 3. Architecture

The level-0 data-flow diagram and system block diagram are in [architecture.md](architecture.md). The original DOCX synopsis template is retained unchanged in `data/`.

## 4. Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Streamlit and Plotly |
| Logic | Python 3.11, pandas, NumPy |
| Database | SQLite |
| Data extension | yfinance cache, eight `.NS` tickers and `^NSEI` |
| ML | scikit-learn logistic regression pipeline |
| Deployment | Docker and Docker Compose |

## 5. Dataset

The supplied `dataset.csv` has **500 rows and 8 columns**: date, ticker, open, high, low, close, volume and daily_return_pct. It has eight NSE ticker symbols and 63 synthetic calendar dates. Cleaning repairs 126 invalid high and 159 invalid low bounds. The separate downloaded cache contains **11,123 validated rows across eight stocks and the NIFTY 50 benchmark**, dated 2021-10-26 through 2026-10-26 in the current report snapshot. The cache may change on future refreshes.

## 6. Key results and metrics

| Measure | Snapshot result |
| --- | --- |
| Cleaning | 500 rows retained; 285 candle-bound repairs across high and low checks |
| TCS annualised risk | Sharpe -0.453; beta vs NIFTY 50 0.821 on 1,235 returns |
| TCS SMA backtest | -23.94% strategy return versus -26.96% buy-and-hold over this sample |
| TCS direction model | 52.74% accuracy versus 53.59% majority baseline on 237 held-out rows |
| Verification | pytest, all six Streamlit views, live health endpoint, Compose configuration |

The ML result is below its simple baseline. None of these historical numbers supports a claim of future trading performance.

## 7. Challenges and resolutions

1. **Invalid OHLC bounds:** vectorised cleaning expands high and low to include open and close, and the report counts repairs.
2. **Short synthetic data:** a separate yfinance cache provides longer histories; the fallback withholds annualised metrics and ML evaluation.
3. **Potential look-ahead bias:** the backtest executes at the next open; ML uses close-known features, a chronological split and a label gap.
4. **Reproducible deployment:** pinned requirements, Compose, a persistent data mount and a health check support clean startup.

## 8. References

1. Supplied HCLTech Project Brief and Dataset Generation Prompt, `data/`.
2. [Streamlit multipage apps](https://docs.streamlit.io/develop/concepts/multipage-apps/pages-directory).
3. [pandas percentage-change documentation](https://pandas.pydata.org/pandas-docs/stable/generated/pandas.DataFrame.pct_change.html).
4. [scikit-learn time-series split documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## 9. Ethical compliance

The application uses virtual money only, has no real brokerage connection and stores no personal information. The learner should review and sign the separate [ethical compliance declaration](ethical_compliance_declaration.md) for submission. This technical draft does not assert consent, authorship or a personal signature.
