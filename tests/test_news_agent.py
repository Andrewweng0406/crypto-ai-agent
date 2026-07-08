"""AI 智能投研 Agent：情緒分析 Prompt 組裝、跟現有開倉部位的共振比對邏輯。"""

import pytest

import main
from main import US_STOCK_SYMBOLS, _match_open_signals_for_symbol, build_sentiment_prompt


@pytest.fixture(autouse=True)
def clean_state():
    """比對邏輯會讀 main.state 這個全域單例，測試前後把相關欄位還原，避免測試互相汙染。"""
    saved_symbols = dict(main.state.symbols)
    saved_us_stock = dict(main.state.us_stock_states)
    main.state.symbols.clear()
    main.state.us_stock_states.clear()
    yield
    main.state.symbols.clear()
    main.state.symbols.update(saved_symbols)
    main.state.us_stock_states.clear()
    main.state.us_stock_states.update(saved_us_stock)


def test_prompt_includes_title_and_summary():
    prompt = build_sentiment_prompt("Bitcoin surges past $100k", "BTC rallied on ETF inflows")
    assert "Bitcoin surges past $100k" in prompt
    assert "BTC rallied on ETF inflows" in prompt


def test_prompt_handles_missing_summary():
    prompt = build_sentiment_prompt("Some headline", "")
    assert "無摘要" in prompt


def test_match_finds_open_crypto_position():
    sym_state = main.state.get_symbol_state("BTC/USDT:USDT")
    sym_state.open_signal = {"side": "Long", "entry_price": 60000}

    matches = _match_open_signals_for_symbol("BTC")
    assert len(matches) == 1
    assert matches[0]["kind"] == "crypto"
    assert matches[0]["side"] == "Long"


def test_match_finds_open_us_stock_position():
    ticker = US_STOCK_SYMBOLS["TSLA"]
    us_state = main.state.get_us_stock_state(ticker)
    us_state.open_signal = {"side": "Short", "entry_price": 400}

    matches = _match_open_signals_for_symbol("TSLA")
    assert len(matches) == 1
    assert matches[0]["kind"] == "us_stock"
    assert matches[0]["side"] == "Short"


def test_no_match_when_no_open_position():
    assert _match_open_signals_for_symbol("BTC") == []


def test_no_match_when_position_exists_but_symbol_differs():
    sym_state = main.state.get_symbol_state("ETH/USDT:USDT")
    sym_state.open_signal = {"side": "Long", "entry_price": 3000}

    assert _match_open_signals_for_symbol("BTC") == []


def test_no_match_when_symbol_state_exists_but_no_open_signal():
    main.state.get_symbol_state("BTC/USDT:USDT")  # 建立狀態但不設定 open_signal
    assert _match_open_signals_for_symbol("BTC") == []
