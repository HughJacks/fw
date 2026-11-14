# fw_migrate.upgrade: a store of any version brought up to the current one, in memory (pure)
import copy, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same
S = F.use_store("t/migrate.json", clean=True)
import fw_migrate as M

A, B = "20260901T100000-aaaa", "20260902T100000-bbbb"
v1 = {"schemaVersion": 1, "freewrites": [
    {"id": A, "name": "garden", "created": "2026-09-01T10:00:00-04:00", "content": "tulips\n\nroses"},
    {"id": B, "name": None, "created": "2026-09-02T10:00:00-04:00",
     "content": [{"type": "text", "text": "\nsee\n"}, {"type": "quote", "ref": A}]}]}
d = M.upgrade(copy.deepcopy(v1))
blocks = {b["id"]: b for b in d["blocks"]}
check("v1 → now: the current version, marked to be saved", d["schemaVersion"] == M.SCHEMA_VERSION == S.SCHEMA_VERSION and d.get("upgraded"), d.get("schemaVersion"))
check("  no entries list, no freewrites: just blocks", set(d) == {"schemaVersion", "blocks", "upgraded"}, set(d))
check("  each old entry an entry block, its name its title", blocks[A].get("entry") and blocks[A]["title"] == "garden" and blocks[B]["title"] is None)
kids = lambda i: [blocks[k]["content"] for k in blocks[i]["content"]]
same("  its text a child block", kids(A), ["tulips\n\nroses"])
same("  a quote a Quote block of its own, blank edges trimmed from text", kids(B), ["see", {"quote": A}])
check("  every block has `updated`", all("updated" in b for b in d["blocks"]))
check("  and it's valid", not S.invalid(d, S.load_schema()), S.invalid(d, S.load_schema()))
current = {"schemaVersion": M.SCHEMA_VERSION, "blocks": [{"id": A, "title": None, "entry": True, "content": [], "created": "x"}]}
same("a current store passes through untouched (not marked to be saved)", M.upgrade(copy.deepcopy(current)), current)
try:
    M.upgrade({"schemaVersion": 2, "freewrites": "nope"}); bad = None
except M.BadStore as e:
    bad = str(e)
check("a store it can't read: BadStore, saying why", bad and "freewrites" in bad, bad)
F.report("MIGRATE")
