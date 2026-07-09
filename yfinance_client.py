"""yfinance 期權數據存取層 —— 免費、無需登入的資料源。

取代原本的 Moomoo/Futu OpenD 方案：Railway 上跑 OpenD 需要真實證券帳戶登入 +
2FA/圖形驗證碼，反覆實測後確認 Railway 的容器網路環境跟 Futu 登入伺服器不
穩定相容（社群維護的 Docker image 自己的文件都承認要用 host networking
才穩，但 Railway 不支援這個模式），過程中還一度觸發帳號的登入失敗次數限制，
風險太高。改用 yfinance（免費、非官方但業界廣泛使用多年、資料來自 Yahoo
Finance 公開頁面）大幅簡化架構：不需要閘道程式、不需要登入、不需要任何
憑證，一個 HTTP 呼叫就有 OI/IV/現貨價，完全不會有帳號被鎖的風險。

已實測：NVDA 現貨價跟先前真實 Moomoo 連線抓到的數字分毫不差；IV 欄位是
小數（如 0.5 代表 50%），不像 Moomoo 是百分比數值，不需要額外除以100。

犧牲：yfinance 沒有逐筆成交數據，「期權大單即時流」功能無法用這個資料源
實作，get_option_chain_legs 只回傳 OI/IV，呼叫端的 whale_sweep_supported
固定回 False——前端已經有對應的「此功能目前不支援」畫面（見
whale-sweep-stream.tsx），不會誤導使用者。

yfinance 底層是同步、阻塞式的 requests 呼叫，每個方法都用 asyncio.to_thread
包起來，維持「絕不在事件迴圈上做阻塞呼叫」的原則。
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import yfinance as yf

logger = logging.getLogger("trading_signal")

# IV 超過這個視為近零時間價值合約（深度價內/價外、極端近到期）的數值不穩定
# 雜訊，捨棄不用——這是真實市場現象，不是資料錯誤，跟 Moomoo 那邊看到的
# 0DTE 極端 IV 是同一件事。
IV_SANE_MAX = 5.0


@dataclass
class OptionLegRaw:
    strike: float
    call_oi: float
    call_iv: float
    put_oi: float
    put_iv: float


async def get_nearest_expiry(ticker_symbol: str) -> Optional[str]:
    """
    回傳最近一個「非當天到期」的到期日（yyyy-MM-dd）。跳過當天到期（0DTE）
    理由同 Moomoo 版本：深度價內/價外合約的 IV 在時間價值趨近零時會出現
    數千趴的離譜數值，拿來算 GEX 會嚴重失真。
    """
    def _fetch() -> tuple:
        return yf.Ticker(ticker_symbol).options

    try:
        expiries = await asyncio.to_thread(_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("查詢 %s 到期日清單失敗：%s", ticker_symbol, exc)
        return None

    if not expiries:
        return None

    today = datetime.now().date().isoformat()
    future_expiries = [e for e in expiries if e > today]
    return future_expiries[0] if future_expiries else None


async def get_spot_price(ticker_symbol: str) -> Optional[float]:
    def _fetch() -> Optional[float]:
        return yf.Ticker(ticker_symbol).fast_info.get("lastPrice")

    try:
        price = await asyncio.to_thread(_fetch)
        return float(price) if price else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("查詢 %s 現貨價失敗：%s", ticker_symbol, exc)
        return None


async def get_option_chain_legs(ticker_symbol: str, expiry: str) -> list[OptionLegRaw]:
    """
    取得單一到期日的完整期權鏈，依履約價彙整成 Call/Put 成對的 legs，直接
    餵給 gex_engine.compute_net_gex_by_strike。任何一檔履約價缺 Call 或缺
    Put 時，缺的那一邊 OI/IV 視為 0（不影響另一邊的 GEX）。
    """
    def _fetch():
        return yf.Ticker(ticker_symbol).option_chain(expiry)

    try:
        chain = await asyncio.to_thread(_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("查詢 %s %s 期權鏈失敗：%s", ticker_symbol, expiry, exc)
        return []

    legs_by_strike: dict[float, OptionLegRaw] = {}

    def _clean(value, *, sane_max: Optional[float] = None) -> float:
        # pandas 回傳缺值是 NaN（浮點數），不是 None，`x or 0.0` 這種寫法接不住
        # NaN（NaN 在 Python 是 truthy），一定要用 isnan 明確檢查，否則 NaN 會
        # 一路帶進 gex_engine 的乘法運算、汙染整條 GEX 曲線，最後連 FastAPI
        # 想序列化成 JSON 回應都會直接壞掉（NaN 不是合法 JSON 數值）。
        try:
            f = float(value)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f) or f < 0:
            return 0.0
        if sane_max is not None and f > sane_max:
            return 0.0
        return f

    def _apply(rows, is_call: bool) -> None:
        for _, row in rows.iterrows():
            strike = _clean(row["strike"])
            leg = legs_by_strike.setdefault(
                strike,
                OptionLegRaw(strike=strike, call_oi=0.0, call_iv=0.0, put_oi=0.0, put_iv=0.0),
            )
            oi = _clean(row.get("openInterest"))
            iv = _clean(row.get("impliedVolatility"), sane_max=IV_SANE_MAX)
            if is_call:
                leg.call_oi = oi
                leg.call_iv = iv
            else:
                leg.put_oi = oi
                leg.put_iv = iv

    _apply(chain.calls, is_call=True)
    _apply(chain.puts, is_call=False)

    return list(legs_by_strike.values())
