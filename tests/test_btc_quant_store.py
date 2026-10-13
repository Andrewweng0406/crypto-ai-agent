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
