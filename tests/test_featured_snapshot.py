from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest

from app.analytics.featured_snapshot import attach_historical_features
from tests.test_contextual_snapshot import inputs  # noqa: F401 -- shared cache and snapshot fixture
from tests.test_merge_historical_features import pair
from tools.merge_historical_features import merge_pair


@pytest.fixture
def example(request):
    mid, snapshot, cache, save, folder = request.getfixturevalue("inputs")
    experience, performance = pair(mid, cache["start_time"])
    for side in ("RADIANT", "DIRE"):
        team_id = cache[f"{side.lower()}_team_id"]
        experience["teams"][side]["team_id"] = performance["teams"][side]["team_id"] = team_id
    for player in experience["players"]:
        player["team_id"] = cache[f"{player['team'].lower()}_team_id"]
    return snapshot, merge_pair(experience, performance), cache, save, folder


def attach(example):
    snapshot, record, _, _, folder = example
    return attach_historical_features(snapshot, record, phase="POST_DRAFT", cache_dir=folder)


def test_preserves_snapshot_features_provenance_decimal_and_read_only_inputs(example):
    snapshot, record, _, _, folder = example
    original_snapshot, original_record = deepcopy(snapshot), deepcopy(record)
    files = {p.name: p.read_bytes() for p in folder.iterdir()}
    result = attach(example)
    assert result.contextual_snapshot.snapshot == snapshot
    assert result.contextual_snapshot.phase == "POST_DRAFT"
    assert result.match_features == record
    assert result.match_features["team_features"] == record["team_features"]
    assert result.match_features["player_features"] == record["player_features"]
    game = result.contextual_snapshot.snapshot
    assert game.requested_game_time_seconds == Decimal("2280.000200000000000000000000001")
    assert game.observations["heroes"].replay_tick == 100335
    assert game.observations["heroes"].age_seconds == Decimal("9.9668")
    assert game.observations["heroes"].origin == "HISTORICAL_ORACLE"
    assert game.observations["pov"].origin == "HISTORICAL_TEAM_POV"
    assert game.observations["pov"].values is None
    assert result.match_features["metadata"] == record["metadata"]
    assert "account_id" not in game.observations["heroes"].values["players"][0]
    result.match_features["player_features"][0]["prior_match_count"] = 999
    game.observations["heroes"].values["players"][0]["hero_id"] = 999
    assert snapshot == original_snapshot and record == original_record
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == files


def test_reuses_existing_composition_and_requires_explicit_phase(example, monkeypatch):
    from app.analytics import featured_snapshot as module
    snapshot, record, _, _, folder = example
    with pytest.raises(TypeError, match="phase"):
        attach_historical_features(snapshot, record, cache_dir=folder)
    with pytest.raises(TypeError, match="positional"):
        attach_historical_features(snapshot, record, "POST_DRAFT", cache_dir=folder)
    calls = []
    original = module.compose_historical_snapshot
    def compose(mid, game, *, phase, cache_dir):
        calls.append((mid, phase, cache_dir))
        return original(mid, game, phase=phase, cache_dir=cache_dir)
    monkeypatch.setattr(module, "compose_historical_snapshot", compose)
    attach(example)
    assert calls == [(record["match_id"], "POST_DRAFT", folder)]


@pytest.mark.parametrize("phase", [None, True, "LIVE", "DRAFT", "PRE_DRAFT"])
def test_wrong_phase_is_rejected_before_cache_access(example, phase):
    snapshot, record, _, _, folder = example
    with pytest.raises(ValueError, match="POST_DRAFT"):
        attach_historical_features(snapshot, record, phase=phase, cache_dir=folder / "absent")


@pytest.mark.parametrize("damage", ["match_id", "sha", "time", "team", "player_team", "side", "hero", "account", "duplicate_slot", "live", "outcome", "nested_outcome", "policy"])
def test_incompatible_records_fail_without_changing_snapshot(example, damage):
    snapshot, record, _, _, _ = example
    before = deepcopy(snapshot)
    if damage == "match_id":
        record["match_id"] += 1
    elif damage == "sha":
        record["replay_sha256"] = "d"*64
    elif damage == "time":
        record["start_time"] += 1
    elif damage == "team":
        record["team_features"]["RADIANT"]["team_id"] = 999
    elif damage == "player_team":
        record["player_features"][0]["team_id"] = 999
    elif damage == "side":
        record["player_features"][0]["team"] = "DIRE"
    elif damage == "hero":
        record["player_features"][0]["hero_id"] = 999
    elif damage == "account":
        record["player_features"][0]["account_id"] = 999
    elif damage == "duplicate_slot":
        record["player_features"][1]["player_slot"] = 0
    elif damage == "live":
        record["context_provenance"] = "LIVE"
    elif damage == "outcome":
        record["radiant_win"] = True
    elif damage == "nested_outcome":
        record["team_features"]["RADIANT"]["performance"]["future_target"] = 1
    else:
        record["metadata"]["performance"]["temporal_policy"]["result_availability_proven"] = True
    with pytest.raises(ValueError):
        attach(example)
    assert snapshot == before


def test_nulls_and_statuses_are_retained_without_borrowing_known_values(example):
    _, record, _, _, _ = example
    record["team_features"]["RADIANT"]["team_id"] = None
    for player in record["player_features"][:5]:
        player["team_id"] = None
    record["player_features"][0].update(account_id=None, hero_id=None, prior_match_count=None,
                                       decayed_prior_match_count=None, status="UNKNOWN_ID")
    record["team_features"]["RADIANT"]["performance"].update(weighted_win_fraction=None,
                                                               status="NO_OBSERVED_HISTORY")
    result = attach(example)
    assert result.match_features == record
    assert result.match_features["team_features"]["RADIANT"]["team_id"] is None
    assert result.match_features["player_features"][0]["hero_id"] is None
    assert result.match_features["player_features"][0]["account_id"] is None


@pytest.mark.parametrize("omit", [True, False])
def test_absent_feature_sha_remains_unverified_and_is_not_filled(example, omit):
    _, record, _, _, _ = example
    if omit:
        del record["replay_sha256"]
    else:
        record["replay_sha256"] = None
    result = attach(example)
    assert result.match_features == record


def test_direct_game_feature_conflict_is_checked_even_if_context_hero_unknown(example):
    _, record, cache, save, _ = example
    cache["players"][0]["hero_id"] = None
    save()
    record["player_features"][0]["hero_id"] = 999
    with pytest.raises(ValueError, match="hero_id mismatch"):
        attach(example)


def test_snapshot_sha_and_side_are_checked_by_existing_composer(example):
    snapshot, _, _, _, _ = example
    snapshot.observations["spatial_global"].values["replay_sha256"] = "e"*64
    with pytest.raises(ValueError, match="SHA mismatch"):
        attach(example)


@pytest.mark.parametrize("location", ["frame", "hero"])
def test_optional_snapshot_team_ids_cannot_contradict_features(example, location):
    snapshot, _, _, _, _ = example
    values = snapshot.observations["heroes"].values
    if location == "frame":
        values["radiant_team_id"] = 999
    else:
        values["players"][0]["team_id"] = 999
    with pytest.raises(ValueError, match="team_id mismatch"):
        attach(example)


def test_foreign_snapshot_source_cannot_be_used_as_live_or_another_namespace(example):
    from app.analytics.historical_snapshot import MatchIdentity
    snapshot, record, _, _, folder = example
    foreign = replace(snapshot, match=MatchIdentity("live", str(record["match_id"])))
    with pytest.raises(ValueError, match="source mismatch"):
        attach_historical_features(foreign, record, phase="POST_DRAFT", cache_dir=folder)
