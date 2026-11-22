"""GET /api/file/{id} and /api/record/{id}: the route that serves the user's photo bytes."""

from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pillow_heif import register_heif_opener

from photosorter.api.app import create_app
from photosorter.api.routes_files import QuietFileResponse
from photosorter.config import Paths, write_json

register_heif_opener()


def _jpeg(color, size=(40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue() + b"\x00" * 3000  # trailing padding so ranges have room


def _rec(i: int, path: Path, kind="photo", sha="s") -> dict:
    return {
        "id": i, "path": str(path), "name": path.name, "ext": path.suffix.lower(), "kind": kind,
        "bytes": path.stat().st_size if path.exists() else 0, "sha256": f"{sha}{i}", "w": 0, "h": 0,
        "duration": 0.0,
    }


class World:
    """A scanned source folder, an outside folder holding a secret, and the files that describe them."""

    def __init__(self, paths: Paths, tmp: Path):
        self.paths = paths
        self.src = tmp / "photos"
        self.src.mkdir()
        self.outside = tmp / "elsewhere"
        self.outside.mkdir()
        self.jpg = self.src / "a.jpg"
        self.jpg_bytes = _jpeg("red")
        self.jpg.write_bytes(self.jpg_bytes)
        self.other_bytes = _jpeg("blue")
        (self.src / "b.jpg").write_bytes(self.other_bytes)
        Image.new("RGB", (64, 48), "green").save(self.src / "c.heic")
        (self.src / "d.mov").write_bytes(b"\x00\x00\x00\x14ftypqt  fake movie bytes" * 50)
        self.secret = self.outside / "secret.jpg"
        self.secret.write_bytes(b"TOP-SECRET-BYTES" * 100)
        self.write([self.jpg, self.src / "c.heic", self.src / "d.mov", self.src / "b.jpg"])

    def write(self, files: list[Path], sha: str = "s") -> None:
        recs = [_rec(i, p, "video" if p.suffix == ".mov" else "photo", sha) for i, p in enumerate(files)]
        self.paths.data.mkdir(parents=True, exist_ok=True)
        write_json(self.paths.inventory_file, recs)
        write_json(self.paths.source_file, {"path": str(self.src), "count": len(recs), "limit": 0})

    def write_raw(self, raw_path: str) -> None:
        rec = _rec(0, self.secret)
        rec["path"] = raw_path
        write_json(self.paths.inventory_file, [rec])


@pytest.fixture
def world(paths: Paths, tmp_path: Path) -> World:
    return World(paths, tmp_path)


def test_missing_id_returns_404(client, world):
    for bad in (99, -1):
        r = client.get(f"/api/file/{bad}")
        assert r.status_code == 404 and "No file" in r.json()["detail"]
    assert client.get("/api/record/99").status_code == 404


def test_no_scan_yet_returns_404(client):
    assert client.get("/api/file/0").status_code == 404


def test_file_deleted_since_the_scan_returns_404_not_500(client, world):
    world.jpg.unlink()
    r = client.get("/api/file/0")
    assert r.status_code == 404 and "no longer" in r.json()["detail"]


def test_jpeg_is_served_untouched_with_accept_ranges(client, world):
    r = client.get("/api/file/0")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == world.jpg_bytes  # these exact bytes, not the neighbour's
    assert r.content != world.other_bytes
    assert client.get("/api/file/3").content == world.other_bytes


def test_range_request_returns_206_with_content_range(client, world):
    size = len(world.jpg_bytes)
    r = client.get("/api/file/0", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 10-19/{size}"
    assert r.content == world.jpg_bytes[10:20]


def test_open_ended_range_runs_to_the_last_byte(client, world):
    size = len(world.jpg_bytes)
    r = client.get("/api/file/0", headers={"Range": "bytes=10-"})
    assert r.status_code == 206 and r.content == world.jpg_bytes[10:]
    assert r.headers["content-range"] == f"bytes 10-{size - 1}/{size}"


def test_range_past_the_end_is_clamped(client, world):
    size = len(world.jpg_bytes)
    r = client.get("/api/file/0", headers={"Range": f"bytes={size - 5}-{size + 5000}"})
    assert r.status_code == 206 and r.content == world.jpg_bytes[-5:]
    assert r.headers["content-range"] == f"bytes {size - 5}-{size - 1}/{size}"


def test_range_starting_past_the_end_is_416(client, world):
    size = len(world.jpg_bytes)
    r = client.get("/api/file/0", headers={"Range": f"bytes={size + 10}-"})
    assert r.status_code == 416


def test_client_disconnect_mid_stream_does_not_raise(world):
    scope = {"type": "http", "method": "GET", "headers": [], "path": "/x", "query_string": b"",
             "extensions": {"http.response.pathsend": {}}}
    scope.pop("extensions")

    async def receive():
        await asyncio.sleep(10)

    for exc in (BrokenPipeError, ConnectionResetError):
        started = []

        async def send(message, exc=exc, started=started):
            started.append(message["type"])
            if message["type"] == "http.response.body":
                raise exc

        asyncio.run(QuietFileResponse(world.jpg)(scope, receive, send))  # raises without the guard
        assert started[0] == "http.response.start"


def test_heic_is_converted_to_jpeg(client, world):
    r = client.get("/api/file/1")
    assert r.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(r.content))
    assert img.format == "JPEG" and img.size == (64, 48)
    assert r.content != (world.src / "c.heic").read_bytes()


def test_converted_image_is_capped_at_2400px_and_exif_transposed(client, world):
    big = Image.new("RGB", (3000, 1000), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 clockwise on display
    p = world.src / "big.tif"
    big.save(p, exif=exif)
    world.write([p])
    img = Image.open(io.BytesIO(client.get("/api/file/0").content))
    assert max(img.size) == 2400
    assert img.size[1] > img.size[0]  # transposed: portrait now


def test_mov_is_served_as_video_mp4(client, world):
    r = client.get("/api/file/2")
    assert r.headers["content-type"] == "video/mp4"
    assert r.content == (world.src / "d.mov").read_bytes()
    assert client.get("/api/file/2", headers={"Range": "bytes=0-3"}).status_code == 206


def test_unreadable_image_conversion_is_a_clean_error(client, world):
    bad = world.src / "broken.heic"
    bad.write_bytes(b"not an image")
    world.write([bad])
    r = client.get("/api/file/0")
    assert r.status_code == 415 and "convert" in r.json()["detail"]


def test_record_endpoint_returns_the_full_record(client, world):
    j = client.get("/api/record/0").json()
    assert set(j) >= {"id", "name", "sha256", "path"}
    assert j["sha256"] == "s0" and j["name"] == "a.jpg"
    assert client.get("/api/record/3").json()["name"] == "b.jpg"


# --- ids are positions: stale ids across a rescan -------------------------------------------------


def test_rescan_is_picked_up_without_a_restart(client, world):
    assert client.get("/api/file/0").content == world.jpg_bytes
    world.write([world.src / "b.jpg", world.jpg], sha="n")  # a rescan reordered the folder
    assert client.get("/api/file/0").content == world.other_bytes
    assert client.get("/api/record/0").json()["name"] == "b.jpg"


def test_a_stale_id_from_an_old_page_is_refused_not_served_as_another_photo(client, world):
    old_sha = client.get("/api/record/0").json()["sha256"]  # what the page open before the rescan holds
    world.write([world.src / "b.jpg", world.jpg], sha="n")
    r = client.get("/api/file/0", params={"sha": old_sha})
    assert r.status_code == 409 and "rescan" in r.json()["detail"].lower()
    assert r.content != world.other_bytes
    ok = client.get("/api/file/0", params={"sha": "n0"})
    assert ok.status_code == 200 and ok.content == world.other_bytes
    assert client.get("/api/record/0", params={"sha": old_sha}).status_code == 409


def test_an_id_past_the_end_after_a_shrinking_rescan_is_404(client, world):
    assert client.get("/api/file/3").status_code == 200
    world.write([world.jpg])
    assert client.get("/api/file/3").status_code == 404


# --- containment: every one of these must be refused by the containment check (403) -----------------
# Each target exists and holds secret bytes, so a 404 would mean "missing", not "refused".


def _refused(client, world, raw_path: str):
    world.write_raw(raw_path)
    r = client.get("/api/file/0")
    assert r.status_code == 403, (raw_path, r.status_code)
    assert "outside" in r.json()["detail"]
    assert b"TOP-SECRET" not in r.content


def test_absolute_path_outside_the_source_is_refused(client, world):
    _refused(client, world, str(world.secret))


def test_dotdot_segments_that_climb_out_are_refused(client, world):
    _refused(client, world, str(world.src / ".." / "elsewhere" / "secret.jpg"))


def test_dotdot_that_stays_inside_is_served(client, world):
    sub = world.src / "sub"
    sub.mkdir()
    world.write_raw(str(sub / ".." / "a.jpg"))
    r = client.get("/api/file/0")
    assert r.status_code == 200 and r.content == world.jpg_bytes  # a.jpg bytes, not the secret


def test_a_sibling_folder_sharing_a_string_prefix_is_refused(client, world):
    evil = world.src.parent / (world.src.name + "_evil")  # "photos_evil" startswith "photos"
    evil.mkdir()
    (evil / "x.jpg").write_bytes(b"TOP-SECRET-BYTES")
    _refused(client, world, str(evil / "x.jpg"))


def test_a_relative_path_is_refused(client, world, monkeypatch):
    monkeypatch.chdir(world.src.parent)  # "elsewhere/secret.jpg" would exist if it were resolved
    _refused(client, world, "elsewhere/secret.jpg")
    monkeypatch.chdir(world.outside)
    _refused(client, world, "secret.jpg")


@pytest.mark.skipif(sys.platform != "win32", reason="drive-relative and UNC forms are Windows paths")
def test_drive_relative_path_is_refused(client, world, monkeypatch):
    monkeypatch.chdir(world.outside)  # "C:secret.jpg" resolves against the cwd of that drive
    _refused(client, world, f"{world.secret.drive}secret.jpg")


@pytest.mark.skipif(sys.platform != "win32", reason="UNC paths are Windows paths")
def test_unc_path_to_the_same_machine_outside_is_refused(client, world):
    unc = "\\\\localhost\\" + str(world.secret).replace(":", "$", 1)
    if not Path(unc).exists():
        pytest.skip("administrative share not available here")
    _refused(client, world, unc)


@pytest.mark.skipif(sys.platform != "win32", reason="extended-length prefix is Windows only")
def test_extended_length_prefix_to_an_outside_file_is_refused(client, world):
    _refused(client, world, "\\\\?\\" + str(world.secret))


@pytest.mark.skipif(sys.platform != "win32", reason="8.3 short names are Windows only")
def test_windows_short_name_of_an_outside_file_is_refused(client, world):
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(world.secret), buf, 1024)
    if not buf.value:
        pytest.skip("short names are disabled on this volume")
    _refused(client, world, buf.value)


def _symlink(link: Path, target: Path, is_dir=False):
    try:
        os.symlink(target, link, target_is_directory=is_dir)
        return
    except (OSError, NotImplementedError):
        pass
    if is_dir and sys.platform == "win32":  # a junction needs no privilege and resolve() follows it too
        import subprocess

        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if done.returncode == 0:
            return
    pytest.skip("cannot create symlinks here")


def test_symlinked_file_pointing_outside_is_refused(client, world):
    link = world.src / "link.jpg"
    _symlink(link, world.secret)
    _refused(client, world, str(link))


def test_symlinked_folder_pointing_outside_is_refused(client, world):
    link = world.src / "linkdir"
    _symlink(link, world.outside, is_dir=True)
    _refused(client, world, str(link / "secret.jpg"))


def test_symlink_that_stays_inside_is_served(client, world):
    link = world.src / "alias.jpg"
    _symlink(link, world.jpg)
    world.write_raw(str(link))
    assert client.get("/api/file/0").content == world.jpg_bytes


def test_a_directory_inside_the_source_is_not_served(client, world):
    sub = world.src / "folder.jpg"
    sub.mkdir()
    world.write_raw(str(sub))
    assert client.get("/api/file/0").status_code == 404


def test_source_json_without_a_path_serves_nothing(client, world):
    write_json(world.paths.source_file, {"count": 4})  # nothing to contain against
    assert client.get("/api/file/0").status_code == 404


def test_path_is_not_a_request_input(client, world):
    r = client.get("/api/file/..%2F..%2Felsewhere%2Fsecret.jpg")
    assert r.status_code in (404, 422)
    assert b"TOP-SECRET" not in r.content


def test_foreign_host_is_still_rejected_on_the_file_route(world, paths):
    c = TestClient(create_app(paths), base_url="http://evil.example:8765")
    assert c.get("/api/file/0").status_code == 400
