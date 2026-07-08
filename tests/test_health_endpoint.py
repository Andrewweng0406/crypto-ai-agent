"""/api/health 必須同時支援 GET 跟 HEAD——外部監控工具（如 UptimeRobot）預設用
HEAD 檢查，只註冊 GET 的話每次健康檢查都會收到 405，被誤判成服務掛掉。這是實際
在正式環境發生過的問題，不是假設性風險。"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_get_returns_200():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_head_returns_200_not_405():
    resp = client.head("/api/health")
    assert resp.status_code == 200
