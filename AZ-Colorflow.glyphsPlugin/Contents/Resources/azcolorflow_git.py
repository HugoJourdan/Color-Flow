"""Reconstruct Color Flow's dated history from a font's git commits.

Color Flow normally accrues one snapshot per day, only on the days the report is
run — so a fresh install has no timeline. When the font lives in a git repo we can
backfill that history: for each past day, check out that day's last commit of the
font, read its per-master ``layer.color`` state, and synthesise the exact same
``{iso_date: {master_id: {glyph_name: key}}}`` shape the live snapshots use. Every
downstream journey/streak function then works unchanged.

This module is the import-clean, fully unit-tested plumbing: it shells out to git
and extracts historical file content, but the font-reading step is injected as a
``load_colors`` callable so the orchestration is testable without Glyphs. The Glyphs
side (open a historical font headlessly, run ``build_master_glyph_colors``) lives in
``azcolorflow_dashboard`` where GlyphsApp is already imported.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

# Every git-history path is bounded to the most-recent `DEFAULT_CAP` points (days or
# commits) unless the caller passes another positive cap explicitly — each point costs
# a headless font open, so an unbounded ancient repo must not stall a report run.
# When capping actually drops history a notice is printed (see _note_truncation).
DEFAULT_CAP = 300

# Hard ceiling for one git subprocess. These run on Glyphs' main thread; a stalled
# git (fs hiccup, credential prompt, huge pack) must fail fast, not freeze the app.
_GIT_TIMEOUT = 10

# One per-master colour snapshot: {master_id: {glyph_name: key}}.
Snapshot = dict[str, dict[str, int]]


def _note_truncation(kind: str, cap: int, dropped: int) -> None:
    """Make a cap that actually drops history visible (Macro window / test capture)
    instead of silently truncating the timeline."""
    print(
        f"Color Flow: git history capped to the {cap} most recent {kind} "
        f"({dropped} older {kind} skipped)."
    )


def _git_text(args: list[str], cwd: Path) -> str | None:
    """Run ``git <args>`` in ``cwd`` and return stdout as text, or ``None`` if git
    is missing, times out, or the command fails (non-zero exit)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _git_bytes(args: list[str], cwd: Path) -> bytes | None:
    """Run ``git <args>`` in ``cwd`` and return stdout as raw bytes, or ``None`` on
    failure/timeout — used for blob/archive content that should not be text-decoded."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def git_root(path: Path) -> Path | None:
    """The repository root containing ``path`` (a file or directory), or ``None`` if
    ``path`` is not inside a git working tree."""
    start = path if path.is_dir() else path.parent
    if not start.exists():
        return None
    out = _git_text(["rev-parse", "--show-toplevel"], start)
    if not out:
        return None
    root = out.strip()
    return Path(root) if root else None


def _rel(repo: Path, target: Path) -> str | None:
    """``target`` as a POSIX path relative to ``repo`` (git speaks forward slashes),
    or ``None`` when it can't be expressed relative to the repo — symlinked working
    copies or APFS case differences can make ``relative_to`` raise, and the git
    plumbing should then degrade gracefully instead of blowing up the backfill."""
    try:
        return target.resolve().relative_to(repo.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def is_tracked(repo: Path, target: Path) -> bool:
    """Whether ``target`` (a file or a ``.glyphspackage`` directory) is tracked in
    ``repo`` — true when git lists at least one file at that path."""
    rel = _rel(repo, target)
    if rel is None:
        return False
    out = _git_text(["ls-files", "--", rel], repo)
    return bool(out and out.strip())


def day_commits(
    repo: Path, target: Path, cap: int = DEFAULT_CAP, skip: set[str] | None = None
) -> list[tuple[str, str]]:
    """The history of ``target`` collapsed to one commit per calendar day.

    Returns ``[(iso_date, sha), ...]`` oldest-first, keeping the *last* commit of
    each day (the day's final state) and at most ``cap`` most-recent days. Days whose
    ISO date is in ``skip`` are then dropped (already recorded — used for incremental
    backfill). Follows first-parent only, so merges don't pull in side-branch states."""
    rel = _rel(repo, target)
    if rel is None:
        return []
    out = _git_text(["log", "--first-parent", "--date=short", "--format=%cd|%H", "--", rel], repo)
    if not out:
        return []
    # git log is newest-first; the first sha seen for a date is that day's latest.
    latest_per_day: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        iso, sha = line.split("|", 1)
        if iso and sha and iso not in latest_per_day:
            latest_per_day[iso] = sha
    days = sorted(latest_per_day)  # oldest-first
    if cap and len(days) > cap:
        _note_truncation("days", cap, len(days) - cap)
        days = days[-cap:]  # keep the most-recent `cap` days
    if skip:
        days = [iso for iso in days if iso not in skip]
    return [(iso, latest_per_day[iso]) for iso in days]


def extract_commit(repo: Path, target: Path, sha: str, dest_dir: Path) -> Path | None:
    """Materialise ``target`` as it was at ``sha`` into ``dest_dir`` and return the
    path to the extracted font. Handles both a single ``.glyphs`` file (``git show``)
    and a ``.glyphspackage`` directory (``git archive`` -> in-memory tar extract).
    Returns ``None`` if the content can't be retrieved."""
    rel = _rel(repo, target)
    if rel is None:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    if target.is_dir():
        data = _git_bytes(["archive", "--format=tar", sha, "--", rel], repo)
        if data is None:
            return None
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                archive.extractall(dest_dir)  # noqa: S202 - our own repo's tree
        except (tarfile.TarError, OSError):
            return None
        extracted = dest_dir / rel
        return extracted if extracted.exists() else None
    data = _git_bytes(["show", f"{sha}:{rel}"], repo)
    if data is None:
        return None
    out_path = dest_dir / Path(rel).name
    try:
        out_path.write_bytes(data)
    except OSError:
        return None
    return out_path


def commit_points(
    repo: Path, target: Path, cap: int = DEFAULT_CAP, skip: set[str] | None = None
) -> list[tuple[str, str]]:
    """Every commit of ``target`` (first-parent), oldest-first, as ``(key, sha)``.

    Unlike :func:`day_commits` this does NOT collapse to one commit per calendar day —
    each commit is its own point, keyed by a sortable local datetime
    (``YYYY-MM-DDTHH:MM:SS``). At most ``cap`` most-recent commits are kept. Keys are
    made unique (commits within the same second get a ``.1``/``.2`` suffix) so they can
    index a snapshot dict and still sort lexicographically. Points whose final key is
    in ``skip`` are then dropped (already recorded — used for incremental backfill)."""
    rel = _rel(repo, target)
    if rel is None:
        return []
    out = _git_text(
        [
            "log",
            "--first-parent",
            "--date=format-local:%Y-%m-%dT%H:%M:%S",
            "--format=%cd|%H",
            "--",
            rel,
        ],
        repo,
    )
    if not out:
        return []
    raw: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        when, sha = line.split("|", 1)
        if when and sha:
            raw.append((when, sha))
    raw.reverse()  # git log is newest-first -> oldest-first
    if cap and len(raw) > cap:
        _note_truncation("commits", cap, len(raw) - cap)
        raw = raw[-cap:]  # keep the most-recent `cap` commits
    counts: dict[str, int] = {}
    points: list[tuple[str, str]] = []
    for when, sha in raw:
        seen = counts.get(when, 0)
        counts[when] = seen + 1
        key = when if seen == 0 else f"{when}.{seen}"
        points.append((key, sha))
    if skip:
        points = [(key, sha) for key, sha in points if key not in skip]
    return points


def _collect_snapshots(
    repo: Path,
    target: Path,
    load_colors: Callable[[Path], Snapshot | None],
    points: list[tuple[str, str]],
    progress: Callable[[float], None] | None,
) -> dict[str, Snapshot]:
    """Extract each ``(key, sha)`` point's font into a temp dir and load its snapshot,
    returning ``{key: snapshot}``. Points that fail to extract or load are skipped."""
    history: dict[str, Snapshot] = {}
    if not points:
        return history
    work_root = Path(tempfile.mkdtemp(prefix="cfgit-"))
    try:
        for index, (key, sha) in enumerate(points):
            sub = work_root / sha[:12]
            extracted = extract_commit(repo, target, sha, sub)
            if extracted is not None:
                try:
                    colors = load_colors(extracted)
                except Exception:  # noqa: BLE001 - one bad commit must not abort the rest
                    colors = None
                if colors:
                    history[key] = colors
            if progress is not None:
                try:
                    progress((index + 1) / len(points))
                except Exception:  # noqa: BLE001 - progress is best-effort
                    pass
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    return history


def collect_git_history(
    font_path: str | Path,
    load_colors: Callable[[Path], Snapshot | None],
    cap: int = DEFAULT_CAP,
    progress: Callable[[float], None] | None = None,
    skip: set[str] | None = None,
) -> dict[str, Snapshot]:
    """Reconstruct ``{iso_date: snapshot}`` from ``font_path``'s git history.

    For each per-day commit, the font at that commit is extracted to a temp dir and
    handed to ``load_colors`` (which returns a ``{master_id: {glyph_name: key}}``
    snapshot, or ``None`` to skip). Days whose ISO date is in ``skip`` are not opened
    at all (incremental backfill). Days that fail to extract or load are skipped.
    Returns ``{}`` when the path is not in a git repo or not tracked."""
    target = Path(font_path)
    repo = git_root(target)
    if repo is None or not is_tracked(repo, target):
        return {}
    return _collect_snapshots(
        repo, target, load_colors, day_commits(repo, target, cap, skip), progress
    )


def collect_commit_history(
    font_path: str | Path,
    load_colors: Callable[[Path], Snapshot | None],
    cap: int = DEFAULT_CAP,
    progress: Callable[[float], None] | None = None,
    skip: set[str] | None = None,
) -> dict[str, Snapshot]:
    """Reconstruct ``{commit_datetime: snapshot}`` from EVERY commit of ``font_path``
    (not collapsed to one per day, capped to the ``cap`` most-recent commits) — the
    substrate for the timeline's per-commit view. Commits whose datetime key is in
    ``skip`` are not opened at all (incremental backfill: already-recorded checkpoints
    cost nothing). Returns ``{}`` when the path is not in a git repo or not tracked."""
    target = Path(font_path)
    repo = git_root(target)
    if repo is None or not is_tracked(repo, target):
        return {}
    return _collect_snapshots(
        repo, target, load_colors, commit_points(repo, target, cap, skip), progress
    )


def merge_history(
    existing: dict[str, Snapshot], git_history: dict[str, Snapshot], cap: int = DEFAULT_CAP
) -> dict[str, Snapshot]:
    """Merge git-derived history under any existing live snapshots. Live snapshots
    win on a shared date (the user actually recorded those), git fills the gaps; the
    result is capped to the most-recent ``cap`` dates (0 = uncapped) — dropping any
    is announced, never silent."""
    merged: dict[str, Snapshot] = dict(git_history)
    merged.update(existing)  # live snapshots take precedence
    if cap and len(merged) > cap:
        _note_truncation("dates", cap, len(merged) - cap)
        for old_date in sorted(merged)[: len(merged) - cap]:
            del merged[old_date]
    return merged
