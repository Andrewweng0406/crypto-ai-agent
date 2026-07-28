"""
2026-07-27發現：主流幣/市場掃描的 state.history 也出現過跟RSI2(2026-07-15)
同一種bug訊號——ALLO/USDT:USDT 在正式站真實歷史紀錄裡，2026-07-13一天內灌出
7筆entry_price=0.5134/exit_price=0.4695/stop_loss完全相同的紀錄，全部在12-14
秒內開平倉完畢。時間點早於2026-07-14「即時報價取代舊K線收盤價當進場價」那次
修復，且修復後至今沒有出現過新的重複組——這是清理歷史髒資料，不是現在還在
發生的bug，但正式站快照裡的舊紀錄仍會拉低使用者看到的win rate統計，所以需要
跟RSI2當初一樣的啟動時清理。_purge_duplicate_trade_history() 把原本只給RSI2
用的邏輯抽成通用版，這裡驗證套在主流幣歷史格式（帶leverage/exit_reason等
欄位，不是RSI2那種格式）一樣正確。
"""

import main


def _main_record(symbol, entry_price, exit_price, stop_loss, leverage, closed_at):
    return {
        "symbol": symbol, "side": "Long", "entry_price": entry_price, "exit_price": exit_price,
        "take_profit": entry_price * 1.05, "stop_loss": stop_loss, "leverage": leverage,
        "result": "LOSS", "pnl_pct": -8.56, "opened_at": closed_at, "closed_at": closed_at,
        "smart_money_notes": [],
    }


def test_purge_drops_allo_style_duplicate_group():
    # 真實正式站案例的簡化重現：同一組entry/exit/stop_loss出現7次，應該整組丟棄
    history = [
        _main_record("ALLO/USDT:USDT", 0.5134, 0.4695, 0.4695, 1, f"2026-07-13T23:{41-i}:14+00:00")
        for i in range(7)
    ] + [
        _main_record("BTC/USDT:USDT", 64000.0, 66000.0, 62000.0, 5, "2026-07-20T10:00:00+00:00"),
    ]
    cleaned = main._purge_duplicate_trade_history(history, "主流幣/市場掃描")
    assert [r["symbol"] for r in cleaned] == ["BTC/USDT:USDT"]


def test_purge_keeps_same_symbol_different_entries():
    # 同一個標的多次交易是正常現象，只要entry_price/stop_loss不完全相同就該保留
    history = [
        _main_record("ETH/USDT:USDT", 3000.0, 3100.0, 2900.0, 5, "2026-07-20T10:00:00+00:00"),
        _main_record("ETH/USDT:USDT", 3050.0, 2950.0, 2950.0, 5, "2026-07-21T10:00:00+00:00"),
    ]
    cleaned = main._purge_duplicate_trade_history(history, "主流幣/市場掃描")
    assert len(cleaned) == 2
