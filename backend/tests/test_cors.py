from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/characters")
def characters() -> dict[str, list[object]]:
    return {"characters": []}


@app.post("/api/chat/stream")
def chat_stream() -> dict[str, str]:
    return {"status": "ok"}

client = TestClient(app)


def test_cors_allows_vite_fallback_localhost_port():
    response = client.get(
        "/api/characters",
        headers={"Origin": "http://localhost:5175"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5175"


def test_cors_preflight_allows_vite_fallback_localhost_port():
    response = client.options(
        "/api/chat/stream",
        headers={
            "Origin": "http://localhost:5175",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5175"
