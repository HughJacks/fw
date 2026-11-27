# pericopes (entries): top-level blocks, marked `entry: true` (schema v10: everything is a block, no entries list);
# made, deleted, cleared when left empty; `updated` stamped by the store on every write
import json, os, sys, time
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("entry")
A, CA, ME, X, QA = "20261001T100000-aa00", "20261001T100000-aa01", "20261021T230000-ff00", "20261021T230000-ff01", "20261021T230000-ff02"
def raw(): return json.load(open(S.DATA_PATH))
def fresh(mask=None, version=9):
    F.store(blk(A, [CA], "Alpha", entry=True), blk(CA, "alpha body, all of it"),
            blk(ME, [X, QA], "mine", entry=True), blk(X, "x"), blk(QA, {"quote": A, **({"mask": mask} if mask else {})}), version=version)

fresh()
d = raw()
check("v9 → now: the store is just blocks", set(d) == {"schemaVersion", "blocks"} and d["schemaVersion"] == S.SCHEMA_VERSION, set(d))
same("  each entry marks itself, right after its title", [list(b)[:3] for b in d["blocks"] if b["id"] in (A, ME)], [["id", "title", "entry"]] * 2)
check("  a child has no mark", not any("entry" in b for b in d["blocks"] if b["id"] in (CA, X)))
same("  the entries are the marked blocks", sorted(S.entry_ids(d)), sorted([A, ME]))

new, _, _ = S.pop_out(X)
check("pop out: the new block is marked an entry", F.blocks()[new].get("entry") is True and new in S.entry_ids(S.load_data()))
_, undo = S.new_entry("fresh", ME)
check("a new entry is marked", any(b.get("title") == "fresh" and b.get("entry") for b in F.blocks().values()))
S.restore(undo)
check("  undo takes it away again", not any(b.get("title") == "fresh" for b in F.blocks().values()))

# --- deleting: for good; a quote of it keeps its last text (a quote is a pointer)
fresh()
kept = S.delete_entry(A)
check("deleting an entry: its blocks erased", A not in F.blocks() and CA not in F.blocks() and A not in S.entry_ids(S.load_data()))
same("  a quote of it keeps the last of what it showed, as plain text", (F.content(QA), kept), ("alpha body, all of it", 1))
fresh(); d = S.block_draft(F.blocks(), A); i = d.index("body")
fresh([i, i + 4])
S.delete_entry(A)
same("  a masked one: what it showed, … for the rest", F.content(QA), "…body…")
check("  not a pericope: refused", F.refused(S.delete_entry, X))

# --- empty untitled pericopes: cleared, but not while just started (it may be open on another machine)
fresh()
F.edit(lambda d, b: S.add_block(d, b, "20261021T230000-ee00", [], entry=True))
S.cmd_migrate(None)
check("migrate leaves a just-started empty pericope alone", "20261021T230000-ee00" in F.blocks())
open("t/clock", "w").write(str(time.time() + 2 * 3600)); os.environ["FW_CLOCK"] = os.path.abspath("t/clock")
S.cmd_migrate(None)
check("  once it's sat untouched an hour, it's cleared", "20261021T230000-ee00" not in F.blocks())
del os.environ["FW_CLOCK"]
check("  an empty kind isn't 'empty' (it has its name)", not S.is_empty_untitled({A: blk(A, {"kind": "x", "blocks": []})}, A))
e, _ = S.new_entry(None, ME)
S.commit(e, "", [], final=True)
check("committed empty and untitled at the end of a session: discarded", e not in F.blocks())
d = raw(); next(b for b in d["blocks"] if "entry" not in b)["entry"] = False; json.dump(d, open(S.DATA_PATH, "w"))
try: S.cmd_migrate(None); bad = False
except SystemExit: bad = True
check("`entry` is true or absent, never false", bad)

# --- updated: on every block, stamped by the store
B_, CB, QBA, C, CC, QCA, CA2 = ("20261002T100000-bb00", "20261002T100000-bb01", "20261002T100000-bb02",
                                "20261003T100000-cc00", "20261003T100000-cc01", "20261003T100000-cc02", "20261001T100000-aa02")
F.store(blk(A, [CA, CA2], "Alpha", entry=True), blk(CA, "alpha body"), blk(CA2, "second"),
        blk(B_, [CB, QBA], "Beta", entry=True), blk(CB, "beta"), blk(QBA, {"quote": A}),
        blk(C, [CC, QCA], "Gamma", entry=True), blk(CC, "gamma"), blk(QCA, {"quote": A, "mask": [0, 5]}))
def up(i): return F.blocks()[i].get("updated")
check("a store from before: every block's updated as it was", all(b.get("updated") == F.T for b in S.load_data()["blocks"]))
S.commit(A, S.block_draft(F.blocks(), A).replace("alpha body", "alpha body, edited"), [])
check("editing a block's text: that block updated now", up(CA) != F.T)
check("  and the entry it's part of", up(A) == up(CA))
check("  not its sibling", up(CA2) == F.T)
check("  not the entries quoting it (their words do follow)", up(B_) == F.T and up(QBA) == F.T and F.blocks()[B_]["words"] == 5, (up(B_), F.blocks()[B_]["words"]))
check("  nor a masked quote whose anchors only moved along", up(QCA) == F.T and up(C) == F.T)
_, record = S.set_quote_show(QBA, ["title"])
check("showing a quote's title updates the quote", up(QBA) != F.T)
S.restore(record)
same("  undone: the time it had", up(QBA), F.T)
check("the schema knows it: readOnly", S.load_schema()["properties"]["updated"]["readOnly"] is True)
F.report()
