"""Attach one validated-format match feature record to an existing snapshot.

Read-only historical POST_DRAFT composition, not a LIVE/pre-draft view. Game
seconds and Unix match start_time are distinct clocks and never converted here.
No history, weights, outcome or game-state fields are computed. Contextual
composition owns snapshot lineage/actor validation; this layer checks the new
feature record against that context and its actors. Missing SHA/IDs remain
unknown, never reconstructed. Coverage and identity metadata are not predictors.
"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Literal

from app.analytics.contextual_snapshot import (
    ContextualHistoricalSnapshot, _actor, _lineage, compose_historical_snapshot,
)
from app.analytics.historical_match_context import DEFAULT_CACHE_DIR
from app.analytics.historical_snapshot import HistoricalSnapshot


TEAM_METRICS = {
    "experience": ("prior_match_count", "decayed_prior_match_count", "status"),
    "performance": ("prior_match_count", "wins", "losses", "weighted_wins", "weighted_matches",
                    "weighted_win_fraction", "status"),
}
PLAYER_METRICS = ("prior_match_count", "decayed_prior_match_count", "prior_hero_match_count",
                  "decayed_prior_hero_match_count", "status", "hero_status")
PROVENANCE = dict(experience="HISTORICAL_OBSERVED_EXPERIENCE",
                  performance="HISTORICAL_OPENDOTA_TEAM_PERFORMANCE")


@dataclass(frozen=True)
class FeaturedHistoricalSnapshot:
    contextual_snapshot: ContextualHistoricalSnapshot
    match_features: dict


def _fields(row, fields):
    if not isinstance(row, Mapping) or set(row) != set(fields):
        raise ValueError(f"Incompatible feature structure; expected fields {fields}")


def _id(value, name, *, nullable=True, minimum=1):
    if value is None and nullable:
        return
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid feature identity/value: {name}")


def _metrics(row, fields):
    for name in fields:
        value = row[name]
        if value is None:
            continue
        if name.endswith("status"):
            if not isinstance(value, str):
                raise ValueError(f"Invalid feature status: {name}")
        elif (type(value) not in (int, float) or value < 0
              or (type(value) is float and not math.isfinite(value))):
            raise ValueError(f"Invalid numeric feature: {name}")


def _team(side, team_id, context, teams):
    _id(team_id, "team_id")
    if side not in teams:
        raise ValueError("Cannot associate team_id with an unknown side.")
    for known in (teams[side]["team_id"], context[f"{side.lower()}_team_id"]):
        if team_id is not None and known is not None and team_id != known:
            raise ValueError(f"Snapshot/feature/context {side} team_id mismatch.")


def attach_historical_features(
    snapshot: HistoricalSnapshot, feature_record: Mapping, *,
    phase: Literal["POST_DRAFT"], cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> FeaturedHistoricalSnapshot:
    """Attach a detached feature copy after exact match/known-identity checks.

    Explicit phase attests post-draft availability, not a game-time heuristic.
    The existing local context cache is read via compose_historical_snapshot.
    A missing/NULL feature SHA cannot prove feature replay lineage. Unavailable
    actor channels likewise cannot independently confirm their player links.
    Snapshot observation ticks are preserved; an absent requested tick is not
    inferred, since HistoricalSnapshot does not retain that field.
    """
    if phase != "POST_DRAFT":
        raise ValueError("An explicit POST_DRAFT historical phase is required.")
    if not isinstance(snapshot, HistoricalSnapshot):
        raise ValueError("Pass an existing HistoricalSnapshot.")
    if not isinstance(feature_record, Mapping):
        raise ValueError("Pass one merged match-level feature mapping.")
    required = ("match_id", "start_time", "half_life_days", "context_provenance", "provenance",
                "team_features", "player_features", "metadata")
    _fields(feature_record, (*required, "replay_sha256") if "replay_sha256" in feature_record else required)
    _id(feature_record["match_id"], "match_id", nullable=False)
    if getattr(snapshot.match, "source_match_id", None) != str(feature_record["match_id"]):
        raise ValueError("Snapshot/feature match_id mismatch.")
    _id(feature_record["start_time"], "start_time")
    _id(feature_record["half_life_days"], "half_life_days", nullable=False)
    if (feature_record["context_provenance"] != "HISTORICAL_POST_DRAFT_CONTEXT"
            or feature_record["provenance"] != PROVENANCE):
        raise ValueError("Incompatible historical/context provenance.")
    state = compose_historical_snapshot(feature_record["match_id"], snapshot,
                                        phase=phase, cache_dir=cache_dir)
    context = state.match_context
    _lineage({k: feature_record[k] for k in ("match_id", "replay_sha256")
              if feature_record.get(k) is not None}, context)
    if (feature_record["start_time"] is not None and context["start_time"] is not None
            and feature_record["start_time"] != context["start_time"]):
        raise ValueError("Feature/context start_time mismatch.")
    teams = feature_record["team_features"]
    _fields(teams, ("RADIANT", "DIRE"))
    for side, row in teams.items():
        _fields(row, ("team_id", "experience", "performance"))
        _team(side, row["team_id"], context, teams)
        for group, fields in TEAM_METRICS.items():
            _fields(row[group], fields)
            _metrics(row[group], fields)
    players = feature_record["player_features"]
    if not isinstance(players, list) or len(players) != 10:
        raise ValueError("Expected ten player feature rows.")
    context_players = {p["player_slot"]: p for p in context["players"]}
    indexed = {}
    for player in players:
        _fields(player, ("player_slot", "team", "team_id", "account_id", "hero_id", *PLAYER_METRICS))
        slot = player["player_slot"]
        _id(slot, "player_slot", nullable=False, minimum=0)
        if slot not in range(10) or slot in indexed:
            raise ValueError("Duplicate/invalid player feature slot.")
        side = "RADIANT" if slot < 5 else "DIRE"
        if player["team"] != side:
            raise ValueError("Player feature side mismatch.")
        for field in ("team_id", "account_id", "hero_id"):
            _id(player[field], field)
        _team(side, player["team_id"], context, teams)
        _metrics(player, PLAYER_METRICS)
        _actor(player, context, context_players)
        indexed[slot] = player
    _fields(feature_record["metadata"], ("experience", "performance"))
    _fields(feature_record["metadata"]["experience"], ("coverage", "status"))
    performance = feature_record["metadata"]["performance"]
    _fields(performance, ("source", "completion_time_basis", "decay_reference", "coverage",
                          "catalog_coverage", "buffer_coverage", "temporal_policy"))
    policy = performance["temporal_policy"]
    if (not isinstance(policy, Mapping) or policy.get("result_availability_proven") is not False
            or policy.get("estimated_end_is_confirmed_wall_clock") is not False):
        raise ValueError("Missing/incompatible historical availability policy.")
    _id(policy.get("buffer_seconds"), "buffer_seconds", nullable=False)
    # Reuse actor checks with the feature roster as the second reference. This
    # catches direct game/feature conflicts even if the cache identity is NULL.
    for channel, observation in state.snapshot.observations.items():
        if observation.values is None:
            continue
        for side in teams:
            field = f"{side.lower()}_team_id"
            if field in observation.values:
                _team(side, observation.values[field], context, teams)
            if channel == "pov":
                group = observation.values.get(side)
                if isinstance(group, Mapping) and "team_id" in group:
                    _team(side, group["team_id"], context, teams)
        if channel not in ("heroes", "spatial_global", "pov_enemy_positions"):
            continue
        enemy = channel == "pov_enemy_positions"
        rows = (r for group in observation.values.values() for r in group) if enemy else observation.values["players"]
        for row in rows:
            _actor(row, context, indexed, enemy=enemy)
            if not enemy and "team_id" in row:
                _team(row["team"], row["team_id"], context, teams)
    return FeaturedHistoricalSnapshot(state, deepcopy(dict(feature_record)))
