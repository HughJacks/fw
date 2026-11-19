import os, sys, subprocess
sys.path.insert(0, "."); import fwtest as F
from fwtest import check
DEV = F.DEV
S = F.use_store("t/e2e.json", clean=True)
def fw(args, keys):
    t = F.fw(*args, cols=60, rows=20); t.key(*keys); t.done(5)
def entry(title):
    d = S.load_data(); B = S.index(d)
    return d, B, next(B[e] for e in S.entry_ids(d) if B[e]["title"] == title)
fw(["e2e"], ["first block", "\r", "second block", "\x11", "\x11"])   # ^Q the entry, ^Q home
d, B, e = entry("e2e")
check("fw: Enter made two blocks", [S.own_text(B, k) for k in e["content"]] == ["first block", "second block"], e["content"])
def unvisited(d):   # (opening records a visit, never an edit: a new minute, or a slow run, writes one; what's compared is the writing)
    return {**d, "blocks": [{k: v for k, v in b.items() if k != "visits"} for b in d["blocks"]]}
before = unvisited(S.load_data())
fw(["e2e"], ["\x11", "\x11"])
after = unvisited(S.load_data())
changed = {b["id"]: sorted(k for k in set(b) | set(o) if b.get(k) != o.get(k))
           for b, o in ((b, {x["id"]: x for x in before["blocks"]}.get(b["id"], {})) for b in after["blocks"]) if b != o}
check("fw e2e again, quit without typing: store unchanged", after == before, changed or [k for k in set(after) | set(before) if after.get(k) != before.get(k)])
fw(["e2e"], [" more", "\x11", "\x11"])
d, B, e = entry("e2e")
check("reopened at the end of the last block: typing goes on there, no blank lines", [S.own_text(B, k) for k in e["content"]] == ["first block", "second block more"], [S.own_text(B, k) for k in e["content"]])
fw(["e2e"], ["\r", "third", "\x11", "\x11"])
d, B, e = entry("e2e")
check("  and Enter starts a new block after it", [S.own_text(B, k) for k in e["content"]] == ["first block", "second block more", "third"], [S.own_text(B, k) for k in e["content"]])
fw([], ["\x11", "\x11"])
check("new entry, nothing written: discarded", len(S.entry_ids(S.load_data())) == 1)
check("no leftover drafts", not [f for f in os.listdir(DEV) if f.startswith(".fw-")])
print(subprocess.run(["zsh", f"{DEV}/fw", "ls"], capture_output=True, text=True).stdout.strip())
F.report("E2E")
