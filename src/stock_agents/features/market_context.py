"""Market-wide context: VN-Index regime, relative strength, foreign flows.

All fetchers degrade gracefully (return None / empty) so the agents keep
working even when a market data endpoint is unavailable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from stock_agents.config import DEFAULT_HISTORY_DAYS, DEFAULT_SOURCE, FALLBACK_SOURCES
from stock_agents.features.technical_features import (
    fmt,
    pct_change,
    pct_from_level,
    safe_float,
)


def _normalize_source(source: str) -> str:
    return str(source or DEFAULT_SOURCE).strip().lower()


def get_index_ohlcv(
    index_symbol: str = "VNINDEX",
    source: str = DEFAULT_SOURCE,
    history_days: int = DEFAULT_HISTORY_DAYS,
    end_date: datetime | None = None,
) -> pd.DataFrame | None:
    """Fetch index OHLCV via vnstock Unified UI with source fallback."""
    try:
        from vnstock.ui import Market

        market = Market()
    except ImportError:
        return None

    primary = _normalize_source(source)
    sources_to_try = [primary] + [
        _normalize_source(s)
        for s in FALLBACK_SOURCES
        if _normalize_source(s) != primary
    ]

    end = end_date or datetime.today()
    start = end - timedelta(days=history_days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    for src in sources_to_try:
        try:
            df = market.index(index_symbol).ohlcv(
                start=start_str, end=end_str, resolution="1D", source=src
            )
        except Exception:
            continue
        if df is None or df.empty or "time" not in df.columns:
            continue
        df = df.copy().sort_values("time").reset_index(drop=True)
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df[df["time"].notna()].reset_index(drop=True)
        if end_date is not None:
            end_norm = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            df = df[df["time"] <= end_norm].reset_index(drop=True)
        if not df.empty:
            return df
    return None


def _classify_regime(latest, ma20, ma50, ma200) -> str:
    latest = safe_float(latest)
    ma50 = safe_float(ma50)
    ma200 = safe_float(ma200)
    if latest is None:
        return "Khong ro"
    if ma50 and ma200 and latest > ma50 > ma200:
        return "Uptrend (xu huong tang)"
    if ma50 and ma200 and latest < ma50 < ma200:
        return "Downtrend (xu huong giam)"
    if ma50 and latest > ma50:
        return "Hoi phuc / tren MA50"
    if ma50 and latest < ma50:
        return "Yeu / duoi MA50"
    return "Trung tinh / sideways"


def build_index_context(
    source: str = DEFAULT_SOURCE,
    history_days: int = DEFAULT_HISTORY_DAYS,
    end_date: datetime | None = None,
) -> dict | None:
    """Compute VN-Index regime metrics from real data for the LLM prompt."""
    df = get_index_ohlcv(
        "VNINDEX", source=source, history_days=history_days, end_date=end_date
    )
    if df is None or df.empty:
        return None

    close = pd.to_numeric(df["close"], errors="coerce")
    latest = float(close.iloc[-1])
    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    context = {
        "df": df,
        "latest": latest,
        "ma20": safe_float(ma20),
        "ma50": safe_float(ma50),
        "ma200": safe_float(ma200),
        "dist_ma50_pct": pct_from_level(latest, ma50),
        "dist_ma200_pct": pct_from_level(latest, ma200),
        "pct_1w": pct_change(close, 5),
        "pct_1m": pct_change(close, 21),
        "pct_3m": pct_change(close, 63),
        "regime": _classify_regime(latest, ma20, ma50, ma200),
    }
    context["summary_text"] = _index_context_to_text(context)
    return context


def _index_context_to_text(ctx: dict) -> str:
    lines = [
        "## Boi canh VN-Index (so lieu that tu vnstock)",
        f"- Pha thi truong (theo MA): {ctx['regime']}",
        f"- Diem hien tai: {fmt(ctx['latest'])}",
        (
            "- MA20 / MA50 / MA200: "
            f"{fmt(ctx['ma20'])} / {fmt(ctx['ma50'])} / {fmt(ctx['ma200'])}"
        ),
        (
            "- Khoang cach so voi MA50 / MA200: "
            f"{fmt(ctx['dist_ma50_pct'], '%')} / {fmt(ctx['dist_ma200_pct'], '%')}"
        ),
        (
            "- Bien dong 1W / 1M / 3M: "
            f"{fmt(ctx['pct_1w'], '%')} / {fmt(ctx['pct_1m'], '%')} / {fmt(ctx['pct_3m'], '%')}"
        ),
        "",
    ]
    return "\n".join(lines)


def _find_column(columns, *needles: str):
    for col in columns:
        name = col[-1] if isinstance(col, tuple) else col
        lowered = str(name).lower()
        if all(needle in lowered for needle in needles):
            return col
    return None


def get_foreign_snapshot(
    symbols: list[str],
    source: str = DEFAULT_SOURCE,
    end_date: datetime | None = None,
) -> dict[str, str]:
    """Current-session foreign buy/sell snapshot per symbol.

    Only meaningful for live runs; skipped for backtests (end_date set) because
    the price board reflects the current session, not a historical one.
    """
    if end_date is not None or not symbols:
        return {}

    try:
        from vnstock import Trading

        trading = Trading(source=source.upper())
        board = trading.price_board([s.upper() for s in symbols])
    except Exception:
        return {}

    if board is None or board.empty:
        return {}

    cols = list(board.columns)
    sym_col = _find_column(cols, "symbol")
    fbv_col = _find_column(cols, "foreign", "buy", "volume")
    fsv_col = _find_column(cols, "foreign", "sell", "volume")
    fbval_col = _find_column(cols, "foreign", "buy", "value")
    fsval_col = _find_column(cols, "foreign", "sell", "value")
    if sym_col is None or (fbv_col is None and fbval_col is None):
        return {}

    result: dict[str, str] = {}
    for _, row in board.iterrows():
        sym = str(row[sym_col]).strip().upper()
        if not sym:
            continue
        buy_vol = safe_float(row[fbv_col]) if fbv_col is not None else None
        sell_vol = safe_float(row[fsv_col]) if fsv_col is not None else None
        buy_val = safe_float(row[fbval_col]) if fbval_col is not None else None
        sell_val = safe_float(row[fsval_col]) if fsval_col is not None else None

        parts = []
        if buy_vol is not None and sell_vol is not None:
            net_vol = buy_vol - sell_vol
            parts.append(
                f"mua {fmt(buy_vol, decimals=0)} / ban {fmt(sell_vol, decimals=0)} cp "
                f"(rong {fmt(net_vol, decimals=0)})"
            )
        if buy_val is not None and sell_val is not None:
            net_val = (buy_val - sell_val) / 1e9
            parts.append(f"rong {fmt(net_val, ' ty', decimals=2)} gia tri")
        if parts:
            result[sym] = "Khoi ngoai (phien gan nhat): " + "; ".join(parts)
    return result
