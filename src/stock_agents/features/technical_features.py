"""Technical indicator and scoring utilities."""

from __future__ import annotations

import pandas as pd


def pct_change(series: pd.Series, days: int) -> float | None:
    if len(series) <= days:
        return None
    return float((series.iloc[-1] / series.iloc[-1 - days] - 1) * 100)


def safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_from_level(value, reference) -> float | None:
    value = safe_float(value)
    reference = safe_float(reference)
    if value is None or reference in (None, 0):
        return None
    return (value / reference - 1) * 100


def range_position_pct(value, low_value, high_value) -> float | None:
    value = safe_float(value)
    low_value = safe_float(low_value)
    high_value = safe_float(high_value)
    if (
        value is None
        or low_value is None
        or high_value is None
        or high_value <= low_value
    ):
        return None
    return (value - low_value) / (high_value - low_value) * 100


def fmt(value, suffix: str = "", decimals: int = 2) -> str:
    value = safe_float(value)
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}{suffix}"


def _first_valid(*values) -> float | None:
    for value in values:
        value = safe_float(value)
        if value is not None and value > 0:
            return value
    return None


def _zone_text(low_value, high_value, decimals: int = 2) -> str:
    low_value = safe_float(low_value)
    high_value = safe_float(high_value)
    if low_value is None and high_value is None:
        return "N/A"
    if low_value is None:
        return fmt(high_value, decimals=decimals)
    if high_value is None:
        return fmt(low_value, decimals=decimals)
    low_value, high_value = sorted([low_value, high_value])
    if abs(high_value - low_value) <= max(low_value * 0.003, 0.05):
        return fmt((low_value + high_value) / 2, decimals=decimals)
    return f"{fmt(low_value, decimals=decimals)} - {fmt(high_value, decimals=decimals)}"


def is_missing_text(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return True
    missing_markers = [
        "chua co du lieu",
        "chưa có dữ liệu",
        "n/a",
        "khong ro",
        "không rõ",
    ]
    return any(marker in text for marker in missing_markers)


def build_trade_levels(indicators: dict) -> dict[str, str]:
    """Build deterministic swing-trade levels from technical indicators."""
    price = _first_valid(indicators.get("latest_price"))
    ma20 = _first_valid(indicators.get("ma20"))
    ma50 = _first_valid(indicators.get("ma50"))
    atr14 = _first_valid(indicators.get("atr14"))
    breakout_20 = _first_valid(indicators.get("breakout_level_20"))
    breakout_60 = _first_valid(indicators.get("breakout_level_60"))
    support_20 = _first_valid(indicators.get("support_level_20"))
    support_60 = _first_valid(indicators.get("support_level_60"))
    range_high_20 = _first_valid(indicators.get("range_high_20"))
    range_low_20 = _first_valid(indicators.get("range_low_20"))
    range_high_60 = _first_valid(indicators.get("range_high_60"))
    range_low_60 = _first_valid(indicators.get("range_low_60"))
    vol_ratio = safe_float(indicators.get("volume_ratio_20"))

    if price is None:
        return {
            "trigger": "Chua co du lieu",
            "early_buy_zone": "Chua co du lieu",
            "safe_buy_zone": "Chua co du lieu",
            "stop_loss": "Chua co du lieu",
            "target_1_2m": "Chua co du lieu",
            "risk_reward": "Chua co du lieu",
        }

    volatility_buffer = atr14 if atr14 is not None else price * 0.02
    breakout_ref = _first_valid(breakout_20, breakout_60)
    support_ref = _first_valid(support_20, support_60, ma50, ma20, price - volatility_buffer)
    trend_ref = _first_valid(ma20, price)

    if breakout_ref is not None:
        early_low = min(trend_ref, breakout_ref)
        early_high = max(trend_ref, breakout_ref)
    else:
        early_low = trend_ref - volatility_buffer * 0.35
        early_high = trend_ref + volatility_buffer * 0.2
    if support_ref is not None:
        early_low = max(early_low, support_ref)

    safe_low = _first_valid(support_20, support_60, ma50, ma20, price - volatility_buffer)
    safe_high = _first_valid(ma20, breakout_20, breakout_60, price)
    if safe_low is None:
        safe_low = price - volatility_buffer * 0.7
    if safe_high is None:
        safe_high = price
    safe_low, safe_high = sorted([safe_low, safe_high])

    stop_candidates = [
        support_20 * 0.985 if support_20 is not None else None,
        support_60 * 0.985 if support_60 is not None else None,
        ma50 * 0.98 if ma50 is not None else None,
        ma20 * 0.975 if ma20 is not None else None,
        price - volatility_buffer * 1.5,
    ]
    stop_loss = min(v for v in stop_candidates if v is not None and v > 0)

    entry_reference = (safe_low + safe_high) / 2

    # T+2.5 / bien do san: co phieu VN chi ban duoc sau ~2.5 phien va mot phien
    # san co the mat 7% (HOSE). Ep stop cach entry it nhat 1.5*ATR de tranh bi
    # quet stop chi vi bien dong 2-3 phien binh thuong.
    min_stop_distance = volatility_buffer * 1.5
    if entry_reference - stop_loss < min_stop_distance:
        stop_loss = max(entry_reference - min_stop_distance, 0.01)

    target_candidates = [
        range_high_20,
        range_high_60,
        breakout_20 + volatility_buffer if breakout_20 is not None else None,
        breakout_60 + volatility_buffer if breakout_60 is not None else None,
        price + volatility_buffer * 2.0,
    ]
    target = max(v for v in target_candidates if v is not None and v > 0)
    if target <= entry_reference:
        target = entry_reference + volatility_buffer * 1.8

    risk = max(entry_reference - stop_loss, 0.01)
    reward = max(target - entry_reference, 0.0)
    rr = reward / risk if risk > 0 else None

    stop_pct = (
        (entry_reference - stop_loss) / entry_reference * 100
        if entry_reference
        else None
    )

    trigger_parts = []
    if breakout_20 is not None:
        trigger_parts.append(f"vuot {fmt(breakout_20)}")
    elif ma20 is not None:
        trigger_parts.append(f"giu tren {fmt(ma20)}")
    else:
        trigger_parts.append("giu duoc nen gia hien tai")
    if vol_ratio is not None:
        if vol_ratio < 1:
            trigger_parts.append("volume can cai thien vuot TB20")
        else:
            trigger_parts.append("volume duy tri it nhat ngang TB20")
    if stop_pct is not None and stop_pct < 7:
        trigger_parts.append(
            "luu y T+2.5 & bien do san -7%: stop kha gan, rui ro gap gia khi ban"
        )
    else:
        trigger_parts.append("luu y T+2.5: chi ban duoc sau ~2.5 phien")

    return {
        "trigger": "; ".join(trigger_parts).capitalize(),
        "early_buy_zone": _zone_text(early_low, early_high),
        "safe_buy_zone": _zone_text(safe_low, safe_high),
        "stop_loss": fmt(stop_loss),
        "target_1_2m": _zone_text(target - volatility_buffer * 0.4, target + volatility_buffer * 0.6),
        "risk_reward": f"1:{rr:.2f}" if rr is not None else "Chua co du lieu",
    }


def compute_relative_strength(
    close: pd.Series, index_df: pd.DataFrame | None
) -> dict[str, float | None]:
    """Return stock return minus index return over 1M / 3M horizons."""
    rs = {"rs_1m": None, "rs_3m": None}
    if index_df is None or index_df.empty or "close" not in index_df.columns:
        return rs
    idx_close = pd.to_numeric(
        index_df.sort_values("time")["close"], errors="coerce"
    ).dropna()
    if idx_close.empty:
        return rs
    for key, days in (("rs_1m", 21), ("rs_3m", 63)):
        stock_ret = pct_change(close, days)
        idx_ret = pct_change(idx_close, days)
        if stock_ret is not None and idx_ret is not None:
            rs[key] = stock_ret - idx_ret
    return rs


def compute_indicators(df: pd.DataFrame, index_df: pd.DataFrame | None = None) -> dict:
    """Compute swing-trading technical features from OHLCV DataFrame.

    When ``index_df`` (VN-Index OHLCV) is provided, relative-strength metrics
    versus the index are added.
    """
    df = df.copy().sort_values("time").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    open_price = df["open"] if "open" in df.columns else df["close"]
    high = df["high"] if "high" in df.columns else df["close"]
    low = df["low"] if "low" in df.columns else df["close"]
    close = df["close"]
    volume = df["volume"]

    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi_series = 100 - 100 / (1 + rs)
    rsi = rsi_series.iloc[-1] if len(rsi_series.dropna()) else None

    daily_returns = close.pct_change().dropna()
    volatility_annual = (
        daily_returns.std() * (252**0.5) * 100
        if not daily_returns.empty
        else None
    )

    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = true_range.rolling(14).mean().iloc[-1] if len(true_range) >= 14 else None

    avg_volume_20 = volume.tail(20).mean() if len(volume) >= 1 else None
    avg_volume_60 = volume.tail(60).mean() if len(volume) >= 1 else None
    last_volume = volume.iloc[-1] if len(volume) >= 1 else None
    volume_ratio_20 = (
        last_volume / avg_volume_20
        if last_volume is not None and avg_volume_20 and avg_volume_20 > 0
        else None
    )
    flow_ratio_20_60 = (
        avg_volume_20 / avg_volume_60
        if avg_volume_20 and avg_volume_60 and avg_volume_60 > 0
        else None
    )

    value_series = close * volume
    avg_value_20 = value_series.tail(20).mean() if len(value_series) >= 1 else None

    range_high_20 = high.tail(20).max() if len(high) >= 20 else None
    range_low_20 = low.tail(20).min() if len(low) >= 20 else None
    range_high_60 = high.tail(60).max() if len(high) >= 60 else None
    range_low_60 = low.tail(60).min() if len(low) >= 60 else None

    breakout_level_20 = (
        high.shift(1).rolling(20).max().iloc[-1] if len(high) >= 21 else None
    )
    breakout_level_60 = (
        high.shift(1).rolling(60).max().iloc[-1] if len(high) >= 61 else None
    )
    support_level_20 = (
        low.shift(1).rolling(20).min().iloc[-1] if len(low) >= 21 else None
    )
    support_level_60 = (
        low.shift(1).rolling(60).min().iloc[-1] if len(low) >= 61 else None
    )

    latest_price = float(close.iloc[-1])

    window_52w = min(len(close), 252)
    high_52w = float(close.tail(window_52w).max())
    low_52w = float(close.tail(window_52w).min())

    rs = compute_relative_strength(close, index_df)

    return {
        "latest_price": latest_price,
        "rs_1m": rs["rs_1m"],
        "rs_3m": rs["rs_3m"],
        "last_open": float(open_price.iloc[-1]) if len(open_price) >= 1 else None,
        "ma20": safe_float(ma20),
        "ma50": safe_float(ma50),
        "ma200": safe_float(ma200),
        "dist_ma20_pct": pct_from_level(latest_price, ma20),
        "dist_ma50_pct": pct_from_level(latest_price, ma50),
        "rsi": safe_float(rsi),
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_1w": pct_change(close, 5),
        "pct_1m": pct_change(close, 21),
        "pct_3m": pct_change(close, 63),
        "pct_6m": pct_change(close, 126),
        "pct_1y": pct_change(close, min(252, len(close) - 1)),
        "day_change_pct": pct_from_level(latest_price, open_price.iloc[-1]),
        "volatility_annual": safe_float(volatility_annual),
        "atr14": safe_float(atr14),
        "atr14_pct": (
            safe_float(atr14) / latest_price * 100
            if atr14 is not None and latest_price not in (None, 0)
            else None
        ),
        "avg_volume_20": safe_float(avg_volume_20),
        "avg_volume_60": safe_float(avg_volume_60),
        "last_volume": safe_float(last_volume),
        "volume_ratio_20": safe_float(volume_ratio_20),
        "flow_ratio_20_60": safe_float(flow_ratio_20_60),
        "avg_value_20": safe_float(avg_value_20),
        "range_high_20": safe_float(range_high_20),
        "range_low_20": safe_float(range_low_20),
        "range_high_60": safe_float(range_high_60),
        "range_low_60": safe_float(range_low_60),
        "range_position_20": range_position_pct(
            latest_price, range_low_20, range_high_20
        ),
        "range_position_60": range_position_pct(
            latest_price, range_low_60, range_high_60
        ),
        "breakout_level_20": safe_float(breakout_level_20),
        "breakout_level_60": safe_float(breakout_level_60),
        "support_level_20": safe_float(support_level_20),
        "support_level_60": safe_float(support_level_60),
        "dist_to_breakout_20_pct": pct_from_level(latest_price, breakout_level_20),
        "dist_to_breakout_60_pct": pct_from_level(latest_price, breakout_level_60),
        "dist_to_support_20_pct": pct_from_level(latest_price, support_level_20),
        "dist_to_support_60_pct": pct_from_level(latest_price, support_level_60),
    }


def score_short_term(indicators: dict) -> dict:
    """Score symbol 0-100 for 1-2 month swing suitability."""
    price = safe_float(indicators.get("latest_price"))
    ma20 = safe_float(indicators.get("ma20"))
    ma50 = safe_float(indicators.get("ma50"))
    ma200 = safe_float(indicators.get("ma200"))
    rsi = safe_float(indicators.get("rsi"))
    pct_1m = safe_float(indicators.get("pct_1m"))
    pct_3m = safe_float(indicators.get("pct_3m"))
    volatility = safe_float(indicators.get("volatility_annual"))
    avg_vol_20 = safe_float(indicators.get("avg_volume_20"))
    avg_vol_60 = safe_float(indicators.get("avg_volume_60"))
    last_vol = safe_float(indicators.get("last_volume"))
    vol_ratio = safe_float(indicators.get("volume_ratio_20"))
    flow_ratio = safe_float(indicators.get("flow_ratio_20_60"))
    atr_pct = safe_float(indicators.get("atr14_pct"))
    dist_ma20 = safe_float(indicators.get("dist_ma20_pct"))
    breakout_20 = safe_float(indicators.get("dist_to_breakout_20_pct"))
    breakout_60 = safe_float(indicators.get("dist_to_breakout_60_pct"))
    support_20 = safe_float(indicators.get("dist_to_support_20_pct"))
    range_pos_20 = safe_float(indicators.get("range_position_20"))
    day_change = safe_float(indicators.get("day_change_pct"))
    rs_1m = safe_float(indicators.get("rs_1m"))
    rs_3m = safe_float(indicators.get("rs_3m"))

    trend_score = 0
    if price and ma20 and price > ma20:
        trend_score += 10
    if ma20 and ma50 and ma20 > ma50:
        trend_score += 8
    if price and ma50 and price > ma50:
        trend_score += 6
    if ma50 and ma200 and ma50 > ma200:
        trend_score += 4
    if pct_1m is not None:
        if pct_1m > 12:
            trend_score += 6
        elif pct_1m > 4:
            trend_score += 4
        elif pct_1m > 0:
            trend_score += 3
        elif pct_1m < -8:
            trend_score -= 5
    if pct_3m is not None and pct_3m < -15:
        trend_score -= 4
    if breakout_20 is not None:
        if breakout_20 >= 0:
            trend_score += 6
        elif breakout_20 >= -2:
            trend_score += 3
        elif breakout_20 < -8:
            trend_score -= 3
    if breakout_60 is not None:
        if breakout_60 >= 0:
            trend_score += 4
        elif breakout_60 >= -3:
            trend_score += 2
    if range_pos_20 is not None:
        if range_pos_20 >= 80:
            trend_score += 4
        elif range_pos_20 >= 60:
            trend_score += 2
        elif range_pos_20 < 25:
            trend_score -= 4
    if rs_1m is not None:
        if rs_1m > 5:
            trend_score += 4
        elif rs_1m > 0:
            trend_score += 2
        elif rs_1m < -8:
            trend_score -= 3
    if rs_3m is not None:
        if rs_3m > 8:
            trend_score += 3
        elif rs_3m > 0:
            trend_score += 1
        elif rs_3m < -12:
            trend_score -= 2
    trend_score = max(0, min(trend_score, 40))

    momentum_score = 0
    if rsi is not None:
        if 48 <= rsi <= 65:
            momentum_score = 12
        elif 40 <= rsi < 48 or 65 < rsi <= 72:
            momentum_score = 8
        elif 35 <= rsi < 40 or 72 < rsi <= 78:
            momentum_score = 5
        else:
            momentum_score = 2
    if dist_ma20 is not None:
        if 0 <= dist_ma20 <= 6:
            momentum_score += 4
        elif 6 < dist_ma20 <= 12:
            momentum_score += 2
        elif dist_ma20 > 15:
            momentum_score -= 3
        elif dist_ma20 < -6:
            momentum_score -= 2
    if day_change is not None:
        if day_change >= 2:
            momentum_score += 2
        elif day_change <= -2.5:
            momentum_score -= 2
    momentum_score = max(0, min(momentum_score, 20))

    liquidity_score = 0
    if avg_vol_20 is not None:
        if avg_vol_20 >= 3_000_000:
            liquidity_score += 12
        elif avg_vol_20 >= 1_000_000:
            liquidity_score += 9
        elif avg_vol_20 >= 300_000:
            liquidity_score += 6
        elif avg_vol_20 >= 100_000:
            liquidity_score += 3
        else:
            liquidity_score += 1
    if vol_ratio is not None:
        if vol_ratio >= 1.4:
            liquidity_score += 4
        elif vol_ratio >= 1.0:
            liquidity_score += 2
        elif vol_ratio < 0.6:
            liquidity_score -= 2
    if flow_ratio is not None:
        if flow_ratio >= 1.2:
            liquidity_score += 4
        elif flow_ratio < 0.8:
            liquidity_score -= 2
    if (
        last_vol is not None
        and avg_vol_60
        and avg_vol_60 > 0
        and last_vol > avg_vol_60 * 1.5
    ):
        liquidity_score += 1
    liquidity_score = max(0, min(liquidity_score, 20))

    risk_score = 0
    if volatility is not None:
        if volatility <= 22:
            risk_score = 10
        elif volatility <= 30:
            risk_score = 8
        elif volatility <= 40:
            risk_score = 5
        else:
            risk_score = 2
    if atr_pct is not None:
        if atr_pct <= 3.5:
            risk_score += 5
        elif atr_pct <= 6:
            risk_score += 3
        elif atr_pct <= 8:
            risk_score += 1
        else:
            risk_score -= 2
    if support_20 is not None:
        if 0 <= support_20 <= 8:
            risk_score += 3
        elif support_20 > 18:
            risk_score -= 2
    risk_score = max(0, min(risk_score, 20))

    total = max(0, min(trend_score + momentum_score + liquidity_score + risk_score, 100))
    return {
        "score_total": total,
        "trend_score": trend_score,
        "momentum_score": momentum_score,
        "liquidity_score": liquidity_score,
        "risk_score": risk_score,
    }


def build_symbol_snapshot(
    symbol: str,
    source: str,
    indicators: dict,
    score: dict,
    foreign_text: str = "",
) -> str:
    """Markdown snapshot for one symbol."""
    trade_levels = build_trade_levels(indicators)
    lines = [
        f"### {symbol}",
        f"- Nguon du lieu: {source}",
        f"- Gia dong cua moi nhat: {fmt(indicators['latest_price'])}",
        f"- Bien dong trong phien gan nhat: {fmt(indicators.get('day_change_pct'), '%')}",
        (
            "- MA20 / MA50 / MA200: "
            f"{fmt(indicators['ma20'])} / {fmt(indicators['ma50'])} / {fmt(indicators['ma200'])}"
        ),
        f"- RSI(14): {fmt(indicators['rsi'])}",
        (
            "- Bien dong 1W / 1M / 3M: "
            f"{fmt(indicators['pct_1w'], '%')} / {fmt(indicators['pct_1m'], '%')} / {fmt(indicators['pct_3m'], '%')}"
        ),
        (
            "- Suc manh tuong doi vs VN-Index 1M / 3M: "
            f"{fmt(indicators.get('rs_1m'), '%')} / {fmt(indicators.get('rs_3m'), '%')}"
        ),
        (
            "- ATR(14) / ATR%: "
            f"{fmt(indicators['atr14'])} / {fmt(indicators['atr14_pct'], '%')}"
        ),
        (
            "- Range 20p / 60p: "
            f"{fmt(indicators['range_low_20'])} - {fmt(indicators['range_high_20'])} / "
            f"{fmt(indicators['range_low_60'])} - {fmt(indicators['range_high_60'])}"
        ),
        (
            "- Muc breakout 20p / 60p: "
            f"{fmt(indicators['breakout_level_20'])} / {fmt(indicators['breakout_level_60'])}"
        ),
        (
            "- Muc support 20p / 60p: "
            f"{fmt(indicators['support_level_20'])} / {fmt(indicators['support_level_60'])}"
        ),
        (
            "- Khoang cach breakout 20p / 60p: "
            f"{fmt(indicators['dist_to_breakout_20_pct'], '%')} / {fmt(indicators['dist_to_breakout_60_pct'], '%')}"
        ),
        (
            "- Volume ratio / flow ratio: "
            f"{fmt(indicators['volume_ratio_20'])} / {fmt(indicators['flow_ratio_20_60'])}"
        ),
        (
            "- Diem ky thuat (0-100): "
            f"{fmt(score['score_total'], decimals=0)} "
            f"(trend={fmt(score['trend_score'], decimals=0)}, "
            f"momentum={fmt(score['momentum_score'], decimals=0)}, "
            f"liquidity={fmt(score['liquidity_score'], decimals=0)}, "
            f"risk={fmt(score['risk_score'], decimals=0)})"
        ),
        f"- Trigger ky thuat goi y: {trade_levels['trigger']}",
        f"- Goi y vung mua som: {trade_levels['early_buy_zone']}",
        f"- Goi y vung mua an toan: {trade_levels['safe_buy_zone']}",
        f"- Goi y stop-loss: {trade_levels['stop_loss']}",
        f"- Goi y muc tieu 1-2 thang: {trade_levels['target_1_2m']}",
        f"- Goi y risk/reward: {trade_levels['risk_reward']}",
    ]
    if foreign_text:
        lines.append(f"- {foreign_text}")
    lines.append("")
    return "\n".join(lines)


def build_combined_summary(
    symbol_reports: list[dict],
    as_of_date=None,
    index_summary: str = "",
    foreign_map: dict[str, str] | None = None,
) -> str:
    """Combine multiple symbol snapshots into one markdown block."""
    from datetime import datetime

    foreign_map = foreign_map or {}
    view_date = (as_of_date or datetime.today()).strftime("%Y-%m-%d")
    lines = [
        f"# Du lieu tong hop co phieu ({view_date})",
        "",
        "Boi canh: swing 1-2 thang, uu tien timing, thanh khoan va risk/reward.",
        "Neu da co muc breakout/support/ATR va goi y ky thuat ben duoi, HAY uu tien dung cac muc do de xac dinh vung mua, stop-loss va muc tieu.",
        "",
    ]
    if index_summary:
        lines += [index_summary, ""]
    for item in symbol_reports:
        lines.append(
            build_symbol_snapshot(
                item["symbol"],
                item["source"],
                item["indicators"],
                item["score"],
                foreign_text=foreign_map.get(item["symbol"], ""),
            )
        )
    ranking = sorted(
        symbol_reports, key=lambda x: x["score"]["score_total"], reverse=True
    )
    lines += ["## Xep hang so bo theo diem ky thuat", ""]
    for idx, item in enumerate(ranking, start=1):
        lines.append(f"{idx}. {item['symbol']}: {item['score']['score_total']:.0f}/100")
    lines.append("")
    return "\n".join(lines)
