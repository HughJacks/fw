# the store as a Loro document (fw.loro): two machines' copies merge. Spans (a link's `at`, a quote's masks) are kept
# as cursors on their first and last character, so an edit merged from the other machine moves them with their text.
# Pure: fw.loro on documents in memory; the store's merge (store.merge_file, `python -m fw.store merge`) on two
# throwaway stores, as a sync between two machines does, with a store in use on one of them.
import copy, json, os, shutil, subprocess, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same
from fw import loro as L

T = "2026-10-01T10:00:00-04:00"
X, Y, E, Q, P = "20261001T100000-aaaa", "20261001T100000-bbbb", "20261001T100000-e000", "20261001T100000-cccc", "20261001T100000-f000"
def blk(i, content, **more):
    return {"id": i, "title": None, "content": content, "words": 0, "created": T, "updated": T, **more}
def data():
    return {"schemaVersion": 17, "blocks": [
        blk(E, [X, Y], entry=True),
        blk(X, "see the LINK here", links=[{"to": P, "at": [8, 12]}]),
        blk(Y, "aaa SHOWN bbb"),
        blk(P, [Q], entry=True),
        blk(Q, {"quote": E, "mask": {Y: [[4, 9]], X: [[0, 3]]}})]}
def by(d): return {b["id"]: b for b in d["blocks"]}
def edit(d, i, at, text):
    """Text inserted in block i at `at`, its own links and every mask on it moved as fw moves them."""
    d = copy.deepcopy(d); b = by(d)
    b[i]["content"] = b[i]["content"][:at] + text + b[i]["content"][at:]
    move = lambda s: [s[0] + len(text) * (s[0] >= at), s[1] + len(text) * (s[1] > at)]
    for l in b[i].get("links") or []:
        l["at"] = move(l["at"])
    for q in d["blocks"]:
        if isinstance(q["content"], dict) and i in q["content"].get("mask", {}):
            q["content"]["mask"][i] = [move(s) for s in q["content"]["mask"][i]]
    return d
def link_text(d, i):
    b = by(d)[i]; s, e = b["links"][0]["at"]; return b["content"][s:e]
def shown(d, i):
    m = by(d)[Q]["content"]["mask"][i]; return [by(d)[i]["content"][s:e] for s, e in m]
def two():
    a = L.load(None, 1); L.write(a, data())
    return a, L.load(L.snapshot(a), 2)
def merged(a, b):
    L.merge(a, L.snapshot(b)); L.merge(b, L.snapshot(a))
    return L.to_data(a), L.to_data(b)

a, b = two()
same("written and read back: the same data", L.to_data(a), data())
raw = a.get_deep_value()["blocks"]
check("a link's span kept with cursors", len(raw[X]["links"][0]["at"]) == 4, raw[X]["links"])
check("  a mask's too", len(raw[Q]["value"]["mask"][Y][0]) == 4, raw[Q]["value"])
was = L.snapshot(a); L.write(a, data())
same("written again unchanged: no new change in the document", a.get_deep_value(), L.load(was, 9).get_deep_value())

# both machines type before the link and the shown text: each moves its own copy's spans; merged, both moves count
a, b = two()
L.write(a, edit(edit(data(), X, 0, "A: "), Y, 0, "A: "))
L.write(b, edit(edit(data(), X, 4, "B "), Y, 2, "BB"))
da, db = merged(a, b)
same("both typed before a link: merged, the link still on its text", link_text(da, X), "LINK")
same("  and the same on both machines", da, db)
same("both typed before a masked span: it still shows its text", shown(da, Y), ["SHOWN"])
same("  a span from the start of a text stays on its text, not what was typed before it", shown(da, X), ["see"])

# one machine types before the link, the other changes the links (a second one): its cursors land right
a, b = two()
L.write(a, edit(data(), X, 0, "typed first, "))
d = data(); by(d)[X]["links"].append({"to": E, "at": [0, 3]})
L.write(b, d)
da, db = merged(a, b)
same("text typed on one machine, the links changed on the other: both links on their text",
     [by(da)[X]["content"][s:e] for s, e in (l["at"] for l in by(da)[X]["links"])], ["LINK", "see"])
check("  (the second on the text it was made on, after what the other typed)", da == db, (da, db))

# one machine types before the shown text, the other changes the mask
a, b = two()
L.write(a, edit(data(), Y, 0, "zzz "))
d = data(); by(d)[Q]["content"]["mask"][Y] = [[0, 3], [4, 9]]
L.write(b, d)
da, db = merged(a, b)
same("typed before a mask on one machine, the mask changed on the other: it shows what was meant",
     shown(da, Y), ["aaa", "SHOWN"])

# typing at a span's edges on the other machine stays outside it; deleting its last character
a, b = two()
L.write(b, edit(edit(data(), X, 12, "xx"), X, 8, "yy"))
da, _ = merged(a, b)
same("typed at both edges of a link on the other machine: outside it", link_text(da, X), "LINK")
a, b = two()
d = data(); by(d)[X]["content"] = "see the LIN here"; by(d)[X]["links"][0]["at"] = [8, 11]
L.write(b, d)
d = edit(data(), X, 0, "> ")
L.write(a, d)
da, _ = merged(a, b)
same("its last character deleted on one machine, text typed before it on the other", link_text(da, X), "LIN")

# a document written before cursors: its spans get them on the next write, and mean the same
a = L.load(None, 1); L.write(a, data())
for k, v in ((X, None), (Q, None)):
    m = a.get_map("blocks").get_or_create_container(k, L.loro.LoroMap())
    if k == X: m.insert("links", [{"to": P, "at": [8, 12]}])
    else: m.insert("value", {"quote": E, "mask": {Y: [[4, 9]], X: [[0, 3]]}})
a.commit()
check("written before cursors: read as the numbers", L.to_data(a) == data())
L.write(a, data())
raw = a.get_deep_value()["blocks"]
check("  the next write gives them cursors", len(raw[X]["links"][0]["at"]) == 4 and len(raw[Q]["value"]["mask"][Y][0]) == 4, raw[X])
same("  meaning the same", L.to_data(a), data())

# through the store: python -m fw.store merge on two throwaway stores
here = os.path.abspath("t/two"); shutil.rmtree(here, ignore_errors=True)
for side in ("laptop", "other"):
    os.makedirs(f"{here}/{side}")
json.dump(data(), open(f"{here}/laptop/freewrites.json", "w"))
def store(side, *args, code=None):
    env = {**os.environ, "FW_DATA": f"{here}/{side}/freewrites.json"}
    return subprocess.run([sys.executable, "-c", code] if code else [sys.executable, "-m", "fw.store", *args], env=env, capture_output=True, text=True)
r = store("laptop", "migrate"); check("migrate makes the document", os.path.exists(f"{here}/laptop/freewrites.loro"), r.stderr)
shutil.copy(f"{here}/laptop/freewrites.loro", f"{here}/other/freewrites.loro")
SAVE = "import json\nfrom fw import store as S\nd = json.load(open('{f}'))\nd['blocks'] = S.masks_in(d['blocks'])\nS.save_data(d)"
for side, d in (("laptop", edit(data(), X, 0, "laptop: ")), ("other", edit(data(), X, 4, "other "))):
    f = f"{here}/{side}/want.json"; json.dump(d, open(f, "w"))
    r = store(side, code=SAVE.format(f=f)); check(f"  saved on the {side}", r.returncode == 0, r.stderr)
r1 = store("laptop", "merge", f"{here}/other/freewrites.loro")
r2 = store("other", "merge", f"{here}/laptop/freewrites.loro")
lap, other = (json.load(open(f"{here}/{s}/freewrites.json")) for s in ("laptop", "other"))
check("merge both ways: the same store", lap == other and r1.returncode == r2.returncode == 0, (r1.stderr, r2.stderr))
same("  the link on its text, both edits in", (link_text(lap, X), by(lap)[X]["content"]), ("LINK", "laptop: see other the LINK here"))

# a picture held in a block, taken out by both machines on their own (store.pictures_apart): merged, one quote
PIC, H = "20261001T100000-dddd", "20261001T100000-d000"
held = {"schemaVersion": 17, "blocks": [blk(H, [X, PIC], entry=True), blk(X, "words"), blk(PIC, {"image": "0123456789abcdef.png"})]}
for side in ("laptop", "other"):
    shutil.rmtree(f"{here}/{side}", ignore_errors=True); os.makedirs(f"{here}/{side}")
d = L.load(None, 1); L.write(d, held); open(f"{here}/laptop/freewrites.loro", "wb").write(L.snapshot(d))
shutil.copy(f"{here}/laptop/freewrites.loro", f"{here}/other/freewrites.loro")   # (one shared history, the picture still held)
for side in ("laptop", "other"):
    r = store(side, "migrate"); check(f"  the {side} takes it out on its own", r.returncode == 0, r.stderr)
r1 = store("laptop", "merge", f"{here}/other/freewrites.loro")
r2 = store("other", "merge", f"{here}/laptop/freewrites.loro")
lap, other = (json.load(open(f"{here}/{s}/freewrites.json")) for s in ("laptop", "other"))
quotes = [b["id"] for b in lap["blocks"] if b["content"] == {"quote": PIC}]
check("a picture taken out on both machines, merged: the same store", lap == other and r1.returncode == r2.returncode == 0, (r1.stderr, r2.stderr))
same("  one quote of it, once in its holder, the picture a pericope", (len(quotes), by(lap)[H]["content"], by(lap)[PIC].get("entry")),
     (1, [X, quotes[0] if quotes else None], True))


# a sync while a store is in use here: the other machine's document merged in under it; what's written here after builds on it
S = F.use_store("here")
E1, E2 = "20261101T100000-a000", "20261101T100000-a001"
F.store(F.blk(E1, [E2], "Alpha", entry=True), F.blk(E2, "alpha text"))
other = os.path.abspath("t/other"); shutil.rmtree(other, ignore_errors=True); os.makedirs(other)
shutil.copy(S.LORO_PATH, f"{other}/freewrites.loro")   # (one shared history, the other machine its own peer)
def on_mini(code):
    r = subprocess.run([sys.executable, "-c", "from fw import store as S\n" + code], env={**os.environ, "FW_DATA": f"{other}/freewrites.json"},
                       capture_output=True, text=True)
    check("  (written on the other machine)", r.returncode == 0, r.stderr)
on_mini("S.cmd_migrate(None)")
data, seen = S.load_versioned()
draft = S.block_draft(S.index(data), E1)
on_mini(f"S.transact(S.editing(lambda d, b: b[{E2!r}].update(content='alpha from the other machine')))")
S.merge_file(f"{other}/freewrites.loro")
same("merged in: the other machine's edit here", S.own_text(F.blocks(), E1), "alpha from the other machine")
S.commit(E1, draft.replace("alpha text", "alpha text and the laptop"), [], at=seen)
same("  a save here from before the merge (its version): merged with it, not over it", S.own_text(F.blocks(), E1), "alpha from the other machine and the laptop")
F.report()
