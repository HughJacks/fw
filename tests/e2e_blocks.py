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
before = S.load_data()
fw(["e2e"], ["\x11", "\x11"])
check("fw e2e again, quit without typing: store unchanged", S.load_data() == before)
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
