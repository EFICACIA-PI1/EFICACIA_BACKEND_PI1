import pytest


@pytest.mark.django_db
def test_health_endpoint_returns_200(client):
    response = client.get("/api/health/")

    assert response.status_code == 200
