"""迷因幣雷達：成交量倍數計算（不含當根的均量基準）。"""

import numpy as np
import pandas as pd

from main import MEME_VOLUME_LOOKBACK, compute_volume_snapshot


def _make_df(volumes, close_price=1.0):
    n = len(volumes)
    return pd.DataFrame({
        "timestamp": np.arange(n),
        "open": close_price, "high": close_price, "low": close_price, "close": close_price,
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
