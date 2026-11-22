from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
import json

import pytest

from app.replay_future_deaths import (
    FEATURE_COLUMNS, LABEL_COLUMNS, build_future_death_rows, write_future_deaths,
)


def _tick(time):
    return 1000 + int((Decimal(str(time)) * 30).to_integral_value(rounding=ROUND_CEILING))


def _event(time, slot=0, delivery_time=None, delivery_tick=None, reincarnate=False):
    frame = time if delivery_time is None else delivery_time
    tick = _tick(frame) if delivery_tick is None else delivery_tick
    return {
        "player_slot": slot, "hero_id": slot + 1,
        "victim_team": "RADIANT" if slot < 5 else "DIRE",
        "victim_unit_name": f"npc_dota_hero_test{slot}",
        "identity_status": "UNIQUE_FOOTER_PLAYER_TEAM_SELECTED_PRIMARY_NONCLONE",
        "combat_log_target_hero": True, "combat_log_target_illusion": False,
        "timestamp_semantics_status": "ENGINE_TIMESTAMP_MINUS_GAME_START_CORROBORATED_AT_DELIVERY",
        "frame_clock_proven": True, "frame_synthetic": False,
        "will_reincarnate": reincarnate, "event_game_time_seconds": time,
        "frame_game_time_seconds": frame, "replay_tick": tick, "frame_replay_tick": tick,
    }


def _inputs(times=(0,), events=(), end=100):
    common = {"schema_version": 1, "match_id": 123, "replay_sha256": "a" * 64,
              "clock_normalization_status": "PROVEN",
              "clock_normalization_method": "GAME_START_TIME_AND_PAUSE_TICKS",
              "zero_replay_tick": 1000, "pause_ticks": 0, "pause_witnessed": False}
    unique = {(e["player_slot"], e["event_game_time_seconds"]): e for e in events}
    counts = Counter(e["player_slot"] for e in unique.values() if not e["will_reincarnate"])
    players = [{"player_slot": slot, "team": "RADIANT" if slot < 5 else "DIRE",
                "hero_id": slot + 1, "unit_name": f"npc_dota_hero_test{slot}",
                "primary_identity_verified": True, "active_clone_ambiguity": False,
                "deaths": counts[slot]} for slot in range(10)]
    death_data = {**common, "artifact_kind": "replay_primary_hero_deaths",
                  "hero_deaths": list(deepcopy(events)), "eof_players": players,
                  "rejected_hero_deaths": [], "game_end_normalized_time_seconds": end,
                  "game_end_replay_tick": _tick(end)}
    visibility = {**common, "artifact_kind": "replay_hero_visibility",
                  "snapshot_interval_seconds": 10, "game_end_time_seconds": end,
                  "snapshots": []}
    pov = []
    for time in times:
        visibility["snapshots"].append({
            "game_time_seconds": time, "source_game_time_seconds": time, "replay_tick": _tick(time),
            "players": [{"player_slot": p["player_slot"], "hero_id": p["hero_id"], "team": p["team"],
                         "hero_entity_handle": 100 + p["player_slot"]} for p in players],
        })
        for team in ("RADIANT", "DIRE"):
            pov.append({"match_id": "123", "replay_sha256": "a" * 64,
                        "pov_team": team, "game_time_seconds": str(time), "replay_tick": str(_tick(time)),
                        "own_alive_hero_count": "5", "own_valid_position_count": "5",
                        "own_unknown_life_state_count": "0", "own_team_spread": "100.5",
                        "visible_enemy_count": "1", "visible_enemy_with_position_count": "1",
                        "hidden_enemy_count": "4", "unknown_enemy_count": "0",
                        "nearest_visible_enemy_distance": "200.5", "own_team_spread_status": "OK",
                        "nearest_visible_enemy_status": "OK"})
    return pov, death_data, visibility


def test_open_left_closed_right_exact_event_boundaries_and_team_orientation():
    inputs = _inputs((10,), [_event(10), _event(40), _event(40.0000000001),
                             _event(70, 5), _event(70.0000000001, 5)])
    rows, _ = build_future_death_rows(*inputs)
    radiant, dire = rows
    assert radiant["own_deaths_next_30s"] == 1
    assert radiant["enemy_deaths_next_30s"] == 0
    assert radiant["own_deaths_next_60s"] == 2
    assert radiant["enemy_deaths_next_60s"] == 1
    assert dire["own_deaths_next_60s"] == 1 and dire["enemy_deaths_next_60s"] == 2
    assert radiant["any_death_next_30s"] == dire["any_death_next_60s"] == 1


def test_decimal_endpoint_addition_does_not_round_a_future_event_into_window():
    rows, _ = build_future_death_rows(*_inputs((0.1,), [_event(30.1), _event(30.1000000001)]))
    assert rows[0]["label_window_end_30s"] == "30.1"
    assert rows[0]["own_deaths_next_30s"] == 1
    assert rows[0]["own_deaths_next_60s"] == 2


@pytest.mark.parametrize("event", [
    _event(10.01, delivery_time=10),  # Already delivered, but native time is future.
    _event(10, delivery_time=10.01),  # Native time is past, delivery is future.
    _event(10.01, delivery_time=10.01, delivery_tick=_tick(10)),
])
def test_event_delivery_disagreements_at_feature_frame_are_explicit_missing_labels(event):
    rows, _ = build_future_death_rows(*_inputs((10,), [event]))
    for h in (30, 60):
        assert rows[0][f"label_status_{h}s"] == "AMBIGUOUS_TIME_BOUNDARY"
        assert rows[0][f"label_ambiguous_event_count_{h}s"] == 1
        assert rows[0][f"own_deaths_next_{h}s"] is None
        assert rows[0][f"enemy_deaths_next_{h}s"] is None
        assert rows[0][f"any_death_next_{h}s"] is None
        assert json.loads(rows[0][f"label_ambiguous_events_{h}s"])[0]["event_id"].startswith("0@")


@pytest.mark.parametrize("event", [_event(40.01, delivery_time=40), _event(40, delivery_time=40.01)])
def test_upper_boundary_clock_disagreement_only_invalidates_affected_horizon(event):
    rows, _ = build_future_death_rows(*_inputs((10,), [event]))
    assert rows[0]["label_status_30s"] == "AMBIGUOUS_TIME_BOUNDARY"
    assert rows[0]["own_deaths_next_30s"] is None
    assert rows[0]["label_status_60s"] == "VALID" and rows[0]["own_deaths_next_60s"] == 1


def test_match_end_is_confirmed_metadata_not_last_available_pov_frame():
    rows, _ = build_future_death_rows(*_inputs((70,), [_event(100)], end=100))
    assert rows[0]["label_status_30s"] == "VALID" and rows[0]["own_deaths_next_30s"] == 1
    assert rows[0]["label_status_60s"] == "CENSORED"
    assert rows[0]["own_deaths_next_60s"] is rows[0]["any_death_next_60s"] is None
    rows, _ = build_future_death_rows(*_inputs((70.0000000001,), end=100))
    assert rows[0]["label_status_30s"] == "CENSORED"


def test_censoring_keeps_boundary_ambiguity_audit_without_zero_targets():
    rows, _ = build_future_death_rows(*_inputs((80,), [_event(80.01, delivery_time=80)], end=100))
    assert rows[0]["label_status_30s"] == "CENSORED"
    assert rows[0]["label_ambiguous_event_count_30s"] == 1
    assert rows[0]["own_deaths_next_30s"] is rows[0]["any_death_next_30s"] is None


def test_reincarnation_and_exact_duplicates_are_not_counted_or_ambiguous():
    normal = _event(20, 5)
    inputs = _inputs(events=[_event(0.01, delivery_time=0, reincarnate=True), normal, deepcopy(normal)])
    rows, audit = build_future_death_rows(*inputs)
    assert audit == {"source_deaths": {"DIRE": 1}, "reincarnations_excluded": 1, "duplicates_excluded": 1}
    assert rows[0]["own_deaths_next_30s"] == 0 and rows[0]["enemy_deaths_next_30s"] == 1
    assert rows[0]["label_status_30s"] == "VALID"


def test_future_frame_append_preserves_all_existing_rows_and_features():
    inputs = _inputs((0, 10), [_event(20)])
    before, _ = build_future_death_rows(*inputs)
    full = _inputs((0, 10, 20, 30), [_event(20)])
    after, _ = build_future_death_rows(*full)
    assert after[:len(before)] == before
    assert [{k:r[k] for k in FEATURE_COLUMNS} for r in before] == inputs[0]


def test_future_deaths_can_change_only_labels_never_feature_columns():
    old = _inputs()
    before, _ = build_future_death_rows(*old)
    later = _inputs(events=[_event(20)])
    later[0][0].update(global_hidden_x=12345, own_deaths_next_30s=999)
    after, _ = build_future_death_rows(*later)
    assert [{k:r[k] for k in FEATURE_COLUMNS} for r in before] == [{k:r[k] for k in FEATURE_COLUMNS} for r in after]
    assert before[0]["own_deaths_next_30s"] == 0 and after[0]["own_deaths_next_30s"] == 1
    assert "global_hidden_x" not in after[0]
    assert not set(FEATURE_COLUMNS) & set(LABEL_COLUMNS)


def test_missing_feature_cells_stay_missing_without_imputation():
    inputs = _inputs()
    inputs[0][0]["nearest_visible_enemy_distance"] = ""
    rows, _ = build_future_death_rows(*inputs)
    assert rows[0]["nearest_visible_enemy_distance"] == ""
    assert rows[0]["any_death_next_30s"] == 0


@pytest.mark.parametrize("problem", ["eof", "lineage", "frame_tick", "duplicate_pov", "missing_team", "conflicting_death"])
def test_bad_identity_clocks_counts_or_duplicate_data_fail_explicitly(problem):
    pov, deaths, visibility = _inputs(events=[_event(20)])
    if problem == "eof":
        deaths["eof_players"][0]["deaths"] += 1
    elif problem == "lineage":
        visibility["replay_sha256"] = "b" * 64
    elif problem == "frame_tick":
        pov[0]["replay_tick"] = "999"
    elif problem == "duplicate_pov":
        pov.append(deepcopy(pov[0]))
    elif problem == "missing_team":
        pov.pop()
    else:
        event = deepcopy(deaths["hero_deaths"][0])
        event["frame_game_time_seconds"] = 20.01
        deaths["hero_deaths"].append(event)
    with pytest.raises(ValueError):
        build_future_death_rows(pov, deaths, visibility)


def test_output_cannot_overwrite_source(tmp_path):
    source = tmp_path / "pov.csv"
    source.write_bytes(b"preserve\n")
    with pytest.raises(ValueError, match="overwrite"):
        write_future_deaths(source, tmp_path / "deaths.json", tmp_path / "visibility.json", source)
    assert source.read_bytes() == b"preserve\n"
