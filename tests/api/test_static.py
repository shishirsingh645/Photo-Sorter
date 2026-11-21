def test_data_peek_and_demo_folders_are_served(client, paths):
    for folder in (paths.data, paths.peek, paths.demo):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a.txt").write_text(folder.name, encoding="utf-8")
        assert client.get(f"/{folder.name}/a.txt").text == folder.name


def test_a_missing_folder_is_a_404_not_a_crash(client):
    assert client.get("/peek/none.jpg").status_code == 404


def test_an_unusable_root_does_not_stop_the_app_being_built(tmp_path):
    from photosorter.api.app import create_app
    from photosorter.config import Paths

    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")  # a file where the root folder should be
    assert create_app(Paths(root=blocker)) is not None
