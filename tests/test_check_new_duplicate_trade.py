"""
2026-07-28新增：即時重複交易偵測 `_check_new_duplicate_trade()` 的單元測試。
這是 `_purge_duplicate_trade_history`（啟動時清理，見
test_main_history_duplicate_purge.py / test_rsi2_no_intraday_flip_flop.py）
的即時版本——每次結算後馬上檢查，不用等重複紀錄累積到有人手動發現。
"""

import main


def _record(symbol, entry_price, stop_loss, closed_at):
    return {
        "symbol": symbol, "entry_price": entry_price, "stop_loss": stop_loss,
        "closed_at": closed_at,
    }


def test_returns_none_when_no_duplicate():
    new_record = _record("BTC/USDT:USDT", 64000.0, 62000.0, "2026-07-28T10:00:00+00:00")
    history = [
        new_record,
        _record("ETH/USDT:USDT", 3000.0, 2900.0, "2026-07-27T10:00:00+00:00"),
    ]
    assert main._check_new_duplicate_trade(history, new_record, "主流幣/市場掃描") is None


def test_returns_none_for_self_only_match():
    # history 裡只有 new_record 自己（appendleft之後的正常情況），不該被當成跟自己重複
    new_record = _record("BTC/USDT:USDT", 64000.0, 62000.0, "2026-07-28T10:00:00+00:00")
    history = [new_record]
    assert main._check_new_duplicate_trade(history, new_record, "主流幣/市場掃描") is None


def test_detects_duplicate_signature_against_other_records():
    new_record = _record("ALLO/USDT:USDT", 0.5134, 0.4695, "2026-07-13T23:41:14+00:00")
    history = [
        new_record,
        _record("ALLO/USDT:USDT", 0.5134, 0.4695, "2026-07-13T23:40:14+00:00"),
        _record("ALLO/USDT:USDT", 0.5134, 0.4695, "2026-07-13T23:39:14+00:00"),
        _record("BTC/USDT:USDT", 64000.0, 62000.0, "2026-07-20T10:00:00+00:00"),
    ]
    warning = main._check_new_duplicate_trade(history, new_record, "主流幣/市場掃描")
    assert warning is not None
    assert "ALLO/USDT:USDT" in warning
    assert "2 筆完全相同" in warning


def test_skips_incomplete_records():
    new_record = _record("BTC/USDT:USDT", None, None, "2026-07-28T10:00:00+00:00")
    history = [
        new_record,
        _record("BTC/USDT:USDT", None, None, "2026-07-28T09:00:00+00:00"),
    ]
    assert main._check_new_duplicate_trade(history, new_record, "主流幣/市場掃描") is None
