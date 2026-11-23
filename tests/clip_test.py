# the rich clipboard: what's copied keeps its links, masks, top lines and nesting, across sessions
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, ESC, QUIT as Q, UNDO as Z
S = F.use_store("t/clip.json", clean=True)
SRC, S1, QS, CT, T1, QT, T2 = ("20261001T100000-5000", "20261001T100000-5001", "20261001T100000-5002",
                               "20261001T100000-5003", "20261001T100000-5004", "20261001T100000-5005",
                               "20261001T100000-5006")
DEST, D1 = "20261001T100000-d000", "20261001T100000-d001"
GARDEN, G1 = "20261001T100000-9000", "20261001T100000-9001"
OLD, O1 = "20261001T100000-0000", "20261001T100000-0001"
LINKER, L1 = "20261001T100000-1000", "20261001T100000-1001"
SUP, SLEFT, COPY, CUT, PASTE, STATIC, REDO = "\x1b[1;2A", "\x1b[1;2D", "\x03", "\x18", "\x16", "\x1b[118;6u", "\x19"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}  # never the real clipboard
GARDEN_AT = [8, 14]   # "garden" in "see the garden here"
def fresh():
    old = [blk(OLD, [O1], "old note"), blk(O1, "old text is long")]
    d = S.block_draft({b["id"]: b for b in old}, OLD)
    linked = lambda i, text: {**blk(i, text), "links": [{"to": GARDEN, "at": GARDEN_AT}]}
    F.write_store([blk(SRC, [S1, QS, CT], "src"), linked(S1, "see the garden here"),
                   blk(QS, {"quote": OLD, "mask": [d.index("text"), d.index("text") + 4], "show": ["title"]}),
                   blk(CT, [T1, QT, T2]), blk(T1, "before"), blk(QT, {"quote": OLD}), blk(T2, "after"),
                   blk(DEST, [D1], "dest"), blk(D1, "dest text"),
                   blk(GARDEN, [G1], "garden"), blk(G1, "flowers"),
                   blk(LINKER, [L1], "linker"), linked(L1, "see the garden here"), *old],
                  [SRC, DEST, GARDEN, OLD, LINKER], version=9)
    S.cmd_migrate(None)
    for f in ("t/mac.txt", S.CLIP_PATH):
        if os.path.exists(f): os.remove(f)
def B(): return S.index(S.load_data())
def shape(i, b=None):
    """A block as what it is, ids left out: text (with its links), a quote's content, or a list of those."""
    b = b or B()
    c = b[i]["content"]
    if isinstance(c, list): return [shape(k, b) for k in c]
    if isinstance(c, dict): return {k: v for k, v in c.items() if k != "quote"} | {"of": c["quote"]}
    return (c, [{k: v for k, v in l.items() if k != "created"} for l in b[i].get("links", [])])   # (link dates: backlink_test)
def bar(t): return t.row(t.scr.lines - 1)
def open_(title): return F.fw(title, rows=30, cols=70, env=ENV)

fresh()
t = open_("src")   # the cursor starts at the end of "after", in the container
t.key(ESC, SUP, SUP)
check("three blocks selected whole: text with a link, a masked quote, a container", "blocks 1–3" in bar(t), bar(t))
t.key(COPY); t.key(Q, ESC); t.done()
check("the Mac clipboard gets their text", open("t/mac.txt").read() == "see the garden here\n\n…text…\n\nbefore\n\nold text is long\n\nafter", open("t/mac.txt").read())
check("  and fw keeps them as data, beside the store", json.load(open(S.CLIP_PATH))["blocks"][0]["links"] == [{"to": GARDEN, "at": GARDEN_AT}])

t = open_("dest")   # another session, another entry: the cursor at the end of "dest text"
t.key(STATIC); t.settle()   # (in its text: inside it)
want = [[("dest text", []), ("see the garden here", [{"to": GARDEN, "at": GARDEN_AT}]), ("…text…", []),
         [("before", []), ("old text is long", []), ("after", [])]]]
same("^⇧V in another session: static copies, the link and the nesting kept, quotes as the text they showed", shape(DEST), want)
check("  new blocks, not the old ones", not set(S.subtree(B(), DEST)) & {S1, QS, CT}, S.subtree(B(), DEST))
check("  the source untouched", shape(SRC) == [("see the garden here", [{"to": GARDEN, "at": GARDEN_AT}]), {"mask": shape(QS)["mask"], "show": ["title"], "of": OLD}, [("before", []), {"of": OLD}, ("after", [])]], shape(SRC))
n = len(B())
t.key(Z); t.settle()
check("^Z takes the paste back out, store and all", shape(DEST) == [("dest text", [])] and len(B()) == n - 7, (shape(DEST), len(B()), n))
t.key(REDO); t.settle()
same("^Y puts it back, links too", shape(DEST), want)
t.key(Z); t.settle()
t.key(PASTE); t.settle()
same("^V: a live quote of each block copied (a quote copied: a copy of it, mask and top line too)", shape(DEST),
     [[("dest text", []), {"of": S1}, {"mask": shape(QS)["mask"], "show": ["title"], "of": OLD}, {"of": CT}]])
check("  drawn: the masked quote with its title, the container's quote inside its own", "─ old note ─" in t.text() and "…text…" in t.text() and "before" in t.text(), t.text())
t.key(Q, ESC); t.done()
t = open_("src")
t.key(ESC, SUP, SUP, "\x1b[H"); t.key("new "); t.settle()   # (the selection gone; typing at the start of "see the garden here")
t.key(Q, ESC); t.done()
t = open_("dest")
check("  live: an edit at the source shows in the quote", "new see the garden here" in t.text(), t.text())
t.key(Q, ESC); t.done()

# cut, then ^V: the blocks themselves move, their quotes elsewhere live throughout
fresh()
QD = "20261001T100000-d0aa"
def put_quote(data, blocks):   # a quote of S1, the block itself (as ^V of it makes)
    S.add_block(data, blocks, QD, {"quote": S1}); blocks[DEST]["content"].append(QD)
S.transact(S.editing(put_quote))
check("(a quote of the block in dest)", {"of": S1} in shape(DEST)[0] if isinstance(shape(DEST)[0], list) else {"of": S1} in shape(DEST), shape(DEST))
t = open_("src")
t.key(ESC, SUP, SUP, CUT); t.settle()
check("cut: gone from the source", shape(SRC) in ([], [("", [])]), shape(SRC))
check("  but kept while the clipboard holds them: the quote of it elsewhere still a quote", S1 in B() and any(S.quoted(b) and S.quoted(b)[0] == S1 for b in B().values()), [b["content"] for b in B().values() if S.quoted(b)])
t.key(Q, ESC); t.done()
t = open_("linker")   # at the end of "see the garden here"
t.key(PASTE); t.settle()
same("^V after a cut moves them: the same blocks, here now", S.children(B()[S.children(B()[LINKER])[0]])[1:], [S1, QS, CT])
check("  the quote of it elsewhere still live, of the same block", any(S.quoted(b) and S.quoted(b)[0] == S1 for b in B().values()))
t.key(PASTE); t.settle()
check("^V again: they're placed now, so quotes of them", sum(1 for b in B().values() if S.quoted(b) and S.quoted(b)[0] == S1) == 2)
t.key(Z, Z); t.settle()
check("^Z twice: back out of linker, loose, still kept for the clipboard", S1 in B() and S.loose(B(), S1) and S1 not in S.subtree(B(), LINKER), S.subtree(B(), LINKER))
t.key(Q, ESC); t.done()

# a span of text keeps its link
fresh()
t = open_("linker")   # at the end of "see the garden here"
t.key(*[SLEFT] * 11, COPY); t.key(Q, ESC); t.done()   # "garden here"
t = open_("dest")
t.key(" ", PASTE); t.settle()
same("a span pasted keeps its link, moved to where it lands", shape(DEST), [("dest text garden here", [{"to": GARDEN, "at": [10, 16]}])])
t.key(Z); t.settle()
same("  ^Z: text and link gone", shape(DEST), [("dest text ", [])])
t.key(Q, ESC); t.done()

# once something else is on the Mac clipboard, a paste is just that text
open("t/mac.txt", "w").write("plain words")
t = open_("dest")
t.key(PASTE); t.settle()
same("copied elsewhere since: a plain paste", shape(DEST), [("dest text plain words", [])])
t.key(Q, ESC); t.done()

# cut and pasted back: one container, its quote still nested, the same block
fresh()
t = open_("src")
t.key(ESC, CUT); t.settle()
check("cutting the container takes it out", len(shape(SRC)) == 2, shape(SRC))
t.key(PASTE); t.settle()
same("  pasting it back (after the quote the cursor was left on): nested as it was", shape(SRC)[-1], [("before", []), {"of": OLD}, ("after", [])])
check("  the same container, moved", CT in S.subtree(B(), SRC), S.subtree(B(), SRC))
t.key(Q, ESC); t.done()
F.report("CLIP")
