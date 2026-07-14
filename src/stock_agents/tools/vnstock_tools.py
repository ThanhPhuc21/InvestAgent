"""Vnstock data fetching with Unified UI and fallbacks."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd

VN_TZ = timezone(timedelta(hours=7))
MARKET_CLOSE_HOUR = 15

from stock_agents.config import (
    API_RETRIES,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SOURCE,
    FALLBACK_SOURCES,
    REQUEST_DELAY_SEC,
)


def _normalize_source(source: str) -> str:
    return str(source or DEFAULT_SOURCE).strip().lower()


def _get_market_client():
    """Return Market client from vnstock Unified UI."""
    try:
        from vnstock.ui import Market

        return Market()
    except ImportError:
        return None


def get_stock_data(
    symbol: str,
    source: str = DEFAULT_SOURCE,
    history_days: int = DEFAULT_HISTORY_DAYS,
    end_date: datetime | None = None,
) -> tuple[pd.DataFrame, str]:
    """Fetch OHLCV via vnstock Unified UI with source fallback."""
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
    candle_count = max(history_days + 50, 300)

    market = _get_market_client()
    last_error: Exception | None = None

    for src in sources_to_try:
        for attempt in range(API_RETRIES):
            try:
                if market is not None:
                    df = market.equity(symbol).ohlcv(
                        start=start_str,
                        end=end_str,
                        resolution="1D",
                        source=src,
                        count=candle_count,
                    )
                else:
                    from vnstock.api.quote import Quote

                    quote = Quote(source=src.upper(), symbol=symbol)
                    df = quote.history(start=start_str, end=end_str, interval="1D")

                if df is None or df.empty:
                    last_error = RuntimeError(
                        f"{src.upper()}: tra ve DataFrame rong ({start_str} -> {end_str})"
                    )
                else:
                    df = df.copy().sort_values("time").reset_index(drop=True)
                    df["time"] = pd.to_datetime(df["time"], errors="coerce")
                    df = df[df["time"].notna()].reset_index(drop=True)
                    if end_date is not None:
                        end_norm = end_date.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        df = df[df["time"] <= end_norm].reset_index(drop=True)
                    if not df.empty:
                        return df, src.upper()
                    last_error = RuntimeError(
                        f"{src.upper()}: khong con du lieu sau khi loc den {end_str}"
                    )
            except Exception as exc:
                last_error = exc

            if attempt < API_RETRIES - 1:
                time.sleep(REQUEST_DELAY_SEC * (attempt + 1))
        time.sleep(REQUEST_DELAY_SEC)

    raise RuntimeError(
        f"Khong lay duoc du lieu gia cho {symbol}. Loi cuoi: {last_error}"
    )


def get_fundamentals(symbol: str, source: str = DEFAULT_SOURCE) -> dict:
    """Fetch company overview and financial ratios."""
    result: dict = {
        "overview": None,
        "ratios": None,
        "shareholders": None,
        "source": source,
        "summary_text": "",
    }

    src = source.upper()
    try:
        from vnstock.api.company import Company
        from vnstock.api.financial import Finance

        company = Company(symbol=symbol, source=src)
        finance = Finance(source=src, symbol=symbol)
    except Exception:
        return result

    try:
        result["overview"] = company.overview()
    except Exception:
        pass

    try:
        result["ratios"] = finance.ratio(period="year", lang="vi")
    except Exception:
        try:
            result["ratios"] = finance.ratio()
        except Exception:
            pass

    try:
        result["shareholders"] = company.shareholders()
    except Exception:
        pass

    result["summary_text"] = _fundamentals_to_text(symbol, result)
    return result


def _fundamentals_to_text(symbol: str, fundamentals: dict) -> str:
    lines = [f"## Co ban {symbol}", ""]
    overview = fundamentals.get("overview")
    if overview is not None and not overview.empty:
        lines += ["### Tong quan", "```", overview.head(3).to_string(index=False), "```", ""]
    ratios = fundamentals.get("ratios")
    if ratios is not None and not ratios.empty:
        lines += ["### Chi so tai chinh", "```", ratios.head(3).to_string(), "```", ""]
    shareholders = fundamentals.get("shareholders")
    if shareholders is not None and not shareholders.empty:
        lines += [
            "### Co dong lon",
            "```",
            shareholders.head(5).to_string(index=False),
            "```",
            "",
        ]
    if len(lines) <= 2:
        return f"## Co ban {symbol}\n\nChua co du lieu co ban.\n"
    return "\n".join(lines)


def drop_unclosed_candle(
    df: pd.DataFrame, end_date: datetime | None = None
) -> pd.DataFrame:
    """Drop the last candle if it belongs to an unfinished trading session.

    Only applies to live runs (end_date is None): if the latest candle is dated
    today (VN time) and the market has not closed yet, that candle is still
    forming and its volume/close would distort indicators.
    """
    if df is None or df.empty or "time" not in df.columns:
        return df
    if end_date is not None:
        return df

    now_vn = datetime.now(VN_TZ)
    if now_vn.hour >= MARKET_CLOSE_HOUR:
        return df

    last_time = pd.to_datetime(df["time"].iloc[-1])
    if pd.isna(last_time):
        return df
    if last_time.date() == now_vn.date() and len(df) > 1:
        return df.iloc[:-1].reset_index(drop=True)
    return df


def fetch_symbol_bundle(
    symbol: str,
    source: str = DEFAULT_SOURCE,
    history_days: int = DEFAULT_HISTORY_DAYS,
    end_date: datetime | None = None,
    quantity: int = 0,
    avg_price: float | None = None,
    index_df: pd.DataFrame | None = None,
) -> dict:
    """Fetch OHLCV, indicators, score, fundamentals for one symbol."""
    from stock_agents.features.portfolio_features import build_position_info
    from stock_agents.features.technical_features import (
        compute_indicators,
        score_short_term,
    )

    df, used_source = get_stock_data(
        symbol, source=source, history_days=history_days, end_date=end_date
    )
    indicator_df = drop_unclosed_candle(df, end_date=end_date)
    indicators = compute_indicators(indicator_df, index_df=index_df)
    score = score_short_term(indicators)
    fundamentals = get_fundamentals(symbol, source=used_source)
    position = build_position_info(
        price=indicators["latest_price"],
        quantity=quantity,
        avg_price=avg_price,
    )

    return {
        "symbol": symbol.upper(),
        "source": used_source,
        "df": df,
        "indicators": indicators,
        "score": score,
        "fundamentals": fundamentals,
        "position": position,
    }
