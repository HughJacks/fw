# visits (schema v15): a block's last 10 visits, its total and its first, kept by the editor, never an edit.
# The clock is a file ($FW_CLOCK) the test moves on, so nothing sleeps.
import copy, json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, QUIT as Q, UNDO as Z, UP, DOWN, ESC
S = F.use_store("t/visits.json", clean=True)
import fw_migrate as M
CLOCK = os.path.abspath("t/clock")
T0 = 1794000000.0                     # (Nov 2026)
M0 = int(T0 // 60)
ENV = {"FW_CLOCK": CLOCK}
def at(t): open(CLOCK, "w").write(str(t))
HOST, CH, QH, CH2 = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002", "20261001T100000-b003"
SRC, CS = "20261001T100000-5a00", "20261001T100000-5a01"
NEST, K, KC, KD, KE = ("20261001T100000-c000", "20261001T100000-c001", "20261001T100000-c002", "20261001T100000-c003",
                       "20261001T100000-c004")
OLD = "2026-10-01T10:00:00-04:00"
def fresh():
    F.write_store([blk(SRC, [CS], "src"), blk(CS, "source words"),
                   blk(HOST, [CH, QH, CH2], "host"), blk(CH, "host first"), blk(QH, {"quote": SRC}), blk(CH2, "host last"),
                   blk(NEST, [K, KD], "nest"), blk(K, [KE, KC]), blk(KE, "also inside"), blk(KC, "deep inside"), blk(KD, "after")],
                  [SRC, HOST, NEST])
    S.cmd_migrate(None)
    at(T0)
def B(): return S.index(S.load_data())
def V(i): return B()[i].get("visits")
def recent(i): return (V(i) or {}).get("recent", [])
def tick(t, n=2):
    """Wait for `n` more idle ticks (each looks at the clock)."""
    w = t.sync[1]; t.until(lambda: t.sync[1] >= w + n)
def leave(t): t.key(Q); t.key(ESC); t.done()

# --- the stored shape, pure
v = S.add_visits(None, {M0: "o"})
same("a first visit: total 1, first, recent [[minute, flags]]", v, {"total": 1, "first": M0, "recent": [[M0, "o"]]})
v = S.add_visits(v, {M0: "cw"})
same("  the same visit again (same minute): flags joined, not counted again", v, {"total": 1, "first": M0, "recent": [[M0, "ocw"]]})
v = S.add_visits(v, {M0 + 20 + n * 15: "c" for n in range(12)})
check("capped at 10, oldest first; the total and the first go on counting",
      len(v["recent"]) == 10 and v["total"] == 13 and v["first"] == M0 and v["recent"][-1][0] == M0 + 20 + 11 * 15
      and v["recent"] == sorted(v["recent"]), v)
same("fw_block.visits gives a block's visits, for ranking later", S.visits({"visits": v})[-1], [M0 + 185, "c"])
check("  none for a block never visited", S.visits({}) == [] and S.last_visit({}) is None)
live, seen = S.attend({}, ["x"], "c", T0)
live, seen2 = S.attend(live, ["x"], "c", T0 + 599)
check("attention within 10 minutes carries the visit on", seen["x"][0] == seen2["x"][0] == M0)
live, seen3 = S.attend(live, ["x"], "c", T0 + 599 + 601)
check("  after 10 minutes without, a new one begins", seen3["x"][0] == int((T0 + 1200) // 60) and S.ended(live, T0 + 1200 + 601) == {"x"})
a = {"total": 5, "first": M0, "recent": [[M0, "o"], [M0 + 30, "c"]]}
b = {"total": 6, "first": M0, "recent": [[M0, "oc"], [M0 + 50, "w"]]}
m = S.merge_visits(a, b, base={"total": 4, "first": M0, "recent": [[M0, "o"]]})
same("merging two copies (a sync): a union, each side's new visits counted",
     m, {"total": 7, "first": M0, "recent": [[M0, "oc"], [M0 + 30, "c"], [M0 + 50, "w"]]})

# --- migration v14 → v15
fresh()
d = json.load(open(os.environ["FW_DATA"]))
check("the store is v15 (or later)", d["schemaVersion"] == M.SCHEMA_VERSION >= 15, d["schemaVersion"])
v14 = {**d, "schemaVersion": 14}
up = M.upgrade(copy.deepcopy(v14))
check("v14 → v15: marked to be saved, the blocks as they were (no visits yet)",
      up["schemaVersion"] == M.SCHEMA_VERSION and up.get("upgraded") and up["blocks"] == d["blocks"] and not any("visits" in b for b in up["blocks"]))
json.dump(v14, open(os.environ["FW_DATA"], "w")); S.cmd_migrate(None)
d2 = json.load(open(os.environ["FW_DATA"]))
check("  migrate saves it: current, same blocks", d2["schemaVersion"] == M.SCHEMA_VERSION and len(d2["blocks"]) == len(d["blocks"]))
spec = S.load_schema()["properties"]["visits"]
check("the schema describes it, readOnly", spec["readOnly"] is True and set(spec["properties"]) == {"total", "first", "recent"})
bad = S.validate({"total": 1, "first": M0, "recent": [[M0, "x"]]}, spec)
check("  and checks it (flags are o, c, w, q)", bad, bad)

# --- opening counts at once; a brief pass doesn't
fresh()
f = F.fw("host", env=ENV)
f.key(UP, UP, UP, UP, DOWN, DOWN)     # through the blocks, quickly (the clock doesn't move)
check("before it's written: nothing in the store yet", V(HOST) is None)
leave(f)
same("open → an `o` visit on the pericope", V(HOST), {"total": 1, "first": M0, "recent": [[M0, "o"]]})
check("  a pass through blocks (under 3 s) counts for none of them", not any(V(i) for i in (CH, CH2, CS, SRC, QH)),
      [(i, V(i)) for i in (CH, CH2, CS, SRC)])
check("  not an edit: `updated` and words as they were", B()[HOST]["updated"] == OLD and B()[HOST]["words"] == 6, (B()[HOST]["updated"], B()[HOST]["words"]))

# --- the cursor staying a few seconds: `c`, carried up
fresh()
f = F.fw("host", env=ENV)              # at the end of "host last"
at(T0 + 2); tick(f)
check("2 s in a block: not yet", True)
at(T0 + 4); tick(f)
leave(f)
same("3 s or more: a `c` visit on the block", recent(CH2), [[M0, "c"]])
same("  and on the pericope that holds it, the same visit", recent(HOST), [[M0, "oc"]])
check("  nothing for the block passed or the source not gone into", not V(CH) and not V(CS) and not V(SRC))
check("  `updated` unchanged by visits", B()[CH2]["updated"] == OLD and B()[HOST]["updated"] == OLD)
data = S.load_data()
check("  nor the content hash an editor's base is", S.content_hash(S.index(data), HOST) == S.content_hash(S.index(copy.deepcopy(data)), HOST))

# --- typing: `w`, at once
fresh()
f = F.fw("host", env=ENV)
f.key("!"); f.settle()
leave(f)
same("typing in a block: `cw` at once (no dwell needed)", recent(CH2), [[M0, "cw"]])
same("  the pericope: `ocw`", recent(HOST), [[M0, "ocw"]])

# --- through a quote: `q` on the source, carried up its own tree, not to the quote
fresh()
f = F.fw("host", env=ENV)
f.key(UP, UP)                                   # the quote selected, then inside it
at(T0 + 5); tick(f)
leave(f)
same("dwelling inside a quote: `cq` on the source block", recent(CS), [[M0, "cq"]])
same("  and its entry (carried up its own tree)", recent(SRC), [[M0, "cq"]])
check("  not the quote block itself (seeing isn't visiting)", not V(QH))
same("  the pericope opened: `o`", recent(HOST), [[M0, "o"]])

# --- nested: carried up through the containers
fresh()
f = F.fw("nest", env=ENV)
f.key(UP)                                       # from "after" up into "deep inside"
at(T0 + 4); tick(f)
leave(f)
same("a block inside a container: `c`", recent(KC), [[M0, "c"]])
same("  the container between gets the visit too", recent(K), [[M0, "c"]])
same("  and the pericope", recent(NEST), [[M0, "oc"]])
check("  its siblings don't", not V(KD) and not V(KE))

# --- 10 minutes without: the visit ends (written then), a new one begins
fresh()
f = F.fw("host", env=ENV)
at(T0 + 4); tick(f)
at(T0 + 4 + 601); tick(f)
check("a visit that ended is written at once", recent(CH2) == [[M0, "c"]] and recent(HOST) == [[M0, "oc"]], (recent(CH2), recent(HOST)))
f.key("x"); f.settle()
leave(f)
M1 = int((T0 + 605) // 60)
same("  the next activity starts a new visit", recent(CH2), [[M0, "c"], [M1, "cw"]])
same("  on the pericope too", (V(HOST)["total"], recent(HOST)), (2, [[M0, "oc"], [M1, "ocw"]]))

# --- no undo step
fresh()
f = F.fw("host", env=ENV)
f.key("y"); f.settle()
at(T0 + 10); tick(f); at(T0 + 700); tick(f)       # its visit ends and is written
f.key(Z); f.settle()
check("^Z undoes the typing, not a visit", "host lasty" not in S.own_text(B(), HOST) and recent(CH2) == [[M0, "cw"]], (S.own_text(B(), HOST), recent(CH2)))
leave(f)
h, record = S.set_quote_show(QH, ["title"])
S.record_visits({QH: {M0: "c"}})
S.restore(record)
check("an undo putting a block back keeps its visits", recent(QH) == [[M0, "c"]] and S.quote_show(B()[QH]) == [], V(QH))

# --- the header: when it was last visited (before this time)
last = S.pretty_time(S.minute_iso(S.last_visit(B()[HOST])))
f = F.fw("host", env=ENV, cols=170)
check("the header shows the last visit (before this one), like updated", f"last visited {last}" in f.row(1), (last, f.row(1)))
leave(f)
fresh()
f = F.fw("host", env=ENV, cols=170)
check("  never visited: nothing said", "visited" not in f.text(), f.row(1))
leave(f)

# --- two sessions: neither loses the other's visits, and neither thinks a block changed
fresh()
g = F.fw("host", env=ENV)                       # session 2, open throughout, from minute M0
at(T0 + 120)
f = F.fw("host", env=ENV)                       # session 1 opens the same pericope two minutes on
at(T0 + 125); tick(f)
leave(f)                                        # and writes its visits
tick(g, 3)
check("an untouched editor isn't told the block changed", "another session" not in g.text(), g.text())
same("  session 1's visits", recent(HOST), [[M0 + 2, "oc"]])
g.key("z"); g.settle()                          # session 2 saves an edit over a store with them
check("  a save there keeps them", recent(HOST) == [[M0 + 2, "oc"]], recent(HOST))
leave(g)
same("  both sessions' visits are there, each its own", recent(HOST), [[M0, "ocw"], [M0 + 2, "oc"]])
same("  counted", V(HOST)["total"], 2)
S.record_visits({HOST: {M0 + 2: "o"}}); S.record_visits({HOST: {M0 + 3: "c"}})
same("record_visits merges with what's stored, never overwrites", recent(HOST), [[M0, "ocw"], [M0 + 2, "oc"], [M0 + 3, "c"]])

# --- an empty new entry isn't kept alive by its visits
fresh()
n = len(S.load_data()["blocks"])
f = F.fw(env=ENV)
at(T0 + 10); tick(f)
leave(f)
same("an empty new pericope is still discarded", len(S.load_data()["blocks"]), n)

# --- two machines (the store a Loro document): visits merge as a union
base = blk(CH, "same"); base["visits"] = {"total": 1, "first": M0, "recent": [[M0, "o"]]}
lap, mini = copy.deepcopy(base), copy.deepcopy(base)
lap["visits"] = S.add_visits(lap["visits"], {M0 + 30: "c"}); mini["visits"] = S.add_visits(mini["visits"], {M0 + 60: "w"})
same("merged: visits on both sides a union, both counted", F.loro_merge(base, lap, mini)["visits"],
     {"total": 3, "first": M0, "recent": [[M0, "o"], [M0 + 30, "c"], [M0 + 60, "w"]]})
edited = {**copy.deepcopy(mini), "content": "edited on the mini", "updated": "2026-11-01T10:00:00-04:00"}
out = F.loro_merge(base, lap, edited)
check("  an edit on one side kept, with both sides' visits", out["content"] == "edited on the mini" and len(out["visits"]["recent"]) == 3, out)
F.report("VISITS")
