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
ED = [os.environ.get("FW_PYTHON", "python3"), f"{DEV}/fw_edit.py"]

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

# 5. two writers, the same block, each from what it read (its version): merged by Loro, never refused, nothing lost
fresh(entry(SELF, "mine", ""), entry(A, "Alpha", "the middle"))
S.commit(A, S.block_draft(S.index(S.load_data()), A), [])   # (the document written: versions from here)
data, seen = S.load_versioned()
draft = S.block_draft(S.index(data), A)
base = S.content_hash(S.index(data), A)
S.commit(A, draft.replace("the middle", "start: the middle"), [], base=base, at=seen)   # one window
check("a version is kept per write", S.written_version() not in (None, seen))
notes, mine, _, _ = S.commit(A, draft.replace("the middle", "the middle :end"), [], base=base, at=seen)   # the other, from the same read
check("the second, written from the same read: merged, not refused", stored(A) == "start: the middle :end", repr(stored(A)))
check("  its answer is its own view (what it wrote on what it saw): it then follows the merge",
      mine != S.content_hash(S.index(S.load_data()), A) and S.written_version() != S.current_version())
try:
    S.commit(A, draft + " (old way)", [], base=base); refused = False
except S.StoreError:
    refused = True
check("  without a version: refused as before (the terminal editor, a script)", refused and stored(A) == "start: the middle :end")

# 6. the document kept in memory: read again only when another process wrote it; a save writes just what changed;
#    the .json copy may come a moment later (the web core), never taken in as edits meanwhile
import copy, fw_loro as L
fresh(entry(SELF, "mine", ""), entry(A, "Alpha", "kept"))
S.commit(A, "kept in memory", [])
d1 = S.document()
check("the document kept in memory between reads", d1 is not None and S.document() is d1)
subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {DEV!r}); import fw_store as S; S.commit({A!r}, 'written by another process', [])"], check=True)
check("  another process's write noticed: read again", S.document() is not d1 and stored(A) == "written by another process", repr(stored(A)))
S.commit(SELF, "mine too", [])
check("  a write here after it keeps theirs", stored(A) == "written by another process" and stored(SELF) == "mine too")
old = S.document().data
new = copy.deepcopy(old)
tid = next(i for i in S.children(S.index(new)[A]))
for b in new["blocks"]:
    if b["id"] == tid:
        b["content"] = "changed, the one block"
full, part = L.load(S.LORO_PATH.read_bytes(), 1), L.load(S.LORO_PATH.read_bytes(), 1)
L.write(full, new); L.write(part, new, old)
check("  just what changed written: the same document as a whole write", L.to_data(full) == L.to_data(part))
was = (S.document().version, stored(A))
try:
    S.transact(lambda st: ({**st, "blocks": [{**b, "content": 5} if b["id"] == tid else b for b in st["blocks"]]}, None)); refused = False
except S.StoreError:
    refused = True
check("  a refused write leaves the document as the file has it", refused and (S.document().version, stored(A)) == was
      and S.document().version == L.version(L.load(S.LORO_PATH.read_bytes(), 1)))
S.json_later(30)
before = open(S.DATA_PATH).read()
S.commit(SELF, "the .json later", [])
check("the .json copy later: not written yet, not taken in as edits, the store has it", open(S.DATA_PATH).read() == before
      and not S.json_changed() and stored(SELF) == "the .json later")
check("  the store's text as of now (an undo outside the editor reads it) has it", "the .json later" in S.store_text())
S.flush_json()
check("  flushed: the .json says it", "the .json later" in open(S.DATA_PATH).read() and not S.json_changed())
S.commit(SELF, "waiting again", [])
theirs = open(S.DATA_PATH).read().replace("written by another process", "their .json edit")
open(S.DATA_PATH, "w").write(theirs)
S.flush_json()
check("  never over a .json someone else wrote meanwhile (theirs, taken in next)", open(S.DATA_PATH).read() == theirs and S.json_changed())
S.json_later(None)
check("  taken in: their edit", stored(A) == "their .json edit", repr(stored(A)))
F.report("LIVE")
