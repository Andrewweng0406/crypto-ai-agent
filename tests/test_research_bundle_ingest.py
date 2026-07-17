"""
2026-07-17新增：美股多機構研究彙總（moomoo研究API本機同步）的雲端接收/查詢
端點。驗證：(1) API key 驗證正確擋掉未授權請求，(2) 送進去的資料原封不動存
起來、且rating數值有正確轉成中文標籤，(3) 查詢端點涵蓋範圍是美股ORB關注
清單跟期權分析關注清單的聯集，(4) 沒同步過的標的回傳 has_data=False 而不是
直接消失或報錯。
"""

from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)

VALID_KEY = "test-research-api-key"


def _reset_watchlists():
    main.state.us_stock_watchlist = {"TSLA": "NCSKTSLA2USD/USDT:USDT"}
    main.state.options_watchlist = {"NVDA": "NVDA"}
    main.state.research_bundles = {}


def test_ingest_rejects_missing_api_key(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", VALID_KEY)
    resp = client.post("/api/ingest/research", json={"symbol": "NVDA"})
    assert resp.status_code == 401


def test_ingest_rejects_wrong_api_key(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", VALID_KEY)
    resp = client.post(
        "/api/ingest/research",
        json={"symbol": "NVDA"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_ingest_disabled_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", None)
    resp = client.post(
        "/api/ingest/research",
        json={"symbol": "NVDA"},
        headers={"X-API-Key": "anything"},
    )
    assert resp.status_code == 401


def test_ingest_accepts_valid_key_and_stores_data(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", VALID_KEY)
    _reset_watchlists()

    payload = {
        "symbol": "nvda",  # 故意小寫，驗證會被正規化成大寫存放
        "consensus_high": 500.0,
        "consensus_average": 309.94,
        "consensus_low": 250.0,
        "consensus_total": 37,
        "consensus_rating": 4,
        "consensus_buy_pct": 97.3,
        "consensus_hold_pct": 2.7,
        "consensus_sell_pct": 0.0,
        "institution_ratings": [
            {
                "institution_name": "花旗",
                "rating": 4,
                "target_price": 300.0,
                "recommendation_date_str": "2026-07-14",
                "rating_url": "https://example.com/citi-nvda",
            },
            {
                "institution_name": "巴克萊銀行",
                "rating": 1,
                "target_price": 200.0,
                "recommendation_date_str": "2026-07-09",
                "rating_url": "https://example.com/barclays-nvda",
            },
        ],
        "morningstar_star_rating": 3,
        "morningstar_fair_value": 280.0,
        "morningstar_fair_value_context": "測試用公允價值敘述",
        "morningstar_moat_label": "寬",
        "morningstar_moat_context": "測試用護城河敘述",
        "morningstar_uncertainty_label": "高",
        "morningstar_financial_health_label": "優良",
    }
    resp = client.post("/api/ingest/research", json=payload, headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert resp.json() == {"accepted": True}

    assert "NVDA" in main.state.research_bundles
    stored = main.state.research_bundles["NVDA"]
    assert stored["consensus_average"] == 309.94
    assert len(stored["institution_ratings"]) == 2
    assert stored["updated_at"] is not None


def test_get_research_bundles_reports_has_data_false_for_unsynced_symbol(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", VALID_KEY)
    _reset_watchlists()

    resp = client.get("/api/us/research-bundles")
    assert resp.status_code == 200
    data = resp.json()
    by_symbol = {u["symbol"]: u for u in data["underlyings"]}
    assert by_symbol["TSLA"]["has_data"] is False
    assert by_symbol["TSLA"]["institution_ratings"] == []


def test_get_research_bundles_covers_union_of_watchlists(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", VALID_KEY)
    _reset_watchlists()

    resp = client.get("/api/us/research-bundles")
    symbols = {u["symbol"] for u in resp.json()["underlyings"]}
    assert symbols == {"TSLA", "NVDA"}


def test_get_research_bundles_returns_stored_data_with_rating_label(monkeypatch):
    monkeypatch.setattr(main, "WHALE_SWEEP_API_KEY", VALID_KEY)
    _reset_watchlists()

    payload = {
        "symbol": "NVDA",
        "consensus_rating": 4,
        "institution_ratings": [
            {"institution_name": "花旗", "rating": 1, "target_price": 200.0},
        ],
    }
    client.post("/api/ingest/research", json=payload, headers={"X-API-Key": VALID_KEY})

    resp = client.get("/api/us/research-bundles")
    by_symbol = {u["symbol"]: u for u in resp.json()["underlyings"]}
    nvda = by_symbol["NVDA"]
    assert nvda["has_data"] is True
    assert nvda["consensus_rating"] == 4
    assert nvda["consensus_rating_label"] == "買入"
    assert nvda["institution_ratings"][0]["institution_name"] == "花旗"
    assert nvda["institution_ratings"][0]["rating"] == 1


def test_rating_label_mapping_covers_all_five_levels():
    assert main.RESEARCH_RATING_LABELS[1] == "賣出"
    assert main.RESEARCH_RATING_LABELS[2] == "表現不佳"
    assert main.RESEARCH_RATING_LABELS[3] == "持有"
    assert main.RESEARCH_RATING_LABELS[4] == "買入"
    assert main.RESEARCH_RATING_LABELS[5] == "強力買入"
