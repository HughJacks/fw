"""Visits: stretches of attention on a block, never an edit (not `updated`, words, content_hash or undo).

On disk `visits` is {"total": n, "first": minute, "recent": [[minute, flags], …]}: the last VISITS_KEPT, oldest
first, each the minute it began (since the epoch) and what happened (FLAGS: o opened, c the cursor stayed,
w written in, q through a quote)."""

from __future__ import annotations

VISIT_GAP = 600      # seconds without attention that end a visit
VISIT_DWELL = 3      # seconds the cursor stays before passing through counts
VISITS_KEPT = 10     # visits kept per block (the total and the first go on counting)
FLAGS = "ocwq"


def visits(b: dict | None) -> list:
    """A block's recent visits, [[minute, flags], …], oldest first."""
    return [list(r) for r in ((b or {}).get("visits") or {}).get("recent", [])]


def last_visit(b: dict | None) -> int | None:
    """The minute its latest visit began."""
    rs = visits(b)
    return rs[-1][0] if rs else None


def flags_union(a: str, b: str) -> str:
    return "".join(f for f in FLAGS if f in a or f in b)


def add_visits(v: dict | None, records: dict) -> dict:
    """Visits `v` with `records` ({minute: flags}) merged in: one in a minute already there joins it, a new one
    counts. Keeps the last VISITS_KEPT."""
    recent = {m: f for m, f in (v or {}).get("recent", [])}
    total, first = (v or {}).get("total", 0), (v or {}).get("first")
    for m, f in records.items():
        m = int(m)
        total += m not in recent
        recent[m] = flags_union(recent.get(m, ""), f)
        first = m if first is None else min(first, m)
    rs = sorted(recent.items())[-VISITS_KEPT:]
    return {"total": max(total, len(rs)), "first": first, "recent": [[m, f] for m, f in rs]}


def merge_visits(a: dict | None, b: dict | None, base: dict | None = None) -> dict | None:
    """Two copies of a block's visits made one: the union; the total counts what each added since `base`, else the
    larger. None if neither has any."""
    if not a and not b:
        return None
    out = add_visits(a, {m: f for m, f in (b or {}).get("recent", [])})
    ta, tb, t0 = (x.get("total", 0) if x else 0 for x in (a, b, base))
    out["total"] = max(ta + tb - t0 if base else max(ta, tb), len(out["recent"]))
    firsts = [x["first"] for x in (a, b) if x and x.get("first") is not None]
    out["first"] = min(firsts) if firsts else out["first"]
    return out


def attend(live: dict, ids, flags: str, at: float) -> tuple[dict, dict]:
    """Attention on `ids` at `at` (seconds): `live` ({id: (minute begun, last attention)}) carries on, or a visit
    begins after VISIT_GAP. Returns (the new `live`, {id: (minute begun, flags)} to record)."""
    live, out = dict(live), {}
    for i in ids:
        start, last = live.get(i, (None, None))
        if start is None or at - last > VISIT_GAP:
            start = int(at // 60)
        live[i] = (start, max(at, last or at))
        out[i] = (start, flags)
    return live, out


def note_visits(pending: dict, records: dict) -> dict:
    """Visits waiting to be written, {id: {minute: flags}}, with `records` (from attend) added."""
    out = {i: dict(r) for i, r in pending.items()}
    for i, (m, f) in records.items():
        out.setdefault(i, {})[m] = flags_union(out.get(i, {}).get(m, ""), f)
    return out


def ended(live: dict, at: float) -> set:
    """The visits under way that have ended by `at`."""
    return {i for i, (_, last) in live.items() if at - last > VISIT_GAP}
