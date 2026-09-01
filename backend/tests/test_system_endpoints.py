from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Adaptive Procurement Scheduling API is running -v2"
    }


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_api_test_endpoint() -> None:
    response = client.get("/api/test")
    assert response.status_code == 200
    assert response.json() == {
        "message": "React successfully connected to FastAPI!"
    }
