import signal, json, os, sys, subprocess
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, Term
DEV = F.DEV; STORE = os.path.abspath("t/fix.json")
S = F.use_store(STORE)
E, C, G, Q, A, CA = ("20261020T100000-e000", "20261020T100000-c000", "20261020T100000-a000",
                     "20261020T100000-9000", "20261020T110000-aaaa", "20261020T110000-ca00")
def blk(i, c, title=None): return F.blk(i, c, title, "2026-10-20T10:00:00-04:00")
def store(): return S.index(S.load_data())

# --- 2. nested blocks survive
QB = "20261020T100000-9b00"
json.dump({"schemaVersion": 5, "entries": [E, Q], "blocks": [
    blk(E, [C], "outer"), blk(C, [G, QB]), blk(G, "grandchild"), blk(QB, {"quote": Q}),
    blk(Q, "quoted", "q")]}, open(STORE, "w"))
before = store()[C]["content"]
subprocess.run([sys.executable, f"{DEV}/fw_store.py", "migrate"], check=True)
check("migrate leaves a nested block alone", store()[C]["content"] == before and G in store(), store()[C]["content"])
S.commit(E, S.block_draft(store(), E), [])
check("saving its entry unchanged leaves it alone too", store()[C]["content"] == before and G in store())
S.commit(E, S.block_draft(store(), E).replace("grandchild", "edited"), [])
check("editing its text (a container's) keeps it nested", store()[C]["content"] == before and store()[G]["content"] == "edited",
      (store()[C]["content"], store()[G]["content"]))

# --- 1: the last save failing keeps the draft (store.finish raises; fw_app says where the draft is)
def fresh():
    json.dump({"schemaVersion": 5, "entries": [A], "blocks": [blk(A, [CA], "alpha"), blk(CA, "alpha text")]}, open(STORE, "w"))
for mode in ("conflict", "broken"):
    fresh()
    ref, tmp, _ = S.stage(A, append=True)
    open(tmp, "a").write("my new words")
    if mode == "conflict":   # meanwhile, another session saves this entry
        S.commit(A, "changed elsewhere", [])
    else:                    # the store goes bad before the final save
        d = json.load(open(STORE)); d["blocks"][0]["created"] = "yesterday"; json.dump(d, open(STORE, "w"))
    try:
        S.finish(ref, tmp); refused = False
    except S.StoreError:
        refused = True
    check(f"{mode}: the last save refused, the draft kept", refused and "my new words" in open(tmp).read())
    if mode == "conflict":
        check("conflict: the other session's text isn't overwritten", S.own_text(store(), A) == "changed elsewhere", S.own_text(store(), A))
    S.drop_draft(tmp)
fresh()
ref, tmp, _ = S.stage(A, append=True)
open(tmp, "a").write("my new words")
S.finish(ref, tmp); S.drop_draft(tmp)
check("no conflict: the draft is saved", "my new words" in S.own_text(store(), A), S.own_text(store(), A))

# --- 3 in the real editor
def session():
    _, tmp, line = S.stage(A, append=True)
    return tmp, Term(["python3", f"{DEV}/fw_edit.py", tmp, f"+{line}", "--meta", tmp[:-4] + ".meta.json"])
def end(tmp):
    try:
        return 0, " ".join(S.finish(A, tmp))
    except S.StoreError as e:
        return 1, str(e)

fresh(); tmp, t = session()
S.commit(A, "changed elsewhere", [])   # another session, while this one sits untouched
t.until(lambda: "changed elsewhere" in t.text() and "alpha text" not in t.text(), 8)
check("an untouched session shows text changed elsewhere", "changed elsewhere" in t.text() and "alpha text" not in t.text())
t.close(); code, err = end(tmp)
check("  and quitting it doesn't revert that text", code == 0 and S.own_text(store(), A) == "changed elsewhere", (code, err, S.own_text(store(), A)))
os.remove(tmp); os.remove(tmp[:-4] + ".meta.json")

fresh(); tmp, t = session()
t.key("one "); t.settle()              # autosaved
S.commit(A, S.block_draft(store(), A) + " plus theirs", [])
t.until(lambda: "plus theirs" in t.text(), 8); t.key("\x1b[F two"); t.settle()
t.close(); code, err = end(tmp)
check("writing after someone else's save keeps both", code == 0 and "plus theirs two" in S.own_text(store(), A) and "one " in S.own_text(store(), A), S.own_text(store(), A))
os.remove(tmp); os.remove(tmp[:-4] + ".meta.json")

fresh(); tmp, t = session()
os.kill(t.pid, signal.SIGSTOP)          # (held still, so the order is certain: it saves as soon as keys stop)
S.commit(A, "theirs", [])               # another session saves this entry...
os.write(t.fd, b"mine")                 # ...while this one is typing on what it had
os.kill(t.pid, signal.SIGCONT)
t.until(lambda: "not saved" in t.text(), 8)
check("a real conflict is refused, with a message", "not saved" in t.text(), [l for l in t.scr.display if l.strip()][-1].strip())
t.close(); code, err = end(tmp)
check("  the other text stays; ours is still in the draft", code == 1 and S.own_text(store(), A) == "theirs" and "mine" in open(tmp).read(), (code, err))
os.remove(tmp); os.remove(tmp[:-4] + ".meta.json")
F.report("FIX")
