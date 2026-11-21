import pytest


def test_post_from_a_foreign_origin_is_rejected(client):
    r = client.post("/api/peek", json={"source": "."}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_every_mutating_method_is_guarded(client, method):
    r = getattr(client, method)("/api/anything", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_a_look_alike_origin_is_rejected(client):
    for origin in ("http://127.0.0.1:8765.evil.example", "http://localhost:9999", "https://127.0.0.1:8765"):
        r = client.post("/api/peek", json={}, headers={"Origin": origin})
        assert r.status_code == 403, origin


def test_post_with_no_origin_header_is_allowed(client):
    assert "origin" not in client.headers
    assert client.post("/api/peek", json={}).status_code != 403


@pytest.mark.parametrize("origin", ["http://localhost:8765", "http://127.0.0.1:8765"])
def test_post_from_localhost_origin_is_allowed(client, origin):
    assert client.post("/api/peek", json={}, headers={"Origin": origin}).status_code != 403


def test_get_requests_are_not_origin_guarded(client):
    r = client.get("/api/state", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200


def test_the_guard_follows_the_port_the_app_was_built_for(paths):
    from fastapi.testclient import TestClient

    from photosorter.api.app import create_app

    c = TestClient(create_app(paths, port=9000), base_url="http://127.0.0.1:9000")
    assert c.post("/x", headers={"Origin": "http://localhost:9000"}).status_code != 403
    assert c.post("/x", headers={"Origin": "http://localhost:8765"}).status_code == 403


def test_the_403_names_the_origin_it_expected(client):
    r = client.post("/x", headers={"Origin": "http://evil.example"})
    assert "http://127.0.0.1:8765" in r.json()["detail"] and "http://evil.example" in r.json()["detail"]


@pytest.mark.parametrize("method", ["get", "post"])
def test_a_foreign_host_header_is_rejected_on_every_method(client, method):
    # DNS rebinding: the browser sends the attacker's hostname as Host
    r = getattr(client, method)("/api/state", headers={"Host": "rebind.evil.example:8765"})
    assert r.status_code == 400


def test_localhost_host_is_accepted(client):
    assert client.get("/api/state", headers={"Host": "localhost:8765"}).status_code == 200


def test_dev_flag_is_accepted(paths):
    from photosorter.api.app import create_app

    assert create_app(paths, dev=True) is not None
