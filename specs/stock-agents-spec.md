# Spec: LangChain Stock Agents (Vietnam)

## 1. Mục tiêu

Hai agent phân tích cổ phiếu Việt Nam cho nhà đầu tư mới:

| Agent | Mục đích | Horizon |
|-------|----------|---------|
| **ShortTermAgent** | Quét mã, đề xuất điểm mua swing | 1-2 tháng |
| **PortfolioAgent** | Quản lý danh mục đã mua | 1-2 tháng |

## 2. Kiến trúc

```
CLI → Agent → [VnstockTools, OpenAIResearchTool] → Features → StructuredDecision → Report + Charts
```

- **Orchestration**: LangChain (`@tool`, `ChatPromptTemplate`, `Runnable`)
- **Data**: `vnstock` Unified UI (`Market.equity().ohlcv`) hoặc fallback `Quote`
- **Research**: OpenAI Responses API + `web_search`
- **Output**: Markdown + PNG charts trong `outputs/`

## 3. Input contracts

### 3.1 ShortTermAgentInput

```json
{
  "symbols": ["FPT", "VHM"],
  "as_of_date": "2026-04-07",
  "history_days": 365,
  "source": "VCI",
  "top_n": 3,
  "model": "gpt-4.1"
}
```

| Field | Type | Default | Mô tả |
|-------|------|---------|-------|
| symbols | list[str] | required | ≥1 mã, uppercase |
| as_of_date | date \| null | today | Ngày cắt dữ liệu (backtest) |
| history_days | int | 365 | 6-12 tháng lịch sử |
| source | str | VCI | VCI / KBS / auto |
| top_n | int | 3 | Số mã ưu tiên |
| model | str | env | OpenAI model |

### 3.2 PortfolioAgentInput

```json
{
  "positions": [
    {"symbol": "FPT", "quantity": 100, "avg_price": 95.5}
  ],
  "as_of_date": null,
  "history_days": 365,
  "source": "VCI",
  "cash_available": null,
  "model": "gpt-4.1"
}
```

## 4. Output contracts

### 4.1 ShortTermSymbolDecision

| Field | Enum / Type |
|-------|-------------|
| action | BUY \| WATCH \| AVOID |
| market_regime | string |
| early_buy_zone | string |
| safe_buy_zone | string |
| stop_loss | string |
| target_1_2m | string |
| holding_window | string |
| rationale | list[str] |

### 4.2 PortfolioSymbolDecision

| Field | Enum / Type |
|-------|-------------|
| action | ADD \| HOLD \| SELL \| REDUCE \| WATCH |
| thesis_status | intact \| weakened \| broken |
| avg_price_context | string |
| risk_flags | list[str] |
| next_action_zone | string |
| reason | list[str] |

## 5. Decision rules

### Agent 1
- Ưu tiên: bối cảnh thị trường 35%, kỹ thuật 40%, catalyst 15%, thanh khoản/rủi ro 10%
- Chỉ `BUY` khi: thị trường hỗ trợ + setup kỹ thuật + catalyst rõ
- `WATCH`: tiềm năng nhưng chưa đủ trigger
- `AVOID`: rủi ro cao hoặc không phù hợp bối cảnh
- Forecast line **chỉ** cho `BUY`

### Agent 2
- Tính PnL, drawdown, khoảng cách support/resistance
- `ADD`: thesis còn + giá hợp lý + momentum hỗ trợ
- `HOLD`: thesis intact, chưa cần hành động
- `REDUCE`/`SELL`: thesis weakened/broken hoặc stop hit
- Khuyến nghị cá nhân hóa theo giá vốn

## 6. Chart rules

- Lịch sử: đường close + MA20/MA50
- BUY: thêm forecast dashed (rule-based 30 phiên từ entry→target)
- WATCH/AVOID: không có forecast
- Ghi chú: "Đường dự báo là kịch bản tham khảo, không phải dữ liệu thực"

## 7. Validation

- Bắt buộc sections: bối cảnh thị trường, đánh giá từng mã, kết luận
- Phải có link nguồn http(s)
- Không dùng tin sau `as_of_date`
- Enum action hợp lệ

## 8. CLI

```bash
# Agent 1
python -m stock_agents short-term FPT VHM VIC --as-of 2026-04-07

# Agent 2
python -m stock_agents portfolio --position FPT:100:95.5 --position VHM:200:42.0
```

## 9. Dependencies

- langchain, langchain-core, langchain-openai
- openai, pandas, python-dotenv, pydantic
- vnstock, matplotlib
- vnstock_ezchart (optional)

## 10. Error handling

- Retry vnstock 3 lần, fallback VCI→KBS
- Mã lỗi: skip mã, tiếp tục các mã còn lại
- Thiếu OPENAI_API_KEY: exit với message rõ ràng
