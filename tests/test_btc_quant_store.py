from btc_quant.store import FileStore


def test_file_store_roundtrip(tmp_path):
    st = FileStore(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    assert st.load() is None
    st.save({"cash": 10.0})
    assert st.load() == {"cash": 10.0}
    for i in range(3):
        st.append({"kind": "open", "ts": f"t{i}"})
    recent = st.recent(2)
    assert [e["ts"] for e in recent] == ["t2", "t1"]


def test_db_store_raises_instead_of_pretending_state_is_missing(monkeypatch):
    # 資料庫暫時連不上時，不能回傳 None（runner 會以為沒有狀態而重置帳戶）
    import pytest

    import database
    from btc_quant.store import DbStore

    monkeypatch.setattr(database, "DATABASE_URL", "postgres://example")

    def boom():
        raise OSError("db down")

    monkeypatch.setattr(database, "_connect", boom)
    with pytest.raises(OSError):
        DbStore().load()
    with pytest.raises(OSError):
        DbStore().save({"cash": 1})
    with pytest.raises(OSError):
        DbStore().append({"kind": "open"})
