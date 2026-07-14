"""Evaluate logged recommendations against realized prices.

Supports fixed horizons (2/4/8 weeks), multiple actions (BUY/WATCH), score
buckets, and minimum age filtering so you only evaluate mature signals.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from stock_agents.config import DEFAULT_SOURCE, OUTPUT_DIR
from stock_agents.reporting.recommendation_log import read_recommendations
from stock_agents.tools.vnstock_tools import get_stock_data

# Calendar-day horizons matching ~2 / 4 / 8 weeks
DEFAULT_HORIZONS = (14, 28, 56)
SCORE_BUCKETS = (
    (0, 40, "0-39"),
    (40, 60, "40-59"),
    (60, 80, "60-79"),
    (80, 101, "80-100"),
)
DEFAULT_EVAL_ACTIONS = ("BUY", "WATCH")
TOP_SYMBOLS_N = 3
HORIZON_WEEK_LABELS = {14: "2 tuan", 28: "4 tuan", 56: "8 tuan"}


def _bucket_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    for low, high, label in SCORE_BUCKETS:
        if low <= score < high:
            return label
    return "unknown"


def _parse_rec_date(rec_date_str: str) -> datetime | None:
    try:
        return datetime.strptime(rec_date_str[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _evaluate_one(
    rec: dict,
    as_of: datetime,
    horizon_days: int | None = None,
) -> dict | None:
    """Walk forward from recommendation date; optional fixed horizon cap."""
    entry = rec.get("entry_price")
    stop = rec.get("stop_price")
    target = rec.get("target_price")
    rec_date_str = rec.get("as_of_date")
    if entry is None or stop is None or target is None or not rec_date_str:
        return None
    if not (stop < entry < target):
        return None

    rec_date = _parse_rec_date(rec_date_str)
    if rec_date is None:
        return None

    eval_end = as_of
    if horizon_days is not None:
        horizon_end = rec_date + timedelta(days=horizon_days)
        if horizon_end < eval_end:
            eval_end = horizon_end

    horizon_span = (eval_end - rec_date).days + 5
    if horizon_span <= 0:
        return None

    try:
        df, _ = get_stock_data(
            rec["symbol"],
            source=rec.get("source") or DEFAULT_SOURCE,
            history_days=horizon_span,
            end_date=eval_end,
        )
    except Exception:
        return None

    df = df[pd.to_datetime(df["time"]) > rec_date].reset_index(drop=True)
    if df.empty:
        return None

    if horizon_days is not None:
        cutoff = rec_date + timedelta(days=horizon_days)
        df = df[pd.to_datetime(df["time"]) <= cutoff].reset_index(drop=True)
        if df.empty:
            return None

    risk = entry - stop
    outcome = "open"
    exit_price = None
    exit_date = None
    for _, row in df.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        hit_stop = low <= stop
        hit_target = high >= target
        if hit_stop and hit_target:
            outcome = "stop"
            exit_price = stop
            exit_date = row["time"]
            break
        if hit_stop:
            outcome = "stop"
            exit_price = stop
            exit_date = row["time"]
            break
        if hit_target:
            outcome = "target"
            exit_price = target
            exit_date = row["time"]
            break

    if outcome == "open":
        if horizon_days is not None:
            outcome = "expired"
        exit_price = float(df["close"].iloc[-1])
        exit_date = df["time"].iloc[-1]

    r_multiple = (exit_price - entry) / risk if risk > 0 else None
    return_pct = (exit_price / entry - 1) * 100 if entry else None

    return {
        "symbol": rec["symbol"],
        "as_of_date": rec_date_str,
        "action": rec.get("action"),
        "score": rec.get("score"),
        "score_bucket": _bucket_label(rec.get("score")),
        "horizon_days": horizon_days,
        "entry": entry,
        "stop": stop,
        "target": target,
        "outcome": outcome,
        "exit_price": exit_price,
        "exit_date": str(exit_date)[:10] if exit_date is not None else None,
        "r_multiple": r_multiple,
        "return_pct": return_pct,
        "days_held": (eval_end - rec_date).days,
    }


def _summarize_results(results: list[dict]) -> dict:
    resolved = [r for r in results if r["outcome"] in ("stop", "target")]
    wins = [r for r in resolved if r["outcome"] == "target"]
    expired = [r for r in results if r["outcome"] == "expired"]
    r_values = [r["r_multiple"] for r in results if r["r_multiple"] is not None]
    ret_values = [r["return_pct"] for r in results if r["return_pct"] is not None]

    return {
        "total": len(results),
        "resolved": len(resolved),
        "wins": len(wins),
        "expired": len(expired),
        "win_rate": (len(wins) / len(resolved) * 100) if resolved else None,
        "avg_r": (sum(r_values) / len(r_values)) if r_values else None,
        "avg_return_pct": (sum(ret_values) / len(ret_values)) if ret_values else None,
        "results": results,
        "by_bucket": _bucket_summary(results),
        "by_action": _group_summary(results, "action"),
        "top_symbols": _top_symbols_by_return(results),
    }


def _bucket_summary(results: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for r in results:
        buckets.setdefault(r.get("score_bucket", "unknown"), []).append(r)
    out = []
    for label in [b[2] for b in SCORE_BUCKETS] + ["unknown"]:
        items = buckets.get(label, [])
        if not items:
            continue
        resolved = [x for x in items if x["outcome"] in ("stop", "target")]
        wins = [x for x in resolved if x["outcome"] == "target"]
        rets = [x["return_pct"] for x in items if x.get("return_pct") is not None]
        out.append(
            {
                "bucket": label,
                "count": len(items),
                "win_rate": (len(wins) / len(resolved) * 100) if resolved else None,
                "avg_return_pct": (sum(rets) / len(rets)) if rets else None,
            }
        )
    return out


def _top_symbols_by_return(results: list[dict], top_n: int = TOP_SYMBOLS_N) -> list[dict]:
    """Rank symbols by average realized return within a horizon."""
    by_symbol: dict[str, list[dict]] = {}
    for row in results:
        if row.get("return_pct") is None:
            continue
        by_symbol.setdefault(row["symbol"], []).append(row)

    ranked: list[dict] = []
    for symbol, rows in by_symbol.items():
        returns = [r["return_pct"] for r in rows]
        best_row = max(rows, key=lambda r: r["return_pct"])
        ranked.append(
            {
                "symbol": symbol,
                "avg_return_pct": sum(returns) / len(returns),
                "best_return_pct": max(returns),
                "samples": len(rows),
                "best_action": best_row.get("action"),
                "best_as_of_date": best_row.get("as_of_date"),
                "best_outcome": best_row.get("outcome"),
            }
        )

    ranked.sort(
        key=lambda item: (item["avg_return_pct"], item["best_return_pct"]),
        reverse=True,
    )
    return ranked[:top_n]


def _format_top_symbols_section(
    top_symbols: list[dict],
    horizon_days: int | None = None,
) -> list[str]:
    if not top_symbols:
        return []

    week_label = HORIZON_WEEK_LABELS.get(horizon_days or 0, "")
    horizon_title = f"{horizon_days} ngay"
    if week_label:
        horizon_title += f" (~{week_label})"

    lines = [
        f"## Top {TOP_SYMBOLS_N} ma hieu suat cao nhat ({horizon_title})",
        "",
        "_Xep hang theo return trung binh cua tat ca khuyen nghi cua ma trong horizon._",
        "",
        "| Hang | Ma | TB return | Return tot nhat | So mau | Lan tot nhat |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for idx, item in enumerate(top_symbols, start=1):
        best_note = (
            f"{item['best_as_of_date']} ({item.get('best_action', '-')}, "
            f"{item.get('best_outcome', '-')})"
        )
        lines.append(
            f"| {idx} | {item['symbol']} | {item['avg_return_pct']:+.2f}% | "
            f"{item['best_return_pct']:+.2f}% | {item['samples']} | {best_note} |"
        )
    lines.append("")
    return lines


def _group_summary(results: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(str(r.get(key, "?")), []).append(r)
    out = []
    for name, items in sorted(groups.items()):
        resolved = [x for x in items if x["outcome"] in ("stop", "target")]
        wins = [x for x in resolved if x["outcome"] == "target"]
        rets = [x["return_pct"] for x in items if x.get("return_pct") is not None]
        out.append(
            {
                "group": name,
                "count": len(items),
                "win_rate": (len(wins) / len(resolved) * 100) if resolved else None,
                "avg_return_pct": (sum(rets) / len(rets)) if rets else None,
            }
        )
    return out


def evaluate_recommendations(
    log_file: Path | None = None,
    as_of: datetime | None = None,
    actions: tuple[str, ...] = DEFAULT_EVAL_ACTIONS,
    horizon_days: int | None = None,
    min_age_days: int = 0,
) -> dict:
    """Evaluate logged recommendations; optionally cap at a fixed horizon."""
    as_of = as_of or datetime.today()
    recs = read_recommendations(log_file)
    results: list[dict] = []
    skipped_young = 0
    skipped_invalid = 0

    for rec in recs:
        if rec.get("action") not in actions:
            continue
        rec_date = _parse_rec_date(rec.get("as_of_date", ""))
        if rec_date is None:
            skipped_invalid += 1
            continue
        age = (as_of - rec_date).days
        if age < min_age_days:
            skipped_young += 1
            continue
        evaluated = _evaluate_one(rec, as_of, horizon_days=horizon_days)
        if evaluated is not None:
            results.append(evaluated)
        else:
            skipped_invalid += 1

    summary = _summarize_results(results)
    summary["horizon_days"] = horizon_days
    summary["skipped_young"] = skipped_young
    summary["skipped_invalid"] = skipped_invalid
    summary["actions"] = list(actions)
    return summary


def evaluate_recommendations_multi_horizon(
    log_file: Path | None = None,
    as_of: datetime | None = None,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    actions: tuple[str, ...] = DEFAULT_EVAL_ACTIONS,
) -> dict:
    """Run evaluation at each horizon (e.g. 14/28/56 days)."""
    as_of = as_of or datetime.today()
    by_horizon: dict[int, dict] = {}
    for h in horizons:
        by_horizon[h] = evaluate_recommendations(
            log_file=log_file,
            as_of=as_of,
            actions=actions,
            horizon_days=h,
            min_age_days=h,
        )
    return {"as_of": as_of.strftime("%Y-%m-%d"), "horizons": by_horizon}


def build_evaluation_report(
    summary: dict,
    as_of: datetime | None = None,
    title_suffix: str = "",
) -> str:
    """Render evaluation results as markdown."""
    as_of = as_of or datetime.today()
    horizon = summary.get("horizon_days")
    horizon_txt = f"{horizon} ngay" if horizon else "khong gioi han"
    lines = [
        f"# Danh gia khuyen nghi{title_suffix} (tinh den {as_of.strftime('%Y-%m-%d')})",
        "",
        f"- Horizon: {horizon_txt}",
        f"- Actions: {', '.join(summary.get('actions', DEFAULT_EVAL_ACTIONS))}",
        f"- Tong so khuyen nghi danh gia: {summary['total']}",
        f"- Bo qua (chua du tuoi): {summary.get('skipped_young', 0)}",
        f"- Bo qua (khong hop le): {summary.get('skipped_invalid', 0)}",
        f"- Da chot (cham stop/target): {summary['resolved']}",
        f"- Het han (chua cham muc trong horizon): {summary.get('expired', 0)}",
        f"- So lenh thang: {summary['wins']}",
        (
            f"- Win-rate (stop vs target): {summary['win_rate']:.1f}%"
            if summary["win_rate"] is not None
            else "- Win-rate: N/A"
        ),
        (
            f"- R-multiple trung binh: {summary['avg_r']:.2f}"
            if summary["avg_r"] is not None
            else "- R-multiple trung binh: N/A"
        ),
        (
            f"- Return trung binh: {summary['avg_return_pct']:+.2f}%"
            if summary.get("avg_return_pct") is not None
            else "- Return trung binh: N/A"
        ),
        "",
    ]

    if summary.get("by_bucket"):
        lines += ["## Theo bucket diem", "", "| Bucket | So mau | Win-rate | TB return |", "| --- | --- | --- | --- |"]
        for b in summary["by_bucket"]:
            wr = f"{b['win_rate']:.1f}%" if b["win_rate"] is not None else "-"
            ret = f"{b['avg_return_pct']:+.2f}%" if b["avg_return_pct"] is not None else "-"
            lines.append(f"| {b['bucket']} | {b['count']} | {wr} | {ret} |")
        lines.append("")

    if summary.get("by_action"):
        lines += ["## Theo hanh dong", "", "| Action | So mau | Win-rate | TB return |", "| --- | --- | --- | --- |"]
        for g in summary["by_action"]:
            wr = f"{g['win_rate']:.1f}%" if g["win_rate"] is not None else "-"
            ret = f"{g['avg_return_pct']:+.2f}%" if g["avg_return_pct"] is not None else "-"
            lines.append(f"| {g['group']} | {g['count']} | {wr} | {ret} |")
        lines.append("")

    lines += _format_top_symbols_section(
        summary.get("top_symbols", []),
        horizon_days=summary.get("horizon_days"),
    )

    lines += [
        "## Chi tiet",
        "",
        "| Ma | Ngay | Action | Score | Horizon | Entry | Stop | Target | Ket qua | Return | R |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in summary["results"]:
        score = f"{r['score']:.0f}" if r.get("score") is not None else "-"
        r_txt = f"{r['r_multiple']:.2f}" if r["r_multiple"] is not None else "-"
        ret_txt = f"{r['return_pct']:+.2f}%" if r.get("return_pct") is not None else "-"
        h_txt = str(r.get("horizon_days") or "-")
        lines.append(
            f"| {r['symbol']} | {r['as_of_date']} | {r.get('action', '-')} | {score} | "
            f"{h_txt} | {r['entry']:.2f} | {r['stop']:.2f} | {r['target']:.2f} | "
            f"{r['outcome']} | {ret_txt} | {r_txt} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_multi_horizon_report(multi: dict, as_of: datetime | None = None) -> str:
    as_of = as_of or datetime.today()
    lines = [
        f"# Danh gia khuyen nghi da horizon (tinh den {as_of.strftime('%Y-%m-%d')})",
        "",
        "So sanh ket qua tai cac muc 2 / 4 / 8 tuan (~14 / 28 / 56 ngay).",
        "",
        "| Horizon | Mau | Win-rate | TB R | TB return | Het han |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for h, summary in sorted(multi["horizons"].items()):
        wr = f"{summary['win_rate']:.1f}%" if summary["win_rate"] is not None else "-"
        avg_r = f"{summary['avg_r']:.2f}" if summary["avg_r"] is not None else "-"
        ret = (
            f"{summary['avg_return_pct']:+.2f}%"
            if summary.get("avg_return_pct") is not None
            else "-"
        )
        lines.append(
            f"| {h} ngay | {summary['total']} | {wr} | {avg_r} | {ret} | {summary.get('expired', 0)} |"
        )
    lines.append("")

    lines += ["## Top 3 ma hieu suat cao nhat theo tung horizon", ""]
    for h, summary in sorted(multi["horizons"].items()):
        lines += _format_top_symbols_section(summary.get("top_symbols", []), horizon_days=h)
    lines.append("")

    for h, summary in sorted(multi["horizons"].items()):
        if summary["total"] == 0:
            continue
        lines.append(build_evaluation_report(summary, as_of=as_of, title_suffix=f" — {h} ngay"))
    return "\n".join(lines)


def save_evaluation_report(
    content: str,
    as_of: datetime | None = None,
    suffix: str = "",
) -> Path:
    as_of = as_of or datetime.today()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"_{suffix}" if suffix else ""
    path = OUTPUT_DIR / f"EVALUATION{tag}_{as_of.strftime('%Y-%m-%d')}.md"
    path.write_text(content, encoding="utf-8")
    return path
