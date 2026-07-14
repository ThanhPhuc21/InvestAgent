"""Pydantic schemas for agent inputs and structured outputs."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ShortTermAction(str, Enum):
    BUY = "BUY"
    WATCH = "WATCH"
    AVOID = "AVOID"


class PortfolioAction(str, Enum):
    ADD = "ADD"
    HOLD = "HOLD"
    SELL = "SELL"
    REDUCE = "REDUCE"
    WATCH = "WATCH"


class ThesisStatus(str, Enum):
    INTACT = "intact"
    WEAKENED = "weakened"
    BROKEN = "broken"


class PositionInput(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    avg_price: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class ShortTermAgentInput(BaseModel):
    symbols: list[str]
    as_of_date: Optional[date] = None
    history_days: int = 365
    source: str = "VCI"
    top_n: int = 3
    model: Optional[str] = None

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for s in v:
            sym = s.strip().upper()
            if sym and sym not in seen:
                out.append(sym)
                seen.add(sym)
        if not out:
            raise ValueError("Cần ít nhất 1 mã cổ phiếu")
        return out


class PortfolioAgentInput(BaseModel):
    positions: list[PositionInput]
    as_of_date: Optional[date] = None
    history_days: int = 365
    source: str = "VCI"
    cash_available: Optional[float] = None
    model: Optional[str] = None

    @field_validator("positions")
    @classmethod
    def require_positions(cls, v: list[PositionInput]) -> list[PositionInput]:
        if not v:
            raise ValueError("Cần ít nhất 1 vị thế")
        return v


class ShortTermSymbolDecision(BaseModel):
    symbol: str
    action: ShortTermAction
    market_regime: str = ""
    setup: str = ""
    early_buy_zone: str = ""
    safe_buy_zone: str = ""
    stop_loss: str = ""
    target_1_2m: str = ""
    holding_window: str = ""
    risk_reward: str = ""
    rationale: list[str] = Field(default_factory=list)


class ShortTermMarketContext(BaseModel):
    regime: str = ""
    score: Optional[int] = None
    deployment_advice: str = ""
    preferred_sectors: str = ""
    avoid_sectors: str = ""
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)


class ShortTermAgentOutput(BaseModel):
    as_of_date: str
    market: ShortTermMarketContext
    symbols: list[ShortTermSymbolDecision]
    deployment_conclusion: str = ""
    priority_symbol: str = ""
    raw_analysis: str = ""


class PortfolioSymbolDecision(BaseModel):
    symbol: str
    action: PortfolioAction
    thesis_status: ThesisStatus
    quantity: int
    avg_price: float
    latest_price: float
    pnl_pct: Optional[float] = None
    avg_price_context: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    next_action_zone: str = ""
    reason: list[str] = Field(default_factory=list)


class PortfolioAgentOutput(BaseModel):
    as_of_date: str
    positions: list[PortfolioSymbolDecision]
    portfolio_summary: str = ""
    raw_analysis: str = ""


class ShortTermSymbolExtraction(BaseModel):
    """Per-symbol fields the LLM must fill (structured output)."""

    symbol: str
    action: ShortTermAction
    setup: str = ""
    early_buy_zone: str = ""
    safe_buy_zone: str = ""
    stop_loss: str = ""
    target_1_2m: str = ""
    holding_window: str = ""
    risk_reward: str = ""
    rationale: list[str] = Field(default_factory=list)


class ShortTermExtraction(BaseModel):
    """Structured extraction of the short-term analysis markdown."""

    market_regime: str = ""
    market_score: Optional[int] = None
    deployment_advice: str = ""
    preferred_sectors: str = ""
    avoid_sectors: str = ""
    market_risks: list[str] = Field(default_factory=list)
    market_catalysts: list[str] = Field(default_factory=list)
    symbols: list[ShortTermSymbolExtraction] = Field(default_factory=list)
    deployment_conclusion: str = ""


class PortfolioSymbolExtraction(BaseModel):
    """Per-position fields the LLM must fill (structured output)."""

    symbol: str
    action: PortfolioAction
    thesis_status: ThesisStatus
    avg_price_context: str = ""
    next_action_zone: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    reason: list[str] = Field(default_factory=list)


class PortfolioExtraction(BaseModel):
    """Structured extraction of the portfolio analysis markdown."""

    portfolio_summary: str = ""
    positions: list[PortfolioSymbolExtraction] = Field(default_factory=list)


class SymbolReportBundle(BaseModel):
    """Internal bundle for one symbol during pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    source: str
    df_json: str = ""
    indicators: dict = Field(default_factory=dict)
    score: dict = Field(default_factory=dict)
    fundamentals_summary: str = ""
    position: Optional[dict] = None
