from copy import deepcopy
import json

import pytest

from tools import export_historical_experience as output_helpers
from tools import merge_historical_features as cli


def pair(mid=100, start=1800000000):
    common = dict(match_id=mid, start_time=start, replay_sha256="a" * 64, half_life_days=45,
                  context_provenance="HISTORICAL_POST_DRAFT_CONTEXT")
    experience = dict(common, provenance="HISTORICAL_OBSERVED_EXPERIENCE", status="AVAILABLE",
        coverage=dict(complete_career_history=False, eligible_prior_matches=2),
        teams={side: dict(team_id=team, prior_match_count=2, decayed_prior_match_count=0.75, status="OBSERVED")
               for side, team in (("RADIANT", 10), ("DIRE", 20))},
        players=[dict(player_slot=i, team="RADIANT" if i < 5 else "DIRE", team_id=10 if i < 5 else 20,
            account_id=2**53+i+1, hero_id=i+1, prior_match_count=2, decayed_prior_match_count=0.75,
            prior_hero_match_count=1, decayed_prior_hero_match_count=0.5, status="OBSERVED", hero_status="OBSERVED")
            for i in range(10)])
    performance = dict(common, provenance="HISTORICAL_OPENDOTA_TEAM_PERFORMANCE",
        source="opendota/proMatches", completion_time_basis="start_time + duration_seconds",
        decay_reference="CATALOG_COMPLETION_TIME", coverage=dict(complete_career_history=False),
        catalog_coverage=dict(unique_matches=2000, radiant_win_false=900),
        buffer_coverage=dict(time_eligible_records=50),
        temporal_policy=dict(buffer_seconds=86400, estimated_end_is_confirmed_wall_clock=False,
                             result_availability_proven=False, limitation="Buffer is not proof"),
        teams={side: dict(team_id=team, prior_match_count=2, wins=1, losses=1, weighted_wins=0.5,
                         weighted_matches=0.75, weighted_win_fraction=2/3, status="AVAILABLE")
               for side, team in (("RADIANT", 10), ("DIRE", 20))})
    return experience, performance


@pytest.fixture
def files(tmp_path, monkeypatch):
    source = tmp_path / "sources"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    experience, performance = source / "experience.jsonl", source / "performance.jsonl"
    monkeypatch.setattr(cli, "EXPERIENCE", experience)
    monkeypatch.setattr(cli, "PERFORMANCE", performance)
    monkeypatch.setattr(cli, "OUTPUT", output)
    monkeypatch.setattr(output_helpers, "OUTPUT", output)
    def save(pairs):
        experience.write_text(''.join(json.dumps(p[0])+'\n' for p in pairs))
        performance.write_text(''.join(json.dumps(p[1])+'\n' for p in pairs))
    save([pair()])
    return experience, performance, output, save


def test_exact_merge_preserves_features_metadata_and_does_not_mutate_inputs():
    experience, performance = pair()
    before = deepcopy((experience, performance))
    result = cli.merge_pair(experience, performance)
    assert result["match_id"] == 100 and result["half_life_days"] == 45
    for side in ("RADIANT", "DIRE"):
        assert result["team_features"][side]["experience"] == {
            k: experience["teams"][side][k] for k in cli.TEAM_EXPERIENCE}
        assert result["team_features"][side]["performance"] == {
            k: performance["teams"][side][k] for k in cli.TEAM_PERFORMANCE}
    assert result["player_features"] == experience["players"]
    assert result["player_features"][0]["account_id"] == 2**53+1
    assert result["metadata"]["performance"]["temporal_policy"] == performance["temporal_policy"]
    assert result["metadata"]["performance"]["catalog_coverage"] == performance["catalog_coverage"]
    assert result["provenance"]["experience"] == experience["provenance"]
    assert result["metadata"]["experience"]["coverage"] == experience["coverage"]
    result["player_features"][0]["prior_match_count"] = 999
    result["metadata"]["performance"]["temporal_policy"]["buffer_seconds"] = 999
    assert (experience, performance) == before


def test_nulls_and_no_observed_history_remain_distinct():
    experience, performance = pair()
    performance["teams"]["RADIANT"].update(prior_match_count=0, wins=0, losses=0,
        weighted_wins=0.0, weighted_matches=0.0, weighted_win_fraction=None, status="NO_OBSERVED_HISTORY")
    performance["teams"]["DIRE"].update({k: None for k in cli.TEAM_PERFORMANCE if k != "status"})
    performance["teams"]["DIRE"]["status"] = "UNKNOWN_TARGET_START_TIME"
    experience["players"][0].update(account_id=None, prior_match_count=None,
                                   decayed_prior_match_count=None, status="UNKNOWN_ID")
    result = cli.merge_pair(experience, performance)
    radiant, dire = result["team_features"]["RADIANT"]["performance"], result["team_features"]["DIRE"]["performance"]
    assert radiant["prior_match_count"] == 0 and radiant["weighted_win_fraction"] is None
    assert dire["prior_match_count"] is dire["weighted_matches"] is None
    assert result["player_features"][0]["account_id"] is result["player_features"][0]["prior_match_count"] is None


@pytest.mark.parametrize("damage", ["team_radiant", "team_dire", "sha", "time", "half_life", "context", "both_live", "origin"])
def test_identity_and_provenance_mismatches_are_explicit(damage):
    experience, performance = pair()
    if damage.startswith("team_"):
        performance["teams"][damage.removeprefix("team_").upper()]["team_id"] = 99
    elif damage == "sha":
        performance["replay_sha256"] = "b"*64
    elif damage == "time":
        performance["start_time"] += 1
    elif damage == "half_life":
        performance["half_life_days"] = 30
    elif damage == "context":
        performance["context_provenance"] = "HISTORICAL_PRE_DRAFT_CONTEXT"
    elif damage == "both_live":
        experience["context_provenance"] = performance["context_provenance"] = "LIVE"
    else:
        performance["provenance"] = "UNKNOWN"
    with pytest.raises(ValueError, match="mismatch|provenance"):
        cli.merge_pair(experience, performance)


@pytest.mark.parametrize("damage", ["outcome", "nested_outcome", "player_slot", "player_team", "policy", "numeric", "sha_type", "time_type"])
def test_unsafe_or_corrupt_payloads_fail_instead_of_guessing(damage):
    experience, performance = pair()
    if damage == "outcome":
        performance["radiant_win"] = True
    elif damage == "nested_outcome":
        performance["teams"]["RADIANT"]["radiant_win"] = True
    elif damage == "player_slot":
        experience["players"][1]["player_slot"] = 0
    elif damage == "player_team":
        experience["players"][0]["team_id"] = 99
    elif damage == "policy":
        performance["temporal_policy"]["result_availability_proven"] = True
    elif damage == "numeric":
        performance["teams"]["RADIANT"]["weighted_matches"] = True
    elif damage == "sha_type":
        performance["replay_sha256"] = 123
    else:
        performance["start_time"] = float(performance["start_time"])
    with pytest.raises(ValueError):
        cli.merge_pair(experience, performance)


def test_deterministic_chronological_export_and_dry_run_without_writes(files, capsys):
    experience, performance, output, save = files
    pairs = [pair(30, 1800000001), pair(20), pair(10)]
    save(pairs)
    before = (experience.read_bytes(), performance.read_bytes())
    assert cli.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "DRY_RUN" and report["validation_scope"] == "COMPLETE_INPUT_FILES"
    assert list(output.iterdir()) == []
    path = output / "merged.jsonl"
    assert cli.main(["--out", str(path)]) == 0
    capsys.readouterr()
    first = path.read_bytes()
    assert [json.loads(line)["match_id"] for line in first.splitlines()] == [10, 20, 30]
    assert len({json.loads(line)["match_id"] for line in first.splitlines()}) == 3
    assert before == (experience.read_bytes(), performance.read_bytes())
    save(list(reversed(pairs)))
    assert cli.main(["--out", str(path)]) == 0
    capsys.readouterr()
    assert path.read_bytes() == first


def test_limit_reads_only_requested_sample_and_reports_partial_validation(files, capsys):
    experience, performance, _, _ = files
    for path in (experience, performance):
        with path.open('a') as stream:
            stream.write('broken JSON outside selected sample\n')
    assert cli.main(["--limit", "1"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["matches"] == 1 and report["validation_scope"] == "FIRST_N_LINES_PER_INPUT"
    assert cli.main([]) == 1
    assert "stopped" in capsys.readouterr().err


@pytest.mark.parametrize("damage", ["duplicate", "missing_id", "sha", "duplicate_json_key", "nonfinite"])
def test_any_input_error_leaves_existing_result_intact(files, capsys, damage):
    experience, performance, output, save = files
    path = output / "previous.jsonl"
    path.write_text("previous result\n")
    if damage == "duplicate":
        save([pair(), pair()])
    elif damage == "missing_id":
        performance.write_text(json.dumps(pair(200)[1])+'\n')
    elif damage == "sha":
        pairs = [pair(), pair(200)]
        pairs[1][1]["replay_sha256"] = "b"*64
        save(pairs)
    elif damage == "duplicate_json_key":
        experience.write_text('{"match_id":100,"match_id":200}\n')
    else:
        pairs = [pair()]
        pairs[0][1]["teams"]["RADIANT"]["weighted_matches"] = float('nan')
        save(pairs)
    assert cli.main(["--out", str(path)]) == 1
    assert "stopped" in capsys.readouterr().err
    assert path.read_text() == "previous result\n"
    assert list(output.iterdir()) == [path]


def test_source_overwrite_and_outside_output_are_rejected(files, capsys):
    experience, performance, _, _ = files
    before = experience.read_bytes()
    assert cli.main(["--out", str(experience)]) == 1
    capsys.readouterr()
    assert experience.read_bytes() == before
    # Also protect sources when they are inside the otherwise allowed output.
    output_helpers.OUTPUT = cli.OUTPUT = experience.parent
    assert cli.main(["--out", str(experience)]) == 1
    assert "cannot overwrite" in capsys.readouterr().err
    assert experience.read_bytes() == before
    assert performance.exists()


def test_limit_must_be_positive(files, capsys):
    assert cli.main(["--limit", "0"]) == 1
    assert "positive" in capsys.readouterr().err
