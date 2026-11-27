# migrate.upgrade: a store of any version brought up to the current one, in memory (pure); `python -m fw.store`
import copy, json, os, subprocess, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("migrate")
from fw import migrate as M

A, B = "20260901T100000-aaaa", "20260902T100000-bbbb"
v1 = {"schemaVersion": 1, "freewrites": [
    {"id": A, "name": "garden", "created": "2026-09-01T10:00:00-04:00", "content": "tulips\n\nroses"},
    {"id": B, "name": None, "created": "2026-09-02T10:00:00-04:00",
     "content": [{"type": "text", "text": "\nsee\n"}, {"type": "quote", "ref": A}]}]}
was = copy.deepcopy(v1)
d = M.upgrade(v1, now=S.now_local(), new_id=S.new_id)
same("upgrade leaves the store it's given as it was (a new one back)", v1, was)
blocks = {b["id"]: b for b in d["blocks"]}
check("v1 → now: the current version, marked to be saved", d["schemaVersion"] == M.SCHEMA_VERSION == S.SCHEMA_VERSION and M.behind(v1), d.get("schemaVersion"))
check("  no entries list, no freewrites: just blocks", set(d) == {"schemaVersion", "blocks"}, set(d))
check("  each old entry an entry block, its name its title", blocks[A].get("entry") and blocks[A]["title"] == "garden" and blocks[B]["title"] is None)
kids = lambda i: [blocks[k]["content"] for k in blocks[i]["content"]]
same("  its text a child block", kids(A), ["tulips\n\nroses"])
same("  a quote a Quote block of its own, blank edges trimmed from text", kids(B), ["see", {"quote": A}])
check("  every block has `updated`", all("updated" in b for b in d["blocks"]))
check("  and it's valid", not S.invalid(d, S.load_schema()), S.invalid(d, S.load_schema()))
current = {"schemaVersion": M.SCHEMA_VERSION, "blocks": [{"id": A, "title": None, "entry": True, "content": [], "created": "x"}]}
same("a current store passes through untouched (not marked to be saved)", (M.upgrade(copy.deepcopy(current), now=S.now_local(), new_id=S.new_id), M.behind(current)), (current, False))
try:
    M.upgrade({"schemaVersion": 2, "freewrites": "nope"}, now=S.now_local(), new_id=S.new_id); bad = None
except M.BadStore as e:
    bad = str(e)
check("a store it can't read: BadStore, saying why", bad and "freewrites" in bad, bad)

# the command line: migrate (cleans old leftovers), list
def cli(*args): return subprocess.run([sys.executable, "-m", "fw.store", *args], capture_output=True, text=True)
A, T, QE = "20261001T100000-aaaa", "20261002T100000-bbbb", "20261003T100000-cccc"
def entry(i, title, blocks): return {"id": i, "title": title, "content": blocks, "words": 1, "created": "2026-10-01T10:00:00-04:00"}
json.dump({"schemaVersion": 3, "freewrites": [
    entry(A, "alpha", [{"type": "text", "text": "alpha"}]),
    entry(T, "texty", [{"type": "text", "text": "some text\n\n"}]),
    entry(QE, "ends in quote", [{"type": "text", "text": "intro"}, {"type": "quote", "ref": A}])]}, open(S.DATA_PATH, "w"))
r = cli("migrate")
b = F.blocks()
check("python -m fw.store migrate: a v3 store brought up to date, a document made", r.returncode == 0 and S.LORO_PATH.exists(), r.stderr)
same("  stored trailing blank lines cleaned", S.own_text(b, T), "some text")
same("  every text block a child, the quote a Quote block", ["quote" if S.quoted(b[k]) else "child" for k in b[QE]["content"]], ["child", "quote"])
r = cli("list")
check("python -m fw.store list: a line per pericope", r.returncode == 0 and all(t in r.stdout for t in ("alpha", "texty", "ends in quote")), r.stdout + r.stderr)
F.report()
