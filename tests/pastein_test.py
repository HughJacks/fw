# pasting blocks into a block: it splits at the cursor and holds them, to any depth
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, ESC, QUIT as Q, UNDO as Z
S = F.use_store("t/pastein.json", clean=True)
HOST, H1, X = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
SRC, S1, S2 = "20261001T100000-5000", "20261001T100000-5001", "20261001T100000-5002"
G, G1 = "20261001T100000-9000", "20261001T100000-9001"
QH, QQ, QX, P = "20261001T100000-c000", "20261001T100000-c001", "20261001T100000-c002", "20261001T100000-d000"
SUP, COPY, PASTE = "\x1b[1;2A", "\x03", "\x1b[118;6u"   # (^⇧V: static copies, whose nesting this is about)
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}
def fresh():
    F.write_store([blk(HOST, [H1, X], "host"), {**blk(H1, "hello world"), "links": [{"to": G, "at": [6, 11]}]}, blk(X, "end"),
                   blk(SRC, [S1, S2], "src"), blk(S1, "pasted one"), blk(S2, "pasted two"), blk(G, [G1], "g"), blk(G1, "gee"),
                   blk(QH, [QQ, QX], "qhost"), blk(QQ, {"quote": P}), blk(QX, "below"), blk(P, "plain words", "Plain")],
                  [HOST, SRC, G, QH, P], version=9)
    S.cmd_migrate(None)
    for f in ("t/mac.txt", S.CLIP_PATH):
        if os.path.exists(f): os.remove(f)
def B(): return S.index(S.load_data())
def kids(i, b=None):
    b = b or B()
    return [("quote", S.quoted(b[k])[0]) if S.quoted(b[k]) else kids(k, b) if S.children(b[k]) else b[k]["content"]
            for k in S.children(b[i])]
def text_with_links(b, i): return [(b[k]["content"], b[k].get("links", [])) for k in S.subtree(b, i) if isinstance(b[k]["content"], str)]
def open_(title, rows=30): return F.fw(title, rows=rows, cols=60, env=ENV)
def copy_src():
    t = open_("src")   # at the end of "pasted two"
    t.key(ESC, SUP, COPY); t.key(Q, ESC); t.done()

fresh(); copy_src()
before = json.dumps(S.load_data()["blocks"], sort_keys=True)
t = open_("host")   # at the end of "end"
t.key(UP, PASTE); t.settle()   # up: into "hello world", 3 in ("hel|lo world")
same("pasted in a block's text: it splits at the cursor and holds its text either side and them",
     kids(HOST), [["hel", "pasted one", "pasted two", "lo world"], "end"])
b = B()
same("  its link went with its text, into the block after the cursor", [tl for tl in text_with_links(b, H1) if tl[1]], [("lo world", [{"to": G, "at": [3, 8]}])])
check("  the block it went into keeps its id, now holding the others", S.children(b[HOST])[0] == H1 and len(S.children(b[H1])) == 4)
t.key(PASTE); t.settle()   # the cursor at the end of "pasted two", inside H1: a level deeper
deep = [["hel", "pasted one", ["pasted two", "pasted one", "pasted two"], "lo world"], "end"]
same("pasted again, in a block inside it: nested a level deeper", kids(HOST), deep)
rows = t.text()
check("  drawn: a box in a box in a box", any(r.startswith("  │││") or "│││" in r[:6] for r in rows.split("\n")) and "┌" in rows, rows)
t.key(Q, ESC); t.done()
t = open_("host")
t.settle()
same("reopened: the nesting is just as it was", kids(HOST), deep)
check("  and it draws the same", t.text().split("\n")[4:20] == rows.split("\n")[4:20], t.text())
t.key(Z, Z); t.settle()   # (a fresh session: nothing to undo here)
t.key(Q, ESC); t.done()

fresh(); copy_src()
before = json.dumps(sorted((b["id"], b["content"], b.get("links")) for b in S.load_data()["blocks"]), default=str)
t = open_("host")
t.key(UP, PASTE); t.settle()
t.key(Z); t.settle()
after = json.dumps(sorted((b["id"], b["content"], b.get("links")) for b in S.load_data()["blocks"]), default=str)
check("^Z after a paste into a block: the store as it was, the block and its link too", after == before, (kids(HOST), after == before))
t.key(Q, ESC); t.done()

t = open_("qhost")   # at the end of "below"
t.key(UP, UP, PASTE); t.settle()   # into the quote of a plain block, 5 in ("plain| words")
same("inside a quote of one block of text: its text either side and them, side by side (no container: the block is the quote's)",
     kids(P), ["plain", "pasted one", "pasted two", " words"])
t.key(Q, ESC); t.done()
F.report("PASTEIN")
