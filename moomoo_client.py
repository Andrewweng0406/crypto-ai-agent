"""Moomoo/Futu OpenD 期權數據存取層。

⚠️ 這支模組的正確性目前只到「跟官方文件描述的介面一致」的程度，還沒辦法
端對端驗證，原因是 Futu/moomoo OpenAPI 的運作方式：
  1. 需要先在某台機器上啟動 OpenD 閘道程式，用真實 Moomoo/Futu 證券帳戶
     登入，這支後端程式再透過 socket 連到 OpenD——不是單純一組 API Key
     就能測，需要使用者本人的帳戶登入，這是我不能代為操作、也不應該
     代為處理密碼的部分（跟這個專案先前處理 OpenAI/Telegram 金鑰的
     謹慎程度一致，證券帳戶密碼的敏感度只會更高）。
  2. 官方文件沒有列出 get_option_chain() 回傳 DataFrame 的完整精確欄位名
     （只確認會包含履約價/OI/IV/Greeks，但沒給精確欄位字串）。下面的
     _OI_COLUMN / _IV_COLUMN 等常數是最可能的欄位名，第一次接上真實 OpenD
     後，如果解析失敗，log 會印出實際收到的欄位清單，對照官方文件或印出的
     欄位名調整這幾個常數即可，不需要改動其他邏輯。

futu-api 是同步、阻塞式的 SDK（底層直接呼叫 socket，不是 asyncio 原生），
直接在背景迴圈裡呼叫會卡住整個事件迴圈、拖慢其他共用同一個 process 的迴圈
（price_monitor_loop、squeeze_mode_loop 等）。這裡每個方法都用
asyncio.to_thread 把阻塞呼叫丟到執行緒池，維持既有「絕不在事件迴圈上做
阻塞呼叫」的原則。
"""

from __future__ import annotations

import asyncio
import logging
import queue
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("trading_signal")

try:
    from futu import RET_OK, OpenQuoteContext, OptionType as FutuOptionType, SubType, TickerHandlerBase

    FUTU_AVAILABLE = True
except ImportError:  # 本機開發沒裝 futu-api，或還沒 pip install 時，模組仍可 import，只是功能停用
    FUTU_AVAILABLE = False
    TickerHandlerBase = object  # type: ignore[assignment,misc]

# 官方文件未明列的欄位名稱，第一次真實連線後如解析失敗以此為調整起點
_CODE_COLUMN = "code"
_STRIKE_COLUMN = "strike_price"
_TYPE_COLUMN = "option_type"       # 值應為 "CALL" / "PUT"
_OI_COLUMN = "option_open_interest"
_IV_COLUMN = "implied_volatility"  # 假設為 0~1 小數；若回傳是百分比（如 35 代表 35%），需除以 100


@dataclass
class OptionLegRaw:
    strike: float
    call_code: Optional[str]
    call_oi: float
    call_iv: float
    put_code: Optional[str]
    put_oi: float
    put_iv: float


class MoomooOptionsClient:
    """包住一個 OpenQuoteContext 連線；所有方法皆為 async。"""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._ctx = None

    @property
    def is_connected(self) -> bool:
        return self._ctx is not None

    async def connect(self) -> bool:
        if not FUTU_AVAILABLE:
            logger.warning("futu-api 套件未安裝，期權分析模塊停用（pip install futu-api）")
            return False
        try:
            self._ctx = await asyncio.to_thread(OpenQuoteContext, host=self._host, port=self._port)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("連線 Moomoo OpenD 失敗（%s:%s）：%s", self._host, self._port, exc)
            self._ctx = None
            return False

    async def close(self) -> None:
        if self._ctx is not None:
            try:
                await asyncio.to_thread(self._ctx.close)
            except Exception as exc:  # noqa: BLE001
                logger.warning("關閉 Moomoo OpenD 連線時發生錯誤：%s", exc)
            self._ctx = None

    async def get_nearest_expiry(self, us_code: str) -> Optional[str]:
        """回傳最近一個尚未到期的到期日（yyyy-MM-dd）。"""
        if self._ctx is None:
            return None
        ret, data = await asyncio.to_thread(self._ctx.get_option_expiration_date, code=us_code)
        if ret != RET_OK:
            logger.warning("查詢 %s 期權到期日失敗：%s", us_code, data)
            return None
        future_dates = data[data["option_expiry_date_distance"] >= 0]
        if future_dates.empty:
            return None
        nearest = future_dates.sort_values("option_expiry_date_distance").iloc[0]
        return str(nearest["strike_time"])

    async def get_spot_price(self, us_code: str) -> Optional[float]:
        if self._ctx is None:
            return None
        ret, data = await asyncio.to_thread(self._ctx.get_market_snapshot, [us_code])
        if ret != RET_OK or data.empty:
            logger.warning("查詢 %s 現貨價失敗：%s", us_code, data)
            return None
        return float(data.iloc[0]["last_price"])

    async def get_option_chain_legs(self, us_code: str, expiry: str) -> list[OptionLegRaw]:
        """
        取得單一到期日的完整期權鏈，依履約價彙整成 Call/Put 成對的 legs，
        直接餵給 gex_engine.compute_net_gex_by_strike。任何一檔履約價缺
        Call 或缺 Put 時，缺的那一邊 OI/IV 視為 0（不影響另一邊的 GEX）。
        """
        if self._ctx is None:
            return []
        ret, data = await asyncio.to_thread(
            self._ctx.get_option_chain,
            code=us_code,
            start=expiry,
            end=expiry,
        )
        if ret != RET_OK:
            logger.warning("查詢 %s %s 期權鏈失敗：%s", us_code, expiry, data)
            return []

        required_columns = {_CODE_COLUMN, _STRIKE_COLUMN, _TYPE_COLUMN, _OI_COLUMN, _IV_COLUMN}
        missing = required_columns - set(data.columns)
        if missing:
            logger.error(
                "%s 期權鏈回傳欄位跟預期不符，缺少 %s；實際欄位：%s（需要對照 futu-api 文件調整 moomoo_client.py 頂部的欄位名常數）",
                us_code, missing, list(data.columns),
            )
            return []

        legs_by_strike: dict[float, OptionLegRaw] = {}
        for _, row in data.iterrows():
            strike = float(row[_STRIKE_COLUMN])
            leg = legs_by_strike.setdefault(
                strike,
                OptionLegRaw(strike=strike, call_code=None, call_oi=0.0, call_iv=0.0,
                             put_code=None, put_oi=0.0, put_iv=0.0),
            )
            oi = float(row[_OI_COLUMN] or 0.0)
            iv = float(row[_IV_COLUMN] or 0.0)
            if str(row[_TYPE_COLUMN]).upper() == "CALL":
                leg.call_code = str(row[_CODE_COLUMN])
                leg.call_oi = oi
                leg.call_iv = iv
            else:
                leg.put_code = str(row[_CODE_COLUMN])
                leg.put_oi = oi
                leg.put_iv = iv

        return list(legs_by_strike.values())


class _WhaleSweepTickerHandler(TickerHandlerBase):
    """
    futu-api 的推播 callback 是從 SDK 內部執行緒同步呼叫，不能直接碰
    asyncio 物件；用一個 thread-safe queue.Queue 當緩衝區，async 端另開
    一個消費迴圈把資料搬進 state，兩邊不共用鎖、不直接互相呼叫。
    """

    def __init__(self, sink: "queue.Queue") -> None:
        super().__init__()
        self._sink = sink

    def on_recv_rsp(self, rsp_pb):
        ret, data = super().on_recv_rsp(rsp_pb)
        if ret == RET_OK:
            self._sink.put(data)
        return RET_OK, data


class WhaleSweepListener:
    """
    大單推播訂閱（實驗性，可行性未經真實帳號驗證——見模組頂部說明）。
    設計成訂閱失敗或該市場/權限不支援 TICKER 時優雅降級：只記一次警告、
    supported 標記為 False，不會讓整個期權分析迴圈掛掉，GEX 牆功能不受影響。
    """

    def __init__(self, client: MoomooOptionsClient) -> None:
        self._client = client
        self._queue: "queue.Queue" = queue.Queue()
        self.supported: Optional[bool] = None  # None=尚未嘗試過

    async def try_subscribe(self, option_codes: list[str]) -> bool:
        if self._client._ctx is None or not option_codes or not FUTU_AVAILABLE:
            return False
        try:
            await asyncio.to_thread(
                self._client._ctx.set_handler, _WhaleSweepTickerHandler(self._queue)
            )
            ret, data = await asyncio.to_thread(
                self._client._ctx.subscribe, option_codes, [SubType.TICKER]
            )
            self.supported = ret == RET_OK
            if not self.supported:
                logger.warning("訂閱期權大單 TICKER 失敗（可能是帳戶權限或市場不支援）：%s", data)
            return self.supported
        except Exception as exc:  # noqa: BLE001
            logger.warning("訂閱期權大單 TICKER 時發生例外：%s", exc)
            self.supported = False
            return False

    def drain(self) -> list:
        """把 callback 執行緒推進來的所有 tick 一次取完（non-blocking）。"""
        items = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items
