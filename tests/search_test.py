# suggesting and searching: randomized HITS over the pericopes' quotes, links and paraphrases (block.pericope_edges,
# hits); home's order and where to go from a pericope (search.home_order, exits), no weights; the search list over
# blocks (search.Search: matches under where they live, paraphrase families, the places quoting a match, the other machine's
# answer by meaning fused in); asking a meaning service (meaning.fetch)
import http.server, json, os, sys, threading, urllib.parse
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("search")
from fw import block as B, search as Q, meaning as FM

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
# where to go from a pericope: alongside it in the structure, where you went next, all fused (search.exits)
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
same("  the search service's nearest blocks count for their pericope", Q.exits(blocks, refs, "L", NOW, meaning=["c1"])[0][:1], ["C"])
related, filled = Q.exits(blocks, refs, "L", NOW)
same("  never empty: short, filled from home's order, said apart (L: nothing points at it, no visits after it)", (related, len(filled)), ([], min(Q.EXITS, len(refs) - 1)))

# --- the search list over blocks
NOTES, N1, N2, N3 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002", "20261001T100000-a003"
SIDE, S1, QB = "20261002T100000-b000", "20261002T100000-b001", "20261002T100000-b002"
PARA, P1, LATER, L1 = "20261003T100000-c000", "20261003T100000-c001", "20261004T100000-d000", "20261004T100000-d001"
F.store(blk(NOTES, [N1, N2, N3], "notes", entry=True), blk(N1, "first idea"), blk(N2, "the aura of the room"), blk(N3, "x"),
        blk(SIDE, [S1, QB], "sidebar", entry=True), blk(S1, "intro words"), blk(QB, {"quote": N2}),
        blk(PARA, [P1], "para", entry=True), blk(P1, {"paraphrase": N2, "text": "a glow in the room"}),
        blk(LATER, [L1], "later", entry=True), blk(L1, {"paraphrase": P1, "text": "the room hums"}))
b = F.blocks()
same("families: paraphrases joined, both ways, transitively", S.families(b).get(L1), [N2, P1, L1])
same("  a block in none has no family", S.families(b).get(N1), None)
lib = S.build_library(S.load_data())
refs = sorted((r for r, e in lib.items() if e["entry"]), reverse=True)
p = Q.Search(lib, refs, inside=Q.blocks_inside(lib, refs))
same("nothing typed: pericopes only", sorted(r[0] for r in p.rows()), sorted(refs))
p.query = "aura"
rows = [r[1] for r in p.rows()]
same("typed: a matching block under where it lives, its paraphrase family under it, the places quoting it below",
     rows, ["notes", "  · the aura of the room", "    ≈ a glow in the room", "    ≈ the room hums", "  “the aura of the room” quoted in sidebar"])
same("  a place's row stands for what it quotes", p.source(p.rows()[-1][0]), N2)
p.query = "glow"
same("a match on another member: the same family, it first", [r[1] for r in p.rows()][:3], ["para", "  · a glow in the room", "    ≈ the aura of the room"])

# --- by meaning: the search service's nearest blocks, fused in by rank
same("fuse: by reciprocal rank, something in both lists first", Q.fuse(["a", "b", "c"], ["c", "x"]), ["c", "a", "b", "x"])
same("ids_of: the answer's block ids, in order, once each", FM.ids_of({"results": [["a", 0.9], ["b", 0.8], ["a", 0.7]]}), ["a", "b"])
p = Q.Search(lib, refs, inside=Q.blocks_inside(lib, refs))
p.query = "intro"
before = [r[1] for r in p.rows()]
p.meaning = ("intro", [L1])
rows = [r[1] for r in p.rows()]
check("with the search service's answer: a block found by meaning under its pericope, said so", "  · the room hums  (by meaning)" in rows and "later" in rows, rows)
p.meaning = ("other", [L1])
same("  an answer to another query isn't used", [r[1] for r in p.rows()], before)
asked = []
class Service(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        asked.append(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)["q"][0])
        body = json.dumps({"model": "fake", "results": [[N2, 0.71], [L1, 0.69]]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
server = http.server.HTTPServer(("127.0.0.1", 0), Service)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_address[1]}"
same("fetch: the ids of the answer", FM.fetch(base, "sea"), [N2, L1])
same("  asked with the query", asked, ["sea"])
try: FM.fetch("http://127.0.0.1:9", "x"); died = False
except OSError: died = True
check("  no service: an OSError", died)
server.shutdown()
F.report()
