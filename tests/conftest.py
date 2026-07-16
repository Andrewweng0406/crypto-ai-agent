"""共用測試工具：合成 K 線 DataFrame，用來餵給 add_indicators / detect_new_signal 等函式測試。"""

import numpy as np
import pandas as pd
import pytest


def make_ohlcv_df(
    direction: str = "up",
    n: int = 210,
    breakout: bool = True,
    volume_spike: bool = True,
    slope: float = 0.05,
    high_low_range: float = 0.8,
) -> pd.DataFrame:
    """
    產生一段穩定趨勢（線性上升或下降）的合成K線，最後一根可控制是否「帶量突破」。
    n=210 是為了超過 MA_SLOW_PERIOD(200) 的最低需求；slope 決定趨勢斜率，
    確保 MA(50) 跟 MA(200) 明確分出多空（線性序列下，近期均線一定偏向趨勢方向）。
    high_low_range 決定每根K棒的高低點寬度，調大可以模擬「ATR相對價格異常大」
    （例如暴漲暴跌的小幣種）的情境，調小可以模擬「波動率天生就低」（例如商品錨定
    代幣）的情境。預設值0.8是刻意選在 MIN/MAX_SANE_STOP_LOSS_PCT 兩個防呆門檻
    之間、留足夠margin的位置（2026-07-15新增下限防呆後，原本的0.3在up/down兩個
    方向會有一邊算出來的停損%剛好卡在門檻邊緣，改成0.8才穩定通過兩個方向）。
    """
    idx = np.arange(n, dtype=float)
    base = 100 + idx * slope if direction == "up" else 100 - idx * slope

    df = pd.DataFrame({
        "timestamp": idx.astype(int),
        "open": base,
        "high": base + high_low_range,
        "low": base - high_low_range,
        "close": base,
        "volume": np.full(n, 1000.0),
    })

    if breakout:
        # shift(1).rolling(20) 在最後一列看的是「不含最後一列」的前20列高/低點
        prior_window = df.iloc[-21:-1]
        if direction == "up":
            jump_to = prior_window["high"].max() + 2.0
            df.loc[df.index[-1], ["close", "high"]] = jump_to
        else:
            jump_to = prior_window["low"].min() - 2.0
            df.loc[df.index[-1], ["close", "low"]] = jump_to

    if volume_spike:
        df.loc[df.index[-1], "volume"] = 5000.0  # 遠高於VOLUME_MULT(2.0)倍均量門檻

    return df


@pytest.fixture
def ohlcv_factory():
    return make_ohlcv_df
