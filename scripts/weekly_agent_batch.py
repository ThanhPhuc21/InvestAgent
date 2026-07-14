"""Run short-term agent weekly and evaluate multi-horizon."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_agents.agents.short_term_agent import ShortTermAgent
from stock_agents.evaluation import (
    build_multi_horizon_report,
    evaluate_recommendations_multi_horizon,
    save_evaluation_report,
)
from stock_agents.schemas import ShortTermAgentInput

SYMBOLS = ["FPT", "GEX", "VHM", "HCM", "LPB", "POW", "VIX", "HDB", "CII", "MWG"]
START = date(2026, 5, 1)
END = date(2026, 7, 6)
EVAL_AS_OF = date(2026, 7, 12)


def weekly_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=7)
    return dates


def run_weekly_agents() -> list[date]:
    agent = ShortTermAgent(stream=False)
    completed: list[date] = []
    for as_of in weekly_dates(START, END):
        print(f"\n=== Short-term {as_of.isoformat()} ===", flush=True)
        try:
            agent.run(
                ShortTermAgentInput(
                    symbols=SYMBOLS,
                    as_of_date=as_of,
                    top_n=3,
                )
            )
            completed.append(as_of)
            print(f"OK {as_of.isoformat()}", flush=True)
        except Exception as exc:
            print(f"FAIL {as_of.isoformat()}: {exc}", flush=True)
    return completed


def run_evaluation() -> Path:
    print("\n=== Evaluate multi-horizon (14/28/56 ngay) ===", flush=True)
    as_of_dt = datetime.combine(EVAL_AS_OF, datetime.min.time())
    multi = evaluate_recommendations_multi_horizon(
        as_of=as_of_dt,
        horizons=(14, 28, 56),
        actions=("BUY", "WATCH", "AVOID"),
    )
    report = build_multi_horizon_report(multi, as_of=as_of_dt)
    path = save_evaluation_report(report, as_of=as_of_dt, suffix="MULTI_HORIZON")
    for h, summary in sorted(multi["horizons"].items()):
        wr = summary["win_rate"]
        wr_txt = f"{wr:.1f}%" if wr is not None else "N/A"
        ret = summary.get("avg_return_pct")
        ret_txt = f"{ret:+.2f}%" if ret is not None else "N/A"
        print(
            f"  {h}d: mau={summary['total']} win-rate={wr_txt} "
            f"return_TB={ret_txt} expired={summary.get('expired', 0)}",
            flush=True,
        )
    print(f"Report: {path.resolve()}", flush=True)
    return path


if __name__ == "__main__":
    done = run_weekly_agents()
    print(f"\nCompleted {len(done)}/{len(weekly_dates(START, END))} weekly runs.")
    if done:
        run_evaluation()
    else:
        print("No runs completed; skip evaluation.")
        sys.exit(1)
