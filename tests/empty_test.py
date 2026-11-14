import json, os, sys
sys.path.insert(0, "."); import drive, fwtest as F
from fwtest import check
S = F.use_store("t/store.json")
SELF, C1, C2 = "20261021T230000-0000", "20261021T230000-c001", "20261021T230000-c002"
META = os.path.abspath("t/f.meta.json"); json.dump({"id": SELF, "fields": []}, open(META, "w"))
def blk(i, c): return {"id": i, "title": None, "content": c, "words": 0, "created": "2026-10-21T23:00:00-04:00"}
def setup():
    json.dump({"schemaVersion": 4, "entries": [SELF], "blocks": [blk(SELF, [{"ref": C1}, {"ref": C2}]), blk(C1, "one"), blk(C2, "two")]}, open("t/store.json", "w"))
    return S.block_draft(S.index(S.load_data()), SELF)
def state():
    d = S.load_data(); B = S.index(d)
    return [S.own_text(B, k) for k in S.children(B[SELF])], len(d["blocks"])
E, SE, DOWN, END, Q = "\r", "\x1b[13;2u", "\x1b[B", "\x1b[F", "\x11"
for label, keys in [
    ("three empty blocks at the end", [DOWN, END, E, E, E, Q]),
    ("empty blocks between two blocks", [END, E, E, E, Q]),
    ("an empty block with blank lines and spaces", [END, E, SE, "   ", SE, Q]),
    ("a block emptied by deleting its text", [DOWN, END, "\x7f\x7f\x7f", Q]),
    ("empty blocks above the first", ["\x1b[H", E, E, Q]),
]:
    drive.run(setup(), keys, ["--meta", META], cols=60, rows=20)
    texts, n = state()
    want = ["one"] if "deleting" in label else ["one", "two"]
    check(label, texts == want and n == 1 + len(want), f"{texts}, {n} blocks in the store")
F.report("EMPTY")
