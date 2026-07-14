# Stock Agents

LangChain agents phân tích cổ phiếu Việt Nam với `vnstock` + OpenAI web search.

## Cài đặt

```bash
pip install -e ".[dev]"
```

Thiết lập `.env`:

```
OPENAI_API_KEY=sk-...
```

## Agent 1 — Quét điểm mua swing 1-2 tháng

```bash
python -m stock_agents short-term FPT VHM VIC --as-of 2026-04-07
```

## Agent 2 — Quản lý danh mục đã mua

```bash
python -m stock_agents portfolio --position FPT:100:95.5 --position VHM:200:42.0
```

## Output

- Báo cáo markdown: `outputs/SHORT_TERM_*.md` hoặc `outputs/PORTFOLIO_*.md`
- Biểu đồ PNG: `outputs/charts/`
- Mã `BUY` có đường dự báo (kịch bản tham khảo)

## Spec

Xem [specs/stock-agents-spec.md](specs/stock-agents-spec.md)

## Test

```bash
pytest tests/ -q
```
