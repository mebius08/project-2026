# Dota Betting Autopilot

## About

This course project explores live analytics and win-probability predictions for
professional Dota 2 matches. The current web application serves a historical
match browser at `/` and a JSON API at `/api/matches`, using FastAPI and either
SQLite or PostgreSQL. It runs in Docker; the minimal web dependencies are pinned
in `requirements-web.txt`. The project performs research and paper simulations,
without executing real bets. The proposed course topic is **Dota 2 match
analytics and prediction**; agreement with the instructor is still required.

Practice L3 container check (2026-10-29): the Dockerfile built successfully;
`GET /` returned HTTP 200 with HTML and `GET /api/matches` returned HTTP 200 with
an empty JSON array using the container's isolated SQLite database.

The target product is a universal, on-demand, medium-frequency LIVE predictor
for professional Dota 2. The user selects an individual map/match (distinct from
a series), can attach after play has started, and receives repeated predictions
as new observations arrive. The research focus is short-horizon changes in game
state and win probabilities; approximately five minutes is a research direction,
not a fixed horizon or update interval. Frequent updates must not artificially
create position switches.

The target output is structured predictions with horizons, observation and
prediction timestamps, model identity, uncertainty, and data-quality information.
Missing, stale, or out-of-distribution inputs must be reported and may prevent a
numerical prediction; missing observations must not be fabricated. A decision
engine, BUY/SELL/HOLD commands, position switching, cash-out, and bet execution
are outside the current product scope. Market-reaction predictions require
separate reliable historical and LIVE market data. These are target requirements,
not a claim that existing provider adapters supply a complete LIVE feed.

EWC 2026 is a historical baseline, not a LIVE runtime restriction. Historical
training eligibility is separate from LIVE inference eligibility: a tournament
name outside the training whitelist alone must not reject a selected LIVE match.
Inference still requires adequate source coverage and model applicability.

The existing legacy rule-based MVP supports Dota 2 betting research. It can run a scoped tournament
session, collect fake matches/odds/streamer speech opinions, score bet
candidates, select a small number of candidates, and record paper bets.

No real money is used. The project does not click bookmaker sites, bypass
captchas, parse private bookmaker accounts, or execute real bets. `auto` mode is
intentionally a safe stub:

```text
Auto execution is intentionally not implemented.
Use an official permitted API adapter only.
```

## Quick Start

```bash
cd dota-betting-autopilot
pip install -e ".[dev]"
pytest
python -m app.main
```

If you prefer `requirements.txt`:

```bash
cd dota-betting-autopilot
pip install -r requirements.txt
pytest
python -m app.main
```

## Run for development

From the project root on macOS (or Linux):

```bash
docker build -t dota-analytics-web:dev .
docker run --rm --name dota-analytics-dev \
  -p 127.0.0.1:8001:8000 \
  -v "$(pwd)/app:/srv/app/app:ro" \
  dota-analytics-web:dev \
  python -m uvicorn app.api:create_app --factory \
  --host 0.0.0.0 --port 8000 --reload --reload-dir /srv/app/app
```

Open http://127.0.0.1:8001/. Source and Jinja templates are bind-mounted;
Python changes reload the development server without rebuilding the image.
Templates refresh on the next request. This command uses a disposable SQLite
database inside the container; existing host databases are not mounted.
Rebuild after changing Python dependencies.

The `/` handler passes the project name and description to
`app/templates/index.html`, which includes the existing match browser and loads
Bootstrap 5.3.8 before its custom styles.

### User features and routes

Users can browse stored matches, open a match's details, refresh the archive,
inspect economy history and team point-of-view observations, and select a game
time to compare available historical observations. The interface reports empty
datasets and unavailable data instead of fabricating observations.

| Method | URL | User action | Status |
|---|---|---|---|
| GET | `/` | Open the match browser | Implemented |
| GET | `/api/matches` | List stored matches | Implemented |
| GET | `/api/matches/{source}/{source_match_id}` | Open one match | Implemented |
| GET | `/api/matches/{source}/{source_match_id}/economy` | Inspect economy history | Implemented |
| GET | `/api/matches/{source}/{source_match_id}/pov` | Inspect team observations | Implemented |

The current web API is read-only. Match imports run through existing CLI tools;
no POST, PUT or DELETE endpoints are needed for this first page. Live match
selection and prediction remain planned features that require reliable source
coverage and validation before their API contracts are defined.

## Analytics REST API

From the repository root, using the project's Python environment:

```bash
python -m pip install -e ".[dev]"
python -m uvicorn app.api:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/** to browse historical matches. The responsive page
loads records from the API and shows loading, empty-database, and error states.
Use **Обновить список** to reload the data.

With the server running, check both the page and the API from another terminal:

```bash
python tools/check_api.py --base-url http://127.0.0.1:8000
```

`--base-url` is optional and defaults to the address above. The HTTPX client
checks HTTP 200 and the HTML/JSON response types, accepts an empty match array,
and prints `OK` or `FAIL` for each endpoint. Requests time out after 10 seconds.
Exit codes: `0` for success, `1` for failed checks, `2` for invalid CLI arguments.

`GET http://127.0.0.1:8000/api/matches` returns historical matches from the
existing SQLite database, `data/autopilot.db` by default. Set
`DOTA_ANALYTICS_DB_PATH` to select another SQLite file. An empty database returns
`[]`. The server uses the existing repository and starts independently of the
CLI scenarios. See [the endpoint documentation](docs.md) for the response format.

### Run the web server in Docker

From the repository root, with Docker running:

```bash
docker build -t dota-analytics-web .
docker volume create dota-analytics-data
docker run --rm -d --name dota-analytics \
  -p 127.0.0.1:8000:8000 \
  --mount type=volume,source=dota-analytics-data,target=/data \
  -e DOTA_ANALYTICS_DB_PATH=/data/history.sqlite3 \
  dota-analytics-web
```

After startup, open **http://127.0.0.1:8000/** and run the existing check-client
from the host's project Python environment:

```bash
python tools/check_api.py --base-url http://127.0.0.1:8000
```

The image uses official Python 3.13 slim and installs FastAPI, Uvicorn, the
PostgreSQL driver and their runtime dependencies from `requirements-web.txt`.
Local databases, replays, caches and research outputs are excluded from the build context.
A new volume starts with an empty database; no match records are generated.
The named volume retains SQLite data when the container stops:

```bash
docker stop dota-analytics
```

To use an existing SQLite directory, replace the volume mount with
`--mount type=bind,source=/absolute/path/to/sqlite-directory,target=/data` and set
`DOTA_ANALYTICS_DB_PATH` to the file's container path. The container runs as
UID/GID `10001:10001`; the mounted directory and database must be writable by
that user. Server logs are available with `docker logs dota-analytics`.

### Web image in GitHub Container Registry

After a push to `university`, the `University web CI` workflow publishes
`ghcr.io/mebius08/dota-analytics-web` only after the existing lint, focused tests,
Docker build and container HTTP checks pass. Pull requests run CI without
publishing. A separate publication job builds the checked commit when its SHA
tag does not yet exist, without repeating the tests. It uses only the built-in
`GITHUB_TOKEN` with `contents: read` and `packages: write`.

The moving tag `:university` identifies the most recently published build; a
full `:<commit-sha>` tag identifies its source revision. The workflow preserves
an existing SHA tag on reruns and serializes publication of the same commit;
registry access errors fail publication instead of being treated as a missing
tag. After pushing, check the
`web` and `publish` jobs in Actions, then open the
[GHCR package](https://github.com/users/mebius08/packages/container/package/dota-analytics-web)
to inspect versions and package access settings. Publishing the image does not
deploy a public website: running the application and PostgreSQL still requires
separate hosting, configuration and persistent storage.

### PostgreSQL with Docker Compose

Copy the environment template without overwriting an existing local file:

```bash
cp -n .env.example .env
```

Set `POSTGRES_PASSWORD` in `.env` to your local database password. Database and
role names are configured with `POSTGRES_DB` and `POSTGRES_USER`. Then run:

```bash
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 120
python tools/check_api.py --base-url http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000/**. If port 8000 is already occupied, set
`DOTA_ANALYTICS_WEB_PORT` in `.env` and use that port in the URL and check-client.
Compose waits for PostgreSQL's healthcheck before starting the web service;
the web healthcheck verifies that `/api/matches` can read the database.

Compose explicitly sets `DOTA_ANALYTICS_DB_BACKEND=postgresql` and connects to
service `db` using `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`,
`POSTGRES_USER` and `POSTGRES_PASSWORD`. On application startup, the PostgreSQL
adapter creates just the `historical_matches` table needed for the existing JSON
contract. It inserts no match records and does not import SQLite data. A fresh
database returns `[]`. Connection and schema errors prevent startup; subsequent
database read failures return HTTP 500, with no fallback to SQLite.

Outside Compose, `DOTA_ANALYTICS_DB_BACKEND` defaults to `sqlite` and the existing
`DOTA_ANALYTICS_DB_PATH` behavior is unchanged. For a direct PostgreSQL launch,
explicitly export `DOTA_ANALYTICS_DB_BACKEND=postgresql` and all five connection
variables above. The local Uvicorn launcher does not automatically load `.env`.

PostgreSQL data persists in the `postgres-data` named volume. These commands
show logs and stop the services while retaining that volume:

```bash
docker compose logs web db
docker compose down
```

### Import a historical SQLite catalog

From the repository root, validate an explicitly selected source:

```bash
python -m tools.import_historical_matches --sqlite-path /absolute/path/to/catalog.sqlite3
```

This is a dry-run: the source is opened read-only, only the 24 `HistoricalMatch`
fields are read, and record count, types, identifiers and timestamps are checked.
PostgreSQL is not contacted and its current schema or existing records are not
checked by dry-run. No source tables are created or changed. Timestamps must
include a timezone; none is inferred.

An applied import uses the same five `POSTGRES_*` connection variables as the
web server and requires its initialized PostgreSQL schema. Rebuild/start the
existing Compose services first so that the image contains the importer support:

```bash
docker compose up --build -d --wait --wait-timeout 120
```

To apply against Compose's PostgreSQL, mount the source directory and the CLI
read-only into a one-off web container, which inherits the existing connection
settings. Replace the source directory and filename with your actual catalog:

```bash
docker compose run --rm --no-deps \
  --volume "$PWD/tools/import_historical_matches.py:/srv/app/tools/import_historical_matches.py:ro" \
  --volume "/absolute/path/to/sqlite-directory:/import:ro" \
  web python -m tools.import_historical_matches \
  --sqlite-path /import/catalog.sqlite3 --apply
```

Omit `--apply` to dry-run that same mounted source. For a PostgreSQL instance
already reachable from the host, the local command also accepts `--apply` after
the five connection variables have been exported. `.env` is read by Compose,
not automatically by the local CLI.

All new records are inserted in one transaction. Existing
`(source, source_match_id)` identities are skipped without overwriting their
values; repeat imports create no duplicates. A conflicting primary key or another
write error rolls back the batch. Connection and commit errors also fail the
command; a retry safely skips any already imported identities. The summary reports
source, inserted and skipped counts; errors return exit code 1. An empty source
does not open a PostgreSQL connection, including with `--apply`. Other tables,
source data and the existing API are unchanged.

### Import historical replay economy

Validate the four canonical compact files without connecting to PostgreSQL:

```bash
python -m tools.import_compact_economy
```

The importer uses `load_replay_trajectory`: clocks must be `PROVEN`, team totals
must agree with player totals, and required economic values cannot be missing.
One row per snapshot stores both teams' net worth, current gold and total XP,
plus replay SHA-256, replay tick and actual callback time taken directly from
`source_game_time_seconds`. Nominal `game_time_seconds` is not used as the stored
timestamp. Compact callbacks can be synthetic; this import does not claim that
they are real network frames or that full economy is available from a LIVE feed.
The data is historical oracle context for future charts.

After the four historical catalog entries have been imported, rebuild the web
image to include the separate economy schema. With Compose's database running,
apply explicitly using its existing connection settings:

```bash
docker compose build web
docker compose run --rm --no-deps \
  --volume "$PWD/tools:/srv/app/tools:ro" \
  web python -m tools.import_compact_economy --apply
```

Omit `--apply` to dry-run inside that same container. A PostgreSQL instance
reachable from the host can also use the local command with `--apply` and the
existing five `POSTGRES_*` environment variables.

`historical_match_economy_snapshots` has a foreign key to
`historical_matches(source, source_match_id)`, with unique replay ticks and actual
times per match. The importer creates only the new table, inside the same
transaction as all snapshot inserts; it never creates or updates catalog records.
An identical repeated import skips existing snapshots. Conflicting values, replay
hashes or frame sets fail instead of overwriting data. Any write/validation error
rolls back the batch; failures return exit code 1. Dry-run checks local inputs
only and does not check existing PostgreSQL parents or snapshots.

### Import historical team POV features

Validate the existing four-match POV CSV without contacting PostgreSQL:

```bash
python -m tools.import_pov_features
```

The default input is
`tools/replay_probe/output/global-pov-oracle-four-matches/pov-features.csv`;
`--csv-path PATH` selects an explicit copy. The importer requires the existing
16-column team POV schema and all 2242 rows: 774 for `8960991322`, 532 for
`8960882635`, 524 for `8958734008`, and 412 for `8957013760`. It validates replay
SHA consistency, unique match/tick/team keys, exact Radiant/Dire pairing, increasing
actual times/ticks, counts, feature availability and original status codes.

The separate `historical_match_pov_snapshots` table references the existing
catalog through `(source, source_match_id)`, using source `replay_clarity`.
It stores replay SHA, actual time, tick, POV team, the three requested enemy
counts, nearest visible enemy distance, own team spread and both feature status
fields. Missing distances/spread remain SQL NULL, never zero. Zero is preserved
when it is an actual supplied value. `visible_enemy_count` counts raw visibility
flags, which may persist after death; `visible_enemy_with_position_count` counts
VISIBLE enemies with verified living positions. Neither field establishes the
total number of living enemies.

CSV `game_time_seconds` is already the actual source frame time from the
validated spatial/visibility export. It is stored as
`actual_game_time_seconds`, without rounding or substituting the nominal grid.
The importer copies the requested feature subset at that same time and tick;
it performs no frame joins, replay processing or feature recomputation. Extra
CSV columns are rejected; GLOBAL coordinates, future labels and last-seen
positions are not imported. Raw clock/visibility guarantees remain those of the
upstream extractor; CSV validation does not independently re-prove them. These
are historical team POV observations, not a confirmed available LIVE feed.

After the catalog parents exist, rebuild the web image to include the new SQL
file. With Compose's PostgreSQL running, apply only when explicitly intended:

```bash
docker compose build web
docker compose run --rm --no-deps \
  --volume "$PWD/tools:/srv/app/tools:ro" \
  web python -m tools.import_pov_features --apply
```

For PostgreSQL reachable from the host, use `python -m tools.import_pov_features
--apply` with the existing five `POSTGRES_*` variables exported. Dry-run is the
default and does not need those settings. Table creation and all inserts share
one transaction. Identical repeated imports skip existing rows; conflicting
values, statuses, SHA or frame sets fail and roll back rather than overwrite.
Other tables and source files are not modified. Errors return exit code 1.

### Import experimental historical OOF death predictions

Validate the existing 2206-row export without contacting PostgreSQL:

```bash
python -m tools.import_death_predictions
```

The default source is `tools/replay_probe/output/pov-deaths-oof-four-matches.csv`;
use `--csv-path PATH` for an explicit copy. Validation requires the exact eight
CSV columns, unique match/tick/team/horizon keys, paired Radiant/Dire frames,
consistent increasing actual times/ticks, horizon 30, finite probabilities in
`[0, 1]` and targets exactly `0` or `1`. Source files are read-only.

With the existing five `POSTGRES_*` variables exported for a reachable database,
apply explicitly:

```bash
python -m tools.import_death_predictions --apply
```

The new `historical_match_death_predictions` table references the existing
catalog through `(source, source_match_id)` with source `replay_clarity`.
`game_time_seconds` is stored as NUMERIC from Decimal, without rounding or POV
joins; float64 probabilities retain the exported model values. Every row stores
`prediction_origin=HISTORICAL_OUT_OF_FOLD`. The target is a future outcome for
retrospective evaluation only, never a predictor. This provenance refers to the
already validated OOF export; the importer neither retrains nor independently
re-proves held-out training or LIVE availability.

Table creation and inserts share one transaction. Identical repeats are skipped;
conflicting values or frame sets fail with rollback, without overwriting existing
predictions. Missing catalog parents fail the foreign key. Dry-run checks local
CSV data only, not database parents. Failures return exit code 1. No existing
tables, API or ML components are changed. For Compose, use the existing mounted
tools procedure above and rebuild the image to include the new SQL file first.

## Legacy paper research pipeline

1. Load `config.example.yaml`.
2. Start a session for a tournament keyword.
3. Fetch fake Dota matches and filter them by tournament scope.
4. Fetch fake odds snapshots and fake streamer utterances.
5. Build streamer speech/opinion signals with simple keyword rules.
6. Score markets with rule-based quality, phase, odds, streamer, and riskophile
   components.
7. Select up to `max_bets_per_match` candidates above threshold.
8. In `paper` mode, record virtual bets in memory.
9. Persist the session and paper bets to SQLite.
10. Build a summary report from stored paper bets.

## Modes

- `paper`: records virtual bets automatically.
- `signal`: scores and selects candidates without placing paper bets.
- `confirm`: reserved for a future confirmation UI/CLI.
- `auto`: deliberately not implemented for safety.

## CLI Usage

Show available commands:

```bash
python -m app.cli --help
```

Run one pass with a manual transcript file:

```bash
python -m app.cli run-once \
  --tournament DreamLeague \
  --transcript data/streamer_transcript.txt
```

Run a bounded loop:

```bash
python -m app.cli loop \
  --tournament DreamLeague \
  --transcript data/streamer_transcript.txt \
  --iterations 5 \
  --interval-seconds 30
```

Typical workflow:

1. Start `loop` during the selected tournament.
2. Write or paste streamer phrases into the transcript file, one phrase per line.
3. The bot reads the transcript, scores candidates, and records paper bets.
4. Paper trading data is stored in `data/autopilot.db`.
5. Use `report` to inspect stored paper trading history.
6. Delete `data/autopilot.db` for a clean research start.

## UX CLI Helpers

Manual transcript helpers:

```bash
python -m app.cli show-transcript --transcript data/streamer_transcript.txt
python -m app.cli add-utterance \
  --transcript data/streamer_transcript.txt \
  --speaker streamer \
  --text "over kills looks playable"
python -m app.cli clear-transcript --transcript data/streamer_transcript.txt
```

Offline SQLite session inspection:

```bash
python -m app.cli list-sessions --db data/autopilot.db
python -m app.cli show-session --db data/autopilot.db --session-id SESSION_ID
```

Transcript commands work with the manual/fake transcript workflow. Session
commands only read local SQLite paper-trading storage. They do not place real
bets, automate bookmaker sites, call Twitch/STT APIs, or use browser automation.

## Reports

Show a paper trading summary from the default SQLite database:

```bash
python -m app.cli report
python -m app.cli report --db data/autopilot.db
```

Filter by session and limit recent bets:

```bash
python -m app.cli report \
  --db data/autopilot.db \
  --session-id SESSION_ID \
  --last-bets 20
```

Include recent streamer utterances:

```bash
python -m app.cli report \
  --db data/autopilot.db \
  --show-utterances \
  --last-utterances 20
```

The report prints sessions, total bets, open and settled bets, profit units,
ROI, average bets per match, and recent bet history. If the database does not
exist yet, run `python -m app.main` or `python -m app.cli run-once` first.

## Settlement

Paper bets start as open bets with `status=placed`, `result=unknown`, and
`profit_units=0.0`. Manual settlement records the final paper result so reports
and ML training can use the history.

List open bets:

```bash
python -m app.cli open-bets
```

Settle a paper bet:

```bash
python -m app.cli settle-bet --bet-id BET_ID --result win
python -m app.cli settle-bet --bet-id BET_ID --result loss
```

`win` and `loss` settled bets are used by ML training. `push` and `void` are
stored for reporting, but they are not training targets. Profit is calculated
from `stake_pct`:

- `win`: `stake_pct * (odds - 1)`
- `loss`: `-stake_pct`
- `push` / `void`: `0.0`

## Data export/import

Export stored paper research data for offline analysis:

```bash
python -m app.cli export-bets --db data/autopilot.db --out exports/bets.csv
python -m app.cli export-candidates \
  --db data/autopilot.db \
  --out exports/candidates.csv
python -m app.cli export-utterances \
  --db data/autopilot.db \
  --out exports/utterances.csv
```

Exports use UTF-8 CSV, create the output directory when needed, always write a
header, and keep columns in the same stable order as the persisted SQLite/domain
fields. Exported CSV files are intended for local offline inspection and are
usually not committed.

Settlement imports work only with existing paper bets:

```csv
bet_id,outcome,profit_units
<bet-id>,win,1.25
<bet-id>,loss,-1.0
```

```bash
python -m app.cli import-settlements --db data/autopilot.db --csv settlements.csv
```

Invalid rows are skipped with warnings, while valid rows are still applied. The
CSV `profit_units` value is validated as numeric input; stored paper profit is
calculated by the existing settlement logic from the bet odds, stake, and
outcome.

Inspect offline data readiness before ML training or evaluation:

```bash
python -m app.cli inspect-dataset --db data/autopilot.db
```

The inspection report prints entity counts, open and settled bet counts,
win/loss/push/void outcomes, streamer utterance counts, usable ML records, and a
simple readiness status. This remains paper/research data only. It is not real
betting, bookmaker automation, or financial advice.

## Personal FONBET history research export

`python -m app.fonbet_history export` is a separate, bounded utility for the
authenticated user's own coupon history. It is not connected to the
STRATZ/OpenDota ingestion pipeline, does not place bets, and does not run
concurrent requests.

Put the saved coupon-summary export at the default local path:

```text
local-data/fonbet-history/summary.json
```

The file may be a coupon array or an object containing `coupons`, `couponList`,
`items`, or `records`. Each coupon needs `couponId`; the known summary fields
such as `registrationTime`, `betState`, `betSum`, `winSum`, `couponType`,
`couponK`, `couponOriginalK`, `betCount`, and `betMode` are retained or mapped.
The entire `local-data/` directory is gitignored. Raw details are written under
`local-data/fonbet-history/raw/` with SHA-256-derived filenames; normalized
coupon exports are `normalized/coupons.json` and `normalized/coupons.csv`.
Offline normalization also writes one row per real coupon leg to
`normalized/legs.json` and `normalized/legs.csv`. It also derives chronological
single-coupon sequences at `normalized/single_event_sequences.json` and
`normalized/single_event_sequences.csv` without making network requests.
The same eligible non-express single coupons are also split into point-in-time
features at `normalized/entry_decisions.json` and
`normalized/entry_decisions.csv`, and post-settlement labels at
`normalized/entry_outcomes.json` and `normalized/entry_outcomes.csv`.

Set session credentials only in the current shell when possible. Copy
`betTypeName` and `sysId` from the same observed `coupon/info` request rather
than guessing them:

```powershell
$env:FONBET_FSID = "<current fsid>"
$env:FONBET_CLIENT_ID = "<current clientId>"
$env:FONBET_BET_TYPE_NAME = "<observed betTypeName>"
$env:FONBET_SYS_ID = "<observed integer sysId>"
```

`FONBET_LANG` is optional and defaults to `ru`. The equivalent runtime options
are `--fsid`, `--client-id`, `--bet-type-name`, `--sys-id`, and `--lang`.
Environment variables are preferred because command-line values can be exposed
by shell history or process inspection.

The amount conversion is deliberately explicit. Compare one `betSum` value in
the summary with the stake shown in the account export: if `10000` represents
100 RUB (100 kopecks per RUB), pass `--amount-divisor 100`; if `100` already
represents 100 RUB, pass `--amount-divisor 1`. The utility records the chosen
divisor and the source `betSum`/`winSum` values in the normalized output; it
never infers a currency scale from magnitude.

Example using the minor-unit contract:

```powershell
..\venv\Scripts\python.exe -m app.fonbet_history export --summary .\local-data\fonbet-history\summary.json --amount-divisor 100 --delay-seconds 1 --timeout 10 --max-fetches 100
```

Requests are sequential. `--max-fetches` bounds network attempts (default 100),
and `--max-fetches 0` performs offline normalization only. A rerun skips any
coupon whose raw detail file already exists. Successful raw responses are saved
immediately, so later request failures do not discard earlier work; normalized
JSON/CSV and a sanitized failure list are still written, and the command exits
nonzero when failures occurred. Delete only an unreadable raw file to retry it.

The normalized coupon-level schema includes:

- `coupon_id`, `registration_time`, `calculation_time`, `coupon_type`,
  `bet_mode`, `bet_count`, and `state`;
- `stake_rub`, `return_rub`, `profit_rub`, `entry_odds`, `event_name`,
  `entry_odds_source`, `selection`, `entry_score`, `result_score`, `is_live`,
  `event_start_time`, and `sport_name`;
- `is_express`, `is_freebet`, `is_cashout`, `cash_stake_rub`,
  `freebet_nominal_rub`, `accounting_method`, source amount/odds fields,
  `amount_divisor`, `leg_count`, and `detail_status`.

JSON retains each express leg in `legs`; CSV stores the same array in
`legs_json`, while keeping one row per coupon so coupon stake and profit are not
double-counted. Combined odds prefer the source `couponK` from summary metadata
or the raw detail header. If it is absent, express odds are derived only when
every leg has a positive `factorValue`: the factors are multiplied and rounded
to two decimal places with `ROUND_HALF_UP`; otherwise `entry_odds` remains null.
`entry_odds_source` records which path was used. For `Win`, `Lose`, and
`Sold`/cash-out cash coupons,
`profit_rub = return_rub - cash_stake_rub`. A freebet's `stake_rub` is its
nominal amount, `cash_stake_rub` is zero, and `profit_rub` uses the zero-cash-
stake convention. The nominal, source amounts, and method are retained so an
analyst can apply a different freebet convention later.

The normalized leg schema is `coupon_id`, `leg_index`, `event_id`, `factor_id`,
`segment_id`, `sport_id`, `event_name`, `selection`, `entry_odds`, `entry_score`,
`result_score`, `event_start_time`, and `is_live`. Leg indexes are one-based
within each coupon. Identifier fields map only from the corresponding raw
`eventId`, `factorId`, `segmentId`, and `sportId` values and remain null when the
source omits them.

The single-event sequence schema is `coupon_id`, `event_id`,
`registration_time`, `sequence_index`, `prior_entry_count`,
`previous_coupon_id`, `previous_selection`, `previous_selection_side`,
`selection`, `selection_side`, `side_switch`, `entry_odds`, `entry_score`,
`result_score`, `is_live`, `cash_stake_rub`, `return_rub`, `profit_rub`,
`is_cashout`, and `state`. It includes only
non-express coupons with exactly one normalized leg and a non-null `event_id`.
Rows are ordered by normalized `registration_time`, with `coupon_id` as the
deterministic tie-breaker. Sequence counters and previous fields are tracked
only within the same exact `event_id`; event names, teams, maps, market
similarity, and strategy quality are never inferred. The first row for each
event has `sequence_index=1`, `prior_entry_count=0`, null previous fields, and
null `side_switch`. `selection_side` and `previous_selection_side` are parsed as
`1` or `2` only from explicit winner selections equivalent to `Поб 1` or
`Поб 2`. When both consecutive sides are parseable, `side_switch` is false for
the same side and true for opposite sides; otherwise it is null. Sides are not
inferred from team names, odds, scores, or arbitrary selection text.

The entry-decision schema is `coupon_id`, `event_id`, `registration_time`,
`sequence_index`, `prior_entry_count`, `seconds_since_previous_entry`,
`prior_cash_stake_rub`, `previous_selection_side`, `selection`,
`selection_side`, `side_switch`, `entry_odds`, `entry_score`, `entry_score_1`,
`entry_score_2`, `selected_side_score_diff`, `selected_side_position`,
`is_live`, `stake_rub`, `cash_stake_rub`, `is_freebet`, and
`freebet_nominal_rub`. Ordering is by `registration_time`, then `coupon_id`.
Timing, cumulative cash stake, previous side, and switch values use only rows
already encountered for the same exact `event_id`; the first event entry has
null `seconds_since_previous_entry` and zero `prior_cash_stake_rub`.

Only an entry score in simple `N:N` form is split into `entry_score_1` and
`entry_score_2`. A selected-side difference and position are derived only when
that score is parseable and `selection_side` is explicitly `1` or `2` from
normalized `Поб 1` or `Поб 2`: positive is `ahead`, zero is `tied`, and negative
is `behind`. Non-side selections retain parsed score components when available,
but their selected-side difference and position remain null.

The entry-outcome schema is `coupon_id`, `state`, `return_rub`, `profit_rub`,
`is_cashout`, `result_score`, and `calculation_time`. Coupon IDs are unique in
both exports and the two ID sets are identical. State, return, profit, cash-out,
result score, and calculation time are outcome-only fields and never appear in
entry decisions. Existing coupon accounting is copied without recalculation.

Offline normalization also writes the audit-only cash-out counterfactual at
`normalized/cashout_hold_audit.json` and
`normalized/cashout_hold_audit.csv`. It includes only cash-funded,
non-express `Sold` coupons and has the schema `coupon_id`, `selection`,
`entry_odds`, `result_score`, `cash_stake_rub`, `actual_return_rub`,
`actual_profit_rub`, `hold_result`, `hold_return_rub`, `hold_profit_rub`,
`cashout_vs_hold_delta_rub`, and `derivation_status`. A hold result is derived
only for the explicit selections `Поб 1`, `Поб 2`, and `Ничья` with a final
score in simple `N:N` form. A losing hold returns zero; a winning hold returns
`cash_stake_rub * entry_odds`, rounded to whole RUB with `ROUND_HALF_UP`, the
same contract verified against settled winning cash coupons. The delta is
`actual_return_rub - hold_return_rub`. Unsupported selections or result scores
leave all counterfactual fields null and record the reason in
`derivation_status`. This post-outcome audit is not included in entry-time
decision features, and it does not change existing coupon accounting.

Regenerate all normalized files without network access using:

```powershell
..\venv\Scripts\python.exe -m app.fonbet_history export --summary .\local-data\fonbet-history\summary.json --local-data-dir .\local-data\fonbet-history --amount-divisor 1 --max-fetches 0
```

Security warning: `fsid` and `clientId` are session credentials. Do not paste
them into source, README examples, fixtures, committed `.env` files, issue
reports, or logs. The utility does not print them, does not include upstream
error bodies, redacts credential values if a response echoes them, and never
persists the request payload. Gitignore is not encryption; protect and delete
`local-data/` according to the sensitivity of personal account history.

## Real match data adapter

The optional PandaScore adapter is a read-only source for Dota 2 match metadata.
It fetches matches and maps them into the existing `Match` domain entity. It
does not fetch bookmaker odds, place bets, run scoring, or execute paper bets.
Fake/manual collectors remain the default fallback for the local workflow.

Set a local PandaScore token before using the real provider:

```powershell
$env:PANDASCORE_TOKEN="your-token-here"
```

Fetch match metadata explicitly:

```bash
python -m app.cli fetch-matches --provider pandascore
python -m app.cli fetch-matches --provider pandascore --status upcoming --limit 10
python -m app.cli fetch-matches --provider pandascore --status live --limit 10
python -m app.cli fetch-matches --provider pandascore --scope ewc-2026
```

Network access happens only when the real provider command is used. Unit tests
mock the network boundary and stay offline. API availability, rate limits, and
provider plan behavior are controlled by PandaScore. Do not commit credentials.

## Historical professional Dota match dataset

The future historical ML model v2 is expected to train on completed
professional Dota match results, not on settled paper bets as its main data
source. This stage adds the storage and inspection foundation only. It stores
provider-listed past Dota matches, preserves provider tournament/league/series
metadata, records explicit match-winner labels when they can be mapped safely,
and keeps unresolved outcomes out of training queries.

This layer does not claim that every internet match returned by a provider is
Tier 1 or fully training-eligible. Provider metadata is preserved so tournament
quality and eligibility rules can be refined later. The current `train-ml`
command remains the old paper-bet v1 pipeline; historical ML v2, recency
weighting, roster lineage, model retraining, and champion/challenger workflows
are not implemented here.

Set a local PandaScore token before running an explicit real sync:

```powershell
$env:PANDASCORE_TOKEN="your-token-here"
```

Sync a bounded historical window:

```powershell
python -m app.cli sync-history --provider pandascore --db data/autopilot.db --since 2025-07-08 --until 2026-07-07 --page-size 100 --timeout 30
```

The sync uses the PandaScore past Dota match source and an explicit date
window. `--since` and `--until` are mandatory. If `--max-pages` is supplied,
the sync reads at most that many provider pages. If `--max-pages` is omitted,
pagination continues until the provider returns an empty or short terminal page
inside the explicit date window, with repeated-page detection to avoid endless
loops. Repeating the same sync is idempotent through
`source + source_match_id`, and later richer provider metadata can update an
existing row. The command is read-only against the provider and does not place
bets, create live signals, train models, or call bookmaker write APIs.

Inspect and export the local historical dataset:

```bash
python -m app.cli history-status --db data/autopilot.db
python -m app.cli export-history --db data/autopilot.db --out exports/history.csv
```

History export writes UTF-8 CSV with a stable header, creates the parent
directory, and never includes API tokens. `history-status` is offline and
reports total matches, usable winner records, point-in-time-ready records,
date ranges, stage distribution, unique teams, and unique tournaments.

Point-in-time safety is strict: a match is available to future features only
after its result is known. If a prediction timestamp is January 3 at 12:00 and
a match completed January 3 at 15:00, that match is not available for the 12:00
prediction. Match start time is not result availability time.

Team matching in this pre-roster layer is limited to PandaScore team IDs or a
controlled normalized-name fallback inside the same organization identity. It
does not create permanent aliases such as Tundra -> 1W or HEROIC -> LGD. A
roster-lineage layer connects relevant history through player/roster continuity
instead of organization-name aliases.

## Player and roster history foundation

The roster-history layer stores player identities separately from team
organizations. Player identity is keyed by provider `source + source_player_id`;
team organization identity is keyed by `source + source_team_id`. Display names
and nicknames can change without creating a new identity, and organization names
are not treated as complete competitive roster identity.

Roster snapshots are temporal, provider-observed records. They preserve the
provider context where the roster was seen, optional tournament identity,
`observed_at`, nullable provider validity metadata, player memberships, optional
coach membership when the provider payload actually contains stable coach data,
and provider provenance. Missing player IDs are not converted into name-only
global identities, missing team IDs are not converted into name-only
organizations, and coaches without stable provider IDs are ignored
conservatively instead of becoming global name-based identities.

The player-composition fingerprint is deterministic, order-independent, and
based on stable player IDs only. Organization ID is not part of that player-only
fingerprint, and coach data does not silently alter it. This means the same five
players may appear under different organizations without merging those
organizations or creating permanent transfer aliases. The storage foundation
does not persist lineage truth; the derived lineage layer below computes
continuity from snapshots at query time.

Sync bounded roster history from PandaScore tournament contexts already present
in the historical match table. The provider call uses PandaScore's tournament
roster endpoint, `GET /tournaments/{tournament_id_or_slug}/rosters`:

```powershell
$env:PANDASCORE_TOKEN="your-token-here"
python -m app.cli sync-rosters --provider pandascore --db data/autopilot.db --max-tournaments 25
```

`sync-rosters` is read-only against PandaScore, bounded by
`--max-tournaments`, and derives the most recent tournament IDs from persisted
historical matches. It stores provider-observed or expected tournament rosters.
The sync does not crawl the entire provider universe, place bets, train models,
or call bookmaker APIs.

Inspect the local roster dataset offline:

```powershell
python -m app.cli roster-status --db data/autopilot.db
```

`roster-status` makes no network calls. It reports player and organization
counts, roster snapshot counts, player and coach memberships, temporal-validity
coverage, observed timestamp range, and unique player-roster fingerprints.
`observed_at` is the point-in-time availability boundary: future-observed roster
information is not backfilled into earlier prediction timestamps. Provider
validity is stored only when the provider supplies it; the project does not
invent roster validity from tournament dates. Derived lineage logic can compare
historical roster continuity from these snapshots without adding permanent
aliases such as Tundra -> 1W or HEROIC -> LGD.

## Derived roster lineage / competitive continuity

Competitive lineage is derived from roster snapshots at query time. It does not
persist permanent transfer aliases, merge `TeamOrganization` rows, rewrite
provider IDs, or create a global competitive-team identity. Organization
identity is explanatory metadata; it is not lineage identity.

Continuity evidence uses stable provider player IDs, not player display names.
Exact player-set equality and strong player overlap are the primary evidence.
Stable coach continuity is represented separately by stable provider coach ID
and can support a qualifying three-player overlap, but coach names are ignored
and coach continuity alone is insufficient. The default conservative policy is:

- `EXACT`: same stable player set with at least five core players.
- `STRONG`: at least four shared players and at least 0.8 overlap against the
  smaller roster.
- `COACH_SUPPORTED`: at least three shared players, at least 0.6 overlap against
  the smaller roster, and the same stable coach provider ID.
- `WEAK`: at least three shared players without enough evidence to auto-link.
- `NONE`: insufficient stable player continuity.

These thresholds are project heuristics for the current lineage foundation, not
statistically proven optimal values. The policy is centralized so later
evaluation can change it without rewriting the resolver.

Availability time and competitive chronology are separate. `observed_at < as_of`
controls whether a snapshot may participate in a point-in-time lineage graph,
and a snapshot observed exactly at `as_of` is excluded. Competitive chronology
only orders already-available snapshots. Chronology precedence is:

1. explicit `valid_from`, when present;
2. tournament historical-match context from point-in-time eligible completed
   matches for the same provider tournament, using strict `ended_at < as_of`,
   then the earliest eligible `historical_matches.started_at`, or the latest
   eligible `ended_at` only if no start timestamp is available;
3. `observed_at` fallback.

Tournament match dates may help order already-available historical roster
observations, but they never make a snapshot available before its `observed_at`.
Lineage is directional: accepted edges point from previous snapshot to current
snapshot, and predecessor history follows those edges backwards. Future
competitive descendants are never returned as predecessor history.

Inspect the derived lineage summary offline:

```powershell
python -m app.cli lineage-status --db data/autopilot.db --as-of 2026-07-07T12:00:00Z
```

`lineage-status` makes no network calls and prints point-in-time available
snapshot count, chronology source counts, accepted exact/strong/coach-supported
links, ambiguity count, root snapshots, derived components, organization-crossing
links, and largest predecessor chain size. It does not print fake confidence
percentages and it does not sync or persist lineages.

## Point-in-time historical features

Historical feature generation is a deterministic offline input layer for a
future Historical ML Model v2. It is not model training, calibration, a betting
signal, bookmaker automation, or a live candidate engine.

Feature rows require an explicit `HistoricalPredictionContext`. For historical
training rows, the prediction timestamp is the target match `started_at`, never
`ended_at`, ingestion time, or current wall-clock time. Only completed historical
matches with `ended_at < prediction_timestamp` may contribute. A match completed
exactly at the prediction timestamp is excluded, matches still in progress at
the timestamp are excluded, and the target match is explicitly removed by
`source + source_match_id` even if malformed fixture timing would otherwise make
it look eligible.

Raw team form uses stable provider team IDs, not display names. Unknown or
unusable winner records are excluded from the denominator rather than counted as
losses. Empty history uses neutral cold-start defaults:
`raw_win_rate=0.5`, `recency_weighted_win_rate=0.5`, and
`opponent_adjusted_strength=0.0`, while explicit sample-count features remain in
the row so the future model can distinguish no history from known .500 history.

Roster lineage is used conservatively where point-in-time roster snapshots make
it safe. The bridge follows accepted predecessor snapshots only, uses chronology
windows for those roster organizations, and does not auto-use ambiguous
branches. Organization identity alone is not competitive history: old unrelated
1W matches do not automatically attach to a transferred Tundra roster, and
ancient unrelated LGD matches do not automatically attach to a transferred
HEROIC roster. Because historical match rows currently store organization/team
IDs rather than exact roster snapshot IDs, this bridge is conservative
organization-window attribution; it does not claim perfect match-to-roster
membership.

Recency weights are computed dynamically for each prediction timestamp with:

```text
exp(-age_days / decay_days)
```

where `age_days = prediction_timestamp - historical_match.ended_at`.
The default `decay_days=90.0` is an initial baseline configuration, not proven
optimal truth. No static eternal match weight is persisted, and the policy can be
changed later to evaluate alternatives such as 30, 60, 120, or 180 days.

Opponent-adjusted strength is a basic deterministic v1 strength-of-schedule
adjustment. For one prediction timestamp it builds one point-in-time historical
universe, computes recency-weighted base form for stable team IDs, runs fixed
batch iterations, and applies low-sample shrinkage toward neutral. Team A and
Team B are read from the same point-in-time strength state, so future opponent
results cannot affect an older row. Difference features consistently use
`Team A value - Team B value`; swapping the target orientation swaps A/B groups
and flips the difference signs.

Inspect feature readiness offline:

```powershell
python -m app.cli feature-status --db data/autopilot.db --as-of 2026-07-07T12:00:00Z --decay-days 90
```

`feature-status` makes no network calls. It reports the cutoff timestamp, decay
policy, available historical matches, usable match-result records, stable teams
in the derived strength state, average raw and weighted history mass,
opponent-adjusted strength range, and neutral cold-start policy.

## Tournament competitive stage model

The current product target is EWC 2026 Dota 2. EWC 2026 currently uses a
single-elimination playoff path, but that is not treated as the only supported
Dota tournament format. Historical professional Dota tournaments may use
double-elimination brackets, so the domain keeps upper-bracket and lower-bracket
contexts available for future historical features.

The model-oriented competitive stages are:

- `group`
- `crossover`
- `upper_bracket`
- `lower_bracket`
- `single_elimination`
- `grand_final`
- `placement`
- `unknown`

Round detail is preserved separately from the high-level competitive stage.
Quarterfinal and semifinal are round metadata; when there is no upper/lower
bracket context, they currently map to the broader `single_elimination` stage.
Upper-bracket matches mean a loss may move a team to a lower bracket.
Lower-bracket matches normally mean a loss eliminates the team.

Current EWC 2026 stage mapping:

- `Group Stage` -> `group`
- `Survival` / crossover matches -> `crossover`
- `Quarterfinal` / `Semifinal` -> `single_elimination`
- `Grand Final` -> `grand_final`
- `Third place` -> `placement`

`Survival - Grand Final` is a survival-phase final, not the tournament grand
final. Stage metadata is a future ML predictor and does not add a manual betting
coefficient or change the current scorer. A future historical model should learn
team-specific behavior in these contexts.

Inspect persisted EWC 2026 scope locally:

```bash
python -m app.cli ewc-status --db data/autopilot.db
```

`ewc-status` is read-only. It makes no network calls, places no bets, creates no
signals, and does not train or run the historical ML v2 layer. If no persisted
EWC 2026 matches exist, it still prints the canonical tournament id and a
friendly no-data message.

Team organization tags are not treated as permanent competitive roster identity.
For example, future roster-lineage work may relate a Tundra roster to current
1W, or a HEROIC roster to current LGD Gaming, but those are not team aliases in
the current system. Competitive relevance will later follow roster/player
continuity instead of organization-name substitution.

## Real odds data adapter

The optional OddsPapi adapter is a read-only source for Dota 2 match-winner odds.
It uses OddsPapi REST API v4 with Dota 2 `sportId=16`, maps supported
match-winner prices into the existing internal `map_winner` odds convention, and
does not run scoring, select candidates, create paper bets, settle bets, or place
real bets. Fake odds remain the default local workflow.

Set a local OddsPapi API key before using the real odds provider:

```powershell
$env:ODDSPAPI_API_KEY="your-api-key-here"
```

Fetch odds explicitly:

```bash
python -m app.cli fetch-odds --provider oddspapi
python -m app.cli fetch-odds --provider oddspapi --limit 10
python -m app.cli fetch-odds --provider oddspapi --bookmakers pinnacle,bet365
```

PandaScore match IDs and OddsPapi fixture IDs are different provider IDs. The
adapter includes deterministic team-name and start-time reconciliation helpers,
but ambiguous matches are skipped rather than attaching odds to the wrong match.
Network access happens only when the explicit odds command is used. Do not commit
credentials.

## Market Probability and Estimated Edge

The edge layer is a read-only research calculation over stored candidates and
odds. It does not create signals, place bets, calculate stake size, call
bookmaker write APIs, or provide financial advice.

Raw implied probability is calculated directly from decimal odds:

```text
raw implied probability = 1 / decimal_odds
```

For a complete two-way `map_winner` market from one bookmaker, bookmaker margin
is removed by normalizing both raw implied probabilities:

```text
fair market probability = selection raw implied probability / market overround
```

This fair market probability is a market-derived baseline after simple two-way
margin normalization. Incomplete markets are not guessed; one side is never
invented from the other side.

Model probability is only available when the ML predictor can load a model that
exposes a real positive-class `predict_proba` output. The current probability is
reported as raw `ml_predict_proba`; it is not claimed to be calibrated. Rule
score is not probability. Hybrid score is not probability. The code does not
normalize arbitrary scores by dividing by 100 or applying a sigmoid.

Estimated edge is a probability-point difference:

```text
estimated edge = model probability - fair market probability
```

Example:

```text
Model probability: 56%
Fair market probability: 49%
Estimated edge: +7 percentage points
```

Expected value per 1 unit is:

```text
expected value = model probability * decimal_odds - 1
```

Inspect persisted data:

```bash
python -m app.cli analyze-edge --db data/autopilot.db
python -m app.cli analyze-edge --db data/autopilot.db --model-path data/models/bet_model.joblib
```

If the model file is missing or cannot provide a valid class probability, the
command reports model probability, estimated edge, and expected value as
unavailable instead of failing. If stored data does not contain complete
same-bookmaker two-way market snapshots for a candidate, the command reports the
market as incomplete. OddsPapi fetching remains read-only and does not imply
that fetched odds have already been persisted to SQLite.

## Historical ML v2

Historical ML v2 predicts professional Dota `P(Team A wins)` from
point-in-time historical feature rows. It is separate from the legacy
settled-paper-bet ML layer and it is not a betting recommendation, market edge
calculation, Nix layer, bookmaker integration, or automatic betting system.

Training rows are built by the existing historical feature engine. For a target
match, the prediction timestamp is the match `started_at`. Only historical
matches completed strictly before that timestamp (`ended_at < started_at`) may
contribute. Roster observations also remain point-in-time safe with
`observed_at < prediction_timestamp`; future roster snapshots are represented
as missing rather than backfilled.

The default Historical ML v2 EWC 2026 baseline target scope is
`ewc_2026_baseline`. It starts at `2025-07-08T00:00:00Z` inclusive and allows
main-event target rows from these competition families:

* The International
* Esports World Cup / EWC
* DreamLeague
* BLAST
* ESL
* PGL
* FISSURE Playground
* BetBoom Dacha

Qualifiers are excluded. Competition family classification is based on
normalized provider tournament, league, and series metadata; season, year, and
edition variations do not need exact full-string equality. `FISSURE Playground`
is allowed, but `FISSURE Universe` and generic FISSURE tournaments are not
automatically allowed. BetBoom Dacha requires both BetBoom and Dacha identity;
generic BetBoom events are not automatically allowed.

Historical SQLite storage remains broad. The raw `historical_matches` table may
contain other professional Dota matches, and those records are not deleted or
rewritten merely because the default model scope is curated. For the default
EWC 2026 baseline, target rows and match-derived feature history use the same
`ewc_2026_baseline` competition policy. Only allowed main-event competition
families from the inclusive scope start may contribute to form, recent win
rate, recency-weighted form, opponent-adjusted strength, roster
matches-together, player match aggregates, and other match-derived values.
Qualifiers do not contribute. `FISSURE Universe`, generic FISSURE events, and
lower-level or unrelated tournaments outside the curated top-level competition
scope do not improve modeled top-level form. `FISSURE Playground` may
contribute when the other point-in-time requirements pass. The strict
feature-history rule still applies after competition eligibility:
`ended_at < prediction_timestamp`.

Roster observations remain a separate point-in-time input governed by
`observed_at < prediction_timestamp`. A roster snapshot is not discarded merely
because it is not itself a match result, but any roster or player aggregate
derived from historical match results uses only the same scoped match-history
universe. Broad raw historical rows remain available in SQLite for future
experimental scopes.

The numeric schema is explicit and deterministic. Metadata such as source IDs,
team names, player names, tournament names, winner fields, and labels are not
model inputs. Competitive stage is represented as one-hot features:
`stage_group`, `stage_crossover`, `stage_upper_bracket`,
`stage_lower_bracket`, `stage_single_elimination`, `stage_grand_final`,
`stage_placement`, and `stage_unknown`; exactly one is active for a row.

Roster features are conservative. Missing rosters use explicit zero/neutral
values. Accepted continuity reuses derived roster lineage and exposes exact,
strong, and coach-supported flags. Ambiguous predecessor branches are not
auto-selected. `roster_matches_together` counts only safely attributable
lineage-window history, so old unrelated organization history does not inflate
transferred roster form.

Player aggregate features use stable provider player IDs, not names. Historical
player participation is attributed only when current point-in-time roster
history safely links the player to a roster snapshot window. Sparse coverage is
expected; no safely attributable player history gives zero sample counts and
neutral raw win-rate values.

The first baseline model is an sklearn `Pipeline`:

```text
StandardScaler -> LogisticRegression
```

Rows are split chronologically instead of randomly. The default baseline policy
is 70% train, 15% validation, and 15% test, with equal prediction timestamp
groups kept together where possible. Preprocessing and the logistic model are
fit only on the train partition; validation and test are never used to fit.
Metrics reported for train, validation, and test are Brier score, log loss,
accuracy, row count, positive label rate, and average predicted probability.

The default artifact path is separate from the legacy model:

```text
data/models/historical_match_win.joblib
```

The artifact stores the fitted pipeline, model type, feature schema version,
ordered feature names, training timestamp, recency decay policy, temporal split
policy, minimum-row policy, competition scope metadata, feature-history scope
semantics, row counts, and recorded metrics. Loading is strict: schema version,
ordered feature names, competition scope metadata, and feature-history scope
semantics must match the current code. Artifacts trained under older broad
feature-history semantics are not compatible with the corrected default
baseline.

Patch-aware Historical ML features remain a future data-source/enrichment task
because the currently confirmed PandaScore historical match payload represented
by this integration does not expose a trusted patch/version field. The current
pipeline does not infer Dota patches from match dates and does not hardcode a
patch calendar.

PowerShell workflow:

```powershell
python -m app.cli sync-history --provider pandascore --db data/autopilot.db --since 2025-07-08 --until 2026-07-07 --page-size 100 --timeout 30
python -m app.cli sync-rosters --provider pandascore --db data/autopilot.db
python -m app.cli historical-ml-status --db data/autopilot.db
python -m app.cli train-historical-ml --db data/autopilot.db --decay-days 90
python -m app.cli evaluate-historical-ml --db data/autopilot.db
```

`train-historical-ml` does not sync or download data. If the database has no
historical matches, or fewer than the configured minimum usable rows, it fails
cleanly without writing a model artifact. `historical-ml-status`,
`train-historical-ml`, and `evaluate-historical-ml` print the active
match-history universe so it is visible that the default baseline uses the
same curated scope for targets and match-derived features.

### Pre-match CatBoost diagnostics

The pre-match Historical ML target is a series-level target:

```text
P(Team A wins the series | information available before the series)
```

Future drafts are not valid inputs for this mode. Completed historical game
drafts inside the target series are also excluded because they would be future
leakage at pre-series prediction time. The existing logistic regression model
remains the baseline/comparator and still uses
`data/models/historical_match_win.joblib`.

`diagnose-historical-ml` is a read-only comparison command. It builds the
current temporal historical dataset, keeps the current grouped chronological
split, evaluates `CONSTANT_0_5`, `TRAIN_LABEL_PRIOR`, the current logistic
pipeline in memory, and a small deterministic CatBoost candidate matrix. It
does not overwrite the logistic artifact and does not save a production
CatBoost artifact by default.

```powershell
python -m app.cli diagnose-historical-ml --db data/autopilot.db
```

The CatBoost candidate uses the existing numeric Historical ML schema directly;
it is not wrapped in `StandardScaler`, does not treat IDs or timestamps as new
numeric model features, and is configured with `loss_function=Logloss`,
`random_seed=42`, `verbose=False`, `allow_writing_files=False`,
`learning_rate=0.03`, and bounded iterations with validation early stopping.
The controlled matrix evaluates decay days `30, 60, 90, 120, 180` with
`depth in {4, 6}` and `l2_leaf_reg in {3, 10}`. Candidate ranking uses
validation Brier first, validation log loss second, validation accuracy third,
then deterministic numeric tie breakers. Test metrics are report-only.

The diagnostic output includes train/validation/test Brier, log loss, accuracy,
positive label rate, and average predicted probability. It also reports test
probability buckets, chronological test buckets, sufficiently sized test
competition/stage groups when available, top standardized feature drift, and
CatBoost feature importance for the validation-selected candidate.

### Historical draft data and post-draft model

Hero draft information is modeled as a separate target:

```text
P(Team A wins the current map | completed draft and pre-map context)
```

This is a POST_DRAFT map/game model, not the pre-match series model. The target
draft is a valid input only for this mode. The target winner is never a feature,
future game drafts cannot contribute, and prior hero history uses strict
`ended_at < target.started_at` completion semantics. A historical game that
ended exactly at the target start timestamp is excluded.

The current PandaScore historical match mapping in this repository preserves
match-level fixture fields, teams, winner, tournament/league/series metadata,
stage, and best-of, but it does not expose complete stable per-game draft
actions. Draft sync therefore uses a separate OpenDota read-only adapter. The
adapter maps the structured OpenDota match payload fields used by this project:
`match_id`, `start_time`, `duration`, `radiant_win`, radiant/dire team IDs and
names, `series_id`, `series_type`, `leagueid`, `league_name`, optional `patch`,
and ordered `picks_bans` entries with `is_pick`, `hero_id`, `team`, and
`order`/`ord`. No HTML scraping, Selenium, Playwright, or browser automation is
used.

PandaScore and OpenDota identities remain separate namespaces. OpenDota team
IDs are source-local IDs; the code does not assume they equal PandaScore team
IDs and does not create permanent team aliases from normalized names. Any future
cross-provider linkage must be explicit and evidence-based. The current draft
status reports source-link coverage rather than guessing.

Sync a bounded draft window explicitly:

```powershell
python -m app.cli sync-drafts --provider opendota --db data/autopilot.db --since 2025-07-08 --until 2026-07-07 --max-pages 3
```

Inspect local draft coverage without network calls:

```powershell
python -m app.cli draft-history-status --db data/autopilot.db
python -m app.cli draft-ml-status --db data/autopilot.db
```

Historical draft/source status:

- OpenDota's initial HTTP 403 was fixed by sending the project User-Agent
  `dota-betting-autopilot/1.0`.
- Free OpenDota still remains limited by rate/rate-limit concerns for the
  intended historical backfill scale.
- STRATZ Default Token GraphQL was tested and closed after even the minimal
  `matches(ids: [Long]!) { id }` path returned `PERMISSION_RESTRICTED`
  / `User is not an admin`. GraphQL schema richness does not change that access
  decision.
- STRATZ public `/match/<Valve match id>` pages were separately investigated
  using ordinary public HTML and embedded client page state only. The public
  page probe uses no STRATZ token, no login, no browser automation, and no auth
  bypass.
- The public-page source-contract decision is `STRATZ_PUBLIC_SUFFICIENT` for
  proceeding to a production historical ingestion/backfill design, with the
  limitations documented in `docs/public_match_page_data_feasibility.md`.
- The production-shaped STRATZ public-page ingestion adapter now lives behind
  `sync-drafts --provider stratz-public`. It uses the same historical Dota game
  repository namespace as draft sync, stores source provenance as
  `stratz_public`, and preserves the public source-contract limitations instead
  of promoting partial fields.
- The post-adapter live gate is now
  `STRATZ_PUBLIC_READY_FOR_BOUNDED_BACKFILL`: the single-match shallow-root
  regression was fixed, the repeated regression match returned `UNCHANGED`, and
  a seven-match bounded live source-shape canary completed with patches
  `177`/`180`/`182`, recognized `pgl`, `the_international`, and `dreamleague`
  families, zero parse failures, zero ingestion-critical invariant failures, and
  seven storage successes.

Probe STRATZ as a free historical game data candidate without writing to the
database:

```powershell
$env:STRATZ_TOKEN = "<your STRATZ Default Token>"
python -m app.cli probe-stratz-history --sample-size 12 --match-id 8886013461 --match-id 8886005043
```

The STRATZ command is a read-only feasibility probe, not a production sync. It
uses `STRATZ_TOKEN` from the environment, never prints the token, does not
persist responses, and reports field-by-field coverage before any future source
promotion decision. When automatic professional-match discovery is not verified
by the live schema, pass repeated `--match-id` values; explicit IDs are batched
at the currently observed STRATZ limit of 10 per request. See
`docs/stratz_historical_data_feasibility.md`.

Probe public professional Dota match pages without a token, login, browser
automation, or database writes:

```powershell
python -m app.cli probe-public-match-pages --source stratz --delay-seconds 1 --match-id 8886013461 --match-id 8886005043
```

The public-page probe uses an honest project User-Agent, checks robots policy,
fetches pages sequentially, parses only public HTML/embedded page state, and
prints provenance-aware coverage. It is a feasibility probe, not a production
crawler. The 12-match EWC smoke sample supports POST_DRAFT training and
PRE_MAP/historical features with limitations, but it does not prove a real-time
live feed, historical bookmaker cash-out prices, complete ordered pick/ban
sequence semantics, item timing, kill timelines, or objective timelines. See
`docs/public_match_page_data_feasibility.md`.

Ingest explicit STRATZ public match pages into the historical draft/game store
without GraphQL, browser automation, authentication, or broad crawling:

```powershell
python -m app.cli sync-drafts --provider stratz-public --db data/autopilot.db --match-id 8886013461 --delay-seconds 1 --max-retries 1
```

The STRATZ public adapter checks robots policy, fetches ordinary public
`/match/<Valve match id>` HTML sequentially with the project User-Agent, and
optionally reads directly referenced public JSON/page-data resources. It is
bounded by explicit `--match-id` values, reports per-match outcomes such as
`INGESTED`, `UPDATED`, `UNCHANGED`, `NOT_FOUND`, `FETCH_FAILED`,
`PARSE_FAILED`, and `SOURCE_INCOMPLETE`, and renders aggregate canary counts.
The report distinguishes `LIVE_REQUEST_EXECUTED` from evidence-derived statuses
such as `LIVE_SINGLE_OR_HOMOGENEOUS_SAMPLE`,
`LIVE_CANARY_CRITICAL_FAILURE`, and
`LIVE_MULTI_FAMILY_CANARY_COMPLETED`. A completed bounded source-shape canary
selects `STRATZ_PUBLIC_READY_FOR_BOUNDED_BACKFILL`; this means deliberately
scoped backfill may be designed next, not unlimited crawling, real-time feed
support, production SLA, objective/item/kill timeline support, or historical
bookmaker odds support.

Draft persistence is relational. `historical_dota_games` stores source/provider
game identity, parent series identity when available, nullable explicit
cross-provider link, timestamps, source-local teams, winner, game number,
best-of, series score before game when safely available, Team A side
(`radiant`/`dire`), optional trusted patch provenance, and draft completeness.
`historical_draft_actions` stores deterministic action order, pick/ban,
team/side, optional team source ID, and stable hero ID. Upsert is idempotent by
`source + source_game_id`; repeated sync does not duplicate actions, and
conflicting source identity or winner semantics are rejected instead of silently
merged.

STRATZ public-page final player state and advantage trajectories are stored in
small side tables rather than pretending they are ordered draft actions.
`historical_dota_player_final_stats` stores player account ID, side/team
association, hero, final K/D/A, final economy/farm/damage summaries, and final
inventory. `historical_dota_advantage_points` stores gold/XP advantage curves
by Valve match ID with `source_index`, optional raw `source_time_value`,
optional `normalized_time_seconds`, and an explicit
`time_semantics_status`. Number-only public curves remain
`source_index_unstable`; downstream code must not treat those indices as
canonical elapsed match seconds.

The bounded source-readiness backfill manifest is
`stratz-public-trajectory-v1`. It is an explicit 18-match list built from the
repository-documented live STRATZ public-page evidence: the 12-match EWC smoke
sample plus the 7-match multi-family source-shape canary, with overlap removed
and fixture-only IDs excluded. It is intentionally much smaller than a crawl:
14 IDs were already persisted in the local STRATZ public game store at manifest
selection time and 4 were documented EWC smoke IDs not yet persisted. The
bounded live manifest run inserted those 4 rows, so the current local corpus has
all 18 manifest IDs persisted on the original development machine. This does
not establish that the database or model artifacts exist in a new checkout.

```powershell
python -m app.cli sync-drafts --provider stratz-public --db data/autopilot.db --manifest stratz-public-trajectory-v1 --delay-seconds 1 --max-retries 1
```

`sync-drafts --manifest` reuses the same STRATZ public sync path as repeated
`--match-id` values. It remains sequential, conservative, idempotent, and
bounded to the named manifest; already ingested matches can return `UNCHANGED`
without creating duplicate rows.

Audit the persisted STRATZ trajectory corpus without network calls:

```powershell
python -m app.cli stratz-trajectory-audit --db data/autopilot.db
```

The audit reports corpus identity, player/composition normalization, gold and
XP point-count distributions, gold/XP pairing, temporal semantics status,
patch-level source-shape variance, family-level source-shape variance, and the
trajectory corpus architecture decision. The recorded audit on the original
development machine found 18
persisted `stratz_public` games, 18 games with both gold and XP curves, 1,626
total advantage points, equal gold/XP point counts for every persisted game,
and no duplicate or non-monotonic stored source indices. It also found 0
explicit source-time values and 0 normalized elapsed-second values; all audited
points remain `source_index_unstable`.

Investigate the unresolved time-axis contract with a bounded public-page
diagnostic:

```powershell
python -m app.cli stratz-trajectory-time-diagnostic --db data/autopilot.db --delay-seconds 1 --inspect-client-assets --max-client-assets 4
```

The diagnostic checks representative manifest matches
`8011794134`, `8346430978`, and `8886013461` across the ordinary public
Overview route. It reports the graph route's robots-policy decision without
fetching the disallowed route. Optional client inspection is limited to
same-origin `/_next/static/*.js` script and script-preload assets directly
referenced by the allowed Overview HTML; it does not execute JavaScript or
crawl chunks. The diagnostic also reports decoded state counts, trajectory
source paths and raw shapes, adjacent coordinate candidates,
duration/point-count relationships from the persisted corpus, timed item rows,
and ordered draft sequence evidence.

The live Overview inspection found five directly referenced static JavaScript
assets, but none contained either exact gold/XP trajectory field identifier or
a deterministic index-to-elapsed-time mapping. The exact 18-match relationship
`point_count = floor(duration_seconds / 60) + 2` therefore remains
corroborative only. It does not prove the likely `(source_index - 1) * 60`
mapping, so persisted trajectory coordinates remain unnormalized.

Timed item evidence requires explicit item ID plus time pairs; final inventory
does not count as timed item data. Ordered draft rows require explicit order,
pick/ban kind, side, and hero. Action number alone does not prove pick/ban
kind, but explicit source phase/kind fields can support ordered draft semantics
when they are associated with the draft rows.

Current trajectory-corpus decision:

```text
STRATZ_PUBLIC_READY_FOR_BOUNDED_BACKFILL
        ->
bounded trajectory backfill manifest
        ->
trajectory corpus audit
        ->
TRAJECTORY_TIME_SEMANTICS_UNRESOLVED
        ->
STRATZ_TRAJECTORY_CORPUS_NEEDS_SOURCE_SEMANTICS_WORK
```

Target prediction roadmap: the primary research direction is short-horizon
game-state and probability changes, approximately `t -> t + 5 minutes`, with
horizons validated against available data. Final match win probability remains
useful as long-horizon context, an auxiliary target, or a baseline. The target
decomposition is game-state trajectory prediction, then win-probability changes,
and, where supported by data, market probability/odds reaction modeling, ending
in structured predictions with uncertainty and data-quality information.
Decision engines, position execution, and cash-out policy are outside scope;
existing paper components remain legacy research tools. STRATZ historical
match trajectories provide game-state trajectory data; they do not provide
historical bookmaker probability or odds trajectories, so market-reaction work
will require a separate bookmaker odds-history dataset or prospectively collected
odds time series.

Next roadmap step: resolve or further evidence STRATZ public trajectory temporal
coordinate semantics from the approved public embedded page state before
defining real `t -> t+5 minute` window labels. Do not train trajectory models,
choose alignment/interpolation semantics, or fall back to final-winner-only work
while `source_index_unstable` remains unresolved.

Post-draft features represent hero IDs as categorical values in the provider
namespace, for example `opendota:hero:100`; hero ID `100` is not treated as
numerically larger than hero ID `10`. Team A and Team B pick slots preserve
provider draft order and require exactly five picks per side for a complete
target. Ban slots are categorical and filled when trusted provider bans are
present, with explicit missing sentinels otherwise. Team A side and trusted
patch are categorical; patch is not inferred from date.

Numeric post-draft context includes game number, best-of, series score before
game when available, point-in-time hero prior form, same-team hero-pair synergy,
cross-team hero matchup history from Team A perspective, sample coverage,
unseen hero/pair counts, and source-local team hero familiarity when team IDs
make that safe. Missing familiarity is distinct from poor familiarity.

The post-draft artifact is separate from the pre-match artifact:

```text
data/models/historical_draft_map_win_catboost.joblib
```

Artifact metadata validates model kind, prediction mode, feature schema,
provider, hero namespace, competition scope, cutoff semantics, patch semantics,
categorical feature list, temporal split metadata, and metrics. It is not loaded
through the pre-match historical predictor.

```powershell
python -m app.cli train-draft-ml --db data/autopilot.db
python -m app.cli evaluate-draft-ml --db data/autopilot.db
```

`train-draft-ml` trains only the POST_DRAFT map model and never overwrites the
pre-match logistic model. If there are too few complete draft rows, it exits
cleanly with a readiness message instead of creating an artifact.

## ML Layer

The bot still starts with rule-based scoring. The optional ML layer is a v1
overlay that learns from settled paper bets and blends its score with the rule
score. If no model exists, the bot keeps using the rule-based fallback.

Train a model from stored paper trading history:

```bash
python -m app.cli train-ml --db data/autopilot.db
```

Run one pass with optional ML scoring:

```bash
python -m app.cli run-once \
  --tournament DreamLeague \
  --transcript data/streamer_transcript.txt \
  --use-ml
```

ML training uses only settled `win` and `loss` paper bets. `unknown`, open,
push, and void bets are not training targets. Until there is enough settled
history, `train-ml` exits cleanly with `Not enough settled bets to train model`.

The current model is a simple `LogisticRegression` pipeline over candidate,
rule-score, odds, and streamer-speech features. It does not place real bets,
call bookmaker APIs, use Twitch APIs, run speech-to-text, or add browser
automation.

## ML Status

Check whether paper trading history has enough settled win/loss examples for
training:

```bash
python -m app.cli ml-status
python -m app.cli ml-status --min-rows 30
```

`ml-status` reports training rows, win/loss balance, ignored bets, and whether
the data is ready for training. Unknown/open bets are not used by ML training.
`push` and `void` bets are stored for reporting, but they are also excluded from
the training dataset.

## Evaluation / Backtest

Evaluate whether the optional ML scorer looks useful compared with the stored
rule-based score on settled paper bets:

```bash
python -m app.cli evaluate-ml --db data/autopilot.db
```

`evaluate-ml` builds an offline train/test split from settled `win` and `loss`
paper bets, trains an in-memory ML model on the train split, and compares it
with the saved rule-based candidate score on the test split. The report prints
usable settled records, train/test sizes, win/loss distribution, rule metrics,
ML metrics, profit/ROI-style paper metrics, and a simple conclusion.

`push`, `void`, open, and `unknown` results are counted in the report but are
not used as binary labels. If there are too few settled bets, the output is
`not_enough_data` or inconclusive instead of a traceback. This is research-only
paper evaluation, not financial advice and not a real-money betting signal.

## MVP Data

The default demo uses fake collectors. The media layer is based on streamer
speech/opinion text, not Twitch chat. Implemented collectors:

- `FakeStreamerSpeechCollector`: built-in fake streamer phrases.
- `TranscriptFileStreamerSpeechCollector`: reads one utterance per non-empty
  line from a local transcript text file.

Real speech-to-text is intentionally not implemented in this MVP. A future
adapter can use a local Whisper/faster-whisper style transcription pipeline or
another permitted STT backend. `python -m app.main` works without real Twitch,
real audio, browser automation, or network calls.

## SQLite Storage

Paper trading data is persisted to `data/autopilot.db`. The database file and
its parent directory are created automatically when you run:

```bash
python -m app.main
```

For a clean research run, stop the app and delete `data/autopilot.db`; the next
demo run will recreate it from `app/storage/schema.sql`.

This is still paper/research tracking only. The project does not place real
bets or implement real auto execution.
