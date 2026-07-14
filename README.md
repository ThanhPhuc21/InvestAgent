# InvestAgent — Stock Agents

Bộ agent LangChain phân tích cổ phiếu Việt Nam, kết hợp dữ liệu `vnstock` và OpenAI (web search + phân tích có cấu trúc).

| Thành phần | Mô tả |
|------------|--------|
| **ShortTermAgent** | Quét mã, tìm điểm mua swing 1–2 tháng |
| **PortfolioAgent** | Tư vấn danh mục đã nắm giữ (mua thêm / giữ / giảm / bán) |
| **evaluate** | Đánh giá win-rate khuyến nghị từ log lịch sử |
| **backtest-score** | Backtest điểm kỹ thuật trên dữ liệu quá khứ |
| **weekly_ma_chart.py** | Biểu đồ khung tuần MA20/50/200 + khối lượng (không cần OpenAI) |

---

## Yêu cầu

- Python **3.10+**
- Tài khoản OpenAI (cho các agent phân tích)
- Thư viện `vnstock` (miễn phí, lấy giá & dữ liệu thị trường)

---

## Cài đặt

Chạy các lệnh trong thư mục `InvestAgent`:

```bash
cd InvestAgent

# Tạo môi trường ảo (khuyến nghị)
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

# Cài package + dev dependencies (pytest)
pip install -e ".[dev]"
```

Hoặc cài từ `requirements.txt` rồi editable install:

```bash
pip install -r requirements.txt
pip install -e .
```

Sau khi cài, có thể gọi CLI bằng một trong hai cách:

```bash
python -m stock_agents --help
stock-agents --help
```

---

## Cấu hình `.env`

Tạo file `.env` tại thư mục `InvestAgent`:

```env
OPENAI_API_KEY=sk-...

# Tuỳ chọn
STOCK_AGENT_MODEL=gpt-4.1
STOCK_AGENT_TEMPERATURE=0.2
STOCK_AGENT_OUTPUT_DIR=outputs
```

> Hỗ trợ cả `OPEN_AI_KEY` (tên cũ) nếu project của bạn đang dùng biến đó.

Các agent **short-term** và **portfolio** bắt buộc có API key. Công cụ `weekly_ma_chart.py` chỉ cần `vnstock`, không cần OpenAI.

---

## Agent 1 — Short-term (swing 1–2 tháng)

Quét danh sách mã, phân tích bối cảnh thị trường + kỹ thuật + tin tức, đưa ra khuyến nghị:

| Action | Ý nghĩa |
|--------|---------|
| `BUY` | Đủ điều kiện mua swing |
| `WATCH` | Tiềm năng, chưa đủ trigger |
| `AVOID` | Rủi ro cao / không phù hợp |

```bash
# Phân tích nhiều mã
python -m stock_agents short-term FPT VHM VIC

# Backtest tại ngày cụ thể
python -m stock_agents short-term FPT GEX VHM --as-of 2026-04-07

# Tuỳ chọn thêm
python -m stock_agents short-term FPT VHM VIC \
  --history-days 365 \
  --source VCI \
  --top-n 3 \
  --model gpt-4.1 \
  --no-stream
```

| Tham số | Mặc định | Mô tả |
|---------|----------|--------|
| `symbols` | (bắt buộc) | ≥1 mã CK |
| `--as-of` | hôm nay | Ngày cắt dữ liệu `YYYY-MM-DD` |
| `--history-days` | `365` | Số ngày lịch sử giá |
| `--source` | `VCI` | Nguồn `VCI` hoặc `KBS` (tự fallback) |
| `--top-n` | `3` | Số mã ưu tiên trong báo cáo |
| `--model` | `gpt-4.1` | Model OpenAI |
| `--no-stream` | — | Tắt stream output khi chạy |

---

## Agent 2 — Portfolio (danh mục đã mua)

Phân tích vị thế đang nắm giữ, gợi ý hành động tiếp theo:

| Action | Ý nghĩa |
|--------|---------|
| `ADD` | Mua thêm |
| `HOLD` | Giữ nguyên |
| `REDUCE` | Giảm tỷ trọng |
| `SELL` | Thoát vị thế |
| `WATCH` | Theo dõi thêm |

```bash
# Một hoặc nhiều vị thế: SYMBOL:SL_LUONG:GIA_VON
python -m stock_agents portfolio \
  --position FPT:100:95.5 \
  --position VHM:200:42.0

# Có tiền mặt khả dụng
python -m stock_agents portfolio \
  --position FPT:100:95.5 \
  --cash 50000000 \
  --as-of 2026-04-07
```

| Tham số | Mặc định | Mô tả |
|---------|----------|--------|
| `--position` | (bắt buộc, lặp) | `SYMBOL:QTY:PRICE` |
| `--as-of` | hôm nay | Ngày cắt dữ liệu |
| `--history-days` | `365` | Số ngày lịch sử |
| `--source` | `VCI` | Nguồn dữ liệu |
| `--cash` | — | Tiền mặt khả dụng (VND) |
| `--model` | `gpt-4.1` | Model OpenAI |
| `--no-stream` | — | Tắt stream output |

---

## Đánh giá khuyến nghị (`evaluate`)

Đọc log từ các lần chạy short-term, tính win-rate / R-multiple / return trung bình.

```bash
# Đánh giá tất cả khuyến nghị đủ điều kiện
python -m stock_agents evaluate

# Đánh giá đến ngày cụ thể
python -m stock_agents evaluate --as-of 2026-07-13

# Một horizon (28 ngày)
python -m stock_agents evaluate --horizon 28

# Đa horizon 14/28/56 ngày (2/4/8 tuần)
python -m stock_agents evaluate --multi-horizon

# Chỉ đánh giá BUY
python -m stock_agents evaluate --actions BUY --horizon 42
```

> Cần chạy `short-term` trước để ghi log vào `outputs/recommendations.jsonl`.

---

## Backtest điểm kỹ thuật (`backtest-score`)

Walk-forward backtest score kỹ thuật trên lịch sử (không gọi OpenAI).

```bash
# Theo danh sách mã
python -m stock_agents backtest-score FPT VHM HCM

# Theo watchlist trong agents.json
python -m stock_agents backtest-score --watchlist vn30_sample

# Khoảng thời gian tuỳ chỉnh
python -m stock_agents backtest-score FPT VHM \
  --start 2025-01-01 \
  --end 2026-07-01 \
  --forward-days 21 42 \
  --step 21
```

Tạo `agents.json` ở thư mục gốc `InvestAgent` nếu dùng `--watchlist`:

```json
{
  "watchlists": {
    "vn30_sample": ["FPT", "VHM", "VIC", "HCM", "MWG"]
  },
  "portfolios": {
    "demo": [
      {"symbol": "FPT", "quantity": 100, "avg_price": 95.5}
    ]
  }
}
```

---

## Biểu đồ MA tuần (`weekly_ma_chart.py`)

Công cụ độc lập — vẽ giá khung tuần với MA20/50/200 và khối lượng. Tự tải thêm dữ liệu warmup để MA200 hiển thị đầy đủ trên khung thời gian chọn.

```bash
# Mặc định FPT, lưu outputs/charts/FPT_weekly_ma.png
python weekly_ma_chart.py

python weekly_ma_chart.py VIX --years 7
python weekly_ma_chart.py FPT --years 10 --source kbs
python weekly_ma_chart.py HPG --show
python weekly_ma_chart.py VCB --no-volume
```

| Tham số | Mặc định | Mô tả |
|---------|----------|--------|
| `symbol` | `FPT` | Mã cổ phiếu |
| `--years` | `5` | Số năm hiển thị (khuyến nghị **7–10** để thấy rõ MA200) |
| `--source` | `kbs` | `kbs` hoặc `vci` |
| `--save` | `outputs/charts/{SYMBOL}_weekly_ma.png` | Đường dẫn file PNG |
| `--show` | — | Hiện cửa sổ thay vì lưu file |
| `--no-volume` | — | Ẩn biểu đồ khối lượng |

---

## Chạy batch hàng tuần (tuỳ chọn)

Script tự động chạy short-term theo từng tuần rồi evaluate đa horizon:

```bash
python scripts/weekly_agent_batch.py
```

Chỉnh danh sách mã và khoảng ngày trong file `scripts/weekly_agent_batch.py` trước khi chạy.

---

## Output

Tất cả output mặc định nằm trong `outputs/` (hoặc `STOCK_AGENT_OUTPUT_DIR`):

| Loại | Đường dẫn |
|------|-----------|
| Báo cáo short-term | `outputs/SHORT_TERM_*.md` |
| Báo cáo portfolio | `outputs/PORTFOLIO_*.md` |
| Báo cáo evaluate | `outputs/EVALUATION_*.md` |
| Báo cáo backtest score | `outputs/SCORE_BACKTEST_*.md` |
| Biểu đồ agent | `outputs/charts/{SYMBOL}_chart.png` |
| Biểu đồ portfolio | `outputs/charts/{SYMBOL}_portfolio.png` |
| Biểu đồ MA tuần | `outputs/charts/{SYMBOL}_weekly_ma.png` |
| Log khuyến nghị | `outputs/recommendations.jsonl` |

- Mã `BUY` (short-term) có thêm **đường dự báo** trên biểu đồ (kịch bản tham khảo, không phải dữ liệu thực).
- Biểu đồ agent dùng khung **ngày** (MA20/MA50); `weekly_ma_chart.py` dùng khung **tuần** (MA20/50/200).

---

## Kiểm thử

```bash
pytest tests/ -q
```

---

## Tài liệu chi tiết

Xem [specs/stock-agents-spec.md](specs/stock-agents-spec.md) cho input/output schema, quy tắc quyết định và validation.
