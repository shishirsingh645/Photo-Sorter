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


def test_state_survives_a_missing_categories_file(client, paths):
    paths.categories_file.unlink()
    assert client.get("/api/state").json()["categories"] == []
