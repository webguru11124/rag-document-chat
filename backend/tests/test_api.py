"""End-to-end API tests using the offline mock provider."""

from tests.conftest import make_pdf, parse_sse

SOLAR = (
    "Solar panels convert sunlight into electricity using photovoltaic cells. "
    "Panels facing south produce the most energy in the northern hemisphere. "
    "A typical residential system pays for itself in eight to twelve years."
)
KUBERNETES = "Kubernetes schedules pods onto nodes and restarts containers that fail health checks."


def upload(client, kb_id: str, filename: str, data: bytes, headers: dict | None = None):
    return client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers or {},
    )


def chat(client, kb_id: str, messages: list[dict], **extra):
    return client.post(
        "/api/chat",
        json={
            "knowledge_base_id": kb_id,
            "messages": messages,
            "provider": "mock",
            "model": "mock-extractive",
            **extra,
        },
    )


def test_health_and_config(client):
    assert client.get("/api/health").json() == {"status": "ok"}

    config = client.get("/api/config").json()
    assert [p["id"] for p in config["providers"]] == ["openai", "anthropic", "google", "mock"]
    # No server keys in tests, so the offline provider is the default.
    assert config["defaults"]["chat_provider"] == "mock"
    assert config["defaults"]["embedding_provider"] == "mock"
    anthropic = next(p for p in config["providers"] if p["id"] == "anthropic")
    assert anthropic["chat_models"][0]["id"] == "claude-opus-5-5"
    assert anthropic["embedding_models"] == []
    assert ".pdf" in config["limits"]["extensions"]


def test_knowledge_base_crud(client, mock_kb):
    listed = client.get("/api/knowledge-bases").json()
    assert [kb["id"] for kb in listed] == [mock_kb["id"]]
    assert listed[0]["document_count"] == 0

    bad = client.post("/api/knowledge-bases", json={"name": "X", "embedding_provider": "anthropic"})
    assert bad.status_code == 400

    assert client.delete(f"/api/knowledge-bases/{mock_kb['id']}").status_code == 204
    assert client.get(f"/api/knowledge-bases/{mock_kb['id']}").status_code == 404
    assert client.delete(f"/api/knowledge-bases/{mock_kb['id']}").status_code == 404


def test_upload_search_and_delete_documents(client, mock_kb):
    kb_id = mock_kb["id"]
    solar = upload(client, kb_id, "solar.txt", SOLAR.encode())
    assert solar.status_code == 201, solar.text
    pdf = upload(client, kb_id, "ops/k8s.pdf", make_pdf(["Cluster basics.", KUBERNETES]))
    assert pdf.status_code == 201, pdf.text
    assert pdf.json()["filename"] == "k8s.pdf"  # directory parts are dropped
    assert pdf.json()["pages"] == 2

    kb = client.get(f"/api/knowledge-bases/{kb_id}").json()
    assert kb["document_count"] == 2 and kb["chunk_count"] >= 3

    hits = client.post(
        f"/api/knowledge-bases/{kb_id}/search",
        json={
            "query": "how does kubernetes restart failed containers",
            "top_k": 2,
            "search_type": "similarity",
        },
    ).json()
    assert hits[0]["filename"] == "k8s.pdf"
    assert hits[0]["page"] == 2
    assert hits[0]["number"] == 1
    assert hits[0]["score"] > hits[1]["score"]

    assert client.delete(f"/api/knowledge-bases/{kb_id}/documents/{pdf.json()['id']}").status_code == 204
    hits = client.post(f"/api/knowledge-bases/{kb_id}/search", json={"query": "kubernetes pods"}).json()
    assert {hit["filename"] for hit in hits} == {"solar.txt"}


def test_upload_rejections(client, mock_kb):
    kb_id = mock_kb["id"]
    assert upload(client, kb_id, "a.txt", SOLAR.encode()).status_code == 201

    duplicate = upload(client, kb_id, "copy-of-a.txt", SOLAR.encode())
    assert duplicate.status_code == 409
    assert "a.txt" in duplicate.json()["detail"]

    assert upload(client, kb_id, "setup.exe", b"MZ").status_code == 415
    assert upload(client, kb_id, "empty.txt", b"").status_code == 400
    assert upload(client, kb_id, "big.txt", b"x" * (1024 * 1024 + 1)).status_code == 413
    assert upload(client, kb_id, "blank.pdf", make_pdf([""])).status_code == 422
    assert upload(client, "missing", "a.txt", b"hello").status_code == 404


def test_embedding_provider_without_a_key_is_a_clear_error(client):
    kb = client.post("/api/knowledge-bases", json={"name": "Docs", "embedding_provider": "openai"}).json()
    assert kb["embedding_model"] == "text-embedding-3-small"
    response = upload(client, kb["id"], "a.txt", b"hello world")
    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_chat_streams_sources_then_answer(client, mock_kb):
    kb_id = mock_kb["id"]
    upload(client, kb_id, "solar.txt", SOLAR.encode())
    upload(client, kb_id, "k8s.txt", KUBERNETES.encode())

    response = chat(client, kb_id, [{"role": "user", "content": "Which direction should solar panels face?"}])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sources" and names[-1] == "done"
    assert set(names[1:-1]) == {"token"}

    sources = events[0][1]["sources"]
    assert sources[0]["filename"] == "solar.txt"
    answer = "".join(data["text"] for name, data in events if name == "token")
    assert "facing south" in answer
    assert "[1]" in answer


def test_follow_up_questions_are_condensed_before_retrieval(client, mock_kb):
    kb_id = mock_kb["id"]
    upload(client, kb_id, "solar.txt", SOLAR.encode())
    response = chat(
        client,
        kb_id,
        [
            {"role": "user", "content": "Tell me about solar panels"},
            {"role": "assistant", "content": "They convert sunlight into electricity [1]."},
            {"role": "user", "content": "How long until they pay off?"},
        ],
    )
    events = parse_sse(response.text)
    query = events[0][1]["query"]
    assert "pay off" in query and "solar panels" in query


def test_chat_validation_errors(client, mock_kb):
    kb_id = mock_kb["id"]
    question = [{"role": "user", "content": "Anything?"}]

    empty = chat(client, kb_id, question)
    assert empty.status_code == 400
    assert "Upload a document" in empty.json()["detail"]

    upload(client, kb_id, "solar.txt", SOLAR.encode())
    assert chat(client, "missing", question).status_code == 404
    assert chat(client, kb_id, question, provider="nope").status_code == 400
    assert chat(client, kb_id, [{"role": "assistant", "content": "Hi"}]).status_code == 422

    no_key = chat(client, kb_id, question, provider="anthropic", model="claude-opus-5-5")
    assert no_key.status_code == 400
    assert "ANTHROPIC_API_KEY" in no_key.json()["detail"]
