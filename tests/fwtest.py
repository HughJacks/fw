"""fwtest — what the suites share: a throwaway store, blocks to fill it, and checks.

    import fwtest as F
    S = F.use_store("quote")                     # fw.store, on t/quote.json (fresh)
    F.store(F.blk(A, [A1], "alpha", entry=True), F.blk(A1, "words"))
    F.same("its text", S.own_text(F.blocks(), A), "words")
    F.report()

A suite prints one line per check ("ok" or "FAIL") and ends with "<NAME> OK" or "<NAME> FAILURES" (run.sh reads them).
The code under test is the copy run.sh puts on PYTHONPATH; the store is always under t/, never a real one.
"""
import copy, json, os, struct, sys, time, zlib

T = "2026-10-01T10:00:00-04:00"   # when the test blocks were made (and last updated)
NAME = os.path.basename(sys.argv[0]).removesuffix("_test.py").upper()

# --- check and report
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'ok' if cond else 'FAIL':5} {label}" + (f": {detail}" if detail and not cond else ""))
def same(label, got, want):
    global ok; good = got == want; ok &= good; print(f"{'ok' if good else 'FAIL':5} {label}" + ("" if good else f": {got!r}  want {want!r}"))
def report(name=NAME): print(f"{name} OK" if ok else f"{name} FAILURES")

def refused(fn, *args, **kw):
    """The StoreError `fn(*args)` raises, as text; None if it went through."""
    try: fn(*args, **kw)
    except S.StoreError as e: return str(e) or "refused"
    return None

def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while not cond():
        if time.time() >= end: return False
        time.sleep(0.02)
    return True

# --- a throwaway store
S = None
def use_store(name):
    """fw.store, on a fresh t/<name>.json (it reads $FW_DATA once, on import)."""
    global S
    os.makedirs("t", exist_ok=True)
    path = os.path.abspath(f"t/{name}.json")
    for f in (path, path[:-5] + ".loro"):
        if os.path.exists(f): os.remove(f)
    os.environ["FW_DATA"] = path
    from fw import store
    assert str(store.DATA_PATH) == path, "use_store before anything imports fw.store"
    S = store
    return store

def blk(i, content, title=None, entry=False, **more):
    """A block: content is text, a list of child ids, or a dict ({"quote": id}, {"image": f}, {"kind": …}, …)."""
    return {"id": i, "title": title, **({"entry": True} if entry else {}), "content": content, "words": 0,
            "created": T, "updated": T, **more}

def store(*blocks, version=17):
    """The store as just these blocks (written as schema `version`: before 11, a quote's mask is anchors into its
    target's draft; from 11, spans per block), migrated as fw does on every run."""
    old = {"entries": [b["id"] for b in blocks if b.get("entry")]} if version < 10 else {}
    json.dump({"schemaVersion": version, **old, "blocks": list(blocks)}, open(os.environ["FW_DATA"], "w"))
    for f in (S.LORO_PATH, S.CLIP_PATH):
        if os.path.exists(f): os.remove(f)
    S.forget()
    S.cmd_migrate(None)

def blocks(): return S.index(S.load_data())
def content(i): return blocks()[i]["content"]

def kids(i, b=None):
    """Block i's blocks as what they are: text, ("quote", its target), ("para", text, source), a list for a container."""
    b = b or blocks()
    def one(k):
        x = b[k]
        if S.quoted(x): return ("quote", S.quoted(x)[0])
        if S.paraphrases(x): return ("para", S.text_of(x), S.paraphrases(x))
        return kids(k, b) if S.children(x) else x["content"]
    return [one(k) for k in S.children(b[i])]

def state():
    """The store as it matters for undo: the pericopes, and every block's content."""
    d = S.load_data()
    return sorted(S.entry_ids(d)), {b["id"]: b["content"] for b in d["blocks"]}

def edit(fn):
    """One store write, fn(data, blocks) changing it in place."""
    return S.transact(S.editing(fn))

def png(path=None, w=4, h=4):
    """A plain grey picture, w × h pixels (written to `path`, if given); its bytes."""
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(b"\x00" + b"\x80" * w for _ in range(h)))) + chunk(b"IEND", b""))
    if path: open(path, "wb").write(data)
    return data

def loro_merge(base: dict, laptop: dict, other: dict) -> dict:
    """Block `base` in two machines' documents (the other machine's a copy of the laptop's), changed on each to `laptop` and
    `other`, then merged: the block as the merged document says it."""
    from fw import loro as L
    one = lambda b: {"schemaVersion": 17, "blocks": [copy.deepcopy(b)]}
    a = L.load(None, 1); L.write(a, one(base))
    b = L.load(L.snapshot(a), 2)
    L.write(a, one(laptop)); L.write(b, one(other))
    L.merge(a, L.snapshot(b))
    return L.to_data(a)["blocks"][0]
