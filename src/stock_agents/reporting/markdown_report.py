"""Markdown report builders."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from stock_agents.config import OUTPUT_DIR
from stock_agents.reporting.validation import build_validation_note
from stock_agents.schemas import (
    PortfolioAgentOutput,
    ShortTermAgentOutput,
    ShortTermSymbolDecision,
)


def _action_vn(action: str) -> str:
    mapping = {
        "BUY": "Mua",
        "WATCH": "Theo doi",
        "AVOID": "Tranh",
        "ADD": "Mua them",
        "HOLD": "Giu",
        "SELL": "Ban",
        "REDUCE": "Giam",
    }
    return mapping.get(action, action)


def build_short_term_report(
    output: ShortTermAgentOutput,
    combined_summary: str,
    chart_paths: dict[str, Path],
    validation: dict | None = None,
    strict: bool = True,
) -> str:
    """Build full markdown report for short-term agent."""
    today = datetime.today().strftime("%Y-%m-%d")
    lines = [
        f"# De xuat swing trade 1-2 thang ({output.as_of_date})",
        "",
        f"*Bao cao tao ngay {today}*",
        "",
    ]

    if validation:
        note = build_validation_note(validation, strict=strict)
        if note:
            lines.append(note)

    if output.raw_analysis:
        lines.append(output.raw_analysis)
        lines.append("")
        if output.symbols:
            lines += [
                "## Ke hoach giao dich ky thuat da chuan hoa",
                "",
                "_Cac muc ben duoi duoc chuan hoa tu output AI va fallback ky thuat MA/support/breakout/ATR khi model bo trong._",
                "",
            ]
            for sym in output.symbols:
                lines += _format_short_term_symbol(sym, chart_paths.get(sym.symbol))
    else:
        lines += [
            "## Boi canh thi truong chung khoan Viet Nam",
            f"- Pha thi truong: {output.market.regime}",
            f"- Diem boi canh: {output.market.score or 'N/A'}/100",
            f"- Khuyen nghi giai ngan: {output.market.deployment_advice}",
            "",
            "## Danh gia tung ma",
            "",
        ]
        for sym in output.symbols:
            lines += _format_short_term_symbol(sym, chart_paths.get(sym.symbol))
        lines += [
            "## Ket luan giai ngan thoi diem hien tai",
            output.deployment_conclusion or "Xem phan tren.",
            "",
        ]

    lines += [
        "---",
        "",
        "## Phu luc: Du lieu ky thuat tu vnstock",
        "",
        combined_summary,
    ]
    return "\n".join(lines)


def _format_short_term_symbol(
    sym: ShortTermSymbolDecision, chart_path: Path | None
) -> list[str]:
    lines = [
        f"### {sym.symbol}",
        f"- **Hanh dong**: {_action_vn(sym.action.value)}",
        f"- Setup: {sym.setup}",
        f"- Vung mua som: {sym.early_buy_zone}",
        f"- Vung mua an toan: {sym.safe_buy_zone}",
        f"- Stop-loss: {sym.stop_loss}",
        f"- Muc tieu 1-2 thang: {sym.target_1_2m}",
        f"- Thoi gian nam giu: {sym.holding_window}",
        f"- Risk/Reward: {sym.risk_reward}",
        "- **Ly do**:",
    ]
    for r in sym.rationale:
        lines.append(f"  - {r}")
    if chart_path and chart_path.exists():
        rel = chart_path.as_posix()
        lines += [
            "",
            f"![Bieu do {sym.symbol}]({rel})",
            "",
        ]
        if sym.action.value == "BUY":
            lines.append(
                "_Duong dut net la kich ban du bao tham khao, khong phai du lieu thuc._"
            )
            lines.append("")
    return lines


def build_portfolio_report(
    output: PortfolioAgentOutput,
    combined_summary: str,
    chart_paths: dict[str, Path],
    validation: dict | None = None,
    strict: bool = True,
) -> str:
    """Build markdown report for portfolio agent."""
    today = datetime.today().strftime("%Y-%m-%d")
    lines = [
        f"# Khuyen nghi danh muc ({output.as_of_date})",
        "",
        f"*Bao cao tao ngay {today}*",
        "",
    ]

    if validation:
        note = build_validation_note(validation, strict=strict)
        if note:
            lines.append(note)

    if output.raw_analysis:
        lines.append(output.raw_analysis)
        lines.append("")
    else:
        lines += [
            "## Tom tat danh muc",
            output.portfolio_summary or "",
            "",
            "## Khuyen nghi tung ma",
            "",
        ]
        for pos in output.positions:
            lines += _format_portfolio_position(pos, chart_paths.get(pos.symbol))
        lines += ["## Ket luan", output.portfolio_summary or "", ""]

    lines += [
        "---",
        "",
        "## Phu luc: Du lieu vi the va ky thuat",
        "",
        combined_summary,
    ]
    return "\n".join(lines)


def _format_portfolio_position(pos, chart_path: Path | None) -> list[str]:
    pnl = f"{pos.pnl_pct:+.2f}%" if pos.pnl_pct is not None else "N/A"
    lines = [
        f"### {pos.symbol}",
        f"- **Hanh dong**: {_action_vn(pos.action.value)}",
        f"- Trang thai luan diem: {pos.thesis_status.value}",
        f"- So luong: {pos.quantity} cp @ {pos.avg_price}",
        f"- Gia hien tai: {pos.latest_price} (PnL: {pnl})",
        f"- Boi canh gia von: {pos.avg_price_context}",
        f"- Vung hanh dong tiep theo: {pos.next_action_zone}",
        "- **Rui ro**:",
    ]
    for f in pos.risk_flags:
        lines.append(f"  - {f}")
    lines.append("- **Ly do**:")
    for r in pos.reason:
        lines.append(f"  - {r}")
    if chart_path and chart_path.exists():
        lines += ["", f"![Bieu do {pos.symbol}]({chart_path.as_posix()})", ""]
    return lines


def save_report(content: str, filename: str, output_dir: Path | None = None) -> Path:
    out = output_dir or OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(content, encoding="utf-8")
    return path
