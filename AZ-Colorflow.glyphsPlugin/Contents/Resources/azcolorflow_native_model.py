"""Pure-Python port of the report's client-side maths (azcolorflow_assets.DASHBOARD_JS).

The native AppKit report (azcolorflow_native_report) renders the SAME model dict
``azcolorflow_dashboard.build_model`` hands to ``build_html``; this module is the
JS "H" helpers — counted sets, graded step %, ``stateAt`` reconstruction, change
counts, coverage rows, lanes, calendar activity, timeline granularity — with no
AppKit dependency so it stays headless-testable. Every function mirrors the JS
one of the same (camelCase) name, so the two reports always agree.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

NO_COLOR = -1
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_LONG = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
CAT_ORDER = ["Letter", "Number", "Punctuation", "Mark", "Separator", "Symbol", "Other"]
TL_SPANS = [
    ("1d", "1D", 1),
    ("1w", "1W", 7),
    ("1m", "1M", 30),
    ("1y", "1Y", 365),
    ("all", "All", 0),
]


def cfd_date(iso: str) -> datetime | None:
    """ "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS[.n]" -> aware UTC datetime (None if bad)."""
    if not isinstance(iso, str):
        return None
    try:
        if "T" in iso:
            return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        return datetime.strptime(iso[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def date_label(iso: str) -> str:
    """ "5 Jun" for per-day keys, "5 Jun 14:30" for per-commit keys."""
    when = cfd_date(iso)
    if when is None:
        return str(iso)
    if "T" in str(iso):
        return f"{when.day} {MONTHS[when.month - 1]} {when:%H:%M}"
    return f"{when.day} {MONTHS[when.month - 1]}"


def iso_minus_days(iso: str, days: int) -> str:
    when = cfd_date(iso)
    if when is None:
        return iso
    return (when - timedelta(days=days)).strftime("%Y-%m-%d")


def snap_date(dates: list[str], target: str) -> str | None:
    """Nearest real snapshot date not after ``target`` (earliest when it predates all)."""
    if not dates:
        return None
    pick = dates[0]
    for date in dates:
        if date <= target:
            pick = date
        else:
            break
    return pick


def pct(n: float, t: float) -> int:
    return round(n / t * 100) if t else 0


def rank_arrow(value: float) -> tuple[str, str]:
    """(glyph, kind) for a signed change: up / down / flat."""
    if value > 0:
        return "▲", "up"
    if value < 0:
        return "▼", "down"
    return "▬", "flat"


def pretty_script(key: str) -> str:
    return "Other" if key == "Other" else key[:1].upper() + key[1:]


def bucket_key(iso: str, unit: str) -> str:
    text = str(iso)
    if unit == "hour":
        return text[:13]
    if unit == "month":
        return text[:7]
    return text[:10]


def smooth_segments(points: list[tuple[float, float]]) -> list[tuple]:
    """Monotone cubic through ``points`` (JS ``smoothPath``): a list of
    ``(c1, c2, end)`` control tuples starting from ``points[0]``. Tangents are
    zeroed at extrema so the curve never overshoots a data value."""
    if len(points) < 2:
        return []
    slopes = []
    for index in range(len(points) - 1):
        dx = points[index + 1][0] - points[index][0]
        slopes.append((points[index + 1][1] - points[index][1]) / dx if dx else 0.0)
    tangents = [slopes[0]]
    for index in range(1, len(points) - 1):
        a, b = slopes[index - 1], slopes[index]
        tangents.append(0.0 if a * b <= 0 else (a + b) / 2)
    tangents.append(slopes[-1])
    segments = []
    for index in range(len(points) - 1):
        (x0, y0), (x1, y1) = points[index], points[index + 1]
        hx = (x1 - x0) / 3
        c1 = (x0 + hx, y0 + tangents[index] * hx)
        c2 = (x1 - hx, y1 - tangents[index + 1] * hx)
        segments.append((c1, c2, (x1, y1)))
    return segments


class ReportModel:
    """The report model dict plus every derived reading the views need, memoised
    exactly where the JS memoises (per master / per master|date / per dataset)."""

    def __init__(self, model: dict) -> None:
        self.h = model
        self.order: list[str] = [str(key) for key in model.get("order", [])]
        self.steps: list[dict] = list(model.get("steps", []))
        self.masters: list[dict] = list(model.get("masters", []))
        self.glyph_names: list[str] = list(model.get("glyphNames", []))
        self.categories: list[str] = list(model.get("categories", []))
        self.scripts: list[str] = list(model.get("scripts", []))
        self.none_label: str = model.get("noneLabel") or "None"
        self.colors: dict = model.get("colors") or {}
        self.paths: dict = model.get("paths") or {}
        self.last_edit: dict = model.get("lastEdit") or {}
        self.non_exporting: list[str] = list(model.get("nonExporting") or [])
        self.glyph_total: int = int(model.get("glyphTotal") or 0)
        self.fine_kind: str = model.get("fineKind") or "commit"
        self._normalize_hidden_keys()
        # timeline datasets (JS tlDay / tlCommit + applyGranularity)
        self.tl_day = {
            "trend": model.get("trend") or {},
            "journeys": model.get("journeys") or {},
            "journeyIndex": model.get("journeyIndex") or {},
        }
        self.tl_commit = (
            {
                "trend": model.get("trendCommits") or {},
                "journeys": model.get("journeysCommits") or {},
                "journeyIndex": model.get("journeyIndexCommits") or {},
            }
            if model.get("hasCommits")
            else None
        )
        self.gran = "save" if self.tl_commit else "time"
        self.bucket = "day"
        self.trend: dict = {}
        self.journeys: dict = {}
        self.journey_index: dict = {}
        self.apply_granularity()
        self._counted: dict | None = None
        self._counted_n = 0
        self._counted_done = False
        self._excl: dict = {}
        self._cstats: dict = {}
        self._stepw: dict | None = None
        self._gp: dict = {}
        self._chg: dict = {}
        self._col: dict = {}
        self._wk: dict = {}
        self._nav: list | None = None
        self._nav_key = ""

    # ----- hidden keys / datasets -------------------------------------------------
    def _normalize_hidden_keys(self) -> None:
        in_order = set(self.order)
        for master in self.masters:
            keys = master.get("keys")
            if not keys:
                continue
            for index, key in enumerate(keys):
                if key != NO_COLOR and str(key) not in in_order:
                    keys[index] = NO_COLOR

    def apply_granularity(self) -> None:
        fine = self.tl_commit or self.tl_day
        src = fine if self.gran == "save" else self._bucketed(fine, self.bucket)
        self.trend = src.get("trend") or {}
        self.journeys = src.get("journeys") or {}
        self.journey_index = src.get("journeyIndex") or {}
        self._gp = {}
        self._chg = {}
        self._col = {}
        self._wk = {}
        self._nav = None

    @staticmethod
    def _bucketed(fine: dict, unit: str) -> dict:
        series = (fine.get("trend") or {}).get("series") or []
        last: dict = {}
        for point in series:
            last[bucket_key(point["date"], unit)] = point
        keys = sorted(last)
        bucket_series = [last[key] for key in keys]
        dates = [point["date"] for point in bucket_series]
        return {
            "trend": {
                "series": bucket_series,
                "dates": dates,
                "today": dates[-1] if dates else None,
                "streak": (fine.get("trend") or {}).get("streak"),
            },
            "journeys": fine.get("journeys") or {},
            "journeyIndex": fine.get("journeyIndex") or {},
        }

    def set_granularity(self, gran: str) -> bool:
        if gran == "save" and not self.tl_commit:
            return False
        if gran == self.gran:
            return False
        self.gran = gran
        self.apply_granularity()
        return True

    def set_bucket(self, unit: str) -> bool:
        if unit == self.bucket:
            return False
        self.bucket = unit
        self.gran = "time"
        self.apply_granularity()
        return True

    @property
    def dates(self) -> list[str]:
        return list(self.trend.get("dates") or [])

    @property
    def series(self) -> list[dict]:
        return list(self.trend.get("series") or [])

    def has_trend(self) -> bool:
        return len(self.series) >= 2

    def timeline_lock(self) -> str:
        """Why the Timeline tab is disabled: "" once 3 snapshots exist (the JS gate)."""
        n = len(self.dates)
        if n >= 3:
            return ""
        by_commit = self.gran == "save"
        units = ("saves" if self.fine_kind == "save" else "commits") if by_commit else "days"
        hint = f"Make another {units[:-1]}." if by_commit else "Save again tomorrow."
        return f"Timeline unlocks at 3 {units} of history — {n} so far. {hint}"

    def dataset_key(self) -> str:
        dates = self.dates
        return f"{self.gran}:{self.bucket}:{len(dates)}:{dates[-1] if dates else ''}"

    # ----- non-exporting exclusion --------------------------------------------------
    def counted_set(self) -> dict | None:
        if not self.non_exporting:
            return None
        if not self._counted_done:
            off = set(self.non_exporting)
            self._counted = {name: 1 for name in self.glyph_names if name not in off}
            self._counted_n = len(self._counted)
            self._counted_done = True
        return self._counted

    def is_counted(self, name: str) -> bool:
        counted = self.counted_set()
        return counted is None or name in counted

    def counted_total(self) -> int:
        return self._counted_n if self.counted_set() is not None else self.glyph_total

    def counted_stats(self, master: dict) -> dict:
        cached = self._cstats.get(master["id"])
        if cached:
            return cached
        counted = self.counted_set()
        dist: dict = {}
        none = 0
        for index, key in enumerate(master.get("keys") or []):
            if counted is not None and self.glyph_names[index] not in counted:
                continue
            skey = str(key)
            if key == NO_COLOR or skey not in self.order:
                none += 1
            else:
                dist[skey] = dist.get(skey, 0) + 1
        counts: dict = {}
        run = 0
        for key in reversed(self.order):
            run += dist.get(key, 0)
            counts[key] = run
        stats = {"dist": dist, "counts": counts, "uncolored": none}
        self._cstats[master["id"]] = stats
        return stats

    def exclusive_of(self, master: dict) -> dict:
        cached = self._excl.get(master["id"])
        if cached is not None:
            return cached
        counted = self.counted_set()
        dist: dict = {}
        for index, key in enumerate(master.get("keys") or []):
            if counted is not None and self.glyph_names[index] not in counted:
                continue
            skey = str(key)
            if key != NO_COLOR and skey in self.order:
                dist[skey] = dist.get(skey, 0) + 1
        self._excl[master["id"]] = dist
        return dist

    def count_for(self, master: dict, key) -> int:
        if self.counted_set() is not None:
            stats = self.counted_stats(master)
            return stats["uncolored"] if key == NO_COLOR else stats["counts"].get(str(key), 0)
        if key == NO_COLOR:
            return int(master.get("uncolored") or 0)
        return int((master.get("counts") or {}).get(str(key), 0))

    def uncolored_for(self, master: dict) -> int:
        if self.counted_set() is not None:
            return self.counted_stats(master)["uncolored"]
        return int(master.get("uncolored") or 0)

    def started_of(self, master: dict) -> int:
        return self.counted_total() - self.uncolored_for(master)

    def master_started(self, master: dict) -> bool:
        return self.uncolored_for(master) < self.counted_total()

    def aggregate(self) -> dict:
        grand = self.counted_total() * len(self.masters)
        agg = {key: 0 for key in self.order}
        for master in self.masters:
            for key in self.order:
                agg[key] += self.count_for(master, key)
        return {"grand": grand, "agg": agg}

    def agg_exclusive(self) -> dict:
        dist = {key: 0 for key in self.order}
        none = 0
        counted = self.counted_set()
        for master in self.masters:
            for index, key in enumerate(master.get("keys") or []):
                if counted is not None and self.glyph_names[index] not in counted:
                    continue
                skey = str(key)
                if key == NO_COLOR or skey not in self.order:
                    none += 1
                else:
                    dist[skey] += 1
        return {"dist": dist, "none": none}

    # ----- graded step progress ------------------------------------------------------
    def step_weights(self) -> dict:
        if self._stepw is not None:
            return self._stepw
        used: set = set()
        for master in self.masters:
            for key in master.get("keys") or []:
                if key != NO_COLOR:
                    used.add(str(key))
        steps = [key for key in self.order if key in used]
        count = len(steps)
        weight = {key: (index + 1) / count for index, key in enumerate(steps)}
        self._stepw = {"weight": weight, "N": count, "steps": steps}
        return self._stepw

    def graded_sum(self, master: dict) -> float:
        weight = self.step_weights()["weight"]
        counted = self.counted_set()
        total = 0.0
        for index, key in enumerate(master.get("keys") or []):
            if counted is not None and self.glyph_names[index] not in counted:
                continue
            total += weight.get(str(key), 0.0)
        return total

    def graded_master_pct(self, master: dict) -> int:
        n = self.counted_total() or len(master.get("keys") or []) or 1
        return round(self.graded_sum(master) / n * 100)

    def graded_overall_pct(self) -> int:
        total = 0.0
        denom = 0
        for master in self.masters:
            total += self.graded_sum(master)
            denom += self.counted_total()
        return round(total / denom * 100) if denom else 0

    def graded_pct_at(self, master_id: str, date: str) -> float:
        cache_key = f"{master_id}|{date}"
        if cache_key in self._gp:
            return self._gp[cache_key]
        weight = self.step_weights()["weight"]
        total = self.counted_total() or 1
        snap = self.state_at(master_id, date)
        value = 0.0
        for name, key in snap.items():
            if not self.is_counted(name):
                continue
            value += weight.get(str(key), 0.0)
        result = value / total * 100
        self._gp[cache_key] = result
        return result

    def graded_overall_pct_at(self, date: str) -> int:
        if not self.masters:
            return 0
        total = sum(self.graded_pct_at(master["id"], date) for master in self.masters)
        return round(total / len(self.masters))

    def graded_state_sum(self, state_map: dict) -> float:
        weight = self.step_weights()["weight"]
        return sum(
            weight.get(str(key), 0.0) for name, key in state_map.items() if self.is_counted(name)
        )

    # ----- labels / lookups ------------------------------------------------------------
    def label_for(self, key) -> str:
        if key == NO_COLOR or str(key) == "-1":
            return self.none_label
        for step in self.steps:
            if str(step.get("key")) == str(key):
                return step.get("label", "")
        return f"Color {key}"

    def rank_of(self, key) -> int:
        try:
            return self.order.index(str(key))
        except ValueError:
            return -1

    def master_by_id(self, master_id) -> dict | None:
        for master in self.masters:
            if master["id"] == master_id:
                return master
        return self.masters[0] if self.masters else None

    def master_index(self, master_id) -> int:
        for index, master in enumerate(self.masters):
            if master["id"] == master_id:
                return index
        return -1

    def when_label(self, name: str) -> str:
        days = self.last_edit.get(name)
        if days is None:
            return ""
        return "today" if days == 0 else f"{days}d ago"

    # ----- journey substrate -----------------------------------------------------------
    def journey_of(self, master_id, name: str) -> list:
        return (self.journey_index.get(master_id) or {}).get(name) or []

    def state_at(self, master_id, iso: str) -> dict:
        per_master = self.journey_index.get(master_id)
        out: dict = {}
        if not per_master:
            return out
        for name, events in per_master.items():
            key = None
            for event in events:
                if event[0] <= iso:
                    key = event[1]
                else:
                    break
            if key is not None:
                out[name] = NO_COLOR if (key != NO_COLOR and str(key) not in self.order) else key
        return out

    def scrub_index(self, scrub) -> int:
        dates = self.dates
        if not dates:
            return -1
        index = len(dates) - 1 if scrub is None else int(scrub)
        return max(0, min(len(dates) - 1, index))

    def change_counts(self, master_id) -> list[int]:
        cached = self._chg.get(master_id)
        if cached is not None:
            return cached
        dates = self.dates
        chg = [0] * len(dates)
        per_master = self.journey_index.get(master_id) or {}
        missing = object()
        for events in per_master.values():
            bp, cur, eff, committed = 0, -1, missing, missing
            for event in events:
                while bp < len(dates) and dates[bp] < event[0]:
                    bp += 1
                if bp >= len(dates):
                    break
                if bp != cur:
                    if cur > 0 and eff != committed:
                        chg[cur] += 1
                    if cur != -1:
                        committed = eff
                    cur = bp
                key = event[1]
                eff = NO_COLOR if (key != NO_COLOR and str(key) not in self.order) else key
            if cur > 0 and eff != committed:
                chg[cur] += 1
        self._chg[master_id] = chg
        return chg

    def col_tally(self, master_id, iso: str) -> dict:
        cache_key = f"{master_id}|{iso}"
        cached = self._col.get(cache_key)
        if cached:
            return cached
        by_key = {key: 0 for key in self.order}
        none = 0
        for name, key in self.state_at(master_id, iso).items():
            if not self.is_counted(name):
                continue
            skey = str(key)
            if key == NO_COLOR or skey not in self.order:
                none += 1
            else:
                by_key[skey] += 1
        tally = {"byKey": by_key, "none": none}
        self._col[cache_key] = tally
        return tally

    def diff_counts(self, master_id, iso_a: str, iso_b: str) -> dict:
        before = self.state_at(master_id, iso_a)
        after = self.state_at(master_id, iso_b)
        names = set(before) | set(after)
        advanced = regressed = unchanged = 0
        for name in names:
            was = before.get(name, NO_COLOR)
            now = after.get(name, NO_COLOR)
            if self.rank_of(now) > self.rank_of(was):
                advanced += 1
            elif self.rank_of(now) < self.rank_of(was):
                regressed += 1
            else:
                unchanged += 1
        denom = self.counted_total() or len(names) or 1
        delta = round((self.graded_state_sum(after) - self.graded_state_sum(before)) / denom * 100)
        return {
            "advanced": advanced,
            "regressed": regressed,
            "unchanged": unchanged,
            "deltaPct": delta,
        }

    # ----- overview cards ----------------------------------------------------------------
    def leaderboard_rows(self) -> list[dict]:
        rows = [
            {
                "id": master["id"],
                "name": master["name"],
                "p": self.graded_master_pct(master),
                "any": self.master_started(master),
            }
            for master in self.masters
        ]
        rows.sort(key=lambda row: (-row["p"], row["name"]))
        return rows

    def week_color_moves(self, week_ago: str) -> dict:
        cached = self._wk.get(week_ago)
        if cached is not None:
            return cached
        moves: dict = {}
        for master in self.masters:
            snap = self.state_at(master["id"], week_ago)
            keys = master.get("keys") or []
            for index, name in enumerate(self.glyph_names):
                if not self.is_counted(name):
                    continue
                now_key = keys[index] if index < len(keys) else NO_COLOR
                then_key = snap.get(name, NO_COLOR)
                if (
                    str(now_key) != str(then_key)
                    and now_key != NO_COLOR
                    and str(now_key) in self.order
                ):
                    moves[str(now_key)] = moves.get(str(now_key), 0) + 1
        self._wk[week_ago] = moves
        return moves

    def week_digest(self) -> dict | None:
        dates = self.dates
        if len(dates) < 2:
            return None
        latest = dates[-1]
        week_ago = snap_date(dates, iso_minus_days(latest, 7))
        if week_ago == latest or week_ago is None:
            return None
        now_pct = self.graded_overall_pct()
        delta = now_pct - self.graded_overall_pct_at(week_ago)
        month_ago = snap_date(dates, iso_minus_days(latest, 30))
        month_delta = (
            now_pct - self.graded_overall_pct_at(month_ago)
            if month_ago and month_ago != latest
            else None
        )
        gains = [
            {
                "master": master,
                "d": round(
                    self.graded_master_pct(master) - self.graded_pct_at(master["id"], week_ago)
                ),
            }
            for master in self.masters
        ]
        top_masters = sorted(
            [gain for gain in gains if gain["d"] > 0],
            key=lambda gain: (-gain["d"], gain["master"]["name"]),
        )[:3]
        moves = self.week_color_moves(week_ago)
        move_total = sum(moves.values())
        top_colors = sorted(
            ({"k": int(key), "n": count} for key, count in moves.items()),
            key=lambda item: (-item["n"], item["k"]),
        )[:3]
        return {
            "delta": delta,
            "monthDelta": month_delta,
            "topMasters": top_masters,
            "topColors": top_colors,
            "moveTotal": move_total,
        }

    def recent_feed(self, master_id) -> list[dict]:
        per_master = self.journey_index.get(master_id) or {}
        feed = []
        for name, events in per_master.items():
            if not events:
                continue
            last = events[-1]
            prev = events[-2][1] if len(events) > 1 else last[1]
            feed.append({"name": name, "date": last[0], "was": prev, "nw": last[1]})
        feed.sort(key=lambda item: item["date"], reverse=True)
        return feed

    # ----- coverage --------------------------------------------------------------------
    def cov_rows(self, which: str, master_id=None) -> list[dict]:
        if self.counted_set() is not None:
            return self._cov_rows_counted(which, master_id)
        by = (self.h.get("coverage") or {}).get(which) or {}
        if master_id is not None:
            return list(by.get(master_id) or [])
        merged: dict = {}
        order_keys: list = []
        for master in self.masters:
            for row in by.get(master["id"]) or []:
                agg = merged.get(row["key"])
                if agg is None:
                    agg = merged[row["key"]] = {
                        "key": row["key"],
                        "total": 0,
                        "uncolored": 0,
                        "glyphs": row.get("total") or 0,
                        "dist": {},
                    }
                    order_keys.append(row["key"])
                agg["total"] += row.get("total") or 0
                agg["uncolored"] += row.get("uncolored") or 0
                for key, count in (row.get("dist") or {}).items():
                    agg["dist"][key] = agg["dist"].get(key, 0) + count
        return [merged[key] for key in order_keys]

    def _cov_rows_counted(self, which: str, master_id) -> list[dict]:
        attrs = self.scripts if which == "byScript" else self.categories
        counted = self.counted_set()
        masters = [self.master_by_id(master_id)] if master_id is not None else self.masters
        group_idx: dict = {}
        gkeys: list = []
        for index, name in enumerate(self.glyph_names):
            if counted is not None and name not in counted:
                continue
            group = (attrs[index] if index < len(attrs) else "") or "Other"
            if group not in group_idx:
                group_idx[group] = []
                gkeys.append(group)
            group_idx[group].append(index)
        out = []
        for group in gkeys:
            idxs = group_idx[group]
            total = uncolored = 0
            dist: dict = {}
            for master in masters:
                if master is None:
                    continue
                keys = master.get("keys") or []
                for index in idxs:
                    key = keys[index] if index < len(keys) else NO_COLOR
                    skey = str(key)
                    total += 1
                    if key == NO_COLOR or skey not in self.order:
                        uncolored += 1
                    else:
                        dist[skey] = dist.get(skey, 0) + 1
            out.append(
                {
                    "key": group,
                    "total": total,
                    "uncolored": uncolored,
                    "glyphs": len(idxs),
                    "dist": dist,
                }
            )
        out.sort(key=lambda row: (-row["glyphs"], row["key"]))
        return out

    def script_rows(self, master_id=None) -> list[dict]:
        return [row for row in self.cov_rows("byScript", master_id) if row["key"] != "Other"]

    def script_meta(self, key: str) -> dict:
        return ((self.h.get("coverage") or {}).get("scriptMeta") or {}).get(key) or {}

    def script_glyph_path(self, meta: dict, master_id=None) -> dict | None:
        glyph = meta.get("glyph") if meta else None
        if not glyph:
            return None
        first = self.masters[0]["id"] if self.masters else None
        mid = master_id if master_id is not None else first
        for candidate in (mid, first):
            outline = (self.paths.get(candidate) or {}).get(glyph)
            if outline:
                return outline
        for per_master in self.paths.values():
            if per_master.get(glyph):
                return per_master[glyph]
        return None

    # ----- master panel ------------------------------------------------------------------
    def master_distribution(self, master: dict, scrub) -> dict:
        """Exclusive colour tally for the master panel bar (scrub-aware)."""
        total = self.counted_total()
        dates = self.dates
        scrubbing = scrub is not None and len(dates) > 1
        dist: dict = {}
        none = 0
        if scrubbing:
            date = dates[self.scrub_index(scrub)]
            snap = self.state_at(master["id"], date)
            for name, key in snap.items():
                if not self.is_counted(name):
                    continue
                skey = str(key)
                if key != NO_COLOR and skey in self.order:
                    dist[skey] = dist.get(skey, 0) + 1
            colored = sum(dist.values())
            none = max(0, total - colored)
            started = colored
            head_pct = round(self.graded_pct_at(master["id"], date))
        else:
            counted = self.counted_set()
            for index, key in enumerate(master.get("keys") or []):
                if counted is not None and self.glyph_names[index] not in counted:
                    continue
                skey = str(key)
                if key == NO_COLOR or skey not in self.order:
                    none += 1
                else:
                    dist[skey] = dist.get(skey, 0) + 1
            started = total - self.uncolored_for(master)
            head_pct = self.graded_master_pct(master)
        return {"dist": dist, "none": none, "started": started, "headPct": head_pct, "total": total}

    def heatmap_items(self, master: dict, scrub) -> tuple[list, dict]:
        """[(name, key, index)] at the picked moment + the before/after changeset."""
        dates = self.dates
        scrub_snap = prev_snap = None
        if scrub is not None and dates:
            index = self.scrub_index(scrub)
            scrub_snap = self.state_at(master["id"], dates[index])
            if index > 0:
                prev_snap = self.state_at(master["id"], dates[index - 1])
        keys = master.get("keys") or []
        items = []
        for index, name in enumerate(self.glyph_names):
            if scrub_snap is not None:
                key = scrub_snap.get(name, NO_COLOR)
            else:
                key = keys[index] if index < len(keys) else NO_COLOR
            items.append((name, key, index))
        changes: dict = {}
        if scrub_snap is not None:
            if prev_snap is not None:
                for name in set(prev_snap) | set(scrub_snap):
                    before = prev_snap.get(name, NO_COLOR)
                    after = scrub_snap.get(name, NO_COLOR)
                    if str(before) != str(after):
                        changes[name] = [before]
        else:
            changes = dict((self.h.get("changes") or {}).get(master["id"]) or {})
            if not changes:
                for name, events in (self.journey_index.get(master["id"]) or {}).items():
                    if events and len(events) >= 2:
                        prev_key, now_key = events[-2][1], events[-1][1]
                        if prev_key != now_key:
                            changes[name] = [prev_key]
        return items, changes

    def group_by_category(self, items: list) -> list[tuple[str, list]]:
        groups: dict = {}
        seen: list = []
        for item in items:
            cat = (self.categories[item[2]] if item[2] < len(self.categories) else "") or "Other"
            if cat not in groups:
                groups[cat] = []
                seen.append(cat)
            groups[cat].append(item)

        def rank(cat: str) -> int:
            return CAT_ORDER.index(cat) if cat in CAT_ORDER else len(CAT_ORDER)

        seen.sort(key=rank)
        return [(cat, groups[cat]) for cat in seen]

    def group_by_color(self, items: list) -> list[tuple[int, list]]:
        by_key: dict = {}
        for item in items:
            key = item[1]
            kk = "none" if (key == NO_COLOR or str(key) not in self.order) else str(key)
            by_key.setdefault(kk, []).append(item)
        out = []
        for kk in [*self.order, "none"]:
            if by_key.get(kk):
                out.append((NO_COLOR if kk == "none" else int(kk), by_key[kk]))
        return out

    def version_indices(self, master_id) -> list[int]:
        dates = self.dates
        if master_id is None:
            return list(range(len(dates)))
        chg = self.change_counts(master_id)
        return [0] + [index for index in range(1, len(dates)) if chg[index]]

    # ----- timeline ------------------------------------------------------------------------
    def view_bounds(self, view_lo, view_hi) -> tuple[int, int]:
        n = len(self.series)
        if n == 0:
            return 0, -1
        lo = 0 if view_lo is None else int(view_lo)
        hi = n - 1 if view_hi is None else int(view_hi)
        lo = max(0, min(lo, n - 1))
        hi = max(0, min(hi, n - 1))
        if lo > hi:
            lo, hi = hi, lo
        if hi - lo < 1:
            if hi < n - 1:
                hi = lo + 1
            else:
                lo = hi - 1
        return lo, hi

    def span_bounds(self, span: str) -> tuple[int | None, int | None]:
        series = self.series
        if span == "all" or not series:
            return None, None
        days = next((entry[2] for entry in TL_SPANS if entry[0] == span), 0)
        last = cfd_date(series[-1]["date"])
        if last is None:
            return None, None
        cut = last - timedelta(days=days)
        lo = 0
        for index, point in enumerate(series):
            when = cfd_date(point["date"])
            if when is not None and when >= cut:
                lo = index
                break
        return lo, len(series) - 1

    def pct_matrix(self, dates: list[str]) -> list[list[float]]:
        return [
            [self.graded_pct_at(master["id"], date) for date in dates] for master in self.masters
        ]

    def nav_overall_series(self) -> list[float]:
        key = self.dataset_key()
        if self._nav is not None and self._nav_key == key:
            return self._nav
        weight = self.step_weights()["weight"]
        denom = (len(self.masters) * (self.counted_total() or 1)) or 1
        out = []
        for point in self.series:
            total = 0.0
            for master in self.masters:
                for name, k in self.state_at(master["id"], point["date"]).items():
                    if self.is_counted(name):
                        total += weight.get(str(k), 0.0)
            out.append(total / denom * 100)
        self._nav = out
        self._nav_key = key
        return out

    def lane_graded_pct(self, names: list[str], iso: str, master_id) -> int:
        if master_id is not None:
            return self._lane_pct_one(master_id, names, iso)
        if not self.masters:
            return 0
        total = sum(self._lane_pct_one(master["id"], names, iso) for master in self.masters)
        return round(total / len(self.masters))

    def _lane_pct_one(self, master_id, names: list[str], iso: str) -> int:
        state = self.state_at(master_id, iso)
        weight = self.step_weights()["weight"]
        total = 0.0
        n = 0
        for name in names:
            if not self.is_counted(name):
                continue
            n += 1
            total += weight.get(str(state.get(name)), 0.0)
        return round(total / n * 100) if n else 0

    def lanes(self, which: str, master_id, scrub) -> list[dict]:
        dates = self.dates
        if not dates:
            return []
        attrs = self.scripts if which == "script" else self.categories
        groups: dict = {}
        for index, name in enumerate(self.glyph_names):
            if not self.is_counted(name):
                continue
            group = (attrs[index] if index < len(attrs) else "") or "Other"
            groups.setdefault(group, []).append(name)
        if which == "script":
            keys = [key for key in groups if key != "Other"]
            if not keys or (len(keys) == 1 and keys[0].lower() == "latin"):
                return []
        else:
            keys = list(groups)
        index = self.scrub_index(scrub)
        scrub_iso = dates[index] if 0 <= index < len(dates) else dates[-1]
        prev_iso = dates[index - 1] if index > 0 else None
        upto = dates[: index + 1] if index >= 0 else list(dates)
        lanes = []
        for key in keys:
            names = groups[key]
            values = [self.lane_graded_pct(names, date, master_id) for date in upto]
            cur = self.lane_graded_pct(names, scrub_iso, master_id)
            delta = cur - self.lane_graded_pct(names, prev_iso, master_id) if prev_iso else 0
            lanes.append(
                {
                    "key": key,
                    "count": len(names),
                    "values": values,
                    "cur": cur,
                    "delta": delta,
                    "prev": prev_iso,
                }
            )
        if which == "script":
            lanes.sort(key=lambda lane: (lane["cur"], lane["key"]))
        else:

            def rank(lane: dict) -> tuple:
                cat = lane["key"]
                return (CAT_ORDER.index(cat) if cat in CAT_ORDER else len(CAT_ORDER), cat)

            lanes.sort(key=rank)
        return lanes

    # ----- calendar ------------------------------------------------------------------------
    def cal_activity(self, master_id) -> dict:
        dates = self.dates
        chg = self.change_counts(master_id)
        return {date: chg[index] for index, date in enumerate(dates)}

    def cal_activity_scoped(self, master_id) -> dict:
        if master_id is not None:
            return self.cal_activity(master_id)
        total = {date: 0 for date in self.dates}
        for master in self.masters:
            for date, count in self.cal_activity(master["id"]).items():
                total[date] = total.get(date, 0) + count
        return total

    @staticmethod
    def cal_level(counts: dict):
        max_count = max([1, *counts.values()]) if counts else 1

        def level(count: int) -> int:
            if not count:
                return 1
            ratio = count / max_count
            return 4 if ratio > 0.66 else 3 if ratio > 0.33 else 2

        return level

    # ----- outline changes / touched after done -------------------------------------------
    def outline_changes(self, master_id) -> list[tuple[str, list]]:
        changes = self.h.get("outlineChanges") or {}
        out = []
        for date in sorted(changes, reverse=True):
            items = [
                change
                for change in (changes.get(date) or [])
                if master_id is None or change.get("master") == master_id
            ]
            if items:
                out.append((date, items))
        return out

    def touched_after_done(self, master_id) -> list[dict]:
        changes = self.h.get("outlineChanges") or {}
        index = self.journey_index
        if not self.order:
            return []
        final_key = self.order[-1]
        rows = []
        for date, items in changes.items():
            for change in items or []:
                if master_id is not None and change.get("master") != master_id:
                    continue
                events = (index.get(change.get("master")) or {}).get(change.get("glyph")) or []
                done_ts = None
                for event in events:
                    stamp = str(event[0])
                    if stamp[:10] >= date:
                        break
                    if str(event[1]) == final_key:
                        if done_ts is None:
                            done_ts = stamp
                    else:
                        done_ts = None
                if done_ts is None:
                    continue
                a, b = cfd_date(date), cfd_date(done_ts[:10])
                if a is None or b is None:
                    continue
                gap = (a - b).total_seconds()
                if gap <= 0:
                    continue
                rows.append(
                    {
                        "glyph": change.get("glyph"),
                        "master": change.get("master"),
                        "change": change,
                        "date": date,
                        "doneDate": done_ts[:10],
                        "gapDays": round(gap / 86400),
                    }
                )
        rows.sort(key=lambda row: (-row["gapDays"], row["glyph"]))
        return rows
