import json


def read_scores(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []


def average(scores):
    count = len(scores)
    return sum(scores) / count


def report(scores):
    print("Report")
    print("Average:", average(scores))
    print("Best:", max(scores))
