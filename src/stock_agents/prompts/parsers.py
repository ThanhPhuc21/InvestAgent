"""Parse structured decisions from LLM markdown output."""

from __future__ import annotations

import re

from stock_agents.schemas import (
    PortfolioAction,
    PortfolioExtraction,
    PortfolioSymbolDecision,
    ShortTermAction,
    ShortTermExtraction,
    ShortTermMarketContext,
    ShortTermSymbolDecision,
    ThesisStatus,
)


def _extract_section(text: str, symbol: str) -> str:
    pattern = rf"###\s*{re.escape(symbol)}\s*\n(.*?)(?=###|\Z)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


def _field(section: str, label: str) -> str:
    pattern = rf"-\s*\*?\*?{re.escape(label)}\*?\*?:\s*(.+)"
    match = re.search(pattern, section, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_action_short(section: str) -> ShortTermAction:
    text = section.lower()
    if "hanh dong" in text:
        if re.search(r"hanh dong.*mua", text) and "theo doi" not in text.split("mua")[0][-20:]:
            if "tranh" not in _field(section, "Hanh dong").lower():
                action_text = _field(section, "Hanh dong").lower()
                if "tranh" in action_text:
                    return ShortTermAction.AVOID
                if "theo doi" in action_text:
                    return ShortTermAction.WATCH
                if "mua" in action_text:
                    return ShortTermAction.BUY
    if re.search(r"\bmua\b", text) and "tranh" not in text:
        return ShortTermAction.BUY
    if "tranh" in text:
        return ShortTermAction.AVOID
    return ShortTermAction.WATCH


def _parse_action_portfolio(section: str) -> PortfolioAction:
    action_text = _field(section, "Hanh dong").lower()
    if "mua them" in action_text or "gia tang" in action_text:
        return PortfolioAction.ADD
    if "ban" in action_text and "mua" not in action_text:
        return PortfolioAction.SELL
    if "giam" in action_text:
        return PortfolioAction.REDUCE
    if "theo doi" in action_text:
        return PortfolioAction.WATCH
    return PortfolioAction.HOLD


def _parse_thesis(section: str) -> ThesisStatus:
    text = _field(section, "Trang thai luan diem").lower() or section.lower()
    if "vo hieu" in text or "broken" in text:
        return ThesisStatus.BROKEN
    if "suy yeu" in text or "weakened" in text:
        return ThesisStatus.WEAKENED
    return ThesisStatus.INTACT


def _parse_rationale(section: str) -> list[str]:
    lines = []
    in_block = False
    for line in section.splitlines():
        low = line.lower().strip()
        if "luan diem" in low or "ly do" in low:
            in_block = True
            continue
        if in_block:
            if line.strip().startswith("- "):
                lines.append(line.strip()[2:])
            elif line.strip().startswith("###"):
                break
    if not lines:
        reason = _field(section, "Ly do")
        if reason:
            lines.append(reason)
    return lines[:5]


def parse_short_term_decisions(
    raw: str, symbols: list[str]
) -> tuple[ShortTermMarketContext, list[ShortTermSymbolDecision], str]:
    """Parse LLM markdown into structured short-term decisions."""
    market = ShortTermMarketContext(
        regime=_field(raw, "Pha thi truong") or "",
        deployment_advice=_field(raw, "Khuyen nghi giai ngan tong the") or "",
    )
    score_match = re.search(r"diem boi canh:\s*(\d+)", raw, re.IGNORECASE)
    if score_match:
        market.score = int(score_match.group(1))

    decisions: list[ShortTermSymbolDecision] = []
    for sym in symbols:
        section = _extract_section(raw, sym)
        action = _parse_action_short(section)
        decisions.append(
            ShortTermSymbolDecision(
                symbol=sym,
                action=action,
                setup=_field(section, "Setup hien tai"),
                early_buy_zone=_field(section, "Vung gia mua som")
                or _field(section, "Vung mua som"),
                safe_buy_zone=_field(section, "Vung gia mua an toan")
                or _field(section, "Vung mua an toan"),
                stop_loss=_field(section, "Stop-loss") or _field(section, "Stop loss"),
                target_1_2m=_field(section, "Gia muc tieu 1-2 thang")
                or _field(section, "Muc tieu"),
                holding_window=_field(section, "Thoi gian nam giu"),
                risk_reward=_field(section, "Ty le risk/reward"),
                rationale=_parse_rationale(section),
            )
        )

    conclusion = ""
    concl_match = re.search(
        r"##\s*ket luan giai ngan.*?\n(.*?)(?=##|\Z)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if concl_match:
        conclusion = concl_match.group(1).strip()

    return market, decisions, conclusion


def extraction_to_short_term(
    extraction: ShortTermExtraction, symbols: list[str]
) -> tuple[ShortTermMarketContext, list[ShortTermSymbolDecision], str]:
    """Convert structured extraction into short-term decision objects."""
    market = ShortTermMarketContext(
        regime=extraction.market_regime,
        score=extraction.market_score,
        deployment_advice=extraction.deployment_advice,
        preferred_sectors=extraction.preferred_sectors,
        avoid_sectors=extraction.avoid_sectors,
        risks=list(extraction.market_risks),
        catalysts=list(extraction.market_catalysts),
    )
    by_symbol = {s.symbol.upper(): s for s in extraction.symbols}
    decisions: list[ShortTermSymbolDecision] = []
    for sym in symbols:
        item = by_symbol.get(sym.upper())
        if item is None:
            decisions.append(
                ShortTermSymbolDecision(symbol=sym, action=ShortTermAction.WATCH)
            )
            continue
        decisions.append(
            ShortTermSymbolDecision(
                symbol=sym,
                action=item.action,
                setup=item.setup,
                early_buy_zone=item.early_buy_zone,
                safe_buy_zone=item.safe_buy_zone,
                stop_loss=item.stop_loss,
                target_1_2m=item.target_1_2m,
                holding_window=item.holding_window,
                risk_reward=item.risk_reward,
                rationale=list(item.rationale)[:5],
            )
        )
    return market, decisions, extraction.deployment_conclusion


def extraction_to_portfolio(
    extraction: PortfolioExtraction, position_reports: list[dict]
) -> tuple[list[PortfolioSymbolDecision], str]:
    """Convert structured extraction into portfolio decision objects."""
    by_symbol = {s.symbol.upper(): s for s in extraction.positions}
    decisions: list[PortfolioSymbolDecision] = []
    for item in position_reports:
        sym = item["symbol"]
        pos = item["position"]
        parsed = by_symbol.get(sym.upper())
        default_ctx = (
            f"Gia von {pos['avg_price']}, gia hien tai {pos['latest_price']}"
        )
        decisions.append(
            PortfolioSymbolDecision(
                symbol=sym,
                action=parsed.action if parsed else PortfolioAction.HOLD,
                thesis_status=parsed.thesis_status if parsed else ThesisStatus.INTACT,
                quantity=pos["quantity"],
                avg_price=pos["avg_price"],
                latest_price=pos["latest_price"],
                pnl_pct=pos.get("pnl_pct"),
                avg_price_context=(
                    parsed.avg_price_context if parsed and parsed.avg_price_context
                    else default_ctx
                ),
                risk_flags=list(parsed.risk_flags)[:3] if parsed else [],
                next_action_zone=parsed.next_action_zone if parsed else "",
                reason=list(parsed.reason)[:5] if parsed else [],
            )
        )
    return decisions, extraction.portfolio_summary


def parse_portfolio_decisions(
    raw: str, position_reports: list[dict]
) -> tuple[list[PortfolioSymbolDecision], str]:
    """Parse portfolio recommendations from LLM markdown."""
    decisions: list[PortfolioSymbolDecision] = []
    for item in position_reports:
        sym = item["symbol"]
        pos = item["position"]
        section = _extract_section(raw, sym)
        decisions.append(
            PortfolioSymbolDecision(
                symbol=sym,
                action=_parse_action_portfolio(section),
                thesis_status=_parse_thesis(section),
                quantity=pos["quantity"],
                avg_price=pos["avg_price"],
                latest_price=pos["latest_price"],
                pnl_pct=pos.get("pnl_pct"),
                avg_price_context=_field(section, "Trang thai vi the")
                or f"Gia von {pos['avg_price']}, gia hien tai {pos['latest_price']}",
                risk_flags=[
                    line.strip("- ").strip()
                    for line in section.splitlines()
                    if line.strip().startswith("- ") and "rui ro" in line.lower()
                ][:3],
                next_action_zone=_field(section, "Vung gia hanh dong tiep theo"),
                reason=_parse_rationale(section),
            )
        )

    summary = ""
    sum_match = re.search(
        r"##\s*tom tat danh muc.*?\n(.*?)(?=##|\Z)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if sum_match:
        summary = sum_match.group(1).strip()

    return decisions, summary
