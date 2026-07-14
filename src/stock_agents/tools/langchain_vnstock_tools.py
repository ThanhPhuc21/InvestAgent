"""LangChain tools for vnstock data access."""

from __future__ import annotations

from datetime import datetime

from langchain_core.tools import tool

from stock_agents.tools.vnstock_tools import fetch_symbol_bundle, get_fundamentals, get_stock_data


@tool
def fetch_ohlcv_tool(
    symbol: str,
    source: str = "VCI",
    history_days: int = 365,
    as_of_date: str | None = None,
) -> str:
    """Lay du lieu OHLCV va chi bao ky thuat cho mot ma co phieu VN.

    Args:
        symbol: Ma co phieu (VD: FPT).
        source: Nguon VCI hoac KBS.
        history_days: So ngay lich su.
        as_of_date: Ngay gioi han YYYY-MM-DD hoac None = hom nay.
    """
    end = datetime.strptime(as_of_date, "%Y-%m-%d") if as_of_date else None
    bundle = fetch_symbol_bundle(
        symbol=symbol.upper(),
        source=source,
        history_days=history_days,
        end_date=end,
    )
    from stock_agents.features.technical_features import build_symbol_snapshot

    return build_symbol_snapshot(
        bundle["symbol"],
        bundle["source"],
        bundle["indicators"],
        bundle["score"],
    )


@tool
def fetch_fundamentals_tool(symbol: str, source: str = "VCI") -> str:
    """Lay thong tin co ban doanh nghiep cho mot ma."""
    data = get_fundamentals(symbol.upper(), source=source)
    return data.get("summary_text", "Khong co du lieu co ban.")


@tool
def fetch_multi_symbols_tool(
    symbols: str,
    source: str = "VCI",
    history_days: int = 365,
    as_of_date: str | None = None,
) -> str:
    """Lay du lieu nhieu ma, symbols cach nhau boi dau phay."""
    from stock_agents.features.technical_features import build_combined_summary

    end = datetime.strptime(as_of_date, "%Y-%m-%d") if as_of_date else None
    reports = []
    for sym in symbols.split(","):
        sym = sym.strip().upper()
        if not sym:
            continue
        try:
            bundle = fetch_symbol_bundle(
                symbol=sym,
                source=source,
                history_days=history_days,
                end_date=end,
            )
            reports.append(
                {
                    "symbol": bundle["symbol"],
                    "source": bundle["source"],
                    "indicators": bundle["indicators"],
                    "score": bundle["score"],
                }
            )
        except Exception as exc:
            reports.append(
                {
                    "symbol": sym,
                    "source": source,
                    "indicators": {"latest_price": 0},
                    "score": {"score_total": 0},
                    "error": str(exc),
                }
            )
    return build_combined_summary(reports, as_of_date=end)


def get_vnstock_tools() -> list:
    """Return all vnstock LangChain tools."""
    return [fetch_ohlcv_tool, fetch_fundamentals_tool, fetch_multi_symbols_tool]
