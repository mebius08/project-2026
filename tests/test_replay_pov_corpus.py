import csv
from decimal import Decimal
import json

import pytest

from app.replay_pov_corpus import COLUMNS, CSV_NAME, build_corpus


def _pair(mid=123, time='10.0002', tick=1300, statuses=('VALID', 'VALID')):
    rows = []
    for index, team in enumerate(('RADIANT', 'DIRE')):
        row = dict(zip(COLUMNS[:16], (
            str(mid), f'{mid:064x}', time, str(tick), team,
            '5', '5', '0', '100.500000' if index == 0 else '200.0',
            '1', '1', '4', '0', '25.0000', 'OK', 'OK',
        )))
        for h, own, enemy, status in zip((30, 60), (2, 3), (1, 4), statuses):
            if index:
                own, enemy = enemy, own
            ambiguous = status == 'AMBIGUOUS_TIME_BOUNDARY'
            events = [{'event_id': '0@10.01', 'reasons': ['LEFT_EVENT_VS_DELIVERY_TICK']}] if ambiguous else []
            row.update({
                f'own_deaths_next_{h}s': str(own) if status == 'VALID' else '',
                f'enemy_deaths_next_{h}s': str(enemy) if status == 'VALID' else '',
                f'any_death_next_{h}s': '1' if status == 'VALID' else '',
                f'label_status_{h}s': status,
                f'label_window_end_{h}s': str(Decimal(time) + h),
                f'label_ambiguous_event_count_{h}s': str(len(events)),
                f'label_ambiguous_events_{h}s': json.dumps(events),
            })
        rows.append(row)
    return rows


def _write(path, rows, columns=COLUMNS):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_merge_three_matches_preserves_cells_missingness_groups_and_pair_orientation(tmp_path):
    first = _pair(123, time='0.100000')
    first[0].update(own_alive_hero_count='1', own_valid_position_count='1',
                    own_team_spread='', own_team_spread_status='INSUFFICIENT_OWN_POSITIONS')
    batches = [list(reversed(first)), _pair(456, statuses=('VALID', 'CENSORED')),
               _pair(789, statuses=('CENSORED', 'CENSORED'))]
    paths = [_write(tmp_path / f'{i}.csv', rows) for i, rows in enumerate(batches)]
    before = [p.read_bytes() for p in paths]
    out = tmp_path / 'corpus'
    manifest = build_corpus(paths, out)
    with (out / CSV_NAME).open(newline='') as f:
        result = list(csv.DictReader(f))
    assert result == first + batches[1] + batches[2]
    assert before == [p.read_bytes() for p in paths]
    assert manifest['counts'] == {
        'matches': 3, 'frames': 3, 'team_rows': 6,
        'label_statuses': {
            '30': {'VALID': 4, 'CENSORED': 2, 'AMBIGUOUS_TIME_BOUNDARY': 0},
            '60': {'VALID': 2, 'CENSORED': 4, 'AMBIGUOUS_TIME_BOUNDARY': 0},
        },
    }
    groups = manifest['column_groups']
    flattened = [c for group in groups.values() for c in group]
    assert len(flattened) == len(set(flattened)) == len(COLUMNS)
    assert set(flattened) == set(COLUMNS)
    assert not set(groups['features_at_t']) & set(groups['future_targets'])
    assert 'any_death_next_30s' in groups['future_targets']
    assert not any('global' in c or 'next_' in c for c in groups['features_at_t'])
    assert manifest['evaluation_policy']['minimum_split_group'] == ['match_id']
    assert manifest['evaluation_policy']['paired_views_and_overlapping_windows_are_not_independent']
    assert json.loads((out / 'manifest.json').read_text()) == manifest
    other = tmp_path / 'reordered'
    build_corpus(list(reversed(paths)), other)
    assert (other / CSV_NAME).read_bytes() == (out / CSV_NAME).read_bytes()


@pytest.mark.parametrize('kind', ['same_path', 'copied_file', 'within_file'])
def test_duplicate_inputs_or_observations_fail_before_writing(tmp_path, kind):
    source = _write(tmp_path / 'one.csv', _pair() * (2 if kind == 'within_file' else 1))
    paths = [source]
    if kind == 'same_path':
        paths.append(source)
    elif kind == 'copied_file':
        paths.append(_write(tmp_path / 'copy.csv', _pair()))
    with pytest.raises(ValueError, match='[Dd]uplicate'):
        build_corpus(paths, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('kind', ['missing_team', 'invalid_team', 'time', 'tick', 'sha', 'same_replay_other_match', 'nonmonotonic'])
def test_incomplete_pairs_and_identity_or_clock_conflicts_fail(tmp_path, kind):
    rows = _pair()
    if kind == 'missing_team':
        rows.pop()
    elif kind == 'invalid_team':
        rows[1]['pov_team'] = 'GLOBAL'
    elif kind == 'time':
        rows[1] = _pair(time='10.0003')[1]
    elif kind == 'tick':
        rows[1]['replay_tick'] = '1301'
    elif kind == 'sha':
        rows[1]['replay_sha256'] = 'b' * 64
    elif kind == 'same_replay_other_match':
        later = _pair(456)
        for row in later:
            row['replay_sha256'] = rows[0]['replay_sha256']
        rows += later
    else:
        rows += _pair(time='20.0002', tick=1200)
    with pytest.raises(ValueError):
        build_corpus([_write(tmp_path / 'input.csv', rows)], tmp_path / 'out')


@pytest.mark.parametrize('kind', [
    'unknown_status', 'empty_valid', 'negative', 'noninteger', 'wrong_any',
    'not_swapped', 'different_status', 'wrong_window', 'audit_length',
    'valid_ambiguity', 'decreasing_horizon', 'nonempty_censored', 'uncensored_longer',
])
def test_invalid_targets_statuses_or_window_boundaries_are_rejected(tmp_path, kind):
    rows = _pair()
    row = rows[0]
    if kind == 'unknown_status':
        row['label_status_30s'] = 'OK'
    elif kind == 'empty_valid':
        row['own_deaths_next_30s'] = ''
    elif kind == 'negative':
        row['own_deaths_next_30s'] = '-1'
    elif kind == 'noninteger':
        row['own_deaths_next_30s'] = '1.5'
    elif kind == 'wrong_any':
        row['any_death_next_30s'] = '0'
    elif kind == 'not_swapped':
        row['enemy_deaths_next_30s'] = '0'
    elif kind == 'different_status':
        rows[1].update({k: v for k, v in _pair(statuses=('VALID', 'CENSORED'))[1].items()})
    elif kind == 'wrong_window':
        row['label_window_end_30s'] = '40.000200000000001'
    elif kind == 'audit_length':
        row['label_ambiguous_event_count_30s'] = '1'
    elif kind == 'valid_ambiguity':
        row.update(label_ambiguous_event_count_30s='1', label_ambiguous_events_30s='[{}]')
    elif kind == 'decreasing_horizon':
        row['own_deaths_next_60s'] = '1'
    elif kind == 'nonempty_censored':
        rows = _pair(statuses=('VALID', 'CENSORED'))
        rows[0]['any_death_next_60s'] = '0'
    else:
        rows = _pair(statuses=('CENSORED', 'VALID'))
    with pytest.raises(ValueError):
        build_corpus([_write(tmp_path / 'input.csv', rows)], tmp_path / 'out')


def test_ambiguity_and_censoring_audit_are_preserved_without_targets(tmp_path):
    rows = _pair(statuses=('AMBIGUOUS_TIME_BOUNDARY', 'CENSORED'))
    for row in rows:
        row['label_ambiguous_event_count_60s'] = row['label_ambiguous_event_count_30s']
        row['label_ambiguous_events_60s'] = row['label_ambiguous_events_30s']
    source = _write(tmp_path / 'input.csv', rows)
    out = tmp_path / 'out'
    manifest = build_corpus([source], out)
    assert manifest['counts']['label_statuses']['30']['AMBIGUOUS_TIME_BOUNDARY'] == 2
    with (out / CSV_NAME).open(newline='') as f:
        assert list(csv.DictReader(f)) == rows


def test_censored_cannot_turn_valid_later_in_same_match(tmp_path):
    rows = _pair(time='10', statuses=('CENSORED', 'CENSORED')) + _pair(time='20', tick=1600)
    with pytest.raises(ValueError, match='tail'):
        build_corpus([_write(tmp_path / 'input.csv', rows)], tmp_path / 'out')


@pytest.mark.parametrize('column,value', [('own_alive_hero_count', 'six'), ('own_team_spread', 'NaN')])
def test_incompatible_feature_types_are_rejected_without_coercion(tmp_path, column, value):
    rows = _pair()
    rows[0][column] = value
    with pytest.raises(ValueError):
        build_corpus([_write(tmp_path / 'input.csv', rows)], tmp_path / 'out')


@pytest.mark.parametrize('column', ['global_hidden_x', 'unknown_feature'])
def test_extra_columns_cannot_enter_feature_contract(tmp_path, column):
    rows = _pair()
    for row in rows:
        row[column] = '1234'
    source = _write(tmp_path / 'input.csv', rows, (*COLUMNS, column))
    with pytest.raises(ValueError, match='schema'):
        build_corpus([source], tmp_path / 'out')


def test_output_cannot_overwrite_input(tmp_path):
    source = _write(tmp_path / CSV_NAME, _pair())
    before = source.read_bytes()
    with pytest.raises(ValueError, match='overwrite'):
        build_corpus([source], tmp_path)
    assert source.read_bytes() == before
