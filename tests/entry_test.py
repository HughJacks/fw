# schema v10: everything is a block. No `entries` list; an entry marks itself (`entry`: true)
import json, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("t/entry.json", clean=True)
A, CA, ME, X = "20261001T100000-aa00", "20261001T100000-aa01", "20261021T230000-ff00", "20261021T230000-ff01"
def raw(): return json.load(open("t/entry.json"))
def B(): return S.index(S.load_data())

F.write_store([blk(A, [CA], "Alpha"), blk(CA, "alpha text"), blk(ME, [X], "mine"), blk(X, "x")], [A, ME], version=9)
S.cmd_migrate(None)
d = raw()
check("v9 → now: the store is just blocks", set(d) == {"schemaVersion", "blocks"} and d["schemaVersion"] == S.SCHEMA_VERSION, set(d))
same("  each entry marks itself, right after its title", [list(b)[:3] for b in d["blocks"] if b["id"] in (A, ME)],
     [["id", "title", "entry"]] * 2)
check("  a child has no mark", not any("entry" in b for b in d["blocks"] if b["id"] in (CA, X)))
same("  the entries are the marked blocks", sorted(S.entry_ids(d)), sorted([A, ME]))

new, _, _ = S.pop_out(X)
check("pop out: the new block is marked an entry", B()[new].get("entry") is True and new in S.entry_ids(S.load_data()))
_, undo = S.new_entry("fresh", ME)
check("a new entry is marked", any(b.get("title") == "fresh" and b.get("entry") for b in B().values()))
S.restore(undo)
check("  undo takes it away again", not any(b.get("title") == "fresh" for b in B().values()))

S.delete_entry(A)
check("delete: the entry and what it held are erased", A not in B() and CA not in B())

d = S.load_data(); d["blocks"].append({**blk("20261021T230000-ee00", []), "entry": True}); S.save_data(d)
S.cmd_migrate(None)
check("an empty untitled entry is removed on migrate", "20261021T230000-ee00" not in B())

d = raw(); next(b for b in d["blocks"] if "entry" not in b)["entry"] = False; json.dump(d, open("t/entry.json", "w"))  # (a child: an entry marked false would just be erased as unreachable)
try:
    S.cmd_migrate(None); bad = False
except SystemExit:
    bad = True
check("`entry` is true or absent, never false", bad)
F.report("ENTRY")
