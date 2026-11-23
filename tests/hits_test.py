# where to start: randomized HITS over the pericopes' quotes, links and paraphrases (fw_block.pericope_edges, hits),
# and home's order (fw_search.home_order): what's alive for you fused with the hubs, no weights
import os, sys
sys.path.insert(0, "."); sys.path.insert(0, "dev")
import fwtest as F
from fwtest import check, same
import fw_block as B
import fw_search as Q

NOW = 29_920_000   # minutes since the epoch (mid-Nov 2026)
def p(i, kids): return {"id": i, "entry": True, "content": kids, "created": "2026-09-01T10:00:00-04:00"}
def t(i, text, **kw): return {"id": i, "content": text, **kw}
def q(i, target): return {"id": i, "content": {"quote": target}}
def pic(i): return {"id": i, "entry": True, "content": {"image": "ab.png"}, "created": "2026-09-01T10:00:00-04:00"}

# H points at A (a quote), B (a link), C (a paraphrase of a block inside C); A points at B; P quotes only a picture
blocks = {b["id"]: b for b in [
    p("H", ["h1", "h2", "h3"]), q("h1", "A"), t("h2", "see b", links=[{"to": "B", "at": [4, 5]}]), {"id": "h3", "content": {"paraphrase": "c1", "text": "in my words"}},
    p("A", ["a1"]), t("a1", "a", links=[{"to": "B", "at": [0, 1]}]),
    p("B", ["b1"]), t("b1", "b"),
    p("C", ["c1"]), t("c1", "c"),
    p("P", ["p1"]), q("p1", "X"), pic("X"),
    p("L", ["l1"]), t("l1", "alone"),
]}
refs = ["H", "A", "B", "C", "P", "X", "L"]
edges = B.pericope_edges(blocks, refs)
same("edges: a quote, a link, a paraphrase (to the pericope holding it); not a quoted picture; none to itself",
     sorted(edges), [("A", "B"), ("H", "A"), ("H", "B"), ("H", "C")])
hub, auth = B.hits(refs, edges)
check("scaled: the average is 1", abs(sum(hub.values()) / len(refs) - 1) < 1e-9 and abs(sum(auth.values()) / len(refs) - 1) < 1e-9, (hub, auth))
same("the best hub points at the most", max(refs, key=hub.get), "H")
same("the best authority is pointed at by the hubs", max(refs, key=auth.get), "B")
check("nothing pointing: below average", hub["L"] < 1 and hub["P"] < 1 and hub["B"] < 1, hub)
check("no pericopes: nothing", B.hits([], set()) == ({}, {}))

# two clusters apart: plain HITS would give one of them everything; randomized keeps both
two = {b["id"]: b for b in [p("H1", ["x1", "x2"]), q("x1", "T1"), q("x2", "T2"), p("T1", []), p("T2", []),
                            p("H2", ["y1"]), q("y1", "T3"), p("T3", [])]}
h2, _ = B.hits(list(two), B.pericope_edges(two, list(two)))
check("two clusters apart: both hubs above average", h2["H1"] > 1 and h2["H2"] > 1, h2)

# home's order: the hubs and what's alive take turns, one in both first, then the rest by last activity
order = Q.home_order(blocks, refs, NOW)
same("home: every pericope once", sorted(order), sorted(refs))
same("  nothing alive (no visits, made long ago): the hub first", order[0], "H")
# where to go from a pericope: alongside it in the structure, where you went next, all fused (fw_search.exits)
same("alongside A: C (H points at both); not H or B, tied to A directly",
     B.alongside(edges, "A"), [("C", 1)])
same("alongside C: A (H points at both); B too (H points at both)", B.alongside(edges, "C"), [("A", 1), ("B", 1)])
def at(i, *ms): blocks[i]["visits"] = {"total": len(ms), "first": ms[0], "recent": [[m, "oc"] for m in ms]}
at("A", NOW - 100, NOW - 50); at("B", NOW - 90, NOW - 45); at("C", NOW - 80); at("L", NOW - 10)
same("next from A: only the visit that came right after (B both times; C later, not next)", B.visited_next(blocks, refs, "A"), [("B", 2)])
same("  nothing within half an hour: nothing", B.visited_next(blocks, refs, "L"), [])
ex = Q.exits(blocks, refs, "C", NOW)[0]
check("exits from C: what points at it (H), alongside it (A, B); not itself", "H" in ex and "A" in ex and "B" in ex and "C" not in ex, ex)
check("exits from H: not what it already points at (on its page)", not set(sum(Q.exits(blocks, refs, "H", NOW), [])) & {"A", "B", "C"}, Q.exits(blocks, refs, "H", NOW))
same("  the mini's nearest blocks count for their pericope", Q.exits(blocks, refs, "L", NOW, meaning=["c1"])[0][:1], ["C"])
related, filled = Q.exits(blocks, refs, "L", NOW)
same("  never empty: short, filled from home's order, said apart (L: nothing points at it, no visits after it)", (related, len(filled)), ([], min(Q.EXITS, len(refs) - 1)))
F.report("HITS")
