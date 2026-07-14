"""
Biểu đồ giá cổ phiếu theo tuần với MA 20, 50, 200 và khối lượng.

Ví dụ:
    python weekly_ma_chart.py FPT
    python weekly_ma_chart.py VCB --years 5 --no-volume
    python weekly_ma_chart.py HPG --source vci --save outputs/charts/HPG_weekly.png
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from vnstock import Quote

DEFAULT_SYMBOL = "FPT"
DEFAULT_SOURCE = "kbs"
DEFAULT_YEARS = 5
MA_WINDOWS = (20, 50, 200)
MA_WARMUP_BUFFER_WEEKS = 10
MA_COLORS = {
    20: "#FF9800",
    50: "#4CAF50",
    200: "#E91E63",
}


def fetch_weekly_ohlcv(
    symbol: str,
    start: datetime,
    end: datetime,
    source: str = DEFAULT_SOURCE,
) -> pd.DataFrame:
    """Lay du lieu OHLCV khung tuan trong khoang thoi gian chi dinh."""
    quote = Quote(source=source.lower(), symbol=symbol.upper())
    df = quote.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1W",
    )
    if df is None or df.empty:
        raise RuntimeError(f"Khong lay duoc du lieu tuan cho {symbol}.")

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("time").reset_index(drop=True)


def prepare_weekly_chart_data(
    symbol: str,
    display_years: int = DEFAULT_YEARS,
    source: str = DEFAULT_SOURCE,
    end_date: datetime | None = None,
) -> pd.DataFrame:
    """
    Lay du lieu hien thi N nam, nhung tinh MA tren lich su dai hon.

    Vi du: hien thi 5 nam gan nhat, nhung tai them ~200 tuan truoc do
    de MA200 co gia tri dung tai moi diem tren bieu do (giong TradingView).
    """
    end = end_date or datetime.today()
    display_start = end - timedelta(days=display_years * 365)
    warmup_weeks = max(MA_WINDOWS) + MA_WARMUP_BUFFER_WEEKS
    fetch_start = display_start - timedelta(weeks=warmup_weeks)

    full_df = fetch_weekly_ohlcv(symbol=symbol, start=fetch_start, end=end, source=source)
    full_df = add_moving_averages(full_df)

    display_df = full_df[full_df["time"] >= pd.Timestamp(display_start)].copy()
    display_df = display_df.reset_index(drop=True)
    if display_df.empty:
        raise RuntimeError(f"Khong du du lieu de hien thi {display_years} nam cho {symbol}.")

    return display_df


def add_moving_averages(df: pd.DataFrame, windows: tuple[int, ...] = MA_WINDOWS) -> pd.DataFrame:
    """Thêm các cột MA theo giá đóng cửa."""
    out = df.copy()
    close = out["close"].astype(float)
    for window in windows:
        out[f"ma{window}"] = close.rolling(window).mean()
    return out


def plot_weekly_ma_chart(
    df: pd.DataFrame,
    symbol: str,
    show_volume: bool = True,
    output_path: Path | None = None,
) -> Path | None:
    """Vẽ biểu đồ giá + MA và khối lượng (tuần)."""
    if df.empty:
        raise ValueError("DataFrame rỗng, không thể vẽ biểu đồ.")

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df.set_index("time")["close"].astype(float)

    if show_volume:
        fig, (ax_price, ax_volume) = plt.subplots(
            2,
            1,
            figsize=(14, 8),
            sharex=True,
            layout="constrained",
            gridspec_kw={"height_ratios": [3, 1]},
        )
    else:
        fig, ax_price = plt.subplots(figsize=(14, 6), layout="constrained")
        ax_volume = None

    ax_price.plot(close.index, close.values, color="#1976D2", linewidth=1.8, label="Giá đóng cửa")

    for window in MA_WINDOWS:
        col = f"ma{window}"
        if col not in df.columns:
            continue
        ma_series = df.set_index("time")[col].astype(float).dropna()
        ax_price.plot(
            ma_series.index,
            ma_series.values,
            color=MA_COLORS[window],
            linewidth=1.2,
            alpha=0.9,
            label=f"MA{window}",
        )

    ax_price.set_title(f"{symbol.upper()} — Khung tuần (MA 20 / 50 / 200)")
    ax_price.set_ylabel("Giá (nghìn VND)")
    ax_price.grid(True, alpha=0.3)
    ax_price.legend(loc="upper left", fontsize=9)

    if show_volume and ax_volume is not None:
        volume = df.set_index("time")["volume"].astype(float)
        colors = ["#26A69A" if c >= o else "#EF5350" for o, c in zip(df["open"], df["close"])]
        ax_volume.bar(volume.index, volume.values, width=4, color=colors, alpha=0.75)
        ax_volume.set_ylabel("KLGD")
        ax_volume.grid(True, alpha=0.25, axis="y")

    ax_price.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    fig.autofmt_xdate()

    if output_path is None:
        plt.show()
        plt.close(fig)
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vẽ biểu đồ MA tuần cho cổ phiếu VN.")
    parser.add_argument("symbol", nargs="?", default=DEFAULT_SYMBOL, help="Mã CK (mặc định: FPT)")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS, help="Số năm dữ liệu (mặc định: 5)")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Nguồn dữ liệu: kbs hoặc vci")
    parser.add_argument("--no-volume", action="store_true", help="Ẩn biểu đồ khối lượng")
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Luu anh (mac dinh: outputs/charts/{SYMBOL}_weekly_ma.png)",
    )
    parser.add_argument("--show", action="store_true", help="Hien cua so bieu do thay vi luu file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper()

    print(f"Loading {args.years}-year weekly data for {symbol} (source: {args.source.upper()})...")
    df = prepare_weekly_chart_data(
        symbol=symbol,
        display_years=args.years,
        source=args.source,
    )

    print(f"Displaying {len(df)} weekly candles: {df['time'].iloc[0].date()} -> {df['time'].iloc[-1].date()}")

    save_path = None if args.show else (args.save or Path("outputs/charts") / f"{symbol}_weekly_ma.png")

    out = plot_weekly_ma_chart(
        df=df,
        symbol=symbol,
        show_volume=not args.no_volume,
        output_path=save_path,
    )
    if out is not None:
        print(f"Chart saved: {out.resolve()}")


if __name__ == "__main__":
    main()
