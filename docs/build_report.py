"""Build the reproducible academic PDF report from the current validated dataset.

Requires reportlab and matplotlib in the local Python environment.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import CLEANED_CSV, QUALITY_REPORT  # noqa: E402
from src.db import price_history  # noqa: E402
from src.ml_model import train_direction_model  # noqa: E402
from src.risk import calculate_risk, close_and_returns  # noqa: E402
from src.signals import backtest_signals, generate_signals  # noqa: E402

OUT = ROOT / "output" / "pdf" / "portfolio_lab_project_report.pdf"
TMP = ROOT / "tmp" / "pdfs"
INK = colors.HexColor("#172236")
TEAL = colors.HexColor("#0E9385")
MUTED = colors.HexColor("#59677B")
PALE = colors.HexColor("#E8F6F3")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=25, leading=31, textColor=INK, spaceAfter=17),
        "h1": ParagraphStyle("ReportH1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=17, leading=22, textColor=TEAL, spaceAfter=12),
        "h2": ParagraphStyle("ReportH2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12.5, leading=17, textColor=INK, spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("ReportBody", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=10.5, leading=16, textColor=INK, spaceAfter=9),
        "small": ParagraphStyle("ReportSmall", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=9, leading=13, textColor=MUTED, spaceAfter=7),
        "cover": ParagraphStyle("ReportCover", parent=base["Normal"], fontName="Helvetica",
                                fontSize=11, leading=17, textColor=MUTED, alignment=TA_CENTER),
    }


def _table(rows: list[list[str]], widths: list[float]) -> Table:
    factor = min(1.0, 174 * mm / sum(widths))
    widths = [width * factor for width in widths]
    header_style = ParagraphStyle("TableHeader", fontName="Helvetica-Bold", fontSize=9,
                                  leading=12, textColor=colors.white)
    body_style = ParagraphStyle("TableBody", fontName="Helvetica", fontSize=9,
                                leading=12, textColor=INK)
    wrapped = [[Paragraph(str(value), header_style if index == 0 else body_style)
                for value in row] for index, row in enumerate(rows)]
    result = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#C9D6DC")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return result


def _plot_assets(supplied: pd.DataFrame, active: pd.DataFrame) -> dict[str, Path]:
    TMP.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    paths: dict[str, Path] = {}

    fig, ax = plt.subplots(figsize=(8.5, 3.3), dpi=160)
    for ticker, color in (("TCS", "#0E9385"), ("RELIANCE", "#5965D7"), ("INFY", "#E0A923")):
        group = active.loc[active["ticker"] == ticker]
        ax.plot(group["date"], group["close"], label=ticker, lw=1.3, color=color)
    ax.set(title="Downloaded closing-price trends", ylabel="INR per share")
    ax.legend(ncol=3, frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    paths["price"] = TMP / "price_trends.png"
    fig.savefig(paths["price"])
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 3.2), dpi=160)
    ax.hist(supplied["daily_return_pct"].dropna(), bins=45, color="#0E9385", edgecolor="white")
    ax.axvline(0, color="#B55252", lw=1)
    ax.set(title="Cleaned supplied daily-return distribution", xlabel="Close-to-close return (%)", ylabel="Observations")
    fig.tight_layout()
    paths["returns"] = TMP / "return_distribution.png"
    fig.savefig(paths["returns"])
    plt.close(fig)

    pivot = supplied.pivot(index="date", columns="ticker", values="daily_return_pct")
    corr = pivot.corr()
    fig, ax = plt.subplots(figsize=(7.2, 4.5), dpi=160)
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu")
    ax.set_xticks(range(len(corr)), corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(corr)), corr.index)
    ax.set_title("Supplied return correlation")
    fig.colorbar(im, ax=ax, fraction=.046, pad=.04)
    fig.tight_layout()
    paths["corr"] = TMP / "correlation.png"
    fig.savefig(paths["corr"])
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 3.1), dpi=160)
    groups = [supplied.loc[supplied["ticker"] == ticker, "volume"].to_numpy() for ticker in sorted(supplied["ticker"].unique())]
    ax.boxplot(groups, tick_labels=sorted(supplied["ticker"].unique()), showfliers=False)
    ax.set(title="Supplied volume by ticker", ylabel="Shares / units")
    ax.tick_params(axis="x", labelrotation=35)
    fig.tight_layout()
    paths["volume"] = TMP / "volume.png"
    fig.savefig(paths["volume"])
    plt.close(fig)
    return paths


def _analysis_plots(returns: pd.DataFrame, backtest: dict) -> dict[str, Path]:
    """Save architecture and evaluation graphics for the report."""
    paths: dict[str, Path] = {}
    fig, ax = plt.subplots(figsize=(9, 3.0), dpi=160)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")
    blocks = [
        (0.2, 1.75, "Synthetic CSV"), (0.2, .35, "yfinance cache"),
        (2.5, 1.05, "Cleaning\n+ provenance"), (4.75, 1.05, "SQLite"),
        (6.5, 1.05, "Analytics"), (8.3, 1.05, "Streamlit UI"),
    ]
    for x, y, label in blocks:
        box = FancyBboxPatch((x, y), 1.45, .75, boxstyle="round,pad=0.07",
                             facecolor="#E8F6F3", edgecolor="#0E9385", linewidth=1.4)
        ax.add_patch(box)
        ax.text(x + .725, y + .375, label, va="center", ha="center", fontsize=9)
    arrows = [((1.7, 2.1), (2.45, 1.55)), ((1.7, .7), (2.45, 1.35)),
              ((4.0, 1.45), (4.7, 1.45)), ((6.2, 1.45), (6.45, 1.45)),
              ((8.0, 1.45), (8.25, 1.45))]
    for start, end in arrows:
        ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "color": "#59677B", "lw": 1.5})
    fig.tight_layout()
    paths["architecture"] = TMP / "architecture.png"
    fig.savefig(paths["architecture"])
    plt.close(fig)

    wealth = (1 + returns["TCS"].dropna()).cumprod()
    drawdown = wealth / wealth.cummax() - 1
    fig, ax = plt.subplots(figsize=(8.5, 3.0), dpi=160)
    ax.plot(drawdown.index, drawdown * 100, color="#B55252", lw=1.4)
    ax.fill_between(drawdown.index, drawdown * 100, 0, color="#B55252", alpha=.13)
    ax.set(title="TCS historical drawdown", ylabel="Percent from previous peak")
    fig.autofmt_xdate()
    fig.tight_layout()
    paths["drawdown"] = TMP / "drawdown.png"
    fig.savefig(paths["drawdown"])
    plt.close(fig)

    equity = backtest["equity"]
    fig, ax = plt.subplots(figsize=(8.5, 3.0), dpi=160)
    ax.plot(equity["date"], equity["strategy"], label="SMA strategy", color="#0E9385", lw=1.4)
    ax.plot(equity["date"], equity["buy_hold"], label="Buy-and-hold", color="#5965D7", lw=1.4)
    ax.set(title="TCS next-open backtest", ylabel="Virtual equity (INR)")
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    paths["equity"] = TMP / "backtest_equity.png"
    fig.savefig(paths["equity"])
    plt.close(fig)
    return paths


def _footer(canvas, document) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#DDE5E9"))
    canvas.line(18 * mm, 18 * mm, width - 18 * mm, 18 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 13 * mm, "Portfolio Lab | HCLTech Career Shaper Project 25")
    canvas.drawRightString(width - 18 * mm, 13 * mm, f"Page {document.page}")
    canvas.restoreState()


def build() -> Path:
    """Render a nine-section PDF with live validation results and source provenance."""
    import json

    OUT.parent.mkdir(parents=True, exist_ok=True)
    supplied = pd.read_csv(CLEANED_CSV, parse_dates=["date"])
    active = price_history()
    report = json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))
    close, returns = close_and_returns()
    ticker = "TCS"
    risk = calculate_risk(returns[ticker], returns["^NSEI"] if "^NSEI" in returns else None)
    backtest = backtest_signals(generate_signals(price_history(ticker)))
    model = train_direction_model(price_history(ticker))
    plots = _plot_assets(supplied, active)
    plots.update(_analysis_plots(returns, backtest))
    s = _styles()
    story = []

    def p(text: str, style: str = "body") -> None:
        story.append(Paragraph(text, s[style]))

    def heading(text: str) -> None:
        p(text, "h1")

    def sub(text: str) -> None:
        p(text, "h2")

    def next_page() -> None:
        story.append(PageBreak())

    # 1. Cover and abstract
    story.append(Spacer(1, 40 * mm))
    p("Advanced Stock Trading and Portfolio Management Application", "title")
    p("HCLTech Career Shaper | Project 25 | Individual academic project", "cover")
    p(f"Validated dataset snapshot: {active['date'].min().date()} to {active['date'].max().date()} | Report generated: {date.today()}", "cover")
    story.append(Spacer(1, 18 * mm))
    heading("Abstract")
    p("Portfolio Lab is a working virtual trading and analysis application for eight NSE stocks. It integrates an auditable SQLite trade ledger, a cleaning pipeline, cached market history, portfolio P&amp;L, risk measures, technical signals, a next-open backtest and a time-ordered classification model. The interface is a five-page Streamlit application with CSV exports and a consistent simulation warning.")
    p(f"The supplied source has {report['input_rows']} synthetic rows. Cleaning repaired {report['high_bounds_fixed']} high and {report['low_bounds_fixed']} low bounds. The active downloaded cache contains {report['active_rows']:,} validated stock and benchmark rows. The historical model evaluation is reported alongside a majority-class baseline and is not represented as investment performance.")
    p("Simulation only. NOT investment advice. Virtual money, no real brokerage connection.", "small")
    next_page()

    # 2. Problem and objectives
    heading("1. Problem statement and objectives")
    p("A learner or portfolio analyst needs a safe place to explore how price data, trade accounting, risk and strategy testing fit together. A raw OHLCV table cannot directly answer how much virtual cash is left after fees, how a sale changes realised profit, or whether a trading signal would have survived realistic order timing. The project solves these questions with reproducible calculations and a local database, without placing real orders.")
    sub("Measurable objectives")
    story.append(_table([
        ["Objective", "Acceptance evidence"],
        ["Clean the supplied data", "500 rows preserved; invalid candle bounds repaired"],
        ["Maintain a virtual portfolio", "Atomic orders, weighted average cost and cash/share guards"],
        ["Quantify risk", "Six historical measures and NIFTY 50 benchmark where available"],
        ["Evaluate signals honestly", "Next-open fills, fees and buy-and-hold comparison"],
        ["Demonstrate ML discipline", "Chronological holdout, label gap, baseline and confusion matrix"],
        ["Deploy reproducibly", "Pinned dependencies, Docker Compose and a health endpoint"],
    ], [62 * mm, 121 * mm]))
    story.append(Spacer(1, 5 * mm))
    sub("Project boundaries")
    p("The application uses virtual money only. It has no broker integration, real-money execution, authentication or personal-data collection. Cached yfinance prices are historical observations rather than live quotes. The app displays a simulation disclaimer on every page. Academic results are descriptive and do not justify a recommendation to trade.")
    sub("How the five views answer the problem")
    p("Dashboard answers what the account is worth and why it changed. Trade provides an auditable cash-and-share ledger. Risk turns a price series into definitions that can be compared with the NIFTY 50 benchmark. Signals separates a visual indicator from its next-open execution rule. Data Explorer exposes the rows and quality decisions behind all other views. The same SQLite database underlies each page, so state is consistent across navigation and restarts.")
    next_page()

    # 3. Dataset and cleaning
    heading("2. Data provenance and quality")
    p("The original `dataset.csv` has eight ticker symbols and columns for date, OHLC prices, volume and a provided daily return. The dates cover 63 consecutive calendar days in early 2024, so weekend rows reveal its synthetic nature. The original files were preserved. The pipeline writes `cleaned_dataset.csv`, recalculates returns by ticker and records all changes in `quality_report.json`.")
    story.append(_table([
        ["Quality check", "Observed / action"],
        ["Rows / duplicate keys", f"{report['input_rows']} / {report['duplicate_keys_dropped']}"],
        ["Invalid high bounds", f"{report['high_bounds_fixed']} repaired using max(high, open, close)"],
        ["Invalid low bounds", f"{report['low_bounds_fixed']} repaired using min(low, open, close)"],
        ["Weekend rows", f"{report['weekend_rows']} retained and labelled synthetic"],
        ["Invalid rows dropped", str(report['invalid_rows_dropped'])],
        ["Active history", f"{report['active_rows']:,} rows from {report['active_source']}"],
    ], [58 * mm, 125 * mm]))
    story.append(Spacer(1, 5 * mm))
    p("When available, yfinance supplies five years of `.NS` history for the eight stocks and `^NSEI` for the benchmark. Activation requires at least 252 rows for each stock and for NIFTY 50. The real cache is kept separate from the synthetic CSV. If download or completeness checks fail, the supplied data remains a functional fallback and annualised measures and ML are withheld.")
    p("After cleaning, each ticker's first close-to-close return is undefined. Volume must be nonnegative and OHLC values positive. SQLite also checks candle order and uniqueness of `(date, ticker)`.")
    p("The cleaning function is vectorised with pandas. It parses dates, coerces numeric fields, drops invalid identifiers or nonpositive prices, deduplicates date-ticker keys, expands candle bounds to include open and close, and recomputes returns after sorting by ticker and date. The quality report counts these actions, making repairs observable rather than silently altering the source. No synthetic row is appended to a downloaded price series.")
    next_page()

    # 4. EDA price and return plots
    heading("3. Exploratory analysis: prices and returns")
    p("Price levels differ substantially by company and can shift over time; direct comparisons of levels are therefore descriptive rather than risk adjusted. The first figure shows three stock close series from the active downloaded cache. The second displays the recomputed returns of the supplied synthetic data. Its short period and artificial calendar mean should not be interpreted as a market distribution.")
    story.append(Image(str(plots["price"]), width=170 * mm, height=69 * mm))
    story.append(Spacer(1, 4 * mm))
    story.append(Image(str(plots["returns"]), width=170 * mm, height=66 * mm))
    p("The executable notebook contains these views plus a correlation heatmap and a volume comparison. The source separation is deliberate: repaired supplied data supports the academic data-cleaning exercise, while the longer real cache supports annualised calculations.", "small")
    next_page()

    # 5. EDA correlation and volume
    heading("4. Exploratory analysis: co-movement and volume")
    p("Pairwise correlations use observations shared by two ticker return series. They describe this sample only; they can change with the date window, missingness and market regime. Volume distributions show that the supplied dataset has different activity scales across tickers, which motivates per-ticker inspection instead of treating all volumes as directly comparable.")
    story.append(Image(str(plots["corr"]), width=140 * mm, height=88 * mm))
    story.append(Spacer(1, 4 * mm))
    story.append(Image(str(plots["volume"]), width=170 * mm, height=65 * mm))
    next_page()

    # 6. Architecture
    heading("5. Architecture and persistence")
    p("Streamlit pages call independent Python modules. The data pipeline validates sources and writes SQLite prices. The portfolio module owns orders and valuation; risk and signals read the same prices; the ML module builds features from past and current observations. `docs/architecture.md` includes the level-0 data-flow diagram and the block diagram in Mermaid form.")
    story.append(_table([
        ["Layer", "Responsibility"],
        ["Streamlit UI", "Dashboard, Trade, Risk, Signals, Data Explorer; shared theme and warning"],
        ["Pipeline", "CSV cleaning, yfinance cache, provenance and quality report"],
        ["SQLite", "Stocks, prices, portfolio, transactions, signals and holdings view"],
        ["Analytics", "P&L, risk, technical indicators, backtest and classifier"],
        ["Deployment", "Python 3.11 slim image, non-root user, bind-mounted data, health check"],
    ], [46 * mm, 137 * mm]))
    story.append(Spacer(1, 5 * mm))
    sub("Transaction integrity")
    p("Orders begin an immediate SQLite transaction before reading cash or shares. A buy checks that its notional plus fee fits cash; a sell checks owned quantity. Order insertion and cash adjustment then commit together. Foreign keys, primary keys, indexes and CHECK constraints reject inconsistent records. SQL parameters are bound rather than interpolated.")
    story.append(Image(str(plots["architecture"]), width=170 * mm, height=57 * mm))
    sub("Reproducibility")
    p("A clean clone can be started with `docker compose up --build`. The first container start initializes the database and signals, then launches Streamlit. The data directory is mounted so trades and cached history survive container replacement. If the network is unavailable, the supplied data still allows a working demonstration.")
    next_page()

    # 7. Portfolio and risk
    heading("6. Portfolio accounting and risk")
    p("The demo portfolio begins with INR 1,000,000 cash. Each buy adds notional and brokerage to its remaining cost basis. Each sell removes quantity at the moving average cost; realised P&amp;L is net proceeds minus the removed cost. Unrealised P&amp;L is current market value minus remaining basis. Total P&amp;L is current cash plus holdings value minus initial funding. A holding's weight is its market value divided by total portfolio value.")
    p("The test suite verifies an example: buy 10 shares at INR 100, sell 4 at INR 120, and charge INR 20 on each order. The six remaining shares have INR 102 average cost; realised P&amp;L is INR 52, unrealised P&amp;L at INR 120 is INR 108 and total P&amp;L is INR 160.")
    sub("Historical risk formulas")
    p("Annualised volatility = sample standard deviation of daily returns x sqrt(252). Sharpe = (mean daily return - 0.065/252) / daily standard deviation x sqrt(252). Beta = covariance(asset, NIFTY 50) / variance(NIFTY 50) on overlapping dates. Maximum drawdown = minimum of compounded wealth / its previous peak - 1. Historical 95% VaR = max(0, minus the fifth percentile daily return). Correlation uses Pearson's coefficient.")
    story.append(_table([
        [f"TCS risk measure ({risk['observations']} returns)", "Value"],
        ["Annualised volatility", f"{risk['volatility'] * 100:.2f}%" if risk["volatility"] is not None else "Unavailable"],
        ["Sharpe, 6.5% risk-free", f"{risk['sharpe']:.3f}" if risk["sharpe"] is not None else "Unavailable"],
        ["Beta vs NIFTY 50", f"{risk['beta']:.3f}" if risk["beta"] is not None else "Unavailable"],
        ["Maximum drawdown", f"{risk['max_drawdown'] * 100:.2f}%" if risk["max_drawdown"] is not None else "Unavailable"],
        ["Historical one-day VaR 95%", f"{risk['var_95'] * 100:.2f}%" if risk["var_95"] is not None else "Unavailable"],
    ], [116 * mm, 67 * mm]))
    story.append(Spacer(1, 4 * mm))
    story.append(Image(str(plots["drawdown"]), width=170 * mm, height=60 * mm))
    p("Current shares and cash are applied to historical closes for the portfolio risk view. That is an exposure scenario, not the realised account value path. All risk figures are historical sample estimates.", "small")
    next_page()

    # 8. signals / ML
    heading("7. Signal simulation and machine learning")
    p("The SMA strategy emits buy and sell signals when the 20-day mean crosses the 50-day mean. RSI(14) uses Wilder-style smoothing and marks oversold observations below 30 or overbought observations above 70. A signal is observed only after the day's close; the backtest trades at the next open. It remains long or in cash, buys whole shares and charges the portfolio's brokerage model. Buy-and-hold purchases at the first open for comparison.")
    story.append(_table([
        ["TCS SMA backtest measure", "Observed result"],
        ["Strategy total return", f"{backtest['strategy_return'] * 100:.2f}%"],
        ["Buy-and-hold return", f"{backtest['buy_hold_return'] * 100:.2f}%"],
        ["Completed round trips", str(backtest["completed_trades"])],
        ["Win rate", f"{backtest['win_rate'] * 100:.2f}%" if backtest["win_rate"] is not None else "Unavailable"],
        ["Maximum drawdown", f"{backtest['max_drawdown'] * 100:.2f}%"],
    ], [116 * mm, 67 * mm]))
    story.append(Spacer(1, 4 * mm))
    p("The next-day classifier uses close-known price, volume, momentum, range, RSI and rolling-volatility features. A scaler and logistic regression are fitted on earlier rows only. The last training label is left before the test period, preventing it from using a test-period close. The final 20% is evaluated once, without random shuffling.")
    if model["available"]:
        story.append(_table([
            ["TCS holdout measure", "Observed result"],
            ["Train / test rows", f"{model['train_rows']} / {model['test_rows']}"],
            ["Accuracy / majority baseline", f"{model['accuracy'] * 100:.2f}% / {model['majority_baseline_accuracy'] * 100:.2f}%"],
            ["Precision / recall / F1", f"{model['precision']:.3f} / {model['recall']:.3f} / {model['f1']:.3f}"],
        ], [116 * mm, 67 * mm]))
    else:
        p(f"ML evaluation unavailable: {model['reason']}")
    story.append(Spacer(1, 4 * mm))
    story.append(Image(str(plots["equity"]), width=170 * mm, height=60 * mm))
    p("These values are a single historical sample. The classifier is not deployed as an order generator, and a score below the majority baseline provides no evidence of a trading advantage.", "small")
    next_page()

    # 9. verification and ethics
    heading("8. Verification, limitations and conclusion")
    p("Focused pytest checks cover cleaning, SQLite constraints, brokerage-aware cost basis, order guards, known beta and drawdown values, next-open execution and chronological ML evaluation. Streamlit's test runner executed the home page and all five feature pages without app exceptions. A live Streamlit server returned HTTP 200 from `/_stcore/health`. Docker Compose configuration passed validation. Container image execution still requires an active Docker daemon on the host.")
    p("The test data includes a fully known two-day order scenario and an artificial overnight price jump that would expose same-day signal execution. These checks are more informative than tests that merely restate the implementation. The app pages were also exercised against the longer cached history to confirm that the risk cards, chart generation and ML evaluation can render with actual observations.")
    sub("Limitations")
    p("Historical prices are cached and may be revised by the provider. The source CSV is synthetic and too short for annualised inference. The backtest uses a single selected ticker, has no slippage, taxes, partial fills, liquidity constraints or corporate-action treatment beyond the provider's downloaded values. A one-off chronological ML holdout has no uncertainty interval or walk-forward validation. Risk estimates are sensitive to sample period and do not limit future loss.")
    sub("Ethical compliance")
    p("The system uses only public price data and a virtual account. It collects no names, credentials or other personal data, has no live broker connection and displays the requested disclaimer on every page. The learner must personally review the final submission, disclose tool assistance where required and sign the separate ethical declaration; this generated report does not claim a personal signature.")
    sub("References")
    p("[1] HCLTech Career Shaper, Project Brief and Dataset Generation Prompt, supplied in `data/`.", "small")
    p('[2] <link href="https://docs.streamlit.io/develop/concepts/multipage-apps/pages-directory">Streamlit, Creating multipage apps using the pages directory</link>.', "small")
    p('[3] <link href="https://pandas.pydata.org/pandas-docs/stable/generated/pandas.DataFrame.pct_change.html">pandas, DataFrame.pct_change documentation</link>.', "small")
    p('[4] <link href="https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html">scikit-learn, TimeSeriesSplit documentation</link>.', "small")
    p("Simulation only. NOT investment advice. Virtual money, no real brokerage connection.", "small")

    document = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18 * mm,
                                 leftMargin=18 * mm, topMargin=20 * mm, bottomMargin=23 * mm)
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return OUT


if __name__ == "__main__":
    print(build())
