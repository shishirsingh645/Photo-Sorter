import socket

import uvicorn
from fastapi.testclient import TestClient

from photosorter import __main__ as cli
from photosorter.api import LOOPBACK
from photosorter.api.app import create_app
from photosorter.api.serve import serve
from photosorter.config import Paths


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
        assert ok.post("/api/state", headers={"origin": f"http://127.0.0.1:{port}"}).status_code != 403
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
    monkeypatch.setattr(cli, "serve", lambda paths, port, dev, open_browser: got.update(p=paths, port=port, dev=dev, b=open_browser) or 0)
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
