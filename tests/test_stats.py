import json

import pytest

from stats import average, read_scores, report


def test_read_scores_keeps_json_data(tmp_path):
    path = tmp_path / "scores.json"
    path.write_text(json.dumps([10, 20, 30]))
    assert read_scores(path) == [10, 20, 30]


@pytest.mark.parametrize("content", [b"not JSON", b"\xff"])
def test_invalid_or_missing_file_returns_empty_scores(tmp_path, content):
    assert read_scores(tmp_path / "missing.json") == []
    path = tmp_path / "invalid.json"
    path.write_bytes(content)
    assert read_scores(path) == []


def test_average_and_report_preserve_starter_behavior(capsys):
    assert average([10, 20, 30]) == 20
    report([10, 20, 30])
    assert capsys.readouterr().out == "Report\nAverage: 20.0\nBest: 30\n"
    with pytest.raises(ZeroDivisionError):
        average([])
