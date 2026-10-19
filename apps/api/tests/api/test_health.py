from fastapi.testclient import TestClient


def test_health_reports_tier_and_cache_mode(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["tier"] == "full"
    assert body["cache_mode"] == "replay"
    assert body["version"]
