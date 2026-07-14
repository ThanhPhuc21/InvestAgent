"""Chart rendering with optional forecast overlay for BUY signals."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stock_agents.config import FORECAST_SESSIONS, OUTPUT_DIR
from stock_agents.features.technical_features import safe_float
from stock_agents.schemas import ShortTermAction, ShortTermSymbolDecision


def _parse_price_zone(zone_text: str, fallback: float) -> float:
    """Extract first numeric price from zone string like '95-98' or '95.5'."""
    import re

    if not zone_text:
        return fallback
    nums = re.findall(r"\d+(?:[.,]\d+)?", zone_text.replace(",", ""))
    if not nums:
        return fallback
    values = [float(n.replace(",", ".")) for n in nums[:2]]
    return sum(values) / len(values)


def build_forecast_series(
    df: pd.DataFrame,
    decision: ShortTermSymbolDecision,
    sessions: int = FORECAST_SESSIONS,
) -> pd.Series | None:
    """Rule-based forecast line from entry zone to target."""
    if decision.action != ShortTermAction.BUY:
        return None
    if df is None or df.empty:
        return None

    close = df["close"].astype(float)
    last_date = pd.to_datetime(df["time"].iloc[-1])
    last_price = float(close.iloc[-1])
    entry = _parse_price_zone(
        decision.safe_buy_zone or decision.early_buy_zone, last_price
    )
    target = _parse_price_zone(decision.target_1_2m, last_price * 1.08)

    future_dates = pd.bdate_range(
        start=last_date + pd.Timedelta(days=1), periods=sessions
    )
    path = np.linspace(entry, target, sessions)
    return pd.Series(path, index=future_dates, name="forecast")


def render_symbol_chart(
    df: pd.DataFrame,
    symbol: str,
    decision: ShortTermSymbolDecision | None = None,
    output_dir: Path | None = None,
) -> Path | None:
    """Render price chart; forecast only for BUY."""
    if df is None or df.empty:
        return None

    out_dir = output_dir or OUTPUT_DIR / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_chart.png"

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df.set_index("time")["close"].astype(float)
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(close.index, close.values, color="#1976D2", linewidth=1.8, label="Close")
    ax.plot(ma20.index, ma20.values, color="#FF9800", linewidth=1.0, alpha=0.8, label="MA20")
    ax.plot(ma50.index, ma50.values, color="#4CAF50", linewidth=1.0, alpha=0.8, label="MA50")

    action_label = ""
    if decision is not None:
        action_label = decision.action.value
        if decision.action == ShortTermAction.BUY:
            forecast = build_forecast_series(df.reset_index(drop=True), decision)
            if forecast is not None and not forecast.empty:
                ax.plot(
                    forecast.index,
                    forecast.values,
                    color="#E91E63",
                    linestyle="--",
                    linewidth=1.5,
                    label="Du bao (kich ban)",
                )
                ax.axhline(
                    _parse_price_zone(decision.stop_loss, close.iloc[-1] * 0.95),
                    color="#F44336",
                    linestyle=":",
                    alpha=0.7,
                    label="Stop-loss",
                )

    title = f"{symbol}"
    if action_label:
        title += f" — {action_label}"
    ax.set_title(title)
    ax.set_xlabel("Ngay")
    ax.set_ylabel("Gia (nghin VND)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return path


def render_portfolio_chart(
    df: pd.DataFrame,
    symbol: str,
    avg_price: float,
    output_dir: Path | None = None,
) -> Path | None:
    """Chart for held position with cost basis line."""
    if df is None or df.empty:
        return None

    out_dir = output_dir or OUTPUT_DIR / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_portfolio.png"

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df.set_index("time")["close"].astype(float)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(close.index, close.values, color="#1976D2", linewidth=1.8, label="Close")
    ax.axhline(avg_price, color="#9C27B0", linestyle="--", label=f"Gia von {avg_price:.2f}")
    ax.set_title(f"{symbol} — Vi the dang nam giu")
    ax.set_xlabel("Ngay")
    ax.set_ylabel("Gia (nghin VND)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return path
