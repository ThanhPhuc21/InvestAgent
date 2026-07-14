"""Load watchlists and portfolio presets from agents.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from stock_agents.schemas import PositionInput

DEFAULT_PRESETS_FILE = Path(
    os.getenv("STOCK_AGENT_PRESETS_FILE", "agents.json")
)


def _resolve_presets_path(path: Path | None = None) -> Path:
    candidate = path or DEFAULT_PRESETS_FILE
    if candidate.is_absolute():
        return candidate
    return Path.cwd() / candidate


def load_presets(path: Path | None = None) -> dict:
    presets_path = _resolve_presets_path(path)
    if not presets_path.exists():
        raise FileNotFoundError(
            f"Khong tim thay file cau hinh: {presets_path}. "
            "Tao agents.json o thu muc goc project."
        )
    with presets_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"File cau hinh khong hop le: {presets_path}")
    return data


def get_watchlist(name: str, path: Path | None = None) -> list[str]:
    data = load_presets(path)
    watchlists = data.get("watchlists", {})
    if name not in watchlists:
        available = ", ".join(sorted(watchlists)) or "(trong)"
        raise KeyError(
            f"Watchlist '{name}' khong ton tai. Co san: {available}"
        )
    symbols = watchlists[name]
    if not isinstance(symbols, list) or not symbols:
        raise ValueError(f"Watchlist '{name}' rong hoac khong hop le.")
    return [str(sym).strip().upper() for sym in symbols if str(sym).strip()]


def get_portfolio(name: str, path: Path | None = None) -> list[PositionInput]:
    data = load_presets(path)
    portfolios = data.get("portfolios", {})
    if name not in portfolios:
        available = ", ".join(sorted(portfolios)) or "(trong)"
        raise KeyError(
            f"Portfolio '{name}' khong ton tai. Co san: {available}"
        )
    raw_positions = portfolios[name]
    if not isinstance(raw_positions, list) or not raw_positions:
        raise ValueError(f"Portfolio '{name}' rong hoac khong hop le.")
    return [
        PositionInput(
            symbol=str(item["symbol"]).strip().upper(),
            quantity=int(item["quantity"]),
            avg_price=float(item["avg_price"]),
        )
        for item in raw_positions
    ]


def list_watchlists(path: Path | None = None) -> list[str]:
    return sorted(load_presets(path).get("watchlists", {}))


def list_portfolios(path: Path | None = None) -> list[str]:
    return sorted(load_presets(path).get("portfolios", {}))
