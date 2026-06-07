"""Tests for the git-backfill plumbing (``colorflow_git``).

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

import colorflow_git as git


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
# root / tracking
# --------------------------------------------------------------------------- #

def test_git_root_found_for_tracked_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    font = _commit_font(repo, _snap({"A": 0}), "2026-06-01")
    assert git.git_root(font) is not None
    assert git.git_root(font).resolve() == repo.resolve()
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
    assert _load_json(extracted) == _snap({"A": 2})


def test_day_commits_caps_to_most_recent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    for day in range(1, 6):
        _commit_font(repo, _snap({"A": day}), f"2026-06-0{day}")
    days = git.day_commits(repo, repo / "font.glyphs", cap=2)
    assert [iso for iso, _ in days] == ["2026-06-04", "2026-06-05"]


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


def test_merge_history_caps_to_most_recent() -> None:
    git_hist = {f"2026-06-0{day}": _snap({"A": day}) for day in range(1, 6)}
    merged = git.merge_history({}, git_hist, cap=2)
    assert sorted(merged) == ["2026-06-04", "2026-06-05"]
