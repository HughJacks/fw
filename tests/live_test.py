import os, sys, json, time, signal, subprocess
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, Term
DEV = F.DEV
S = F.use_store("t/store.json")
SELF, A = "20261021T230000-0000", "20261001T100000-aaaa"
def entry(i, title, text): return {"id": i, "title": title, "content": [{"type": "text", "text": text}] if text else [], "words": 0, "created": "2026-10-01T10:00:00-04:00"}
def fresh(*entries): json.dump({"schemaVersion": 3, "freewrites": list(entries)}, open("t/store.json", "w"))
def meta(path, i): json.dump({"id": i, "fields": [{"key": "title", "value": "", "editable": True}]}, open(path, "w"))
def stored(i): return S.own_text(S.index(S.load_data()), i)
ED = ["python3", f"{DEV}/fw_edit.py"]

# 1. autosave goes straight into the store (killed without any chance to save on exit)
fresh(entry(SELF, "mine", ""))
open("t/d1.txt", "w").write(""); meta("t/d1.json", SELF)
t = Term(ED + ["t/d1.txt", "--meta", "t/d1.json"]); t.key("written live"); t0 = F.time.time()
t.until(lambda: stored(SELF) == "written live", 8); took = F.time.time() - t0
check("the store has the text as soon as the keys stop: no waiting to save (there was a 1 s wait)", stored(SELF) == "written live" and took < 0.8, (repr(stored(SELF)), round(took, 2)))
os.kill(t.pid, signal.SIGKILL); os.waitpid(t.pid, 0)

# 2. a quote shows its block's current text when the store changes underneath
fresh(entry(SELF, "mine", ""), entry(A, "Alpha", "old alpha text"))
open("t/d2.txt", "w").write("{{quote " + A + "}}"); meta("t/d2.json", SELF)
t = Term(ED + ["t/d2.txt", "--meta", "t/d2.json"])
check("quote shows the text at open", "old alpha text" in t.text())
S.commit(A, "new alpha text, saved elsewhere", [])
new = lambda: "new alpha text, saved elsewhere" in t.text() and "old alpha" not in t.text()
t.until(new, 8)
check("quote updated within ~1.5s of another save", "new alpha text, saved elsewhere" in t.text() and "old alpha" not in t.text())
t.close()

# 3. two real editors: typing in one shows up live in the other's quote
fresh(entry(SELF, "mine", ""), entry(A, "Alpha", "start"))
open("t/w.txt", "w").write("start"); meta("t/w.json", A)
open("t/r.txt", "w").write("{{quote " + A + "}}"); meta("t/r.json", SELF)
writer = Term(ED + ["t/w.txt", "+1", "--meta", "t/w.json"]); reader = Term(ED + ["t/r.txt", "--meta", "t/r.json"])
writer.key("\x1b[F and more, typed in the other editor")
deadline, seen = time.time() + 4, None
while time.time() < deadline and seen is None:
    writer.pump(0.1); reader.pump(0.1)
    if "typed in the other editor" in reader.text(): seen = round(4 - (deadline - time.time()), 1)
check("the reader's quote followed the writer", seen is not None, f"after {seen}s (1s autosave + up to 1s poll)")
writer.close(); reader.close()

# 4. many sessions saving at once lose nothing (the lock)
ids = [f"20261021T23{n:02d}00-{n:04x}" for n in range(16)]
fresh(*[entry(i, f"e{n}", "") for n, i in enumerate(ids)])
procs = [subprocess.Popen([sys.executable, "-c", f"import sys; sys.path.insert(0, {DEV!r}); import fw_store as S; S.commit({i!r}, 'text {n}', [])"]) for n, i in enumerate(ids)]
[p.wait() for p in procs]
check("16 simultaneous commits all landed", all(stored(i) == f"text {n}" for n, i in enumerate(ids)),
      f"{sum(stored(i) == f'text {n}' for n, i in enumerate(ids))}/16")
F.report("LIVE")
