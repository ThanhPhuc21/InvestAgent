"""Walk-forward backtest of ``score_short_term`` on historical OHLCV.

Scores each symbol at periodic cut-off dates, then measures forward return
over 1-2 month horizons. Use the bucket summary to judge whether higher scores
actually predict better forward performance.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from stock_agents.config import DEFAULT_HISTORY_DAYS, DEFAULT_SOURCE, OUTPUT_DIR
from stock_agents.features.market_context import get_index_ohlcv
from stock_agents.features.technical_features import compute_indicators, score_short_term
from stock_agents.tools.vnstock_tools import get_stock_data

DEFAULT_FORWARD_DAYS = (21, 42)  # ~1M and ~2M trading sessions
DEFAULT_STEP_DAYS = 21
SCORE_BUCKETS = (
    (0, 40, "0-39"),
    (40, 60, "40-59"),
    (60, 80, "60-79"),
    (80, 101, "80-100"),
)


def _bucket_label(score: float) -> str:
    for low, high, label in SCORE_BUCKETS:
        if low <= score < high:
            return label
    return "unknown"


def _cutoff_dates(
    start: datetime, end: datetime, step_days: int, max_forward: int
) -> list[datetime]:
    """Generate as-of dates that still leave room for forward measurement."""
    last_cutoff = end - timedelta(days=max_forward)
    if last_cutoff < start:
        return []
    dates: list[datetime] = []
    current = start
    while current <= last_cutoff:
        dates.append(current)
        current += timedelta(days=step_days)
    return dates


def _forward_return(close: pd.Series, as_of_idx: int, forward_days: int) -> float | None:
    if as_of_idx + forward_days >= len(close):
        return None
    base = float(close.iloc[as_of_idx])
    if base <= 0:
        return None
    future = float(close.iloc[as_of_idx + forward_days])
    return (future / base - 1) * 100


def backtest_symbol_scores(
    symbol: str,
    start: datetime,
    end: datetime,
    forward_days: tuple[int, ...] = DEFAULT_FORWARD_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
    source: str = DEFAULT_SOURCE,
    history_days: int = DEFAULT_HISTORY_DAYS,
) -> list[dict]:
    """Walk-forward score vs forward return for one symbol."""
    max_forward = max(forward_days)
    cutoffs = _cutoff_dates(start, end, step_days, max_forward)
    if not cutoffs:
        return []

    span = (end - start).days + history_days + max_forward + 30
    try:
        df, _ = get_stock_data(
            symbol,
            source=source,
            history_days=span,
            end_date=end,
        )
    except Exception:
        return []

    if df is None or df.empty:
        return []

    df = df.copy().sort_values("time").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["time"])
    close = pd.to_numeric(df["close"], errors="coerce")

    index_df = get_index_ohlcv(
        source=source, history_days=span, end_date=end
    )

    rows: list[dict] = []
    for cutoff in cutoffs:
        mask = df["time"] <= cutoff
        if not mask.any():
            continue
        sub = df.loc[mask].reset_index(drop=True)
        if len(sub) < 60:
            continue

        idx_sub = None
        if index_df is not None and not index_df.empty:
            idx_sub = index_df[index_df["time"] <= cutoff].reset_index(drop=True)

        indicators = compute_indicators(sub, index_df=idx_sub)
        score = score_short_term(indicators)
        as_of_idx = len(sub) - 1

        row_base = {
            "symbol": symbol.upper(),
            "as_of_date": cutoff.strftime("%Y-%m-%d"),
            "score_total": score["score_total"],
            "score_bucket": _bucket_label(score["score_total"]),
            "close_at_cutoff": float(close.iloc[as_of_idx]),
        }
        for fd in forward_days:
            ret = _forward_return(close, as_of_idx, fd)
            if ret is not None:
                row_base[f"return_{fd}d_pct"] = ret
        if any(k.startswith("return_") for k in row_base):
            rows.append(row_base)
    return rows


def backtest_scores(
    symbols: list[str],
    start: datetime,
    end: datetime,
    forward_days: tuple[int, ...] = DEFAULT_FORWARD_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
    source: str = DEFAULT_SOURCE,
) -> dict:
    """Run walk-forward score backtest across symbols."""
    all_rows: list[dict] = []
    failed: list[tuple[str, str]] = []
    for sym in symbols:
        try:
            rows = backtest_symbol_scores(
                sym,
                start=start,
                end=end,
                forward_days=forward_days,
                step_days=step_days,
                source=source,
            )
            if rows:
                all_rows.extend(rows)
            else:
                failed.append((sym, "Khong du du lieu trong khoang thoi gian"))
        except Exception as exc:
            failed.append((sym, str(exc)))

    bucket_stats = _aggregate_buckets(all_rows, forward_days)
    return {
        "symbols": symbols,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "forward_days": list(forward_days),
        "step_days": step_days,
        "total_samples": len(all_rows),
        "rows": all_rows,
        "bucket_stats": bucket_stats,
        "failed": failed,
    }


def _aggregate_buckets(rows: list[dict], forward_days: tuple[int, ...]) -> list[dict]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    stats: list[dict] = []
    for low, high, label in SCORE_BUCKETS:
        bucket = df[df["score_bucket"] == label]
        if bucket.empty:
            continue
        entry: dict = {"bucket": label, "count": len(bucket)}
        for fd in forward_days:
            col = f"return_{fd}d_pct"
            if col in bucket.columns:
                entry[f"avg_return_{fd}d"] = float(bucket[col].mean())
                entry[f"median_return_{fd}d"] = float(bucket[col].median())
                entry[f"win_rate_{fd}d"] = float((bucket[col] > 0).mean() * 100)
        stats.append(entry)
    return stats


def build_score_backtest_report(summary: dict) -> str:
    """Render score backtest results as markdown."""
    lines = [
        "# Backtest score_short_term (walk-forward)",
        "",
        f"- Ma: {', '.join(summary['symbols'])}",
        f"- Khoang: {summary['start']} -> {summary['end']}",
        f"- Forward horizons (ngay giao dich): {summary['forward_days']}",
        f"- Buoc lap: {summary['step_days']} ngay",
        f"- Tong mau: {summary['total_samples']}",
        "",
        "## Ket qua theo bucket diem",
        "",
    ]
    if not summary["bucket_stats"]:
        lines.append("_Khong du mau de tong hop._")
    else:
        fwd = summary["forward_days"]
        header = "| Bucket | So mau |"
        sep = "| --- | --- |"
        for fd in fwd:
            header += f" TB return {fd}d | Win% {fd}d |"
            sep += " --- | --- |"
        lines += [header, sep]
        for b in summary["bucket_stats"]:
            row = f"| {b['bucket']} | {b['count']} |"
            for fd in fwd:
                avg = b.get(f"avg_return_{fd}d")
                wr = b.get(f"win_rate_{fd}d")
                avg_txt = f"{avg:+.2f}%" if avg is not None else "-"
                wr_txt = f"{wr:.1f}%" if wr is not None else "-"
                row += f" {avg_txt} | {wr_txt} |"
            lines.append(row)

    if summary.get("failed"):
        lines += ["", "## Ma that bai", ""]
        for sym, err in summary["failed"]:
            lines.append(f"- {sym}: {err}")

    lines += [
        "",
        "## Ghi chu",
        "",
        "- Neu bucket 60-79 / 80-100 co return va win-rate cao hon ro ret so voi 0-39, "
        "he thong score dang co gia tri du doan.",
        "- Neu cac bucket gan nhu nhau, can dieu chinh lai trong so trend/momentum/liquidity/risk.",
        "",
    ]
    return "\n".join(lines)


def save_score_backtest_report(content: str, end: datetime | None = None) -> Path:
    end = end or datetime.today()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"SCORE_BACKTEST_{end.strftime('%Y-%m-%d')}.md"
    path.write_text(content, encoding="utf-8")
    return path
