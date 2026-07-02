"""Tests for the git-backfill plumbing (``azcolorflow_git``).

A real temporary git repository is built with commits stamped on chosen dates, so
the git-shelling logic (root detection, tracking, one-commit-per-day collapsing,
blob/package extraction) is exercised end to end. The only injected seam is
``load_colors`` — here a trivial JSON reader standing in for the Glyphs font open.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import azcolorflow_git as git


def _run(args: list[str], cwd: Path, date: str | None = None) -> None:
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = os.devnull          # isolate from the user's git config
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True, text=True
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _run(["init", "-q"], repo)
    _run(["config", "user.email", "t@example.com"], repo)
    _run(["config", "user.name", "Tester"], repo)
    return repo


def _commit_font(repo: Path, snapshot: dict, iso: str, name: str = "font.glyphs") -> Path:
    font = repo / name
    font.write_text(json.dumps(snapshot), encoding="utf-8")
    _run(["add", name], repo)
    _run(["commit", "-q", "-m", f"state {iso}"], repo, date=f"{iso}T12:00:00")
    return font


def _snap(values: dict[str, int]) -> dict:
    """A one-master snapshot {'m1': {glyph: key}}."""
    return {"m1": dict(values)}


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# subprocess hardening — a stalled/hung git must fail fast, never freeze Glyphs
# --------------------------------------------------------------------------- #

def test_git_helpers_return_none_on_timeout(monkeypatch, tmp_path: Path) -> None:
    def hang(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=git._GIT_TIMEOUT)

    monkeypatch.setattr(git.subprocess, "run", hang)
    assert git._git_text(["status"], tmp_path) is None
    assert git._git_bytes(["status"], tmp_path) is None
    assert git.git_root(tmp_path) is None                     # degrades to "no repo"


def test_git_subprocess_runs_with_timeout_and_no_stdin(monkeypatch, tmp_path: Path) -> None:
    seen: dict = {}
    real_run = subprocess.run

    def spy(cmd: list, **kwargs: object):
        seen.update(kwargs)
        return real_run(cmd, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(git.subprocess, "run", spy)
    git._git_text(["--version"], tmp_path)
    assert seen["timeout"] == git._GIT_TIMEOUT
    assert seen["stdin"] == subprocess.DEVNULL                # never waits on a prompt
    seen.clear()
    git._git_bytes(["--version"], tmp_path)
    assert seen["timeout"] == git._GIT_TIMEOUT
    assert seen["stdin"] == subprocess.DEVNULL


def test_default_cap_bounds_history() -> None:
    # 0 (unlimited) invited unbounded per-commit headless opens on old repos; the
    # default must be a positive most-recent bound now.
    assert git.DEFAULT_CAP == 300


# --------------------------------------------------------------------------- #
# root / tracking
# --------------------------------------------------------------------------- #

def test_git_root_found_for_tracked_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    font = _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    root = git.git_root(font)
    assert root is not None
    assert root.resolve() == repo.resolve()
    assert git.is_tracked(repo, font) is True


def test_git_root_none_outside_repo(tmp_path: Path) -> None:
    lonely = tmp_path / "no_repo"
    lonely.mkdir()
    stray = lonely / "font.glyphs"
    stray.write_text("{}", encoding="utf-8")
    assert git.git_root(stray) is None


def test_is_tracked_false_for_untracked_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    untracked = repo / "other.glyphs"
    untracked.write_text("{}", encoding="utf-8")
    assert git.is_tracked(repo, untracked) is False


def test_rel_degrades_gracefully_for_target_outside_repo(tmp_path: Path) -> None:
    # relative_to raises ValueError for a path outside the repo (symlinked working
    # copies / APFS case differences hit the same path); every helper must degrade
    # to "not tracked / no history" instead of blowing up the backfill.
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    outside = tmp_path / "elsewhere" / "font.glyphs"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    assert git._rel(repo, outside) is None
    assert git.is_tracked(repo, outside) is False
    assert git.day_commits(repo, outside) == []
    assert git.commit_points(repo, outside) == []
    assert git.extract_commit(repo, outside, "HEAD", tmp_path / "x") is None


# --------------------------------------------------------------------------- #
# one-commit-per-day
# --------------------------------------------------------------------------- #

def test_day_commits_keep_last_per_day_oldest_first(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    _commit_font(repo, _snap({"A": 1}), "2026-06-02")
    _commit_font(repo, _snap({"A": 2}), "2026-06-02")   # same day, later -> wins
    _commit_font(repo, _snap({"A": 3}), "2026-06-04")
    days = git.day_commits(repo, repo / "font.glyphs")
    assert [iso for iso, _ in days] == ["2026-06-01", "2026-06-02", "2026-06-04"]
    # the day's snapshot is the LAST commit that day (A:2, not A:1)
    sha_0602 = dict(days)["2026-06-02"]
    extracted = git.extract_commit(repo, repo / "font.glyphs", sha_0602, tmp_path / "x")
    assert extracted is not None
    assert _load_json(extracted) == _snap({"A": 2})


def test_day_commits_caps_to_most_recent(tmp_path: Path, capsys) -> None:
    repo = _init_repo(tmp_path)
    for day in range(1, 6):
        _commit_font(repo, _snap({"A": day}), f"2026-06-0{day}")
    days = git.day_commits(repo, repo / "font.glyphs", cap=2)
    assert [iso for iso, _ in days] == ["2026-06-04", "2026-06-05"]
    # dropping history is announced, never silent
    assert "capped" in capsys.readouterr().out


def test_day_commits_no_truncation_notice_when_under_cap(tmp_path: Path, capsys) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    git.day_commits(repo, repo / "font.glyphs", cap=5)
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------- #
# collect_git_history end to end
# --------------------------------------------------------------------------- #

def test_collect_git_history_round_trips_per_day(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0, "B": -1}), "2026-06-01")
    _commit_font(repo, _snap({"A": 1, "B": 0}), "2026-06-03")
    history = git.collect_git_history(repo / "font.glyphs", _load_json)
    assert history == {
        "2026-06-01": _snap({"A": 0, "B": -1}),
        "2026-06-03": _snap({"A": 1, "B": 0}),
    }


def test_collect_git_history_skips_known_days(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    _commit_font(repo, _snap({"A": 1}), "2026-06-02")
    _commit_font(repo, _snap({"A": 2}), "2026-06-03")
    # pretend 2026-06-02 is already recorded -> it isn't re-opened
    history = git.collect_git_history(repo / "font.glyphs", _load_json, skip={"2026-06-02"})
    assert list(history) == ["2026-06-01", "2026-06-03"]


def test_collect_git_history_empty_outside_repo(tmp_path: Path) -> None:
    lonely = tmp_path / "no_repo"
    lonely.mkdir()
    stray = lonely / "font.glyphs"
    stray.write_text("{}", encoding="utf-8")
    assert git.collect_git_history(stray, _load_json) == {}


def test_collect_git_history_skips_load_failures(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    _commit_font(repo, _snap({"A": 1}), "2026-06-02")

    def flaky(path: Path) -> dict | None:
        data = _load_json(path)
        if data["m1"].get("A") == 0:
            raise ValueError("boom")        # the first day fails to load
        return data

    history = git.collect_git_history(repo / "font.glyphs", flaky)
    assert list(history) == ["2026-06-02"]


def test_collect_git_history_progress_reaches_one(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    _commit_font(repo, _snap({"A": 1}), "2026-06-02")
    seen: list[float] = []
    git.collect_git_history(repo / "font.glyphs", _load_json, progress=seen.append)
    assert seen and seen[-1] == 1.0
    assert all(0 < value <= 1 for value in seen)


# --------------------------------------------------------------------------- #
# .glyphspackage (directory) extraction
# --------------------------------------------------------------------------- #

def test_extract_commit_handles_package_directory(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    pkg = repo / "Font.glyphspackage"
    pkg.mkdir()
    (pkg / "fontinfo.plist").write_text(json.dumps(_snap({"A": 2})), encoding="utf-8")
    _run(["add", "Font.glyphspackage"], repo)
    _run(["commit", "-q", "-m", "pkg"], repo, date="2026-06-01T12:00:00")

    def load_pkg(path: Path) -> dict:
        return json.loads((Path(path) / "fontinfo.plist").read_text(encoding="utf-8"))

    history = git.collect_git_history(pkg, load_pkg)
    assert history == {"2026-06-01": _snap({"A": 2})}


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #

def test_merge_history_live_wins_and_fills_gaps() -> None:
    git_hist = {
        "2026-06-01": _snap({"A": 0}),
        "2026-06-02": _snap({"A": 1}),   # also live -> live wins
    }
    live = {"2026-06-02": _snap({"A": 9}), "2026-06-03": _snap({"A": 2})}
    merged = git.merge_history(live, git_hist)
    assert merged == {
        "2026-06-01": _snap({"A": 0}),
        "2026-06-02": _snap({"A": 9}),   # live value, not git's
        "2026-06-03": _snap({"A": 2}),
    }


def test_merge_history_caps_to_most_recent(capsys) -> None:
    git_hist = {f"2026-06-0{day}": _snap({"A": day}) for day in range(1, 6)}
    merged = git.merge_history({}, git_hist, cap=2)
    assert sorted(merged) == ["2026-06-04", "2026-06-05"]
    assert "capped" in capsys.readouterr().out                 # truncation is announced


# --------------------------------------------------------------------------- #
# commit_points / collect_commit_history (the timeline's per-commit view)
# --------------------------------------------------------------------------- #

def _commit_at(repo: Path, snapshot: dict, when: str, name: str = "font.glyphs") -> None:
    """Write+commit ``snapshot`` with an explicit local datetime (YYYY-MM-DDTHH:MM:SS)."""
    (repo / name).write_text(json.dumps(snapshot), encoding="utf-8")
    _run(["add", name], repo)
    _run(["commit", "-q", "-m", when], repo, date=when)


_PLAN = [
    (_snap({"A": 0}), "2026-06-01T09:00:00"),
    (_snap({"A": 1}), "2026-06-01T15:00:00"),   # same day as the first -> NOT collapsed
    (_snap({"A": 2}), "2026-06-02T10:00:00"),
]


def test_commit_points_keeps_every_commit_not_collapsed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    for snap, when in _PLAN:
        _commit_at(repo, snap, when)
    keys = [key for key, _sha in git.commit_points(repo, repo / "font.glyphs")]
    assert keys == ["2026-06-01T09:00:00", "2026-06-01T15:00:00", "2026-06-02T10:00:00"]


def test_commit_points_caps_to_most_recent(tmp_path: Path, capsys) -> None:
    repo = _init_repo(tmp_path)
    for snap, when in _PLAN:
        _commit_at(repo, snap, when)
    keys = [key for key, _sha in git.commit_points(repo, repo / "font.glyphs", cap=2)]
    assert keys == ["2026-06-01T15:00:00", "2026-06-02T10:00:00"]   # oldest dropped
    assert "capped" in capsys.readouterr().out                      # truncation is announced


def test_commit_points_skips_known_keys(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    for snap, when in _PLAN:
        _commit_at(repo, snap, when)
    keys = [key for key, _sha in git.commit_points(
        repo, repo / "font.glyphs", skip={"2026-06-01T15:00:00"})]
    assert keys == ["2026-06-01T09:00:00", "2026-06-02T10:00:00"]


def test_collect_commit_history_one_snapshot_per_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    for snap, when in _PLAN:
        _commit_at(repo, snap, when)
    history = git.collect_commit_history(
        repo / "font.glyphs", lambda path: json.loads(Path(path).read_text(encoding="utf-8")))
    assert list(history) == ["2026-06-01T09:00:00", "2026-06-01T15:00:00", "2026-06-02T10:00:00"]
    assert history["2026-06-01T15:00:00"] == {"m1": {"A": 1}}
    assert history["2026-06-02T10:00:00"] == {"m1": {"A": 2}}


def test_collect_commit_history_empty_when_not_in_repo(tmp_path: Path) -> None:
    loose = tmp_path / "loose.glyphs"
    loose.write_text("{}", encoding="utf-8")
    assert git.collect_commit_history(loose, lambda path: {"m1": {}}) == {}


def test_collect_commit_history_skip_never_opens_known_commits(tmp_path: Path) -> None:
    # incremental backfill: a commit whose key is already recorded is not extracted
    # or opened at all — the injected loader must never see its content.
    repo = _init_repo(tmp_path)
    for snap, when in _PLAN:
        _commit_at(repo, snap, when)
    opened: list[dict] = []

    def counting_load(path: Path) -> dict:
        data = _load_json(path)
        opened.append(data)
        return data

    history = git.collect_commit_history(
        repo / "font.glyphs", counting_load, skip={"2026-06-01T15:00:00"})
    assert list(history) == ["2026-06-01T09:00:00", "2026-06-02T10:00:00"]
    assert len(opened) == 2                                   # the skipped commit cost nothing
    assert _snap({"A": 1}) not in opened                      # its snapshot was never loaded


def test_collect_commit_history_caps_to_most_recent(tmp_path: Path, capsys) -> None:
    repo = _init_repo(tmp_path)
    for snap, when in _PLAN:
        _commit_at(repo, snap, when)
    history = git.collect_commit_history(repo / "font.glyphs", _load_json, cap=1)
    assert list(history) == ["2026-06-02T10:00:00"]
    assert "capped" in capsys.readouterr().out
