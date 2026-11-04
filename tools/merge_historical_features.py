"""Strict 1:1 merge of existing historical exports; no feature recomputation.

No --out means dry-run. --limit bounds reading to the first N lines of EACH
input; it validates only that sample, never claims full-file identity coverage.
IDs/coverage/source metadata are not default numeric ML predictors. Post-draft
historical scope and the conservative, unproven availability policy are retained.
"""

import argparse
from copy import deepcopy
from itertools import islice
import json
import math
from pathlib import Path
import sys

from tools.export_historical_experience import OUTPUT, output_path, write_jsonl


EXPERIENCE = OUTPUT / "historical-experience.jsonl"
PERFORMANCE = OUTPUT / "historical-team-performance.jsonl"
IDENTITY = ("match_id", "start_time", "replay_sha256", "half_life_days", "context_provenance")
EXPERIENCE_METADATA = ("status", "coverage")
PERFORMANCE_METADATA = (
    "source", "completion_time_basis", "decay_reference", "coverage", "catalog_coverage",
    "buffer_coverage", "temporal_policy",
)
TEAM_EXPERIENCE = ("prior_match_count", "decayed_prior_match_count", "status")
TEAM_PERFORMANCE = (
    "prior_match_count", "wins", "losses", "weighted_wins", "weighted_matches",
    "weighted_win_fraction", "status",
)
PLAYER_FIELDS = (
    "player_slot", "team", "team_id", "account_id", "hero_id", "prior_match_count",
    "decayed_prior_match_count", "prior_hero_match_count", "decayed_prior_hero_match_count",
    "status", "hero_status",
)
TEAMS = ("RADIANT", "DIRE")


def _integer(value, field, *, minimum=1, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid {field}: expected integer >= {minimum} or permitted NULL")


def _fields(row, fields):
    if not isinstance(row, dict) or set(row) != set(fields):
        raise ValueError(f"Unexpected/missing fields; expected {fields}")


def _features(row, fields):
    _fields(row, fields)
    for field, value in row.items():
        if value is None:
            continue
        if field in ("status", "hero_status", "team"):
            if not isinstance(value, str):
                raise ValueError(f"Invalid {field}")
        elif field in ("player_slot", "team_id", "account_id", "hero_id"):
            _integer(value, field, minimum=0 if field == "player_slot" else 1)
        else:
            if (type(value) not in (int, float) or value < 0
                    or (type(value) is float and not math.isfinite(value))):
                raise ValueError(f"Invalid numeric feature: {field}")
            if field in ("prior_match_count", "prior_hero_match_count", "wins", "losses"):
                _integer(value, field, minimum=0)
            if field == "weighted_win_fraction" and value > 1:
                raise ValueError("Invalid weighted_win_fraction")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_jsonl(path, limit=None):
    records = {}
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(islice(stream, limit), 1):
            try:
                row = json.loads(line, object_pairs_hook=_object)
                json.dumps(row, allow_nan=False)  # Reject non-finite metadata as well.
                if not isinstance(row, dict):
                    raise ValueError("JSONL record must be an object")
                mid = row.get("match_id")
                _integer(mid, "match_id")
                if mid in records:
                    raise ValueError(f"Duplicate match_id: {mid}")
                records[mid] = row
            except ValueError as exc:
                raise ValueError(f"{path.name}:{number}: {exc}") from exc
    if not records:
        raise ValueError(f"Empty JSONL input: {path}")
    return records


def merge_pair(experience, performance):
    _fields(experience, (*IDENTITY, "provenance", "teams", "players", *EXPERIENCE_METADATA))
    _fields(performance, (*IDENTITY, "provenance", "teams", *PERFORMANCE_METADATA))
    for row, provenance in ((experience, "HISTORICAL_OBSERVED_EXPERIENCE"),
                            (performance, "HISTORICAL_OPENDOTA_TEAM_PERFORMANCE")):
        _integer(row["match_id"], "match_id")
        _integer(row["start_time"], "start_time", nullable=True)
        _integer(row["half_life_days"], "half_life_days")
        sha = row["replay_sha256"]
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
            raise ValueError("Invalid replay_sha256")
        if row["context_provenance"] != "HISTORICAL_POST_DRAFT_CONTEXT" or row["provenance"] != provenance:
            raise ValueError("Unsupported historical/context provenance; no LIVE/pre-draft fallback")
        _fields(row["teams"], TEAMS)
    for field in IDENTITY:
        if experience[field] != performance[field]:
            raise ValueError(f"Match {experience['match_id']}: {field} mismatch")
    policy = performance["temporal_policy"]
    if (not isinstance(policy, dict) or policy.get("estimated_end_is_confirmed_wall_clock") is not False
            or policy.get("result_availability_proven") is not False):
        raise ValueError("Missing/unsupported result availability policy")
    _integer(policy.get("buffer_seconds"), "buffer_seconds")
    teams = {}
    for side in TEAMS:
        own, results = experience["teams"][side], performance["teams"][side]
        _features(own, ("team_id", *TEAM_EXPERIENCE))
        _features(results, ("team_id", *TEAM_PERFORMANCE))
        if own["team_id"] != results["team_id"]:
            raise ValueError(f"Match {experience['match_id']}: {side} team_id mismatch")
        teams[side] = dict(team_id=own["team_id"],
                          experience={k: own[k] for k in TEAM_EXPERIENCE},
                          performance={k: results[k] for k in TEAM_PERFORMANCE})
    players = experience["players"]
    if not isinstance(players, list) or len(players) != 10:
        raise ValueError("Expected ten player feature rows")
    slots = set()
    for player in players:
        _features(player, PLAYER_FIELDS)
        slot = player["player_slot"]
        _integer(slot, "player_slot", minimum=0)
        if slot not in range(10) or slot in slots:
            raise ValueError("Duplicate/invalid player_slot")
        slots.add(slot)
        side = "RADIANT" if slot < 5 else "DIRE"
        if player["team"] != side or player["team_id"] != teams[side]["team_id"]:
            raise ValueError("Player/team identity mismatch")
    return {**{k: experience[k] for k in IDENTITY},
            "provenance": dict(experience=experience["provenance"], performance=performance["provenance"]),
            "team_features": teams, "player_features": deepcopy(players),
            "metadata": dict(
                experience={k: deepcopy(experience[k]) for k in EXPERIENCE_METADATA},
                performance={k: deepcopy(performance[k]) for k in PERFORMANCE_METADATA})}


def merge_records(experience, performance):
    if experience.keys() != performance.keys():
        raise ValueError(f"1:1 match_id mismatch: experience-only={sorted(experience.keys()-performance.keys())}, "
                         f"performance-only={sorted(performance.keys()-experience.keys())}")
    records = [merge_pair(experience[mid], performance[mid]) for mid in sorted(experience)]
    return sorted(records, key=lambda r: (r["start_time"] is None, r["start_time"] or 0, r["match_id"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experience", type=Path, default=EXPERIENCE)
    parser.add_argument("--performance", type=Path, default=PERFORMANCE)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be positive")
        destination = output_path(args.out, OUTPUT / "match-context") if args.out else None
        if destination in (args.experience.resolve(), args.performance.resolve()):
            raise ValueError("--out cannot overwrite either source JSONL")
        records = merge_records(read_jsonl(args.experience, args.limit), read_jsonl(args.performance, args.limit))
        if destination is not None:
            write_jsonl(destination, records)
        print(json.dumps(dict(mode="EXPORT" if destination else "DRY_RUN", matches=len(records),
            team_feature_groups=2*len(records), player_feature_rows=sum(len(r["player_features"]) for r in records),
            validation_scope="COMPLETE_INPUT_FILES" if args.limit is None else "FIRST_N_LINES_PER_INPUT",
            limit=args.limit, out=str(destination) if destination else None), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Historical feature merge stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
