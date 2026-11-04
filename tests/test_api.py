import pytest
from fastapi.testclient import TestClient

from shortstock import db
from shortstock.api import create_app


@pytest.fixture
def client():
    with TestClient(create_app(start_worker=False)) as c:
        yield c


def test_settings_are_masked_and_updatable(client):
    client.put(
        "/api/settings", json={"values": {"fish_api_key": "fish-1234567890abcd", "tts_provider": "fish"}}
    )
    rows = {s["key"]: s for s in client.get("/api/settings").json()}
    assert rows["fish_api_key"]["value"] == "fis••••abcd"
    assert rows["tts_provider"]["value"] == "fish"
    client.put("/api/settings", json={"values": {"fish_api_key": "fis••••abcd"}})
    assert db.get_setting("fish_api_key") == "fish-1234567890abcd"
    assert client.put("/api/settings", json={"values": {"nope": "x"}}).status_code == 400


def test_run_lifecycle(client, script):
    r = client.post("/api/runs", json={"script": script, "options": {"aspect_ratio": "16:9", "speed": 1.1}})
    assert r.status_code == 200
    run = r.json()
    assert run["status"] == "queued" and run["options"]["aspect_ratio"] == "16:9"

    detail = client.get(f"/api/runs/{run['id']}").json()
    assert [s["name"] for s in detail["stages"]] == ["voice", "plan", "footage", "render"]
    assert detail["video"] is None

    assert client.post(f"/api/runs/{run['id']}/retry").status_code == 409
    db.update_run(run["id"], status="failed")
    assert (
        client.post(f"/api/runs/{run['id']}/retry", json={"from_stage": "footage"}).json()["status"]
        == "queued"
    )
    assert client.delete(f"/api/runs/{run['id']}").status_code == 200
    assert client.get(f"/api/runs/{run['id']}").status_code == 404


def test_validation_and_errors(client):
    assert client.post("/api/runs", json={"script": "x", "options": {"speed": 3}}).status_code == 422
    assert client.get("/api/voices?provider=elevenlabs").status_code == 400
    checks = {c["name"]: c for c in client.get("/api/health").json()["checks"]}
    assert checks["voice"]["ok"] is False and checks["footage"]["ok"] is False


def test_storyboard_reports_sentences_and_offsets(client, script):
    board = client.post("/api/storyboard", json={"script": script}).json()
    assert board["title"] == "Walking"
    first = board["sentences"][0]
    assert first["query"] == "person walking in park" and first["query_source"] == "hint"
    assert script[first["start"] : first["end"]].startswith("A short walk")
    assert board["sentences"][1]["query_source"] == "keywords"
    assert client.post("/api/storyboard", json={"script": ""}).json()["sentences"] == []
    assert client.post("/api/storyboard/suggest", json={"script": script}).status_code == 400
    assert client.get("/api/footage/search?q=forest").status_code == 400  # no Pexels key
