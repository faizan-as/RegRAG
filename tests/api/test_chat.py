"""Focused API tests for durable citation-first chat."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.deps import get_agent_graph, get_db_session
from apps.api.main import create_app
from apps.api.ratelimit import enforce_chat_rate_limit
from apps.api.resources import AppResources
from apps.api.schemas.answer import Answer
from apps.api.schemas.documents import DocumentStatus
from apps.api.schemas.evidence import EvidenceCard
from apps.api.security import AuthenticatedUser, get_current_user
from apps.api.settings import Settings
from src.common.storage import LocalArtifactStore
from src.db.models import AuditEventRecord, ChatSessionRecord, ChatTurnRecord


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, record) -> None:
        self.added.append(record)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class _FakeGraph:
    async def ainvoke(self, state):
        card = EvidenceCard(
            citation_id="[1]",
            document_id="guidance-1",
            chunk_id="guidance-1:version:1",
            title="FDA Guidance",
            section_id="section-1",
            section_title="Scope",
            page_number=1,
            passage="Grounded FDA passage.",
            source_url="https://www.fda.gov/example",
            version_hash="a" * 64,
            document_status=DocumentStatus.FINAL,
            retrieval_score=0.8,
            rerank_score=0.9,
            confidence=0.9,
        )
        return {
            **state,
            "answer": Answer(
                text="Grounded answer [1].",
                evidence=[card],
                confidence=0.9,
                session_id=state["session_id"],
            ),
            "bound_evidence": [card],
            "faithfulness_passed": True,
            "retrieval_diagnostics": {"dense_status": "success"},
        }

    async def astream(self, state, *, stream_mode):
        yield await self.ainvoke(state)


async def _fake_initializer(app):
    resources = AppResources(
        settings=Settings(_env_file=None),
        artifact_store=LocalArtifactStore(app.state.test_artifact_path),
    )
    app.state.resources = resources
    return resources


def test_chat_creates_server_session_and_durable_turn(tmp_path) -> None:
    application = create_app(_fake_initializer)
    application.state.test_artifact_path = tmp_path
    fake_session = _FakeSession()

    async def db_override():
        yield fake_session

    application.dependency_overrides[get_db_session] = db_override
    application.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id="user-1", roles=["researcher"]
    )
    application.dependency_overrides[get_agent_graph] = lambda: _FakeGraph()
    application.dependency_overrides[enforce_chat_rate_limit] = lambda: None

    with TestClient(application) as client:
        response = client.post("/api/chat", json={"query": "What does FDA say?"})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["turn_id"]
    assert body["answer"]["evidence"][0]["citation_id"] == "[1]"
    assert any(isinstance(record, ChatSessionRecord) for record in fake_session.added)
    assert any(isinstance(record, ChatTurnRecord) for record in fake_session.added)
    assert any(isinstance(record, AuditEventRecord) for record in fake_session.added)
    assert fake_session.commits == 1


def test_chat_stream_emits_answer_only_in_final_event(tmp_path) -> None:
    application = create_app(_fake_initializer)
    application.state.test_artifact_path = tmp_path
    fake_session = _FakeSession()

    async def db_override():
        yield fake_session

    application.dependency_overrides[get_db_session] = db_override
    application.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id="user-1", roles=["researcher"]
    )
    application.dependency_overrides[get_agent_graph] = lambda: _FakeGraph()

    with TestClient(application) as client:
        response = client.post("/api/chat/stream", json={"query": "What does FDA say?"})

    body = response.text
    assert response.status_code == 200
    assert body.index("event: started") < body.index("event: committed") < body.index("event: done")
    assert body.count("Grounded answer [1].") == 1
    assert "Grounded answer [1]." not in body[: body.index("event: committed")]
