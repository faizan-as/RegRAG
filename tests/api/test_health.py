"""Tests for API liveness and request middleware."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.deps import get_db_session
from apps.api.main import create_app
from apps.api.resources import AppResources
from apps.api.settings import Settings
from src.common.storage import LocalArtifactStore


async def _fake_initializer(app):
    resources = AppResources(
        settings=Settings(_env_file=None),
        artifact_store=LocalArtifactStore(app.state.test_artifact_path),
    )
    app.state.resources = resources
    return resources


def test_health_is_dependency_free_and_sets_request_id(tmp_path) -> None:
    application = create_app(_fake_initializer)
    application.state.test_artifact_path = tmp_path

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_readiness_returns_503_when_required_resources_are_unavailable(tmp_path) -> None:
    application = create_app(_fake_initializer)
    application.state.test_artifact_path = tmp_path

    class FakeSession:
        async def execute(self, statement):
            return None

    async def db_override():
        yield FakeSession()

    application.dependency_overrides[get_db_session] = db_override

    with TestClient(application) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert any(not dependency["healthy"] for dependency in response.json()["dependencies"])
