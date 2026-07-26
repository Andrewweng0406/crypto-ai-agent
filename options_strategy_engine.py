"""
期權賣方價差策略引擎——純計算層，不做任何I/O（yfinance查詢在main.py層做，
這裡只吃已經抓好的期權鏈資料），方便單元測試。

範圍（2026-07-26使用者確認）：只做「賣方收租」家族——Bull Put Spread /
Bear Call Spread / Iron Condor，不做Bull Call Spread這種買方策略。這個
功能定位是「高勝率」，賣方策略的高勝率統計特性（volatility risk premium：
隱含波動率長期平均高於事後已實現波動率，是被廣泛研究過的長期現象）跟這個
定位一致；買方策略是完全不同的勝率結構（低勝率、高賠率），不該混在同一個
「高勝率策略產生器」裡。現有的confluence engine（lib/confluence.ts）也只
輸出方向+信心分數，沒有「小資金/想搏大漲」這種輸入，沒辦法乾淨地觸發買方
策略的推薦時機。

理論勝率用Delta近似（業界標準做法，tastytrade/Option Alpha的Probability of
Profit也是這樣算）：機率OTM ≈ 1 - |短腿Delta|。這只是Black-Scholes假設下的
理論值，不是回測驗證過的統計勝率——常態分佈假設低估了肥尾風險，但賣方普遍
享有volatility risk premium的優勢，兩個偏差方向相反、不會剛好抵消，所以
刻意回傳一個區間字串（如「70-80%」）而不是一個看起來精確到小數點的數字
（如「78.53%」），避免使用者誤以為這是backtest驗證過的硬數據。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

from gex_engine import black_scholes_delta
from yfinance_client import OptionLegRaw

# 使用者原始規則：安全墊落在現價8%~15%之間——在這個範圍內選「離現價最近」
# 的履約價當短腿，同時滿足最低安全邊際跟最大化權利金這兩個目標。
MIN_OTM_PCT = 0.08
MAX_OTM_PCT = 0.15

OPTIONS_MULTIPLIER = 100  # 標準美股股票期權合約乘數（1口=100股）

SpreadSide = Literal["put", "call"]
SpreadType = Literal["put_credit", "call_credit", "iron_condor"]


@dataclass
class SpreadLegResult:
    action: Literal["SELL", "BUY"]
    option_type: Literal["PUT", "CALL"]
    strike_price: float
    reason: str


@dataclass
class SpreadResult:
    name: str
    spread_type: SpreadType
    legs: list[SpreadLegResult]
    max_profit: float
    max_loss: float
    margin_required: float
    risk_reward_ratio: str
    win_rate_bucket: str
    ai_advice: str


def _otm_pct(spot: float, strike: float, side: SpreadSide) -> float:
    if side == "put":
        return (spot - strike) / spot
    return (strike - spot) / spot


def select_credit_spread_strikes(
    legs: list[OptionLegRaw], spot: float, side: SpreadSide,
) -> Optional[tuple[OptionLegRaw, OptionLegRaw]]:
    """
    在安全墊 [MIN_OTM_PCT, MAX_OTM_PCT] 範圍內，選「離現價最近」的履約價
    當短腿（安全邊際剛好卡在門檻、拿到的權利金最多）；長腿是短腿再往外一檔
    「實際掛牌」的履約價——不是短腿strike再加減一個固定金額，因為不同標的、
    不同價位區間，交易所掛牌的履約價間距本來就不一樣，用真實掛牌的下一檔
    才能保證這是一個真的能下單的價差組合，不是理論上存在但實際上買不到的
    組合。找不到符合安全墊範圍的履約價，或短腿已經是最極端一檔（沒有更遠
    的長腿可選）時回傳 None。
    """
    sorted_legs = sorted(legs, key=lambda l: l.strike)
    candidates = [l for l in sorted_legs if MIN_OTM_PCT <= _otm_pct(spot, l.strike, side) <= MAX_OTM_PCT]
    if not candidates:
        return None

    short_leg = min(candidates, key=lambda l: _otm_pct(spot, l.strike, side))
    short_idx = sorted_legs.index(short_leg)

    if side == "put":
        if short_idx == 0:
            return None
        long_leg = sorted_legs[short_idx - 1]  # 更下方一檔，鎖定下檔風險
    else:
        if short_idx == len(sorted_legs) - 1:
            return None
        long_leg = sorted_legs[short_idx + 1]  # 更上方一檔，鎖定上檔風險

    return short_leg, long_leg


def estimate_win_rate_bucket(delta: float) -> str:
    """回傳理論勝率的10%區間字串（見檔頭說明：故意不用精確數字）。"""
    pop_pct = (1 - abs(delta)) * 100
    lower = max(0, min(90, int(pop_pct // 10) * 10))
    upper = lower + 10
    return f"{lower}-{upper}%"


def build_credit_spread(
    legs: list[OptionLegRaw], spot: float, side: SpreadSide, time_to_expiry_years: float,
) -> Optional[SpreadResult]:
    picked = select_credit_spread_strikes(legs, spot, side)
    if picked is None:
        return None
    short_leg, long_leg = picked

    if side == "put":
        short_bid, long_ask, short_iv = short_leg.put_bid, long_leg.put_ask, short_leg.put_iv
        option_type: Literal["PUT", "CALL"] = "PUT"
    else:
        short_bid, long_ask, short_iv = short_leg.call_bid, long_leg.call_ask, short_leg.call_iv
        option_type = "CALL"

    if short_bid <= 0 or long_ask <= 0:
        return None  # 無流動性（沒人報價），這種價差實際上下不了單
    credit = short_bid - long_ask
    if credit <= 0:
        return None  # 理論上價差應該收租，算出負值代表報價異常（多半是深度價外流動性太差）

    width = abs(long_leg.strike - short_leg.strike)
    max_profit = round(credit * OPTIONS_MULTIPLIER, 2)
    max_loss = round((width - credit) * OPTIONS_MULTIPLIER, 2)
    margin_required = max_loss  # 定義風險價差的標準保證金公式：保證金 = 最大虧損

    win_rate_bucket = "N/A"
    if short_iv > 0:
        delta = float(black_scholes_delta(
            spot=spot, strike=short_leg.strike, time_to_expiry_years=time_to_expiry_years,
            iv=short_iv, option_type=option_type.lower(),
        ))
        if not math.isnan(delta):
            win_rate_bucket = estimate_win_rate_bucket(delta)

    otm_pct = _otm_pct(spot, short_leg.strike, side) * 100
    side_label = "下方" if side == "put" else "上方"
    strategy_name = "Bull Put Spread（賣出看跌價差）" if side == "put" else "Bear Call Spread（賣出看漲價差）"
    ai_advice = (
        f"短腿履約價 ${short_leg.strike:.0f} 距現價{side_label}約{otm_pct:.1f}%，"
        f"理論勝率（Delta估算）約{win_rate_bucket}。此為賣方策略，時間流逝（Theta）對你有利，"
        f"只要到期時股價{'高於' if side == 'put' else '低於'} ${short_leg.strike:.0f} 即可拿到最大收益。"
    )

    return SpreadResult(
        name=strategy_name,
        spread_type="put_credit" if side == "put" else "call_credit",
        legs=[
            SpreadLegResult(action="SELL", option_type=option_type, strike_price=short_leg.strike,
                             reason=f"距現價{side_label}約{otm_pct:.1f}%，提供安全緩衝"),
            SpreadLegResult(action="BUY", option_type=option_type, strike_price=long_leg.strike,
                             reason="鎖定最大風險，避免極端行情"),
        ],
        max_profit=max_profit,
        max_loss=max_loss,
        margin_required=margin_required,
        risk_reward_ratio=f"1 : {max_loss / max_profit:.1f}" if max_profit > 0 else "N/A",
        win_rate_bucket=win_rate_bucket,
        ai_advice=ai_advice,
    )


def build_iron_condor(
    legs: list[OptionLegRaw], spot: float, time_to_expiry_years: float,
) -> Optional[SpreadResult]:
    put_side = build_credit_spread(legs, spot, "put", time_to_expiry_years)
    call_side = build_credit_spread(legs, spot, "call", time_to_expiry_years)
    if put_side is None or call_side is None:
        return None  # 兩側都要能組出價差，任一側不成就不勉強湊一個殘缺的鐵鷹

    max_profit = round(put_side.max_profit + call_side.max_profit, 2)
    max_loss = round(max(put_side.max_loss, call_side.max_loss), 2)  # 到期只會有一側被突破，不會兩側同時虧損
    margin_required = max_loss

    put_short_strike = put_side.legs[0].strike_price
    call_short_strike = call_side.legs[0].strike_price

    return SpreadResult(
        name="Iron Condor（鐵鷹策略）",
        spread_type="iron_condor",
        legs=put_side.legs + call_side.legs,
        max_profit=max_profit,
        max_loss=max_loss,
        margin_required=margin_required,
        risk_reward_ratio=f"1 : {max_loss / max_profit:.1f}" if max_profit > 0 else "N/A",
        win_rate_bucket=f"賣方Put {put_side.win_rate_bucket} / 賣方Call {call_side.win_rate_bucket}",
        ai_advice=(
            f"兩側各設一組價差，只要到期時股價落在 ${put_short_strike:.0f} ~ ${call_short_strike:.0f} "
            f"之間即可拿到最大收益，適合震盪整理格局；若單邊被突破，虧損以較嚴重的那一側為準（兩側不會同時虧損）。"
        ),
    )
