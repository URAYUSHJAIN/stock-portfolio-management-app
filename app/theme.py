"""Shared finance dashboard colours, formatting and page chrome."""

from __future__ import annotations

import math
import sys
from pathlib import Path

_LOCAL_DEPS = Path(__file__).resolve().parents[1] / ".deps"
if _LOCAL_DEPS.exists() and str(_LOCAL_DEPS) not in sys.path:
    sys.path.append(str(_LOCAL_DEPS))

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from src.config import DISCLAIMER

BG = "#0B1220"
SURFACE = "#121B2E"
BORDER = "#1F2A44"
TEXT = "#E5E7EB"
MUTED = "#94A3B8"
TEAL = "#14B8A6"
INDIGO = "#6366F1"
AMBER = "#F59E0B"
PROFIT = "#22C55E"
LOSS = "#EF4444"

TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, sans-serif", "color": TEXT},
        colorway=[TEAL, INDIGO, AMBER, PROFIT, LOSS, MUTED],
        xaxis={"gridcolor": BORDER, "zerolinecolor": BORDER, "linecolor": BORDER},
        yaxis={"gridcolor": BORDER, "zerolinecolor": BORDER, "linecolor": BORDER},
        legend={"bgcolor": "rgba(0,0,0,0)"},
    )
)
pio.templates["portfolio_dark"] = TEMPLATE


def chart_layout(fig: go.Figure, *, height: int = 390) -> go.Figure:
    """Apply the one reusable chart template and common spacing."""
    fig.update_layout(template="portfolio_dark", height=height,
                      margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified")
    return fig


def indian_number(value: float) -> str:
    """Format a number with Indian digit grouping and two decimals."""
    if not math.isfinite(value):
        return "—"
    sign = "-" if value < 0 else ""
    whole, decimals = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        chunks = []
        while head:
            chunks.append(head[-2:])
            head = head[:-2]
        whole = ",".join(reversed(chunks)) + "," + tail
    return f"{sign}{whole}.{decimals}"


def inr(value: float) -> str:
    """Format money in Indian rupees."""
    formatted = indian_number(value)
    return "—" if formatted == "—" else f"₹{formatted}"


def signed_inr(value: float) -> str:
    """Show P&L direction with an arrow in addition to any colour."""
    return f"{'▲' if value >= 0 else '▼'} {inr(abs(value))}"


def percent(value: float, *, arrow: bool = False) -> str:
    """Format a ratio as a two-decimal percentage."""
    if value is None or not math.isfinite(value):
        return "—"
    prefix = ("▲ " if value >= 0 else "▼ ") if arrow else ""
    return f"{prefix}{abs(value) * 100:.2f}%" if arrow else f"{value * 100:.2f}%"


def setup_page(title: str) -> None:
    """Set page metadata and render the same banner and fixed footer everywhere."""
    st.set_page_config(page_title=f"{title} | Portfolio Lab", page_icon="📈", layout="wide")
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        html, body, [class*="css"], [data-testid="stApp"] { font-family: Inter, system-ui, sans-serif; }
        [data-testid="stApp"], [data-testid="stSidebar"] { background: #0B1220; color: #E5E7EB; }
        [data-testid="stHeader"] { background: rgba(11,18,32,.85); }
        [data-testid="stMetric"] { background: #121B2E; border: 1px solid #1F2A44;
          border-radius: 12px; padding: 16px 20px; box-shadow: 0 8px 24px rgba(0,0,0,.12); }
        [data-testid="stMetricValue"], [data-testid="stMetricDelta"] { font-variant-numeric: tabular-nums; }
        .stButton button, .stDownloadButton button { border-radius: 10px; }
        .simulation-banner { background: rgba(245,158,11,.10); border: 1px solid #F59E0B;
          border-radius: 12px; padding: 12px 16px; color: #FDE68A; margin-bottom: 20px; }
        .simulation-footer { position: fixed; bottom: 0; left: 0; right: 0; z-index: 999;
          background: #121B2E; border-top: 1px solid #1F2A44; color: #94A3B8;
          text-align: center; padding: 7px 12px; font-size: 12px; }
        .block-container { padding-bottom: 76px; max-width: 1440px; }
        </style>
    """, unsafe_allow_html=True)
    st.markdown(f'<div class="simulation-banner">{DISCLAIMER}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="simulation-footer">{DISCLAIMER}</div>', unsafe_allow_html=True)
