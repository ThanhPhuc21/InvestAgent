"""Append and read swing-trade recommendation logs (JSONL) for evaluation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from stock_agents.config import OUTPUT_DIR
from stock_agents.schemas import ShortTermAgentOutput

DEFAULT_LOG_FILE = OUTPUT_DIR / "recommendations.jsonl"


def _normalize_price_text(text: str) -> str:
    """Normalize unicode dashes and separators for numeric extraction."""
    return (
        str(text)
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace(",", "")
    )


def _avg_price(text: str, n: int = 2) -> float | None:
    if not text:
        return None
    nums = re.findall(r"\d+(?:[.,]\d+)?", _normalize_price_text(text))
    if not nums:
        return None
    values = [float(x) for x in nums[:n]]
    return sum(values) / len(values)


def _first_price(text: str) -> float | None:
    if not text:
        return None
    nums = re.findall(r"\d+(?:[.,]\d+)?", _normalize_price_text(text))
    return float(nums[0]) if nums else None


def log_short_term_recommendations(
    output: ShortTermAgentOutput,
    score_map: dict[str, float] | None = None,
    source: str = "",
    model: str = "",
    log_file: Path | None = None,
) -> Path:
    """Append one JSONL row per symbol decision for later evaluation."""
    path = log_file or DEFAULT_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    score_map = score_map or {}
    logged_at = datetime.now().isoformat(timespec="seconds")

    rows: list[dict] = []
    for dec in output.symbols:
        entry = _avg_price(dec.safe_buy_zone) or _avg_price(dec.early_buy_zone)
        rows.append(
            {
                "logged_at": logged_at,
                "as_of_date": output.as_of_date,
                "agent": "short_term",
                "symbol": dec.symbol,
                "action": dec.action.value,
                "source": source,
                "model": model,
                "score": score_map.get(dec.symbol),
                "early_buy_zone": dec.early_buy_zone,
                "safe_buy_zone": dec.safe_buy_zone,
                "stop_loss": dec.stop_loss,
                "target_1_2m": dec.target_1_2m,
                "risk_reward": dec.risk_reward,
                "entry_price": entry,
                "stop_price": _first_price(dec.stop_loss),
                "target_price": _avg_price(dec.target_1_2m),
            }
        )

    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def read_recommendations(log_file: Path | None = None) -> list[dict]:
    """Read all logged recommendations from JSONL."""
    path = log_file or DEFAULT_LOG_FILE
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
