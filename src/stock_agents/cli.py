"""CLI entrypoints for stock agents."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from stock_agents.agents.portfolio_agent import PortfolioAgent
from stock_agents.agents.short_term_agent import ShortTermAgent
from stock_agents.config import DEFAULT_HISTORY_DAYS, DEFAULT_MODEL, DEFAULT_SOURCE
from stock_agents.schemas import PortfolioAgentInput, PositionInput, ShortTermAgentInput


def _parse_symbols(raw: list[str]) -> list[str]:
    symbols = []
    for token in raw:
        for part in token.split(","):
            sym = part.strip().upper()
            if sym:
                symbols.append(sym)
    seen: set[str] = set()
    unique = []
    for s in symbols:
        if s not in seen:
            unique.append(s)
            seen.add(s)
    return unique


def _parse_position(raw: str) -> PositionInput:
    """Parse SYMBOL:QTY:PRICE format."""
    parts = raw.split(":")
    if len(parts) != 3:
        raise ValueError(
            f"Vi the khong hop le '{raw}'. Dung dinh dang SYMBOL:QTY:PRICE"
        )
    return PositionInput(
        symbol=parts[0].strip().upper(),
        quantity=int(parts[1]),
        avg_price=float(parts[2]),
    )


def _parse_date(raw: str | None):
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


def cmd_short_term(args: argparse.Namespace) -> int:
    symbols = _parse_symbols(args.symbols)
    if len(symbols) < 1:
        print("Can it nhat 1 ma co phieu.", file=sys.stderr)
        return 1

    agent_input = ShortTermAgentInput(
        symbols=symbols,
        as_of_date=_parse_date(args.as_of),
        history_days=args.history_days,
        source=args.source,
        top_n=args.top_n,
        model=args.model,
    )

    print(f"[ShortTermAgent] Phan tich {len(symbols)} ma: {', '.join(symbols)}")
    agent = ShortTermAgent(model=args.model, stream=not args.no_stream)
    result = agent.run(agent_input)

    print(f"\nDa luu bao cao: {result['report_path'].resolve()}")
    for sym, path in result.get("chart_paths", {}).items():
        print(f"  Chart {sym}: {path.resolve()}")

    if result.get("failed"):
        print("\nMa that bai:")
        for sym, err in result["failed"]:
            print(f"  - {sym}: {err}")

    val = result.get("validation", {})
    if val.get("errors"):
        print("\nCanh bao validation:")
        for e in val["errors"]:
            print(f"  - {e}")
    return 0


def cmd_portfolio(args: argparse.Namespace) -> int:
    if not args.position:
        print("Can it nhat 1 --position SYMBOL:QTY:PRICE", file=sys.stderr)
        return 1

    positions = [_parse_position(p) for p in args.position]
    agent_input = PortfolioAgentInput(
        positions=positions,
        as_of_date=_parse_date(args.as_of),
        history_days=args.history_days,
        source=args.source,
        cash_available=args.cash,
        model=args.model,
    )

    syms = ", ".join(p.symbol for p in positions)
    print(f"[PortfolioAgent] Phan tich danh muc: {syms}")
    agent = PortfolioAgent(model=args.model, stream=not args.no_stream)
    result = agent.run(agent_input)

    print(f"\nDa luu bao cao: {result['report_path'].resolve()}")
    for sym, path in result.get("chart_paths", {}).items():
        print(f"  Chart {sym}: {path.resolve()}")

    if result.get("failed"):
        print("\nMa that bai:")
        for sym, err in result["failed"]:
            print(f"  - {sym}: {err}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from stock_agents.evaluation import (
        DEFAULT_EVAL_ACTIONS,
        DEFAULT_HORIZONS,
        build_evaluation_report,
        build_multi_horizon_report,
        evaluate_recommendations,
        evaluate_recommendations_multi_horizon,
        save_evaluation_report,
    )

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of else None
    actions = tuple(a.upper() for a in args.actions) if args.actions else DEFAULT_EVAL_ACTIONS

    if args.multi_horizon:
        horizons = tuple(args.horizon) if args.horizon else DEFAULT_HORIZONS
        print(f"[Evaluate] Danh gia da horizon: {horizons} ngay, actions={actions}")
        multi = evaluate_recommendations_multi_horizon(
            as_of=as_of,
            horizons=horizons,
            actions=actions,
        )
        total = sum(s["total"] for s in multi["horizons"].values())
        if total == 0:
            print(
                "Chua co khuyen nghi nao du dieu kien. "
                "Can log tu short-term agent (BUY/WATCH co entry/stop/target) "
                f"va du tuoi >= horizon ({horizons})."
            )
            return 0
        report = build_multi_horizon_report(multi, as_of=as_of)
        path = save_evaluation_report(report, as_of=as_of, suffix="MULTI_HORIZON")
        for h, summary in sorted(multi["horizons"].items()):
            wr = summary["win_rate"]
            if wr is not None:
                print(f"  {h}d: mau={summary['total']} win-rate={wr:.1f}%")
            else:
                print(f"  {h}d: mau={summary['total']} win-rate=N/A")
            top = summary.get("top_symbols", [])
            if top:
                leaders = ", ".join(
                    f"{item['symbol']} ({item['avg_return_pct']:+.1f}%)"
                    for item in top
                )
                print(f"       Top 3: {leaders}")
        print(f"Da luu bao cao: {path.resolve()}")
        return 0

    horizon = args.horizon[0] if args.horizon else None
    print(
        f"[Evaluate] Dang danh gia (horizon={horizon or 'khong gioi han'}, "
        f"min_age={args.min_age}, actions={actions})..."
    )
    summary = evaluate_recommendations(
        as_of=as_of,
        actions=actions,
        horizon_days=horizon,
        min_age_days=args.min_age,
    )
    if summary["total"] == 0:
        print(
            "Chua co khuyen nghi nao du dieu kien danh gia. "
            "Chay short-term agent truoc, hoac giam --min-age / them --actions."
        )
        if summary.get("skipped_young"):
            print(f"  (Bo qua {summary['skipped_young']} khuyen nghi chua du tuoi)")
        return 0

    report = build_evaluation_report(summary, as_of=as_of)
    suffix = f"{horizon}D" if horizon else ""
    path = save_evaluation_report(report, as_of=as_of, suffix=suffix)

    win_rate = summary["win_rate"]
    avg_r = summary["avg_r"]
    print(
        f"Tong: {summary['total']} | Chot: {summary['resolved']} | "
        f"Thang: {summary['wins']} | Het han: {summary.get('expired', 0)}"
    )
    print(f"Win-rate: {win_rate:.1f}%" if win_rate is not None else "Win-rate: N/A")
    print(f"R-multiple TB: {avg_r:.2f}" if avg_r is not None else "R-multiple TB: N/A")
    if summary.get("avg_return_pct") is not None:
        print(f"Return TB: {summary['avg_return_pct']:+.2f}%")
    top = summary.get("top_symbols", [])
    if top:
        print("Top 3 ma:")
        for idx, item in enumerate(top, start=1):
            print(
                f"  {idx}. {item['symbol']}: TB {item['avg_return_pct']:+.2f}% "
                f"(tot nhat {item['best_return_pct']:+.2f}%)"
            )
    print(f"Da luu bao cao: {path.resolve()}")
    return 0


def cmd_backtest_score(args: argparse.Namespace) -> int:
    from datetime import timedelta

    from stock_agents.presets import get_watchlist
    from stock_agents.score_backtest import (
        DEFAULT_FORWARD_DAYS,
        build_score_backtest_report,
        backtest_scores,
        save_score_backtest_report,
    )

    if args.watchlist:
        symbols = get_watchlist(args.watchlist)
    else:
        symbols = _parse_symbols(args.symbols or [])
    if not symbols:
        print("Can it nhat 1 ma hoac --watchlist.", file=sys.stderr)
        return 1

    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.today()
    start = (
        datetime.strptime(args.start, "%Y-%m-%d")
        if args.start
        else end - timedelta(days=365)
    )
    forward_days = tuple(args.forward_days) if args.forward_days else DEFAULT_FORWARD_DAYS

    print(
        f"[BacktestScore] {len(symbols)} ma, {start.date()} -> {end.date()}, "
        f"forward={forward_days}, step={args.step}"
    )
    summary = backtest_scores(
        symbols=symbols,
        start=start,
        end=end,
        forward_days=forward_days,
        step_days=args.step,
        source=args.source,
    )
    if summary["total_samples"] == 0:
        print("Khong du du lieu de backtest score trong khoang thoi gian nay.")
        if summary.get("failed"):
            for sym, err in summary["failed"]:
                print(f"  - {sym}: {err}")
        return 1

    report = build_score_backtest_report(summary)
    path = save_score_backtest_report(report, end=end)
    print(f"Tong mau: {summary['total_samples']}")
    for b in summary["bucket_stats"]:
        parts = [f"  {b['bucket']}: n={b['count']}"]
        for fd in forward_days:
            avg = b.get(f"avg_return_{fd}d")
            if avg is not None:
                parts.append(f"TB{fd}d={avg:+.2f}%")
        print(" ".join(parts))
    print(f"Da luu bao cao: {path.resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LangChain stock agents cho co phieu Viet Nam"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    st = sub.add_parser(
        "short-term",
        help="Agent 1: quet diem mua swing 1-2 thang",
    )
    st.add_argument("symbols", nargs="+", help="Ma co phieu (VD: FPT VHM)")
    st.add_argument("--as-of", default=None, help="Ngay gioi han YYYY-MM-DD")
    st.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_HISTORY_DAYS,
        help="So ngay lich su",
    )
    st.add_argument("--source", default=DEFAULT_SOURCE, help="VCI hoac KBS")
    st.add_argument("--top-n", type=int, default=3, help="So ma uu tien")
    st.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model")
    st.add_argument("--no-stream", action="store_true", help="Tat stream output")
    st.set_defaults(func=cmd_short_term)

    pf = sub.add_parser(
        "portfolio",
        help="Agent 2: khuyen nghi mua them/giu/ban",
    )
    pf.add_argument(
        "--position",
        action="append",
        required=True,
        help="Vi the SYMBOL:QTY:PRICE (lap lai cho nhieu ma)",
    )
    pf.add_argument("--as-of", default=None, help="Ngay gioi han YYYY-MM-DD")
    pf.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_HISTORY_DAYS,
    )
    pf.add_argument("--source", default=DEFAULT_SOURCE)
    pf.add_argument("--cash", type=float, default=None, help="Tien mat kha dung")
    pf.add_argument("--model", default=DEFAULT_MODEL)
    pf.add_argument("--no-stream", action="store_true")
    pf.set_defaults(func=cmd_portfolio)

    ev = sub.add_parser(
        "evaluate",
        help="Danh gia win-rate/R-multiple tu log khuyen nghi",
    )
    ev.add_argument(
        "--as-of",
        default=None,
        help="Danh gia tinh den ngay YYYY-MM-DD (mac dinh hom nay)",
    )
    ev.add_argument(
        "--horizon",
        type=int,
        action="append",
        help="Gioi han horizon ngay (lap lai cho nhieu muc). VD: --horizon 14 --horizon 28",
    )
    ev.add_argument(
        "--multi-horizon",
        action="store_true",
        help="Danh gia dong thoi 2/4/8 tuan (14/28/56 ngay) neu khong chi dinh --horizon",
    )
    ev.add_argument(
        "--min-age",
        type=int,
        default=0,
        help="Bo qua khuyen nghi moi hon N ngay (mac dinh 0)",
    )
    ev.add_argument(
        "--actions",
        nargs="+",
        default=None,
        help="Actions can danh gia (mac dinh: BUY WATCH)",
    )
    ev.set_defaults(func=cmd_evaluate)

    bt = sub.add_parser(
        "backtest-score",
        help="Backtest score_short_term tren du lieu lich su",
    )
    bt.add_argument(
        "symbols",
        nargs="*",
        help="Ma co phieu (hoac dung --watchlist)",
    )
    bt.add_argument("--watchlist", default=None, help="Ten watchlist trong agents.json")
    bt.add_argument("--start", default=None, help="Ngay bat dau YYYY-MM-DD")
    bt.add_argument("--end", default=None, help="Ngay ket thuc YYYY-MM-DD")
    bt.add_argument(
        "--forward-days",
        type=int,
        nargs="+",
        default=None,
        help="So ngay giao dich do forward return (mac dinh 21 42)",
    )
    bt.add_argument(
        "--step",
        type=int,
        default=21,
        help="Buoc lap walk-forward (ngay, mac dinh 21)",
    )
    bt.add_argument("--source", default=DEFAULT_SOURCE)
    bt.set_defaults(func=cmd_backtest_score)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
