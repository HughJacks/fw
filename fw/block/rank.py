"""Ranking pericopes, derived, never stored: a memory read from visits (the garden), and the graph of what points
at what (hubs and authorities, what sits alongside, where you went next).

Memory is FSRS-style: each visit a review graded by its strongest flag; stability S (days) grows most after the
block had started to fade; retrievability R = (1 + t/(9S))^-1, t days after the last visit."""

from __future__ import annotations

from fw.block.case import image_of, links, paraphrases, quoted
from fw.block.text import iso_minute
from fw.block.view import home_of
from fw.block.visits import last_visit, visits

RECENT_DAYS = 7      # active this recently: "recent"
FADED_AT = 0.9       # R under this: dropped out of memory
RESURFACE = 12       # at most this many resurfacing
TOP = 10             # the first: recent and resurfacing in turn
GRADE = {"w": 1.0, "c": 0.7, "q": 0.6, "o": 0.4}
S_FIRST = 1.0        # stability (days) after the first visit or the writing
HITS_JUMP = 0.15     # randomized HITS's chance of a jump anywhere, so separate clusters don't collapse onto one
HITS_ROUNDS = 100
NEXT_WITHIN = 30     # minutes: a visit begun this soon after one to `here` is where you went next


def grade(flags: str) -> float:
    return max((GRADE[f] for f in flags if f in GRADE), default=GRADE["o"])


def retrievability(stability: float, days: float) -> float:
    return (1 + max(days, 0) / (9 * stability)) ** -1


def memory(b: dict | None, now_min: int) -> tuple[float, float]:
    """(stability in days, retrievability now) of `b`, replayed from its visits (`created` if it has none)."""
    reviews = [(m, f) for m, f in visits(b)]
    first = ((b or {}).get("visits") or {}).get("first")
    if first is not None and (not reviews or first < reviews[0][0]):
        reviews.insert(0, (first, "o"))
    if not reviews:
        made = iso_minute((b or {}).get("created"))
        reviews = [(made, "w")] if made is not None else []
    if not reviews:
        return S_FIRST, 0.0
    s, last = S_FIRST, reviews[0][0]
    for m, f in reviews[1:]:
        r = retrievability(s, (m - last) / 1440)
        s *= 1 + 26.9 * s ** -0.15 * (2.718281828 ** (1 - r) - 1) * grade(f)  # e^1.5·(11−5) ≈ 26.9
        last = m
    return s, retrievability(s, (now_min - last) / 1440)


def last_active(b: dict | None) -> int | None:
    """The latest minute `b` was visited or changed."""
    return max((t for t in (last_visit(b), iso_minute((b or {}).get("updated"))) if t is not None), default=None)


def last_action(b: dict | None) -> tuple[str, int | None]:
    """("written" | "read" | "opened" | "seen in a quote" | "edited" | "made", minute)."""
    rs, upd = visits(b), iso_minute((b or {}).get("updated"))
    if rs and (upd is None or rs[-1][0] >= upd - 10):
        f = rs[-1][1]
        return ("written" if "w" in f else "read" if "c" in f else "seen in a quote" if "q" in f else "opened"), rs[-1][0]
    if upd is not None and upd > (iso_minute((b or {}).get("created")) or upd) + 1:
        return "edited", upd
    return "made", iso_minute((b or {}).get("created"))


def garden(blocks: dict, refs: list, now_min: int) -> list[tuple[str, str]]:
    """`refs` in the garden's order, each with why: "recent", "resurfacing" (faded, the most rehearsed first) or "".
    The first TOP take the two in turn, then the rest of each, then the others by last activity."""
    b = lambda i: blocks[i].get("block", blocks[i])
    act = {i: last_active(b(i)) or 0 for i in refs}
    recent = sorted((i for i in refs if now_min - act[i] <= RECENT_DAYS * 1440), key=lambda i: -act[i])
    mem = {i: memory(b(i), now_min) for i in refs if i not in set(recent)}
    total = lambda i: (b(i).get("visits") or {}).get("total") or 0
    faded = sorted((i for i, (s, r) in mem.items() if r < FADED_AT),
                   key=lambda i: -(1 - mem[i][1]) * (1 + total(i)) * mem[i][0] ** 0.5)[:RESURFACE]
    rest = sorted((i for i in refs if i not in set(recent) | set(faded)), key=lambda i: -act[i])
    r, f = [(i, "recent") for i in recent], [(i, "resurfacing") for i in faded]
    top = [x for pair in zip(r, f) for x in pair] + r[len(f):] + f[len(r):]
    return top[:TOP] + [x for x in r + f if x not in top[:TOP]] + [(i, "") for i in rest]


def pericope_edges(blocks: dict, refs: list) -> set:
    """(a, b): a block in pericope `a` quotes, links to or paraphrases one in pericope `b`, a != b (a quote of a
    picture only shows it: not pointing)."""
    tops, out = set(refs), set()
    for i, b in blocks.items():
        q = quoted(b)
        targets = ([q[0]] if q else []) + [x["to"] for x in links(b)] + ([paraphrases(b)] if paraphrases(b) else [])
        if not targets:
            continue
        a = home_of(blocks, i)[0]
        for t in targets:
            if t not in blocks or (q and t == q[0] and image_of(blocks[t])):
                continue
            h = t if t in tops else home_of(blocks, t)[0]
            if a in tops and h in tops and a != h:
                out.add((a, h))
    return out


def hits(refs: list, edges: set) -> tuple[dict, dict]:
    """Randomized HITS (Ng, Zheng & Jordan 2001) over `edges`: ({ref: hub}, {ref: authority}), each averaging 1.
    A hub points at good authorities (where to start); an authority is pointed at by good hubs."""
    n = len(refs)
    if not n:
        return {}, {}
    outd, ind = {}, {}
    for a, b in edges:
        outd[a], ind[b] = outd.get(a, 0) + 1, ind.get(b, 0) + 1
    def step(src, deg, forward):
        new = {r: HITS_JUMP / n for r in refs}
        for a, b in edges:
            fro, to = (a, b) if forward else (b, a)
            new[to] += (1 - HITS_JUMP) * src[fro] / deg[fro]
        total = sum(new.values())
        return {r: v / total for r, v in new.items()}
    hub = auth = {r: 1 / n for r in refs}
    for _ in range(HITS_ROUNDS):
        auth = step(hub, outd, True)
        hub = step(auth, ind, False)
    return {r: v * n for r, v in hub.items()}, {r: v * n for r, v in auth.items()}


def alongside(edges: set, here: str) -> list[tuple[str, int]]:
    """The pericopes sitting with `here`, with their ties, most first: pointed at by one that points at `here`
    (co-citation), or pointing at one `here` points at (coupling); not those tied to it directly."""
    out_of, into = {}, {}
    for a, b in edges:
        out_of.setdefault(a, set()).add(b)
        into.setdefault(b, set()).add(a)
    direct = out_of.get(here, set()) | into.get(here, set()) | {here}
    ties = {}
    for o in [o for c in into.get(here, set()) for o in out_of.get(c, set()) - direct] + \
             [o for t in out_of.get(here, set()) for o in into.get(t, set()) - direct]:
        ties[o] = ties.get(o, 0) + 1
    return sorted(ties.items(), key=lambda x: (-x[1], x[0]))


def visited_next(blocks: dict, refs: list, here: str) -> list[tuple[str, int]]:
    """Where you went right after `here`: per visit to it, the pericope(s) whose visit began next, within
    NEXT_WITHIN minutes; with how many visits each followed, most first, then the latest."""
    theirs = {r: [m for m, _ in visits(blocks.get(r))] for r in refs if r != here}
    count, last = {}, {}
    for m, _ in visits(blocks.get(here)):
        after = {r: min((v for v in vs if m < v <= m + NEXT_WITHIN), default=None) for r, vs in theirs.items()}
        soonest = min((v for v in after.values() if v is not None), default=None)
        for r, v in after.items():
            if v is not None and v == soonest:
                count[r] = count.get(r, 0) + 1
                last[r] = max(last.get(r, 0), v)
    return [(r, count[r]) for r in sorted(count, key=lambda r: (-count[r], -last[r]))]
