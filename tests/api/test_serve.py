import socket
import threading

import uvicorn
from fastapi.testclient import TestClient

from photosorter import __main__ as cli
from photosorter.api import LOOPBACK
from photosorter.api.app import create_app
from photosorter.api.serve import serve
from photosorter.jobs import JobRunner


def _free_port() -> int:
    with socket.socket() as s:
        s.bind((LOOPBACK, 0))
        return s.getsockname()[1]


def _capture_run(monkeypatch):
    """Replace the blocking server loop with one that records what it was handed."""
    seen = {}

    def fake_run(self, sockets=None):
        seen["server"], seen["sockets"] = self, sockets

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    return seen


def test_serve_binds_loopback_on_the_requested_port_and_app_agrees(monkeypatch, paths):
    port = _free_port()
    seen = _capture_run(monkeypatch)
    assert serve(paths, port=port, dev=False, open_browser=False) == 0
    sock = seen["sockets"][0]
    try:
        assert sock.getsockname() == (LOOPBACK, port)
        app = seen["server"].config.app
        ok = TestClient(app, base_url=f"http://127.0.0.1:{port}")
        assert ok.get("/api/state").status_code == 200
        # /api/state is GET-only (405), so this only proves the Origin allow-list accepts the bound port;
        # point it at a real POST route once Task 4's land.
        assert ok.post("/api/state", headers={"origin": f"http://127.0.0.1:{port}"}).status_code != 403
        assert ok.post("/api/state", headers={"origin": "http://127.0.0.1:8765"}).status_code == 403
        # the default port must NOT be accepted when another one was bound
        assert TestClient(app, base_url="http://127.0.0.1:8765").get("/api/state").status_code == 400
    finally:
        sock.close()


def test_port_in_use_names_the_port_and_suggests_another(capsys, paths):
    with socket.socket() as busy:
        busy.bind((LOOPBACK, 0))
        port = busy.getsockname()[1]
        assert serve(paths, port=port, dev=False, open_browser=False) == 1
    out = capsys.readouterr().out
    assert str(port) in out and f"--port {port + 1}" in out


def test_serve_subcommand_passes_flags_through(monkeypatch, tmp_path):
    got = {}

    def fake(paths, port, dev, open_browser):
        got.update(p=paths, port=port, dev=dev, b=open_browser)
        return 0

    monkeypatch.setattr("photosorter.api.serve.serve", fake)
    assert cli.main(["serve", "--root", str(tmp_path), "--port", "8766", "--dev", "--no-browser"]) == 0
    assert (got["port"], got["dev"], got["b"], got["p"].root) == (8766, True, False, tmp_path)
    cli.main(["serve", "--root", str(tmp_path)])
    assert (got["port"], got["dev"], got["b"]) == (8765, False, True)


def test_no_host_flag():
    import pytest

    with pytest.raises(SystemExit):
        cli._parser().parse_args(["serve", "--host", "0.0.0.0"])


def test_json_data_is_served_with_no_store(client, paths):
    (paths.data / "labels.json").parent.mkdir(exist_ok=True)
    (paths.data / "labels.json").write_text("{}")
    r = client.get("/data/labels.json")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"


def test_missing_frontend_build_says_what_to_do(client):
    r = client.get("/")
    assert r.status_code == 200 and "npm run build" in r.text and "text/html" in r.headers["content-type"]
    assert client.get("/api/state").status_code == 200  # API unaffected


def test_built_frontend_is_served_at_root(paths):
    dist = paths.root / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>REAL BUILD</html>")
    r = TestClient(create_app(paths), base_url="http://127.0.0.1:8765").get("/")
    assert "REAL BUILD" in r.text and r.headers["cache-control"] == "no-store"
    assert TestClient(create_app(paths), base_url="http://127.0.0.1:8765").get("/api/state").status_code == 200


def test_dev_skips_dist_and_sends_no_store(paths):
    dist = paths.root / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>STALE BUNDLE</html>")
    (paths.data / "x.png").parent.mkdir(exist_ok=True)
    (paths.data / "x.png").write_bytes(b"png")
    c = TestClient(create_app(paths, dev=True), base_url="http://127.0.0.1:8765")
    r = c.get("/")
    assert "STALE BUNDLE" not in r.text and r.headers["cache-control"] == "no-store"
    assert c.get("/data/x.png").headers["cache-control"] == "no-store"


def test_port_zero_uses_the_port_the_os_chose(monkeypatch, paths):
    seen = _capture_run(monkeypatch)
    assert serve(paths, port=0, dev=False, open_browser=False) == 0
    sock = seen["sockets"][0]
    try:
        real = sock.getsockname()[1]
        assert real != 0
        c = TestClient(seen["server"].config.app, base_url=f"http://127.0.0.1:{real}")
        assert c.get("/api/state").status_code == 200
    finally:
        sock.close()


def test_the_served_app_has_a_job_runner(monkeypatch, paths):
    # create_app(runner=None) is the default, and every other test injects a runner, so only the real
    # serve() path can notice that nobody attached one. Without it every start was refused.
    seen = _capture_run(monkeypatch)
    assert serve(paths, port=0, dev=False, open_browser=False) == 0
    sock = seen["sockets"][0]
    try:
        app = seen["server"].config.app
        assert isinstance(app.state.runner, JobRunner)
        c = TestClient(app, base_url=f"http://127.0.0.1:{sock.getsockname()[1]}")
        assert "no job runner" not in c.post("/api/cancel").text
    finally:
        sock.close()


def test_out_of_range_port_is_a_sentence_not_a_traceback(capsys, paths):
    for bad in (70000, -1):
        assert serve(paths, port=bad, dev=False, open_browser=False) == 1
    assert "0 to 65535" in capsys.readouterr().out


def test_browser_timer_is_daemon(monkeypatch, paths):
    made = []
    real = threading.Timer

    def spy(*a, **k):
        made.append(real(*a, **k))
        return made[-1]

    monkeypatch.setattr("photosorter.api.serve.threading.Timer", spy)
    seen = _capture_run(monkeypatch)
    assert serve(paths, port=0, dev=False, open_browser=True) == 0
    seen["sockets"][0].close()
    assert made and made[0].daemon
    made[0].cancel()


def test_previews_revalidate_but_json_is_never_stored(client, paths):
    (paths.peek / "0001.jpg").parent.mkdir(exist_ok=True)
    (paths.peek / "0001.jpg").write_bytes(b"jpg")
    (paths.data / "labels.json").parent.mkdir(exist_ok=True)
    (paths.data / "labels.json").write_text("{}")
    assert client.get("/peek/0001.jpg").headers["cache-control"] == "no-cache"
    assert client.get("/data/labels.json").headers["cache-control"] == "no-store"


def test_head_on_the_no_build_page_works(client):
    assert client.head("/").status_code == 200
