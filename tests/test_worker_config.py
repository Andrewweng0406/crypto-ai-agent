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
