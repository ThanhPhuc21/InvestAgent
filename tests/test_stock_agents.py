"""Tests for stock_agents package."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_agents.features.portfolio_features import (
    build_portfolio_risk_summary,
    build_position_info,
)
from stock_agents.features.technical_features import (
    build_trade_levels,
    compute_indicators,
    compute_relative_strength,
    score_short_term,
)
from stock_agents.prompts.parsers import (
    extraction_to_short_term,
    parse_portfolio_decisions,
    parse_short_term_decisions,
)
from stock_agents.reporting.chart_renderer import build_forecast_series
from stock_agents.reporting.validation import validate_analysis_output
from stock_agents.schemas import (
    PositionInput,
    ShortTermAction,
    ShortTermAgentInput,
    ShortTermExtraction,
    ShortTermSymbolDecision,
    ShortTermSymbolExtraction,
)


def _sample_ohlcv(n: int = 120) -> pd.DataFrame:
    import numpy as np

    dates = pd.bdate_range("2025-01-01", periods=n)
    close = 100 + np.cumsum(np.random.default_rng(42).normal(0, 1, n))
    return pd.DataFrame(
        {
            "time": dates,
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.random.default_rng(42).integers(100_000, 500_000, n),
        }
    )


def test_compute_indicators_keys():
    df = _sample_ohlcv()
    ind = compute_indicators(df)
    assert "latest_price" in ind
    assert "rsi" in ind
    assert "ma20" in ind


def test_score_short_term_range():
    df = _sample_ohlcv()
    ind = compute_indicators(df)
    score = score_short_term(ind)
    assert 0 <= score["score_total"] <= 100


def test_build_position_info_pnl():
    pos = build_position_info(price=110.0, quantity=100, avg_price=100.0)
    assert pos is not None
    assert pos["pnl_pct"] == pytest.approx(10.0)
    assert pos["market_value"] == 11000.0


def test_short_term_agent_input_validation():
    inp = ShortTermAgentInput(symbols=["fpt", "VHM"])
    assert inp.symbols == ["FPT", "VHM"]


def test_position_input():
    pos = PositionInput(symbol="fpt", quantity=50, avg_price=95.5)
    assert pos.symbol == "FPT"


def test_parse_short_term_decisions():
    raw = """
## Boi canh thi truong chung khoan Viet Nam
- Pha thi truong: Uptrend
- Diem boi canh: 65/100

## Danh gia tung ma
### FPT
- Setup hien tai: Breakout
- Hanh dong: Mua
- Vung gia mua som: 95-97
- Vung gia mua an toan: 93-95
- Stop-loss: 90
- Gia muc tieu 1-2 thang: 105
- Thoi gian nam giu: 4-8 tuan
- Ty le risk/reward: 1:2
- Luan diem:
  - Timing tot
  - Catalyst BCTC

## Ket luan giai ngan thoi diem hien tai
- Co nen giai ngan luc nay? Co
"""
    market, decisions, conclusion = parse_short_term_decisions(raw, ["FPT"])
    assert decisions[0].action == ShortTermAction.BUY
    assert decisions[0].safe_buy_zone
    assert "giai ngan" in conclusion.lower() or conclusion == ""


def test_parse_portfolio_decisions():
    raw = """
## Tom tat danh muc
- Tong quan: Dang lai nhe

## Khuyen nghi tung ma
### FPT
- Trang thai vi the: Lai 5%
- Trang thai luan diem: con nguyen ven
- Hanh dong: Giu
- Vung gia hanh dong tiep theo: 95-100
- Ly do:
  - Thesis con tot

## Ket luan
- Hanh dong uu tien: Giu FPT
"""
    reports = [
        {
            "symbol": "FPT",
            "position": build_position_info(105, 100, 100),
        }
    ]
    decisions, summary = parse_portfolio_decisions(raw, reports)
    assert decisions[0].symbol == "FPT"
    assert decisions[0].action.value == "HOLD"


def test_forecast_only_for_buy():
    df = _sample_ohlcv()
    buy_decision = ShortTermSymbolDecision(
        symbol="FPT",
        action=ShortTermAction.BUY,
        safe_buy_zone="98",
        target_1_2m="110",
    )
    watch_decision = ShortTermSymbolDecision(
        symbol="FPT",
        action=ShortTermAction.WATCH,
        safe_buy_zone="98",
        target_1_2m="110",
    )
    assert build_forecast_series(df, buy_decision) is not None
    assert build_forecast_series(df, watch_decision) is None


def test_validate_analysis_missing_sections():
    result = validate_analysis_output("No sections here", mode="short_term")
    assert result["errors"]


def test_rsi_is_bounded():
    df = _sample_ohlcv()
    ind = compute_indicators(df)
    assert ind["rsi"] is not None
    assert 0 <= ind["rsi"] <= 100


def test_relative_strength_sign():
    strong = pd.Series([100.0 + i for i in range(80)])
    weak_index = pd.DataFrame(
        {"time": pd.bdate_range("2025-01-01", periods=80), "close": [100.0] * 80}
    )
    rs = compute_relative_strength(strong, weak_index)
    assert rs["rs_1m"] is not None
    assert rs["rs_1m"] > 0


def test_compute_indicators_with_index_adds_rs():
    df = _sample_ohlcv()
    idx = _sample_ohlcv()
    ind = compute_indicators(df, index_df=idx)
    assert "rs_1m" in ind
    assert "rs_3m" in ind


def test_trade_levels_min_stop_distance():
    df = _sample_ohlcv()
    ind = compute_indicators(df)
    levels = build_trade_levels(ind)
    atr = ind["atr14"]
    price = ind["latest_price"]
    stop = float(levels["stop_loss"].replace(",", ""))
    # stop must sit at least ~1.5 ATR below current price (with small tolerance)
    assert price - stop >= atr * 1.5 - 0.5


def test_trade_levels_mentions_t25():
    df = _sample_ohlcv()
    ind = compute_indicators(df)
    levels = build_trade_levels(ind)
    assert "t+2.5" in levels["trigger"].lower()


def test_extraction_to_short_term():
    extraction = ShortTermExtraction(
        market_regime="Uptrend",
        market_score=70,
        symbols=[
            ShortTermSymbolExtraction(
                symbol="FPT",
                action=ShortTermAction.BUY,
                safe_buy_zone="95-97",
                stop_loss="90",
            )
        ],
        deployment_conclusion="Giai ngan mot phan",
    )
    market, decisions, conclusion = extraction_to_short_term(extraction, ["FPT"])
    assert market.regime == "Uptrend"
    assert decisions[0].action == ShortTermAction.BUY
    assert "phan" in conclusion.lower()


def test_extraction_missing_symbol_defaults_watch():
    extraction = ShortTermExtraction(symbols=[])
    _, decisions, _ = extraction_to_short_term(extraction, ["FPT"])
    assert decisions[0].action == ShortTermAction.WATCH


def test_portfolio_risk_summary_flags_concentration():
    df = _sample_ohlcv()
    ind = compute_indicators(df)
    price = ind["latest_price"]
    reports = [
        {"symbol": "FPT", "indicators": ind, "position": build_position_info(price, 1000, price)},
        {"symbol": "VHM", "indicators": ind, "position": build_position_info(price, 50, price)},
    ]
    summary = build_portfolio_risk_summary(reports, cash_available=10_000_000)
    assert "Quan tri rui ro" in summary
    assert "tap trung" in summary.lower()


def test_recommendation_log_roundtrip(tmp_path):
    from stock_agents.reporting.recommendation_log import (
        log_short_term_recommendations,
        read_recommendations,
    )
    from stock_agents.schemas import ShortTermAgentOutput, ShortTermMarketContext

    output = ShortTermAgentOutput(
        as_of_date="2026-05-01",
        market=ShortTermMarketContext(),
        symbols=[
            ShortTermSymbolDecision(
                symbol="FPT",
                action=ShortTermAction.BUY,
                safe_buy_zone="95 - 97",
                stop_loss="90",
                target_1_2m="108 - 110",
            )
        ],
    )
    log_file = tmp_path / "rec.jsonl"
    log_short_term_recommendations(
        output, score_map={"FPT": 72}, source="VCI", model="m", log_file=log_file
    )
    rows = read_recommendations(log_file)
    assert rows[0]["entry_price"] == 96.0
    assert rows[0]["stop_price"] == 90.0
    assert rows[0]["target_price"] == 109.0


def test_evaluate_one_target_hit(monkeypatch):
    import stock_agents.evaluation as ev

    def fake_get(symbol, source, history_days, end_date=None):
        dates = pd.bdate_range("2026-05-02", periods=15)
        df = pd.DataFrame(
            {
                "time": dates,
                "open": 95,
                "high": [98] * 5 + [111] + [112] * 9,
                "low": [94] * 15,
                "close": 100,
            }
        )
        return df, "VCI"

    monkeypatch.setattr(ev, "get_stock_data", fake_get)
    rec = {
        "symbol": "FPT",
        "as_of_date": "2026-05-01",
        "action": "BUY",
        "score": 72,
        "entry_price": 96.0,
        "stop_price": 90.0,
        "target_price": 109.0,
    }
    from datetime import datetime

    res = ev._evaluate_one(rec, datetime(2026, 6, 1))
    assert res["outcome"] == "target"
    assert res["r_multiple"] > 0


def test_drop_unclosed_candle_backtest_noop():
    from stock_agents.tools.vnstock_tools import drop_unclosed_candle
    from datetime import datetime

    df = _sample_ohlcv(30)
    out = drop_unclosed_candle(df, end_date=datetime(2025, 6, 1))
    assert len(out) == len(df)


def test_recommendation_log_en_dash_prices(tmp_path):
    from stock_agents.reporting.recommendation_log import (
        _avg_price,
        _first_price,
    )

    assert _avg_price("27.76 – 29.15") == pytest.approx(28.455)
    assert _first_price("24.48") == 24.48


def test_evaluate_one_expired_at_horizon(monkeypatch):
    import stock_agents.evaluation as ev

    def fake_get(symbol, source, history_days, end_date=None):
        dates = pd.bdate_range("2026-05-02", periods=20)
        df = pd.DataFrame(
            {
                "time": dates,
                "open": 95,
                "high": [97] * 20,
                "low": [94] * 20,
                "close": [96] * 20,
            }
        )
        return df, "VCI"

    monkeypatch.setattr(ev, "get_stock_data", fake_get)
    rec = {
        "symbol": "FPT",
        "as_of_date": "2026-05-01",
        "action": "WATCH",
        "score": 60,
        "entry_price": 96.0,
        "stop_price": 90.0,
        "target_price": 109.0,
    }
    from datetime import datetime

    res = ev._evaluate_one(rec, datetime(2026, 7, 1), horizon_days=14)
    assert res is not None
    assert res["outcome"] == "expired"
    assert res["horizon_days"] == 14


def test_evaluate_recommendations_includes_watch(tmp_path, monkeypatch):
    import json
    import stock_agents.evaluation as ev

    log_file = tmp_path / "rec.jsonl"
    row = {
        "as_of_date": "2026-05-01",
        "symbol": "FPT",
        "action": "WATCH",
        "source": "VCI",
        "score": 65,
        "entry_price": 96.0,
        "stop_price": 90.0,
        "target_price": 109.0,
    }
    log_file.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def fake_get(symbol, source, history_days, end_date=None):
        dates = pd.bdate_range("2026-05-02", periods=15)
        df = pd.DataFrame(
            {
                "time": dates,
                "open": 95,
                "high": [98] * 5 + [111] + [112] * 9,
                "low": [94] * 15,
                "close": 100,
            }
        )
        return df, "VCI"

    monkeypatch.setattr(ev, "get_stock_data", fake_get)
    from datetime import datetime

    summary = ev.evaluate_recommendations(
        log_file=log_file, as_of=datetime(2026, 6, 1), actions=("WATCH",)
    )
    assert summary["total"] == 1
    assert summary["wins"] == 1


def test_score_backtest_bucket_aggregate():
    from stock_agents.score_backtest import _aggregate_buckets

    rows = [
        {"score_bucket": "60-79", "return_21d_pct": 5.0},
        {"score_bucket": "60-79", "return_21d_pct": -2.0},
        {"score_bucket": "0-39", "return_21d_pct": -4.0},
    ]
    stats = _aggregate_buckets(rows, (21,))
    by_label = {s["bucket"]: s for s in stats}
    assert by_label["60-79"]["count"] == 2
    assert by_label["60-79"]["avg_return_21d"] == pytest.approx(1.5)
    assert by_label["60-79"]["win_rate_21d"] == pytest.approx(50.0)


def test_top_symbols_by_return():
    from stock_agents.evaluation import _top_symbols_by_return

    results = [
        {"symbol": "VHM", "return_pct": 20.0, "action": "BUY", "as_of_date": "2026-05-01", "outcome": "target"},
        {"symbol": "VHM", "return_pct": 10.0, "action": "WATCH", "as_of_date": "2026-05-08", "outcome": "expired"},
        {"symbol": "LPB", "return_pct": 18.0, "action": "BUY", "as_of_date": "2026-05-01", "outcome": "target"},
        {"symbol": "FPT", "return_pct": -4.0, "action": "WATCH", "as_of_date": "2026-05-01", "outcome": "stop"},
        {"symbol": "HCM", "return_pct": 12.0, "action": "WATCH", "as_of_date": "2026-05-01", "outcome": "expired"},
    ]
    top = _top_symbols_by_return(results, top_n=3)
    assert [item["symbol"] for item in top] == ["LPB", "VHM", "HCM"]
    assert top[1]["avg_return_pct"] == pytest.approx(15.0)


def test_validate_analysis_ok():
    raw = """
## Boi canh thi truong chung khoan Viet Nam
- Nguon: https://example.com/news (2026-01-01)

## Danh gia tung ma
### FPT
- Hanh dong: Mua

## Ket luan giai ngan thoi diem hien tai
- Co
"""
    result = validate_analysis_output(raw, mode="short_term")
    assert not any("Thieu section" in e for e in result.get("errors", []))
