# the pure parts stay pure (the audit of 2026-11-19): block's with_* setters return a new block and leave the one
# they're given as it was
import copy, json, os, subprocess, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("pure")
from fw import block as B

Q = {"id": "20261001T100000-a000", "title": None, "content": {"quote": "20261001T100000-b000", "mask": [0, 3], "show": ["title"]},
     "links": [{"to": "x", "at": [0, 1]}], "kinds": {"k": True}, "visits": {"total": 1, "first": 1, "recent": [[1, "o"]]}}
T = {"id": "20261001T100000-a001", "title": "t", "content": ["c1"], "links": [{"to": "x", "at": [0, 1]}]}
K = {"id": "20261001T100000-a002", "title": "poem", "content": {"kind": "poem", "blocks": ["c1"]}}
cases = [
    ("with_children", T, ["c2"], lambda b: b["content"] == ["c2"]),
    ("with_children (a kind keeps its name)", K, ["c2"], lambda b: b["content"] == {"kind": "poem", "blocks": ["c2"]}),
    ("with_links", T, [], lambda b: "links" not in b),
    ("with_links (some)", T, [{"to": "y", "at": [1, 2]}], lambda b: b["links"] == [{"to": "y", "at": [1, 2]}]),
    ("with_mask", Q, None, lambda b: "mask" not in b["content"] and b["content"]["show"] == ["title"]),
    ("with_inner", Q, {"q": [0, 1]}, lambda b: b["content"]["inner"] == {"q": [0, 1]}),
    ("with_show", Q, ["words", "title"], lambda b: b["content"]["show"] == ["title", "words"] and b["content"]["mask"] == [0, 3]),
    ("with_lock", Q, True, lambda b: b["content"]["lock"] is True),
    ("with_visits", Q, None, lambda b: "visits" not in b),
    ("with_kinds", Q, {}, lambda b: "kinds" not in b),
]
for name, block, value, ok in cases:
    was = copy.deepcopy(block)
    new = getattr(B, name.split(" ")[0])(block, value)
    check(f"{name}: a new block, as asked", new is not block and ok(new), new)
    same(f"  the one given left as it was", block, was)
    same(f"  its other fields kept, in their order", [k for k in new if k in block], [k for k in block if k in new])

# transact (the audit's "every store write is a mutation"): a change gets the store and returns (a new store, a
# result), never changing the store it's given; the flags (upgraded, rebased) ride beside it, never in the data
E, E1, E2, P = "20261002T100000-e000", "20261002T100000-e001", "20261002T100000-e002", "20261002T100000-e003"
F.store(blk(E, [E1, E2], "host", entry=True), blk(E1, "one"), blk(E2, "two"))
given = []
def change(store):
    given.append((store, copy.deepcopy(store)))
    new = {**store, "blocks": [b if b["id"] != E1 else {**b, "content": "one, changed"} for b in store["blocks"]]}
    return new, "done"
same("a change: (new store, result); the result back", S.transact(change), "done")
same("  the store it was given left as it was", given[0][0], given[0][1])
same("  the new store saved", S.index(S.load_data())[E1]["content"], "one, changed")
given.clear()
def in_place(data, blocks):
    blocks[E2]["content"] = "two, changed"
    return "edited"
def watched(store):
    given.append((store, copy.deepcopy(store)))
    return S.editing(in_place)(store)
same("editing: an edit in place made a change", S.transact(watched), "edited")
same("  on a copy: the store it was given left as it was", given[0][0], given[0][1])
same("  the edit saved", S.index(S.load_data())[E2]["content"], "two, changed")
new, r, rebased = S.editing(lambda d, b: d.setdefault("rebased", set()).add(E1))(S.load_data())
check("  the quotes it rebased come back beside the store, not in it", rebased == {E1} and "rebased" not in new, (rebased, list(new)))
raw = json.load(open(S.DATA_PATH))
check("nothing saved carries a flag", not {"upgraded", "rebased"} & set(raw), list(raw))
saves = []
real_save = S.save_data
S.save_data = lambda *a, **k: (saves.append(1), real_save(*a, **k))[1]
pid, record = S.paraphrase_it(E1)
S.save_data = real_save
kids = S.children(S.index(S.load_data())[E])
check("paraphrase_it: one transaction, one save", len(saves) == 1 and kids[0] == pid, (saves, kids))
S.restore(record)
same("  its record undoes all of it", [S.index(S.load_data())[k]["content"] for k in S.children(S.index(S.load_data())[E])],
     ["one, changed", "two, changed"])
try:
    S.paraphrase_it("20261002T100000-ffff"); refused = None
except S.StoreError as e:
    refused = str(e)
same("  refused whole (nothing there): nothing saved", refused, "write something first")

# the clock and fresh ids come in from the edge (the audit's "Purity, medium"): migrating makes blocks with the time
# and ids it's given, and never reads the clock itself; new blocks and `updated` stamps take the time given
from fw import migrate as M, draft as D
from datetime import datetime
v1 = {"schemaVersion": 1, "freewrites": [{"id": "20261001T100000-aa00", "name": "garden", "created": "nope",
      "content": "tulips"}, {"id": "20261001T100000-aa01", "name": None, "created": "2026-10-01T10:00:00-04:00",
      "content": [{"type": "text", "text": "see"}, {"type": "quote", "ref": "20261001T100000-aa00"}]}]}
real_now = D.now_local
D.now_local = lambda: (_ for _ in ()).throw(AssertionError("the clock read inside migrate"))
then = datetime.fromisoformat("2026-11-20T03:00:00-05:00")
made = []
def ids(taken, created):
    i = f"{created.strftime('%Y%m%dT%H%M%S')}-{len(made):04x}"; made.append(i); return i
try:
    up = M.upgrade(copy.deepcopy(v1), now=then, new_id=ids); err = None
except AssertionError as e:
    up, err = None, str(e)
D.now_local = real_now
check("upgrade: the time and ids it's given, no clock read", err is None and made and all(any(b["id"] == i for b in up["blocks"]) for i in made), err or made)
check("  a block made where the old one had no good date: made `now`", any(b.get("created") == then.isoformat(timespec="seconds") for b in up["blocks"]),
      [b.get("created") for b in up["blocks"]])
same("new_block: made at the time given", S.new_block("x", "", now=then)["created"], "2026-11-20T03:00:00-05:00")
d = {"blocks": [{"id": "a", "title": None, "content": "new", "created": "c", "updated": "c"}]}
S.stamp_updated(d, [{"id": "a", "title": None, "content": "old", "created": "c", "updated": "c"}], frozenset(), then)
same("stamp_updated: stamps the time given", d["blocks"][0]["updated"], "2026-11-20T03:00:00-05:00")

# a store fw can't read: load_data raises (a web request's thread answers it), the commands still say it and stop
open(S.DATA_PATH, "w").write(json.dumps({"schemaVersion": 2, "freewrites": "nope"}))
try:
    S.load_data(); raised = None
except S.StoreError as e:
    raised = str(e)
except SystemExit:
    raised = "exited"
S.forget()
check("an unreadable store: load_data raises StoreError, never exits", raised and raised != "exited" and "freewrites" in raised, raised)
cli = subprocess.run([sys.executable, "-m", "fw.store", "migrate"], capture_output=True, text=True)
check("  python -m fw.store migrate on it: says so and stops (exit 1)", cli.returncode == 1 and cli.stderr.startswith("fw: "), (cli.returncode, cli.stderr))

F.report()
