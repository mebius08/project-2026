import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api
from tests.history_test_helpers import make_historical_match


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTA_ANALYTICS_DB_BACKEND", "sqlite")
    application = api.create_app(tmp_path / "course.sqlite3")
    return TestClient(application), application.state.repository


def test_project_templates_static_files_and_json_remain_available(web, monkeypatch):
    client, _ = web
    monkeypatch.setattr(api, "PROJECT_NAME", "<b>Project</b>")
    for path in ("/", "/archive"):
        response = client.get(path)
        assert response.status_code == 200
        assert "&lt;b&gt;Project&lt;/b&gt;" in response.text
        assert "<b>Project</b>" not in response.text
        assert "bootstrap@5.3.8" in response.text
        assert response.text.index("bootstrap@5.3.8") < response.text.index("/static/css/style.css")
        assert "/static/img/cat.svg" in response.text
    css, image = client.get("/static/css/style.css"), client.get("/static/img/cat.svg")
    assert css.status_code == image.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert image.headers["content-type"].startswith("image/svg+xml")
    assert "background:" in css.text
    assert client.get("/api/matches").json() == []
    assert client.get("/static/.env").status_code == 404


def test_server_rendered_archive_uses_actual_storage_filter_and_limit(web):
    client, repository = web
    first = replace(make_historical_match("archive-1"), source="replay_clarity", source_match_id="archive-1",
                    team_a_name="Team Spirit", team_b_name="Example Opponent", winner_name=None,
                    winner_side=None, tournament_name=None)
    second = replace(first, id="archive-2", source_match_id="archive-2", team_a_name="Team Liquid")
    repository.save_historical_match(first)
    repository.save_historical_match(second)
    page = client.get("/archive?team=SPIRIT&limit=1")
    assert page.status_code == 200
    assert "Team Spirit" in page.text and "Example Opponent" in page.text
    assert "Team Liquid" not in page.text and "Нет данных" in page.text
    assert "/api/matches/replay_clarity/archive-1" in page.text
    assert len(client.get("/api/matches").json()) == 2
    assert client.get("/api/matches/replay_clarity/archive-1").json()["team_a_name"] == "Team Spirit"


def test_query_and_stored_text_are_html_escaped(web):
    client, repository = web
    unsafe = '<script>alert("demo")</script>'
    repository.save_historical_match(replace(make_historical_match("escaped"), team_a_name=unsafe))
    page = client.get("/archive", params={"team": unsafe})
    assert page.status_code == 200
    assert unsafe not in page.text and "&lt;script&gt;" in page.text
    assert 'value="&lt;script&gt;' in page.text


@pytest.mark.parametrize("limit", ["two", "0", "201", "-1"])
def test_invalid_numeric_query_is_validation_error_not_server_error(web, limit):
    response = web[0].get("/archive", params={"limit": limit})
    assert response.status_code == 422


def test_empty_archive_preserves_explicit_empty_state(web):
    response = web[0].get("/archive?team=Unknown")
    assert response.status_code == 200
    assert "Матчи не найдены." in response.text


def entrypoint():
    spec = importlib.util.spec_from_file_location("course_entrypoint", Path(__file__).parents[1] / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_root_entrypoint_default_and_reload_configuration(monkeypatch):
    launcher = entrypoint()
    calls = []
    monkeypatch.setattr(launcher.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    launcher.main([])
    assert calls[-1] == (("app.api:create_app",), dict(factory=True, host="127.0.0.1", port=5001, reload=False))
    launcher.main(["--host", "0.0.0.0", "--port", "5002", "--reload"])
    assert calls[-1][1] == dict(factory=True, host="0.0.0.0", port=5002, reload=True)


@pytest.mark.parametrize("port", ["0", "65536", "-1", "two"])
def test_entrypoint_rejects_invalid_ports(port):
    with pytest.raises(SystemExit) as error:
        entrypoint().main(["--port", port])
    assert error.value.code == 2
