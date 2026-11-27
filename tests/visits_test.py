# visits (schema v15): a block's last 10 visits, its total and its first, noted by the editor, never an edit; and
# what they're read for: memory (FSRS-style), the garden's order (recent, then resurfacing)
import copy, json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("visits")
from fw import migrate as M
T0 = 1794000000.0                     # (Nov 2026)
M0 = int(T0 // 60)
HOST, CH, QH, CH2 = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002", "20261001T100000-b003"
SRC, CS = "20261001T100000-5a00", "20261001T100000-5a01"
NEST, K, KC, KD, KE = ("20261001T100000-c000", "20261001T100000-c001", "20261001T100000-c002", "20261001T100000-c003",
                       "20261001T100000-c004")
OLD = "2026-10-01T10:00:00-04:00"
def fresh(version=17):
    F.store(blk(SRC, [CS], "src", entry=True), blk(CS, "source words"),
            blk(HOST, [CH, QH, CH2], "host", entry=True), blk(CH, "host first"), blk(QH, {"quote": SRC}), blk(CH2, "host last"),
            blk(NEST, [K, KD], "nest", entry=True), blk(K, [KE, KC]), blk(KE, "also inside"), blk(KC, "deep inside"), blk(KD, "after"),
            version=version)
def V(i): return F.blocks()[i].get("visits")
def recent(i): return (V(i) or {}).get("recent", [])

# --- the stored shape, pure
v = S.add_visits(None, {M0: "o"})
same("a first visit: total 1, first, recent [[minute, flags]]", v, {"total": 1, "first": M0, "recent": [[M0, "o"]]})
v = S.add_visits(v, {M0: "cw"})
same("  the same visit again (same minute): flags joined, not counted again", v, {"total": 1, "first": M0, "recent": [[M0, "ocw"]]})
v = S.add_visits(v, {M0 + 20 + n * 15: "c" for n in range(12)})
check("capped at 10, oldest first; the total and the first go on counting",
      len(v["recent"]) == 10 and v["total"] == 13 and v["first"] == M0 and v["recent"][-1][0] == M0 + 20 + 11 * 15
      and v["recent"] == sorted(v["recent"]), v)
same("block.visits gives a block's visits, for ranking later", S.visits({"visits": v})[-1], [M0 + 185, "c"])
check("  none for a block never visited", S.visits({}) == [] and S.last_visit({}) is None)
live, seen = S.attend({}, ["x"], "c", T0)
live, seen2 = S.attend(live, ["x"], "c", T0 + 599)
check("attention within 10 minutes carries the visit on", seen["x"][0] == seen2["x"][0] == M0)
live, seen3 = S.attend(live, ["x"], "c", T0 + 599 + 601)
check("  after 10 minutes without, a new one begins", seen3["x"][0] == int((T0 + 1200) // 60) and S.ended(live, T0 + 1200 + 601) == {"x"})
a = {"total": 5, "first": M0, "recent": [[M0, "o"], [M0 + 30, "c"]]}
b = {"total": 6, "first": M0, "recent": [[M0, "oc"], [M0 + 50, "w"]]}
m = S.merge_visits(a, b, base={"total": 4, "first": M0, "recent": [[M0, "o"]]})
same("merging two copies (fwsync): a union, each side's new visits counted",
     m, {"total": 7, "first": M0, "recent": [[M0, "oc"], [M0 + 30, "c"], [M0 + 50, "w"]]})

# --- migration v14 → v15
fresh()
d = json.load(open(os.environ["FW_DATA"]))
check("the store is v15 (or later)", d["schemaVersion"] == M.SCHEMA_VERSION >= 15, d["schemaVersion"])
v14 = {**d, "schemaVersion": 14}
up = M.upgrade(copy.deepcopy(v14), now=S.now_local(), new_id=S.new_id)
check("v14 → v15: marked to be saved, the blocks as they were (no visits yet)",
      up["schemaVersion"] == M.SCHEMA_VERSION and M.behind(v14) and up["blocks"] == d["blocks"] and not any("visits" in b for b in up["blocks"]))
json.dump(v14, open(os.environ["FW_DATA"], "w")); os.remove(S.LORO_PATH); S.forget(); S.cmd_migrate(None)
d2 = json.load(open(os.environ["FW_DATA"]))
check("  migrate saves it: current, same blocks", d2["schemaVersion"] == M.SCHEMA_VERSION and len(d2["blocks"]) == len(d["blocks"]))
spec = S.load_schema()["properties"]["visits"]
check("the schema describes it, readOnly", spec["readOnly"] is True and set(spec["properties"]) == {"total", "first", "recent"})
bad = S.validate({"total": 1, "first": M0, "recent": [[M0, "x"]]}, spec)
check("  and checks it (flags are o, c, w, q)", bad, bad)

# --- written: record_visits, carried up to the blocks holding it (not through quotes); never an edit
fresh()
S.record_visits({KC: {M0: "c"}})
same("a block's visit, written", recent(KC), [[M0, "c"]])
check("  not an edit: updated as it was", F.blocks()[KC]["updated"] == F.T and F.blocks()[NEST]["updated"] == F.T)
data = S.load_data()
check("  nor the content hash an editor's base is", S.content_hash(S.index(data), NEST) == S.content_hash(S.index(copy.deepcopy(data)), NEST))
S.record_visits({HOST: {M0 + 2: "o"}}); S.record_visits({HOST: {M0 + 3: "c"}})
same("record_visits merges with what's stored, never overwrites", recent(HOST), [[M0 + 2, "o"], [M0 + 3, "c"]])
_, record = S.set_quote_show(QH, ["title"])
S.record_visits({QH: {M0: "c"}})
S.restore(record)
check("an undo putting a block back keeps its visits", recent(QH) == [[M0, "c"]] and S.quote_show(F.blocks()[QH]) == [], V(QH))
S.commit(HOST, S.block_draft(F.blocks(), HOST) + "!", [])
same("a save over a store with visits keeps them", recent(HOST), [[M0 + 2, "o"], [M0 + 3, "c"]])

# --- two machines (the store a Loro document): visits merge as a union
base = blk(CH, "same"); base["visits"] = {"total": 1, "first": M0, "recent": [[M0, "o"]]}
lap, other = copy.deepcopy(base), copy.deepcopy(base)
lap["visits"] = S.add_visits(lap["visits"], {M0 + 30: "c"}); other["visits"] = S.add_visits(other["visits"], {M0 + 60: "w"})
same("merged: visits on both sides a union, both counted", F.loro_merge(base, lap, other)["visits"],
     {"total": 3, "first": M0, "recent": [[M0, "o"], [M0 + 30, "c"], [M0 + 60, "w"]]})
edited = {**copy.deepcopy(other), "content": "edited on the other machine", "updated": "2026-11-01T10:00:00-04:00"}
out = F.loro_merge(base, lap, edited)
check("  an edit on one side kept, with both sides' visits", out["content"] == "edited on the other machine" and len(out["visits"]["recent"]) == 3, out)

# --- memory and the garden (home's order before suggesting)
NOW, DAY = 29_920_000, 1440
fresh_ = {"created": "2026-11-15T10:00:00-05:00", "visits": {"total": 1, "first": NOW - 2 * DAY, "recent": [[NOW - 2 * DAY, "ow"]]}}
s1, r1 = S.memory(fresh_, NOW)
check("one visit 2 days ago: S is a day, R about .8", abs(s1 - 1) < 1e-9 and 0.8 < r1 < 0.85, (s1, r1))
spaced = {"visits": {"total": 4, "first": NOW - 200 * DAY, "recent": [[NOW - 200 * DAY, "ow"], [NOW - 190 * DAY, "oc"], [NOW - 150 * DAY, "ow"], [NOW - 60 * DAY, "oc"]]}}
crammed = {"visits": {"total": 4, "first": NOW - 200 * DAY, "recent": [[NOW - 200 * DAY, "ow"], [NOW - 200 * DAY + 30, "oc"], [NOW - 200 * DAY + 60, "ow"], [NOW - 60 * DAY, "oc"]]}}
check("spaced visits build more stability than crammed ones", S.memory(spaced, NOW)[0] > S.memory(crammed, NOW)[0])
w = {"visits": {"total": 2, "first": NOW - 30 * DAY, "recent": [[NOW - 30 * DAY, "ow"], [NOW - 20 * DAY, "ow"]]}}
o = {"visits": {"total": 2, "first": NOW - 30 * DAY, "recent": [[NOW - 30 * DAY, "ow"], [NOW - 20 * DAY, "o"]]}}
check("writing in it counts for more than a glance", S.memory(w, NOW)[0] > S.memory(o, NOW)[0])
check("no visits: its writing stands for the first", S.memory({"created": "2026-11-01T10:00:00-05:00"}, NOW)[1] < 1)
same("ago", [S.ago(NOW - n, NOW) for n in (0, 5, 120, 3 * DAY, 70 * DAY, 400 * DAY)], ["just now", "5m ago", "2h ago", "3d ago", "2mo ago", "1y ago"])
same("last action: the last visit's strongest flag", (S.last_action(w)[0], S.last_action(o)[0]), ("written", "opened"))
same("  none, never changed: made", S.last_action({"created": "2026-11-01T10:00:00-05:00", "updated": "2026-11-01T10:00:00-05:00"})[0], "made")
def vis(*ago, flags="ow"): return {"total": len(ago), "first": NOW - ago[0], "recent": [[NOW - a, flags] for a in ago]}
G = {i: {"id": i, "content": "x", "created": "2026-06-01T10:00:00-04:00", **({"visits": v} if v else {})} for i, v in (
    ("recent", vis(DAY)), ("faded", vis(300 * DAY, 299 * DAY, 200 * DAY)), ("faded once", vis(100 * DAY, flags="o")),
    ("steady", vis(400 * DAY, 390 * DAY, 370 * DAY, 330 * DAY, 250 * DAY, 30 * DAY)), ("plain", None))}
order = S.garden(G, list(G), NOW)
why = dict(order)
same("the garden: recent first", order[0], ("recent", "recent"))
check("  faded ones resurface, the more rehearsed first", why["faded"] == why["faded once"] == "resurfacing"
      and [i for i, _ in order].index("faded") < [i for i, _ in order].index("faded once"), order)
same("  well rehearsed, seen a month ago: still in mind", why["steady"], "")
same("  everything once", sorted(why), sorted(G))
G = {f"2026110{n}T100000-r000": {"content": "x", "visits": vis((n + 1) * 60)} for n in range(5)}
G |= {f"2026060{n}T100000-f000": {"content": "x", "visits": vis((200 + n) * DAY)} for n in range(3)}
same("the first cards: recent and resurfacing in turn, then the recent left", [w for _, w in S.garden(G, list(G), NOW)],
     ["recent", "resurfacing"] * 3 + ["recent"] * 2)
many = {f"2026110{n % 10}T1{n:05d}-r000": {"content": "x", "visits": vis(n + 1)} for n in range(14)}
same("  only the first TOP mix: a busy week's recent come after", [w for _, w in S.garden(G | many, list(G | many), NOW)][:S.TOP].count("resurfacing"), 3)
F.report()
