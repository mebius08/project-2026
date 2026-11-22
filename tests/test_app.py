"""Opt-in HTTP integration tests for an already running project container.

Run with DOTA_TEST_BASE_URL=http://127.0.0.1:8080. CI sets this only after the
container's readiness check. No server, database, Docker or network download is
started by pytest; ordinary local unit-test runs skip these external checks.
"""

import os

import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def server():
    base_url = os.environ.get("DOTA_TEST_BASE_URL")
    if not base_url:
        pytest.skip("Set DOTA_TEST_BASE_URL to the running Docker app to enable HTTP tests")
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        yield client


def test_matches_returns_json_list_over_http(server):
    response = server.get("/api/matches")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    matches = response.json()
    assert isinstance(matches, list)
    assert all(isinstance(match, dict) and "source_match_id" in match for match in matches)


def test_unknown_match_returns_404_over_http(server):
    response = server.get("/api/matches/course_ci/no-such-match")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Historical match not found."


def test_invalid_archive_limit_is_validation_error_over_http(server):
    response = server.get("/archive", params={"limit": "two"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_page_and_packaged_static_are_available_over_http(server):
    page = server.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "История матчей" in page.text
    css = server.get("/static/css/style.css")
    image = server.get("/static/img/cat.svg")
    assert css.status_code == image.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert image.headers["content-type"].startswith("image/svg+xml")
