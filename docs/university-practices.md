# Practices L2-L6 in the main project

The project repository is [mebius08/project-2026](https://github.com/mebius08/project-2026),
branch `university`. The name follows L3 Task 9 and L4 Task 9, which explicitly
call the project repository `project-2026`. The existing local folder can remain
`dota-betting-autopilot`; `origin` points to the renamed GitHub repository.
Classroom examples are adapted to Dota match analytics. FastAPI
is explicitly permitted in L4/L5; a second Flask application is not required.

## Project and practice submissions are separate

| Work | Repository used for submission |
|---|---|
| Dota project / Project CI (Task 9) | `mebius08/project-2026`, branch `university` |
| Individual L5/L6 practice Tasks 1-8 | The assigned Classroom repository; the existing one is [ci-tests-2026-w-mebius08](https://github.com/CS-intro-with-Python/ci-tests-2026-w-mebius08), branch `main` |
| JSON/Docker practice | A separate repository issued by the `docker-json-2026-th` Classroom assignment; it is not created by renaming this project |

The project adaptations below do not replace the literal practice hand-ins.
In particular, `hello.yml`, `python.yml`, `ci.yml`, `hello.py` and the books HTTP
tests belong in the CI practice repository for its Tasks 4-8, even though the
Dota project has its own equivalent CI and HTTP tests. Check the assigned
repository, branch and revision when reconciling course results. A green run in
this project alone does not establish that an individual laboratory was handed in
or that an assessment snapshot has been updated.

## What corresponds to the practice tasks

| Practice | Implementation in this project | Check |
|---|---|---|
| L2: server and routes | Root `app.py` starts `app.api:create_app`; the existing `/api/matches` and match-detail routes provide multiple routes | `python app.py --port 5001` |
| L2: parameters, safe rendering and validation | `/archive?team=Spirit&limit=20`; Jinja escapes query/stored text; invalid limits return 422, unknown match identity returns 404 | `tests/test_course_web.py`, `tests/test_api.py` |
| L3: JSON and list/detail responses | `/api/matches` and `/api/matches/{source}/{source_match_id}` return JSON from actual storage | `python tools/check_api.py --base-url http://127.0.0.1:5001` |
| L3: persistent source | Existing SQLite/PostgreSQL repositories supply match records; an extra books JSON would duplicate storage | Existing API/repository tests |
| L3: image and project description | `Dockerfile`, `.dockerignore`, pinned `requirements-web.txt`, README About | Python 3.14 slim; container port 5001 |
| L3: image publication | Existing gated GHCR workflow publishes the project image after successful tests/build/HTTP checks | README GHCR section; publication occurs after push |
| L4: templates and variables | `/` uses `templates/index.html`; `/archive` uses `templates/archive.html` with project name, description and search variables | HTML responses and escaping tests |
| L4: template loop | `/archive` renders the existing match list with `{% for %}`, including an explicit empty state and unknown fields | `tests/test_course_web.py` |
| L4: Bootstrap/static assets | Bootstrap 5.3.8 CDN, then local `app/static/css/style.css`; `app/static/img/cat.svg` is the local pet image | CSS/SVG return HTTP 200 |
| L4: development bind mount | README Run for development mounts `app/` and `app.py` and enables reload | Refresh assets/templates; Python reloads automatically |
| L4: project route plan | README User features and routes lists implemented read-only GET routes; imports remain CLI operations | No new write API is introduced |
| L5: Ruff | `ruff check .`, plus import-order and specific-exception checks on course files | Commands below; GitHub Actions |
| L5: text tests | `text_utils.format_text` and `tests/test_text_utils.py`: short/long/trimmed/invalid input | 20 parameterized cases |
| L5: price test/bug | `prices.apply_discount` and the existing classroom `tests/test_prices.py`, copied unchanged | 200 at 10% gives 180; 0% keeps 200 |
| L5: stats | Classroom `stats.py` uses specific file/JSON/encoding exceptions; average/report behavior is preserved | `tests/test_stats.py` |
| L6 Project CI: unit tests | Existing client/input validation, error handling, text and price unit tests | `tests/test_check_api.py`, `tests/test_text_utils.py`, `tests/test_prices.py` |
| L6 Project CI: real HTTP tests | Four tests send HTTPX requests to an already running Docker app: JSON list, unknown-match 404, invalid-input 422, HTML/static availability | `tests/test_app.py`, enabled by `DOTA_TEST_BASE_URL` |
| L6 Project CI: workflow | One `.github/workflows/ci.yml`: Ruff, Docker build/run, bounded readiness check, pytest, cleanup | PRs test only; successful `university` pushes may publish through the existing GHCR job |

The L5 sources were found in the already existing local repository
`../ci-tests-2026-w-mebius08/`. The supplied `stats.py` and `prices.py` were
already corrected there. Their working versions and both existing test files
are included here; no failing starter test was rewritten or deliberately broken.
These small course utilities are separate from the research/ML implementation.

The L2 Task 5 slide is empty. The original L5 slides postponed Tasks 4-9 until
the next lecture. The newer L5-6 lecture and “Tasks 4-9 (for L6)” practices now
define Project CI (page 9). Both practice copies have the same project requirements;
their Classroom invitation links differ. The project implements the Project CI
section using Dota routes and one existing workflow, without extra Hello-world
workflows or a books service.
The existing main repository was renamed; no additional Classroom enrollment,
repository clone or account registration was performed. Repository naming is
separate from automatic Classroom grading/submission registration.

## Run and verify locally

From the repository root, using the existing `../venv/bin/python`, or replace
it with `.venv/bin/python` after installing `requirements-web-dev.txt`:

```bash
../venv/bin/python app.py --reload
# Open http://127.0.0.1:5001/ and http://127.0.0.1:5001/archive
```

```bash
../venv/bin/python -m ruff check .
../venv/bin/python -m ruff check --select I,BLE001 app.py stats.py text_utils.py prices.py \
  tests/test_stats.py tests/test_text_utils.py tests/test_prices.py tests/test_course_web.py
../venv/bin/python -m pytest -q tests/test_api.py tests/test_check_api.py \
  tests/test_postgres_api.py tests/test_course_web.py tests/test_text_utils.py \
  tests/test_prices.py tests/test_stats.py tests/test_app.py
git diff --check
```

The unit tests use temporary SQLite files and mocked PostgreSQL connections.
They do not start PostgreSQL, Clarity, replay downloads or models. The four
external HTTP tests skip unless `DOTA_TEST_BASE_URL` is explicitly provided.
With that variable set, an unreachable server fails the tests instead of skipping.
CI starts the Docker container and waits for HTTP readiness before running pytest,
including the real HTTP tests. PRs do not publish an image. The existing GHCR
publication remains dependent on all CI checks passing.

## L6: test the running Docker application

The existing `requirements.txt` already includes `ruff`, `pytest` and `httpx`.
CI installs the smaller `requirements-web-dev.txt` subset, which includes those
same required tools and the server runtime without unrelated research libraries.

```bash
docker build -t dota-analytics-web:course .
docker run --rm -d --name dota-analytics-l6 \
  -p 127.0.0.1:8080:5001 \
  -e DOTA_ANALYTICS_DB_BACKEND=sqlite dota-analytics-web:course
../venv/bin/python tools/check_api.py --base-url http://127.0.0.1:8080
# Once the readiness client reports OK:
DOTA_TEST_BASE_URL=http://127.0.0.1:8080 \
  ../venv/bin/python -m pytest tests/test_app.py -v
docker stop dota-analytics-l6
```

These are network integration tests, not FastAPI TestClient/ASGI-only tests.
They use independent read-only requests and accept an empty JSON match list.
The target URL belongs only in test configuration; it is not an API credential.
The container uses its own disposable SQLite and has no production volume mounts.
Do not point test fixtures at the working PostgreSQL volume.

The `web` job in `.github/workflows/ci.yml` runs Ruff, builds the image, publishes
loopback port 18000 to container port 5001, checks readiness, then runs the focused
unit/API tests plus `tests/test_app.py` with `DOTA_TEST_BASE_URL` set. Failure
logs and cleanup use `failure()`/`always()` conditions. There is no duplicate
`university-web.yml` build and no separate expensive test run in `publish`.

Local L6 check on 2026-11-19: the focused suite passed **109 tests**, including
all four `tests/test_app.py` HTTP checks against the actual Docker container.
The unit/client test process used host Python 3.13.7; the container server used
Python 3.14.10. Without `DOTA_TEST_BASE_URL`, the same selection produced 105
passes and four explicit integration skips. Ruff, the workflow YAML/shell checks
and Compose configuration validation passed. The disposable check container was
removed after testing. GitHub Actions itself still needs a commit/push of the
new workflow; local success is not a claim of a completed remote Actions run.

## Docker checks

Container port is 5001; the host can keep port 8000:

```bash
docker build -t dota-analytics-web:course .
docker run --rm -d --name dota-analytics-course \
  -p 127.0.0.1:8000:5001 dota-analytics-web:course
python tools/check_api.py --base-url http://127.0.0.1:8000
docker exec dota-analytics-course ls /srv/app/app/templates /srv/app/app/static
docker stop dota-analytics-course
```

See README for the reload/bind-mount command and persistent Compose setup.
An image keeps its source snapshot until rebuilt; a bind-mounted development
container sees source changes. Use distinct tags and host ports when comparing
two image versions. The 40 GiB reserve is a replay-download policy, not a gate
for web-image builds. Existing replay data and database volumes must be preserved.

Local Docker verification on 2026-11-12 passed for Python 3.14.10 and container
port 5001. The image was built as
`dota-analytics-web:course-20261112-adafbcbd`. `/`, `/archive`, `/api/matches`,
the local CSS and SVG returned HTTP 200; an invalid numeric limit returned 422
and an unknown match returned 404. Empty storage and one synthetic stored match
were checked through list/detail JSON and the filtered HTML archive, including
NULL preservation. Templates/static files were present inside the image.

The check used UID/GID 10001:10001, loopback-only port publication, SQLite inside
the disposable container and no mounted volumes. The test container was removed;
the built image remains locally. Existing PostgreSQL and replay data were not
accessed or modified. This verifies the local ARM64 image; the existing workflow
will separately build/check its runner image after push. Commit/push, remote
Actions results and registry publication remain separate actions. No image was
published and no public website was deployed by this local check.

A subsequent runtime bind-mount/reload check could not start because Docker
Desktop's daemon socket became unavailable. It does not invalidate the completed
image/HTTP checks above; dev hot reload has configuration/unit-test coverage but
still needs that separate runtime check once Docker Desktop is running again.
