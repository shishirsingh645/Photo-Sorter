import pytest

from photosorter.config import write_json


def test_state_on_an_empty_install_reports_no_steps_done(client):
    s = client.get("/api/state").json()
    assert s["files"] == 0
    assert s["bytes"] == 0
    assert s["steps"] == {"scan": False, "dupes": False, "label": False, "jev_labels": False, "apply": False}
    assert len(s["categories"]) == 14
    assert s["source"] is None
    assert s["job"]["running"] is False


def test_state_reports_claude_and_jev_availability(client, monkeypatch):
    monkeypatch.setattr("photosorter.api.routes_state.find_claude", lambda: "/bin/claude")
    monkeypatch.setattr("photosorter.api.routes_state.find_jev_key", lambda paths: "k")
    s = client.get("/api/state").json()
    assert s["claude_cli"] is True and s["jev_key"] is True
    monkeypatch.setattr("photosorter.api.routes_state.find_claude", lambda: None)
    monkeypatch.setattr("photosorter.api.routes_state.find_jev_key", lambda paths: None)
    s = client.get("/api/state").json()
    assert s["claude_cli"] is False and s["jev_key"] is False


def test_state_reads_the_scan_from_the_slim_index_and_source_file(client, paths):
    write_json(paths.slim_file, [{"id": 0, "kind": "photo", "bytes": 10}, {"id": 1, "kind": "video", "bytes": 5}])
    write_json(paths.source_file, {"path": "/photos", "count": 2, "limit": 50})
    # a corrupt full inventory must not be touched: counting comes from the slim index
    paths.inventory_file.write_text("not json", encoding="utf-8")
    write_json(paths.overrides_file, {"0": "snaps", "1": "clips"})
    s = client.get("/api/state").json()
    assert (s["files"], s["bytes"]) == (2, 15)
    assert (s["source"], s["limit"]) == ("/photos", 50)
    assert s["steps"]["scan"] is True
    assert s["overrides"] == 2


def test_state_step_flags_follow_the_files_on_disk(client, paths):
    write_json(paths.dupes_file, [])
    write_json(paths.labels_file, {})
    write_json(paths.jev_file, {})
    assert client.get("/api/state").json()["steps"] == {
        "scan": False, "dupes": True, "label": True, "jev_labels": True, "apply": False,
    }


def test_state_names_the_file_manager_and_picker(client, monkeypatch):
    monkeypatch.setattr("photosorter.api.routes_state.file_manager_name", lambda: "Finder")
    monkeypatch.setattr("photosorter.api.routes_state.picker_available", lambda: (False, "no tkinter"))
    s = client.get("/api/state").json()
    assert s["file_manager"] == "Finder"
    assert s["picker_available"] is False and s["picker_reason"] == "no tkinter"
    assert isinstance(s["platform"], str) and s["platform"]




@pytest.mark.parametrize("raw", [b"{not json", b'{"a": 1}', b'[{"key": "x"}]', b"\xff\xfe\x00bad"])
def test_state_survives_a_damaged_categories_file(client, paths, raw):
    paths.categories_file.write_bytes(raw)
    r = client.get("/api/state")
    assert r.status_code == 200 and r.json()["categories"] == []


@pytest.mark.parametrize(
    "slim", ["{not json", '{"a": 1}', '["x", 3]', '[{"bytes": "9"}, {"bytes": null}, {"bytes": 4}]']
)
def test_state_survives_a_damaged_slim_index(client, paths, slim):
    paths.slim_file.parent.mkdir(parents=True, exist_ok=True)
    paths.slim_file.write_text(slim, encoding="utf-8")
    r = client.get("/api/state")
    assert r.status_code == 200
    assert r.json()["bytes"] in (0, 4)


def test_state_survives_a_damaged_source_file(client, paths):
    paths.source_file.parent.mkdir(parents=True, exist_ok=True)
    paths.source_file.write_text('{"path": 5, "limit": "x"}', encoding="utf-8")
    s = client.get("/api/state").json()
    assert s["source"] is None and s["limit"] is None


def test_a_raising_runner_does_not_take_state_down(paths):
    from fastapi.testclient import TestClient

    from photosorter.api.app import create_app

    class Boom:
        def state(self):
            raise ValueError("band_keys blew up")

    c = TestClient(create_app(paths, runner=Boom()), base_url="http://127.0.0.1:8765")
    r = c.get("/api/state")
    assert r.status_code == 200 and r.json()["job"]["running"] is False


def test_platform_is_one_of_the_three_names_the_page_branches_on(client, monkeypatch):
    import sys

    from photosorter.platform import platform_name

    for real, name in (("win32", "windows"), ("darwin", "darwin"), ("linux", "linux"), ("freebsd14", "linux")):
        monkeypatch.setattr(sys, "platform", real)
        assert platform_name() == name
    monkeypatch.undo()
    assert client.get("/api/state").json()["platform"] in {"windows", "darwin", "linux"}
