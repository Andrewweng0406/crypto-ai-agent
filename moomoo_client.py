"""Moomoo/Futu OpenD 期權數據存取層。

已對照使用者本機真實 OpenD（Moomoo OpenD 10.8.6808，帳戶美股期權 LV1 權限）
實際回傳資料校準過一次，關鍵發現跟原本假設不同：
  1. get_option_chain() 真的「只回傳靜態結構」——只有 code/strike/option_type/
     expiry 等，完全沒有 OI/IV/Greeks，比官方文件字面描述更嚴格。OI/IV/
     Greeks 要另外呼叫 get_market_snapshot(該到期日的所有合約代碼) 才拿得到，
     用 code 當 join key 合併回去。
  2. option_implied_volatility 是「百分比數值」（54.7 代表 54.7%），要除以
     100 轉成 gex_engine 預期的小數，不是原本假設的 0~1 小數。
  3. 當天到期（0DTE，option_expiry_date_distance==0）的合約，深度價內/價外
     的 IV 會是數千的離譜數值（時間價值趨近於零時的數值不穩定，是真實市場
     現象，不是資料錯誤）——選到期日時要跳過 distance==0，一律選下一個。
  4. get_market_snapshot 一次餵 100~160 個合約代碼（單一到期日的完整鏈）
     沒被拒絕；為保險起見仍加了分批上限，避免未來標的的鏈更長時被吃掉一部分。

futu-api 是同步、阻塞式的 SDK（底層直接呼叫 socket，不是 asyncio 原生），
直接在背景迴圈裡呼叫會卡住整個事件迴圈、拖慢其他共用同一個 process 的迴圈
（price_monitor_loop、squeeze_mode_loop 等）。這裡每個方法都用
asyncio.to_thread 把阻塞呼叫丟到執行緒池，維持既有「絕不在事件迴圈上做
阻塞呼叫」的原則。

大單即時流（Whale Sweep / TICKER 訂閱）：已實測確認目前帳戶權限下，美股期權
TICKER 訂閱本身會成功（20個合約代碼只佔用1/60的訂閱配額，用量很寬鬆）。
還沒驗證的只剩「真的有大單成交時，tick 資料裡的欄位（price/volume/
ticker_direction）長什麼樣子」——這需要盤中真實成交才能看到，收盤時段訂閱
不會有資料進來。另外實測發現一個限制：同一批合約代碼訂閱後至少要等1分鐘
才能取消訂閱，所以程式設計成「成功訂閱過一次就不再重複訂閱/取消」，不是
每輪重新訂閱。
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

# 已對照真實 OpenD 回傳資料核對過的欄位名稱（見上方模組說明）
_CODE_COLUMN = "code"                              # get_option_chain 的合約代碼欄位
_STRIKE_COLUMN = "strike_price"                    # get_option_chain 的履約價欄位
_TYPE_COLUMN = "option_type"                       # get_option_chain 的 Call/Put 欄位，值為 "CALL" / "PUT"
_SNAPSHOT_OI_COLUMN = "option_open_interest"        # get_market_snapshot 的未平倉量欄位
_SNAPSHOT_IV_COLUMN = "option_implied_volatility"   # get_market_snapshot 的 IV 欄位，單位是「百分比數值」，需除以100
_SNAPSHOT_MAX_CODES_PER_CALL = 200                  # 防禦性分批上限；單一到期日鏈實測 100~160 個一次可過


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
        """
        回傳最近一個「非當天到期」的到期日（yyyy-MM-dd）。刻意跳過
        distance==0（當天到期/0DTE）——實測發現 0DTE 深度價內/價外合約的
        IV 會是數千的離譜數值（時間價值趨近零時的正常數值不穩定現象，不是
        資料錯誤），拿來算 GEX 會嚴重失真，0DTE 本身的部位動態也跟一般
        GEX 牆想呈現的「跨天結構性擠壓」是不同的東西。
        """
        if self._ctx is None:
            return None
        ret, data = await asyncio.to_thread(self._ctx.get_option_expiration_date, code=us_code)
        if ret != RET_OK:
            logger.warning("查詢 %s 期權到期日失敗：%s", us_code, data)
            return None
        future_dates = data[data["option_expiry_date_distance"] > 0]
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

        get_option_chain() 只回傳靜態結構（代碼/履約價/Call或Put），完全沒有
        OI/IV——這兩個要另外呼叫 get_market_snapshot(合約代碼清單) 才拿得到，
        用合約代碼當 join key 合併回去。
        """
        if self._ctx is None:
            return []
        ret, chain = await asyncio.to_thread(
            self._ctx.get_option_chain,
            code=us_code,
            start=expiry,
            end=expiry,
        )
        if ret != RET_OK:
            logger.warning("查詢 %s %s 期權鏈失敗：%s", us_code, expiry, chain)
            return []

        required_columns = {_CODE_COLUMN, _STRIKE_COLUMN, _TYPE_COLUMN}
        missing = required_columns - set(chain.columns)
        if missing:
            logger.error(
                "%s 期權鏈回傳欄位跟預期不符，缺少 %s；實際欄位：%s（需要對照 futu-api 文件調整 moomoo_client.py 頂部的欄位名常數）",
                us_code, missing, list(chain.columns),
            )
            return []

        codes = chain[_CODE_COLUMN].tolist()
        oi_iv_by_code = await self._fetch_oi_iv(codes)

        legs_by_strike: dict[float, OptionLegRaw] = {}
        for _, row in chain.iterrows():
            strike = float(row[_STRIKE_COLUMN])
            code = str(row[_CODE_COLUMN])
            leg = legs_by_strike.setdefault(
                strike,
                OptionLegRaw(strike=strike, call_code=None, call_oi=0.0, call_iv=0.0,
                             put_code=None, put_oi=0.0, put_iv=0.0),
            )
            oi, iv = oi_iv_by_code.get(code, (0.0, 0.0))
            if str(row[_TYPE_COLUMN]).upper() == "CALL":
                leg.call_code = code
                leg.call_oi = oi
                leg.call_iv = iv
            else:
                leg.put_code = code
                leg.put_oi = oi
                leg.put_iv = iv

        return list(legs_by_strike.values())

    async def _fetch_oi_iv(self, codes: list[str]) -> dict[str, tuple[float, float]]:
        """
        用 get_market_snapshot 批次查詢一串合約代碼的 OI/IV，回傳 {code: (oi, iv)}。
        IV 原始值是百分比數值（如 54.7 代表 54.7%），這裡先除以100轉成
        gex_engine 預期的小數；異常值（負數、或超過500%的離譜數字，通常是
        近零時間價值合約的數值不穩定）視為無效，回傳 0（gex_engine 對 iv<=0
        的合約已經會跳過、gamma記0，不會污染其他履約價的加總）。
        """
        result: dict[str, tuple[float, float]] = {}
        for i in range(0, len(codes), _SNAPSHOT_MAX_CODES_PER_CALL):
            chunk = codes[i:i + _SNAPSHOT_MAX_CODES_PER_CALL]
            ret, snap = await asyncio.to_thread(self._ctx.get_market_snapshot, chunk)
            if ret != RET_OK:
                logger.warning("批次查詢 OI/IV 失敗（%d 個代碼）：%s", len(chunk), snap)
                continue

            missing = {_CODE_COLUMN, _SNAPSHOT_OI_COLUMN, _SNAPSHOT_IV_COLUMN} - set(snap.columns)
            if missing:
                logger.error(
                    "get_market_snapshot 回傳欄位跟預期不符，缺少 %s；實際欄位：%s",
                    missing, list(snap.columns),
                )
                continue

            for _, row in snap.iterrows():
                oi = float(row[_SNAPSHOT_OI_COLUMN] or 0.0)
                iv_pct = float(row[_SNAPSHOT_IV_COLUMN] or 0.0)
                iv = iv_pct / 100 if 0 < iv_pct <= 500 else 0.0
                result[str(row[_CODE_COLUMN])] = (oi, iv)

        return result


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
    大單推播訂閱（已實測確認目前帳戶對美股期權支援 TICKER 訂閱——見模組頂部
    說明；tick 事件的實際欄位內容仍待盤中真實成交驗證）。設計成訂閱失敗或
    該市場/權限不支援 TICKER 時優雅降級：只記一次警告、supported 標記為
    False，不會讓整個期權分析迴圈掛掉，GEX 牆功能不受影響。
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
