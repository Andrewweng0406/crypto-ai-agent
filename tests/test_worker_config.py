import main


def test_env_flag_accepts_true_values(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("BACKGROUND_WORKERS_ENABLED", value)
        assert main._env_flag("BACKGROUND_WORKERS_ENABLED", False) is True


def test_env_flag_accepts_false_values(monkeypatch):
    for value in ("0", "false", "FALSE", "no", "off"):
        monkeypatch.setenv("BACKGROUND_WORKERS_ENABLED", value)
        assert main._env_flag("BACKGROUND_WORKERS_ENABLED", True) is False


def test_env_flag_uses_default_for_missing_or_invalid_values(monkeypatch):
    monkeypatch.delenv("BACKGROUND_WORKERS_ENABLED", raising=False)
    assert main._env_flag("BACKGROUND_WORKERS_ENABLED", True) is True

    monkeypatch.setenv("BACKGROUND_WORKERS_ENABLED", "maybe")
    assert main._env_flag("BACKGROUND_WORKERS_ENABLED", False) is False


def test_background_job_lease_ttl_has_minimum():
    assert main.background_job_lease_ttl(5, 6) == 120
    assert main.background_job_lease_ttl(300, 2) == 600


def test_legacy_strategy_loops_disabled_by_default(monkeypatch):
    for name in ("US_STOCK_ORB_ENABLED", "RSI2_MEANREV_ENABLED", "MEME_TRADE_ENABLED", "SCAN_UNIVERSE_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    assert main.legacy_strategy_flags() == {
        "us_stock_orb": False,
        "rsi2_meanrev": False,
        "meme_trade": False,
        "scan_universe": False,
    }


def test_legacy_strategy_loops_can_be_reenabled(monkeypatch):
    monkeypatch.setenv("MEME_TRADE_ENABLED", "true")
    assert main.legacy_strategy_flags()["meme_trade"] is True


def test_disabled_scan_universe_clears_altcoins_without_calling_exchanges(monkeypatch):
    import asyncio

    monkeypatch.delenv("SCAN_UNIVERSE_ENABLED", raising=False)
    main.state.scan_universe = ["PUMP/USDT:USDT", "SAND/USDT:USDT"]  # 例如從舊快照還原的名單
    asyncio.run(main.refresh_scan_universe({}))  # 空的 exchange_pool：若有呼叫交易所會 KeyError
    assert main.state.scan_universe == []
