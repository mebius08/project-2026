"""Descriptive review of existing replay artifacts; no training or new features.

Window selection uses future deaths as evaluation annotations only. Feature
snapshots are built independently, using actual time AND replay tick <= decision.
GLOBAL fields stay separate from each team's already-aligned POV fields.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import csv
import math
from pathlib import Path

from app.replay_pov_alignment import (
    FEATURE_COLUMNS, MAX_POV_AGE_SECONDS, TEAMS, _features, _integer, _lineage,
    _number,
)
from app.replay_trajectory import load_replay_trajectory


GLOBAL_FIELDS = (
    "team_spread", "nearest_enemy_distance", "valid_position_count",
    "team_spread_change_30s", "lookback_game_time_seconds",
    "lookback_elapsed_seconds", "team_spread_status", "nearest_enemy_status",
    "spread_change_status",
)
HORIZONS = (120, 180, 300)


def _optional_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not math.isfinite(result := float(value)):
        raise ValueError("Expected a finite number or missing value")
    return result


def _players(frame):
    players = {p["player_slot"]: p for p in frame["players"]}
    if len(players) != 10 or len(frame["players"]) != 10:
        raise ValueError("Expected ten unique players")
    if any(sum(p["team"] == t for p in players.values()) != 5 for t in TEAMS):
        raise ValueError("Expected five players per team")
    return players


def _deaths(frame, team):
    return sum(_integer(p["deaths"]) for p in _players(frame).values()
               if p["team"] == team)


def death_windows(compact: Mapping) -> list[dict]:
    """Evaluation-only proxy: cumulative player deaths between adjacent minutes."""
    result = []
    for start, end in zip(compact["snapshots"], compact["snapshots"][1:]):
        a, z = _players(start), _players(end)
        if (end["game_time_seconds"] - start["game_time_seconds"] != 60
                or end["source_game_time_seconds"] <= start["source_game_time_seconds"]
                or end["replay_tick"] <= start["replay_tick"]):
            raise ValueError("Expected adjacent minute snapshots with increasing clocks")
        if (a.keys() != z.keys() or any(
            (p["team"], p["hero_id"]) != (z[slot]["team"], z[slot]["hero_id"])
            or _integer(z[slot]["deaths"]) < _integer(p["deaths"])
            for slot, p in a.items()
        )):
            raise ValueError("Player identity changed or death counter decreased")
        row = {
            "decision_grid_time_seconds": start["game_time_seconds"],
            "decision_game_time_seconds": start["source_game_time_seconds"],
            "decision_replay_tick": start["replay_tick"],
            "eval_end_grid_time_seconds": end["game_time_seconds"],
            "eval_end_game_time_seconds": end["source_game_time_seconds"],
            "eval_end_replay_tick": end["replay_tick"],
            "eval_window_elapsed_seconds": end["source_game_time_seconds"] - start["source_game_time_seconds"],
        }
        for team in TEAMS:
            row[f"eval_next_minute_{team.lower()}_deaths"] = _deaths(end, team) - _deaths(start, team)
        row["eval_next_minute_total_deaths"] = sum(row[f"eval_next_minute_{t.lower()}_deaths"] for t in TEAMS)
        result.append(row)
    return result


def select_windows(windows: Sequence[Mapping]) -> list[dict]:
    """Five largest proxies, >=300 actual seconds apart; unique prior controls."""
    candidates = [w for w in windows if w["eval_next_minute_total_deaths"] >= 2]
    episodes = []
    for window in sorted(candidates, key=lambda w: (-w["eval_next_minute_total_deaths"], w["decision_game_time_seconds"])):
        if all(abs(window["decision_game_time_seconds"] - w["decision_game_time_seconds"]) >= 300 for w in episodes):
            episodes.append(window)
        if len(episodes) == 5:
            break
    result, used_controls = [], set()
    for episode in sorted(episodes, key=lambda w: w["decision_game_time_seconds"]):
        pair = episode["decision_grid_time_seconds"]
        result.append({**episode, "window_kind": "KILL_CLUSTER_PROXY", "paired_episode_grid_seconds": pair})
        controls = [w for w in windows if w["eval_next_minute_total_deaths"] == 0
                    and w["decision_grid_time_seconds"] not in used_controls]
        earlier = [w for w in controls if w["decision_game_time_seconds"] < episode["decision_game_time_seconds"]]
        if controls:
            control = (max(earlier, key=lambda w: w["decision_game_time_seconds"]) if earlier
                       else min(controls, key=lambda w: abs(w["decision_game_time_seconds"] - episode["decision_game_time_seconds"])))
            used_controls.add(control["decision_grid_time_seconds"])
            result.append({**control, "window_kind": "ZERO_DEATH_CONTROL", "paired_episode_grid_seconds": pair})
    return sorted(result, key=lambda w: w["decision_game_time_seconds"])


def feature_snapshots(compact: Mapping, aligned: Sequence[Mapping], global_rows: Sequence[Mapping]) -> dict:
    """No window annotations or outcomes are accepted by this function."""
    if compact["clock_normalization_status"] != "PROVEN":
        raise ValueError("Clock must be PROVEN")
    lineage = _lineage(compact)
    frames = {f["game_time_seconds"]: f for f in compact["snapshots"]}
    by_team = {t: [] for t in TEAMS}
    for row in global_rows:
        if _lineage(row) != lineage or row["team"] not in TEAMS:
            raise ValueError("GLOBAL identity mismatch")
        by_team[row["team"]].append((_number(row["game_time_seconds"]), _integer(row["replay_tick"]), row))
    for rows in by_team.values():
        rows.sort(key=lambda r: r[0])
        if any(b[0] <= a[0] or b[1] <= a[1] for a, b in zip(rows, rows[1:])):
            raise ValueError("Duplicate or nonmonotonic GLOBAL frames")
    result = {}
    for pov in aligned:
        grid, team = _integer(pov["decision_grid_time_seconds"]), pov["team"]
        if _lineage(pov) != lineage or team not in TEAMS or (grid, team) in result:
            raise ValueError("Aligned decision identity mismatch/duplicate")
        frame = frames[grid]
        time, tick = frame["source_game_time_seconds"], frame["replay_tick"]
        if (_number(pov["decision_game_time_seconds"]) != time
                or _integer(pov["decision_replay_tick"]) != tick
                or _integer(pov["team_id"]) != compact[team.lower() + "_team_id"]
                or pov["decision_id"] != f"{lineage[0]}:{grid}:{team}"):
            raise ValueError("Decision does not match its exact compact source")
        row = {"decision_id": pov["decision_id"], "team": team,
               "pov_alignment_status": pov["alignment_status"],
               "pov_game_time_seconds": None, "pov_replay_tick": None, "pov_age_seconds": None}
        if pov["alignment_status"] == "MATCHED":
            pt, pk = _number(pov["pov_game_time_seconds"]), _integer(pov["pov_replay_tick"])
            if (pt > time or pk > tick or time - pt > MAX_POV_AGE_SECONDS
                    or not math.isclose(_number(pov["pov_age_seconds"]), time - pt, abs_tol=1e-9, rel_tol=0)):
                raise ValueError("POV is future, stale or has an incorrect age")
            row.update(pov_game_time_seconds=pt, pov_replay_tick=pk, pov_age_seconds=time - pt)
            row.update({"pov_" + k: v for k, v in _features(pov).items()})
        else:
            if pov["alignment_status"] not in ("STALE_POV", "NO_PAST_POV") or any(pov[k] not in (None, "") for k in FEATURE_COLUMNS):
                raise ValueError("Unmatched POV must have missing features")
            row.update(dict.fromkeys("pov_" + k for k in FEATURE_COLUMNS))
        eligible = [g for g in by_team[team] if g[0] <= time and g[1] <= tick]
        source = eligible[-1] if eligible else None
        matched = source is not None and time - source[0] <= MAX_POV_AGE_SECONDS
        row.update(global_alignment_status="MATCHED" if matched else "STALE_GLOBAL" if source else "NO_PAST_GLOBAL",
                   global_game_time_seconds=source[0] if matched else None,
                   global_replay_tick=source[1] if matched else None,
                   global_age_seconds=time - source[0] if matched else None)
        for name in GLOBAL_FIELDS:
            row["global_" + name] = (source[2][name] if name.endswith("_status") else _optional_number(source[2][name])) if matched else None
        if matched:
            past = row["global_lookback_game_time_seconds"]
            elapsed = row["global_lookback_elapsed_seconds"]
            if ((past is not None and (past < 0 or past > source[0]))
                    or (row["global_team_spread_change_30s"] is not None
                        and (past is None or elapsed is None or not math.isclose(elapsed, source[0] - past, abs_tol=1e-9, rel_tol=0)))):
                raise ValueError("GLOBAL spread change has an invalid/future lookback")
        result[grid, team] = row
    return result


def review_windows(compact: Mapping, windows: Sequence[Mapping], features: Mapping, outcomes: Sequence[Mapping]) -> list[dict]:
    """Attach future values only under eval_* columns, after features are fixed."""
    frames = {f["game_time_seconds"]: f for f in compact["snapshots"]}
    indexed = {}
    for outcome in outcomes:
        grid, h, team = _integer(outcome["game_time_seconds"]), _integer(outcome["horizon_seconds"]), outcome["team"]
        key = (grid, team, h)
        if (_integer(outcome["match_id"]) != compact["match_id"] or team not in TEAMS
                or h not in HORIZONS or _integer(outcome["future_game_time_seconds"]) != grid + h
                or key in indexed or grid not in frames or grid + h not in frames):
            raise ValueError("Invalid or duplicate outcome horizon")
        indexed[key] = outcome
    rows = []
    for window in windows:
        grid = window["decision_grid_time_seconds"]
        for team in TEAMS:
            row = {"match_id": compact["match_id"], "replay_sha256": compact["replay_sha256"],
                   **window, **features[grid, team]}
            opponent = "DIRE" if team == "RADIANT" else "RADIANT"
            for h in HORIZONS:
                suffix = str(h)
                future = frames.get(grid + h)
                outcome = indexed.get((grid, team, h))
                status = "AVAILABLE" if outcome else "OUTCOME_MISSING" if future else "NO_FUTURE_SNAPSHOT"
                row["eval_outcome_status_" + suffix] = status
                for name in ("future_grid_time", "future_game_time", "future_replay_tick", "elapsed_seconds", "total_deaths", "net_worth_diff_change", "kill_diff_change"):
                    row[f"eval_{name}_{h}"] = None
                if outcome:
                    own, enemy = _integer(outcome["future_team_deaths"]), _integer(outcome["future_opponent_deaths"])
                    if (own != _deaths(future, team) or enemy != _deaths(future, opponent)
                            or future["source_game_time_seconds"] <= window["decision_game_time_seconds"]
                            or future["replay_tick"] <= window["decision_replay_tick"]):
                        raise ValueError("Outcome does not match the future compact state")
                    row.update({
                        f"eval_future_grid_time_{h}": grid + h,
                        f"eval_future_game_time_{h}": future["source_game_time_seconds"],
                        f"eval_future_replay_tick_{h}": future["replay_tick"],
                        f"eval_elapsed_seconds_{h}": future["source_game_time_seconds"] - window["decision_game_time_seconds"],
                        f"eval_total_deaths_{h}": own + enemy - _deaths(frames[grid], team) - _deaths(frames[grid], opponent),
                        f"eval_net_worth_diff_change_{h}": _optional_number(outcome["net_worth_diff_change"]),
                        f"eval_kill_diff_change_{h}": _optional_number(outcome["kill_diff_change"]),
                    })
            rows.append(row)
    return rows


def _display(value, precision=1):
    return "—" if value is None else f"{value:.{precision}f}" if isinstance(value, float) else str(value)


def render_report(compact, windows, rows):
    selected = [r for r in rows if r["team"] == "RADIANT"]
    pairs = {(r["decision_grid_time_seconds"], r["team"]): r for r in rows}
    lines = [
        f"Матч {compact['match_id']}: описательная проверка kill-cluster proxy.",
        f"Кандидатов >=2 смертей за минуту: {sum(w['eval_next_minute_total_deaths'] >= 2 for w in windows)}; нулевых окон: {sum(w['eval_next_minute_total_deaths'] == 0 for w in windows)}.",
        "Выбраны пять крупнейших кластеров, разнесённых минимум на 300 фактических секунд; контроль — ближайшее предшествующее свободное окно без смертей (при отсутствии — ближайшее последующее).",
        "Это ретроспективный отбор примеров по будущим смертям, не точная разметка начала teamfight и не оценка предсказательной способности.",
        "Признаки построены отдельно от отбора и outcomes. GLOBAL и POV ограничены actual time и replay tick decision; давность <=15 с. GLOBAL не объявляется доступным в LIVE.",
        "Расстояния — единицы Source 2. Δspread30 взят из существующего GLOBAL CSV: отрицательное значение означает меньший средний разброс доступных живых героев, а не доказанное движение всех героев к бою.",
        "V/coords/H/U — видимые враги / видимые с координатами / скрытые / неизвестные. Покрытие своих координат вынесено в CSV. Прочерк означает отсутствие значения.",
        "", "| Окно (сетка) | Тип | Фактический decision | Источник GLOBAL/POV; возраст | Смерти R/D +60 | GLOBAL min | V/coords/H/U R; D | POV min R; D | Spread R; D | GLOBAL Δspread30 R; D |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in selected:
        d = pairs[r["decision_grid_time_seconds"], "DIRE"]
        def coverage(x):
            return "/".join(str(x["pov_" + k]) for k in ("visible_enemy_count", "visible_enemy_with_position_count", "hidden_enemy_count", "unknown_enemy_count"))
        lines.append("| " + " | ".join([
            f"{r['decision_grid_time_seconds']}–{r['eval_end_grid_time_seconds']}", r["window_kind"],
            str(r["decision_game_time_seconds"]),
            f"G={r['global_game_time_seconds']} ({_display(r['global_age_seconds'], 4)}s); R={r['pov_game_time_seconds']} ({_display(r['pov_age_seconds'], 4)}s); D={d['pov_game_time_seconds']} ({_display(d['pov_age_seconds'], 4)}s)",
            f"{r['eval_next_minute_radiant_deaths']}/{r['eval_next_minute_dire_deaths']}",
            _display(r["global_nearest_enemy_distance"]), coverage(r) + "; " + coverage(d),
            _display(r["pov_nearest_visible_enemy_distance"]) + "; " + _display(d["pov_nearest_visible_enemy_distance"]),
            _display(r["pov_own_team_spread"]) + "; " + _display(d["pov_own_team_spread"]),
            _display(r["global_team_spread_change_30s"]) + "; " + _display(d["global_team_spread_change_30s"]),
        ]) + " |")
    lines += ["", "| Decision (сетка) | Смерти за 120/180/300 с | Δ net worth diff Radiant за 120/180/300 с |", "|---|---|---|"]
    for r in selected:
        lines.append(f"| {r['decision_grid_time_seconds']} | " + " / ".join(_display(r[f"eval_total_deaths_{h}"]) for h in HORIZONS) + " | " + " / ".join(_display(r[f"eval_net_worth_diff_change_{h}"]) for h in HORIZONS) + " |")
    controls = [r for r in selected if r["window_kind"] == "ZERO_DEATH_CONTROL" and r["global_nearest_enemy_distance"] is not None]
    if controls:
        closest = min(controls, key=lambda r: r["global_nearest_enemy_distance"])
        lines += ["", f"Контрпример близости: на decision {closest['decision_grid_time_seconds']} GLOBAL min = {_display(closest['global_nearest_enemy_distance'])}, но в следующую минуту смертей нет. Малая дистанция одной пары героев не означает начало командной драки."]
    for r in selected:
        d = pairs[r["decision_grid_time_seconds"], "DIRE"]
        rv, dv = r["pov_visible_enemy_count"], d["pov_visible_enemy_count"]
        if rv is not None and dv is not None and ((rv > 0 and dv == 0) or (dv > 0 and rv == 0)):
            lines += ["", f"Асимметрия на decision {r['decision_grid_time_seconds']}: V Radiant/Dire = {rv}/{dv}; GLOBAL min {_display(r['global_nearest_enemy_distance'])}, POV min R/D {_display(r['pov_nearest_visible_enemy_distance'])}/{_display(d['pov_nearest_visible_enemy_distance'])}. Смертей в следующую минуту: {r['eval_next_minute_total_deaths']}."]
    hidden_clusters = [str(r["decision_grid_time_seconds"]) for r in selected
                       if r["window_kind"] == "KILL_CLUSTER_PROXY" and r["pov_visible_enemy_count"] == 0
                       and pairs[r["decision_grid_time_seconds"], "DIRE"]["pov_visible_enemy_count"] == 0]
    if hidden_clusters:
        lines += ["", "Перед выбранными кластерами " + ", ".join(hidden_clusters) + " ни один POV не видит врагов на использованном кадре. Это не показывает точное время появления врагов или начала боя внутри следующей минуты."]
    lines += [
        "", "Числа будущих смертей суммируются по игрокам, не по kills. Outcomes используют прежнюю номинальную сетку t+h; фактические будущие время/tick и elapsed отдельно сохранены в CSV. Контроль нулевой только на +60 с, а не на +120/180/300 с.",
        "Прокси покрывает только пары полных минутных снимков; последний неполный отрезок после последнего compact snapshot не размечен.",
        "Флаги видимости не гарантируют координаты живого героя. Отсутствие видимости не доказывает Smoke. Один кадр минимального расстояния не доказывает начало сближения.",
        "Один матч и отбор крупнейших кластеров не позволяют оценить причинность, качество прогноза, частоту ложных сигналов или переносимость на другие матчи/LIVE. GLOBAL-координаты скрытых врагов не входят в POV.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("compact", "aligned", "global", "outcomes", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    paths = [args.compact, args.aligned, getattr(args, "global"), args.outcomes]
    outputs = [args.output_dir / "selected_windows.csv", args.output_dir / "report.md"]
    if any(p.resolve() in {s.resolve() for s in paths} for p in outputs):
        parser.error("Outputs must not overwrite inputs")
    def read_csv(path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))
    try:
        compact = load_replay_trajectory(args.compact)
        features = feature_snapshots(compact, read_csv(args.aligned), read_csv(getattr(args, "global")))
        windows = death_windows(compact)
        selected = select_windows(windows)
        rows = review_windows(compact, selected, features, read_csv(args.outcomes))
        if not rows:
            raise ValueError("No candidate windows selected")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with outputs[0].open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        outputs[1].write_text(render_report(compact, windows, rows), encoding="utf-8")
    except (KeyError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"WROTE windows={len(selected)} team_rows={len(rows)} output_dir={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
