"""Portfolio position metrics and summaries."""

from __future__ import annotations

from stock_agents.features.technical_features import (
    build_trade_levels,
    fmt,
    safe_float,
)

CONCENTRATION_WARN_PCT = 35.0
RISK_PER_TRADE_PCT = 2.0


def _parse_first_price(text: str) -> float | None:
    """Extract the first numeric price from a level string like '95.0 - 97.0'."""
    import re

    if not text:
        return None
    nums = re.findall(r"\d+(?:[.,]\d+)?", str(text).replace(",", ""))
    if not nums:
        return None
    return safe_float(nums[0])


def build_position_info(
    price: float, quantity: int, avg_price: float | None
) -> dict | None:
    """Compute position PnL and market value."""
    if not quantity or quantity <= 0:
        return None

    info: dict = {
        "quantity": quantity,
        "avg_price": avg_price,
        "latest_price": price,
        "market_value": price * quantity,
    }

    if avg_price and avg_price > 0:
        info["cost_basis"] = avg_price * quantity
        info["pnl_abs"] = (price - avg_price) * quantity
        info["pnl_pct"] = (price / avg_price - 1) * 100
    else:
        info["cost_basis"] = None
        info["pnl_abs"] = None
        info["pnl_pct"] = None

    return info


def build_position_snapshot(
    symbol: str,
    position: dict,
    indicators: dict,
    source: str,
    foreign_text: str = "",
) -> str:
    """Markdown block for portfolio position context."""
    pnl_pct = position.get("pnl_pct")
    pnl_abs = position.get("pnl_abs")

    if pnl_pct is not None:
        status = "LAI" if pnl_pct > 0 else ("LO" if pnl_pct < 0 else "HOA")
    else:
        status = "Chua khai bao gia mua"

    lines = [
        f"### {symbol} (vi the dang nam giu)",
        f"- Nguon du lieu: {source}",
        f"- So luong: {fmt(position['quantity'], decimals=0)} cp",
        f"- Gia von TB: {fmt(position.get('avg_price'))}",
        f"- Gia hien tai: {fmt(position['latest_price'])}",
        f"- Gia tri thi truong: {fmt(position['market_value'], decimals=0)}",
        f"- Von goc: {fmt(position.get('cost_basis'), decimals=0)}",
        f"- Lai/Lo: {fmt(pnl_abs, decimals=0)} ({fmt(pnl_pct, '%')})",
        f"- Trang thai: {status}",
        f"- RSI(14): {fmt(indicators.get('rsi'))}",
        f"- MA20 / MA50: {fmt(indicators.get('ma20'))} / {fmt(indicators.get('ma50'))}",
        (
            "- Suc manh tuong doi vs VN-Index 1M / 3M: "
            f"{fmt(indicators.get('rs_1m'), '%')} / {fmt(indicators.get('rs_3m'), '%')}"
        ),
        f"- Support 20p: {fmt(indicators.get('support_level_20'))}",
        f"- Breakout 20p: {fmt(indicators.get('breakout_level_20'))}",
    ]
    if foreign_text:
        lines.append(f"- {foreign_text}")
    lines.append("")
    return "\n".join(lines)


def compute_drawdown_pct(df, as_of_price: float | None = None) -> float | None:
    """Max drawdown from recent peak as percentage."""
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = df["close"].astype(float)
    peak = close.cummax()
    dd = (close / peak - 1) * 100
    if as_of_price is not None:
        return safe_float(dd.iloc[-1])
    return safe_float(dd.min())


def build_portfolio_risk_summary(
    position_reports: list[dict], cash_available: float | None = None
) -> str:
    """Portfolio-level risk view: weights, per-position risk, sizing hints."""
    if not position_reports:
        return ""

    total_value = sum(
        (item["position"].get("market_value") or 0) for item in position_reports
    )
    if total_value <= 0:
        return ""

    nav = total_value + (cash_available or 0)

    lines = ["## Quan tri rui ro cap danh muc", ""]
    concentration_flags: list[str] = []
    total_risk_abs = 0.0

    for item in position_reports:
        pos = item["position"]
        symbol = item["symbol"]
        market_value = pos.get("market_value") or 0
        weight = market_value / total_value * 100 if total_value else None
        price = safe_float(pos.get("latest_price"))
        quantity = pos.get("quantity") or 0

        levels = build_trade_levels(item.get("indicators", {}))
        stop = _parse_first_price(levels.get("stop_loss", ""))
        risk_abs = None
        risk_pct_nav = None
        if price is not None and stop is not None and stop < price and quantity:
            risk_abs = (price - stop) * quantity
            total_risk_abs += risk_abs
            if nav > 0:
                risk_pct_nav = risk_abs / nav * 100

        weight_text = fmt(weight, "%")
        detail = f"- {symbol}: ty trong {weight_text}"
        if risk_abs is not None:
            detail += (
                f", rui ro toi stop ~{fmt(risk_abs, decimals=0)} "
                f"({fmt(risk_pct_nav, '%')} NAV, stop {fmt(stop)})"
            )
        else:
            detail += ", chua uoc luong duoc rui ro (thieu stop/gia)"
        lines.append(detail)

        if weight is not None and weight > CONCENTRATION_WARN_PCT:
            concentration_flags.append(
                f"{symbol} chiem {weight_text} danh muc (>{CONCENTRATION_WARN_PCT:.0f}%)"
            )

    lines.append("")
    if nav > 0 and total_risk_abs > 0:
        lines.append(
            f"- Tong rui ro toi stop: {fmt(total_risk_abs, decimals=0)} "
            f"({fmt(total_risk_abs / nav * 100, '%')} NAV)"
        )
    if concentration_flags:
        lines.append("- Canh bao tap trung: " + "; ".join(concentration_flags))

    if cash_available and cash_available > 0:
        risk_budget = nav * RISK_PER_TRADE_PCT / 100
        lines += [
            "",
            (
                f"- Tien mat kha dung: {fmt(cash_available, decimals=0)} "
                f"({fmt(cash_available / nav * 100, '%')} NAV)"
            ),
            (
                f"- Goi y sizing khi mua them: gioi han rui ro <= {RISK_PER_TRADE_PCT:.0f}% "
                f"NAV/lenh (~{fmt(risk_budget, decimals=0)}). So luong toi da = "
                "risk_budget / (gia mua - stop)."
            ),
        ]

    return "\n".join(lines)


def build_portfolio_combined_summary(
    position_reports: list[dict],
    as_of_date=None,
    index_summary: str = "",
    foreign_map: dict[str, str] | None = None,
    cash_available: float | None = None,
) -> str:
    """Combine position snapshots for LLM input."""
    from datetime import datetime

    foreign_map = foreign_map or {}
    view_date = (as_of_date or datetime.today()).strftime("%Y-%m-%d")
    lines = [
        f"# Danh muc dang nam giu ({view_date})",
        "",
    ]
    if index_summary:
        lines += [index_summary, ""]
    total_value = 0.0
    total_cost = 0.0
    for item in position_reports:
        pos = item["position"]
        lines.append(
            build_position_snapshot(
                item["symbol"],
                pos,
                item["indicators"],
                item["source"],
                foreign_text=foreign_map.get(item["symbol"], ""),
            )
        )
        total_value += pos.get("market_value") or 0
        if pos.get("cost_basis"):
            total_cost += pos["cost_basis"]

    if total_cost > 0:
        pnl = (total_value / total_cost - 1) * 100
        lines += [
            "## Tong hop danh muc",
            f"- Gia tri thi truong: {fmt(total_value, decimals=0)}",
            f"- Von goc: {fmt(total_cost, decimals=0)}",
            f"- Lai/Lo danh muc: {fmt(pnl, '%')}",
            "",
        ]

    risk_summary = build_portfolio_risk_summary(
        position_reports, cash_available=cash_available
    )
    if risk_summary:
        lines += [risk_summary, ""]
    return "\n".join(lines)
