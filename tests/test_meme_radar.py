"""迷因幣雷達：成交量倍數計算（不含當根的均量基準）。"""

import numpy as np
import pandas as pd
import pytest

from main import MEME_VOLUME_LOOKBACK, compute_volume_snapshot


def _make_df(volumes, close_price=1.0):
    n = len(volumes)
    closes = close_price if isinstance(close_price, (list, np.ndarray)) else np.full(n, close_price)
    return pd.DataFrame({
        "timestamp": np.arange(n),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": volumes,
    })


def test_volume_multiple_excludes_current_bar_from_baseline():
    # 前25根量都是100（滿足最低資料需求），最後一根是400 -> 應該是均量(100)的4倍，
    # 不是被自己拉高的均量
    volumes = [100.0] * (MEME_VOLUME_LOOKBACK + 1) + [400.0]
    df = _make_df(volumes)
    snapshot = compute_volume_snapshot(df)
    assert snapshot is not None
    assert snapshot["volume_multiple"] == 4.0


def test_no_spike_gives_multiple_near_one():
    volumes = [100.0] * (MEME_VOLUME_LOOKBACK + 2)
    df = _make_df(volumes)
    snapshot = compute_volume_snapshot(df)
    assert snapshot["volume_multiple"] == 1.0


def test_insufficient_data_returns_none():
    volumes = [100.0] * 5  # 遠少於 MEME_VOLUME_LOOKBACK + 2
    df = _make_df(volumes)
    assert compute_volume_snapshot(df) is None


def test_zero_baseline_volume_returns_none():
    volumes = [0.0] * MEME_VOLUME_LOOKBACK + [100.0]
    df = _make_df(volumes)
    assert compute_volume_snapshot(df) is None


def test_change_1h_pct_detects_pump_direction():
    n = MEME_VOLUME_LOOKBACK + 2
    volumes = [100.0] * n
    closes = [1.0] * (n - 1) + [1.5]  # 最後一根從1.0拉到1.5，同樣爆量，方向是拉盤
    df = _make_df(volumes, close_price=closes)
    snapshot = compute_volume_snapshot(df)
    assert snapshot["change_1h_pct"] == pytest.approx(50.0)


def test_change_1h_pct_detects_dump_direction():
    n = MEME_VOLUME_LOOKBACK + 2
    volumes = [100.0] * n
    closes = [1.0] * (n - 1) + [0.5]  # 最後一根從1.0砸到0.5，方向是砸盤
    df = _make_df(volumes, close_price=closes)
    snapshot = compute_volume_snapshot(df)
    assert snapshot["change_1h_pct"] == pytest.approx(-50.0)


def test_change_24h_pct_compares_against_24_bars_ago():
    n = MEME_VOLUME_LOOKBACK + 2  # 26 根：index -(MEME_VOLUME_LOOKBACK+1) = index 1 才是「24根前」
    volumes = [100.0] * n
    closes = [1.0, 2.0] + [1.0] * (n - 2)  # index1(24h前)是2.0，最後一根是1.0 -> -50%
    df = _make_df(volumes, close_price=closes)
    snapshot = compute_volume_snapshot(df)
    assert snapshot["change_24h_pct"] == pytest.approx(-50.0)
