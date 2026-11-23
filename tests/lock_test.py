# locked quotes (schema v17): Lock writing through, a quote's own toggle. Through a locked quote (and
# everything shown through it, at any depth) nothing is written: the bar says locked. The cursor still goes
# in, selecting, copying and Open it work, and the quote's own mask, top line and lock stay its holder's.
import copy, json, os, struct, sys, zlib
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, LEFT, HOME, END, ESC, BS, DEL, ENTER, MENU, QUIT as Q, UNDO as Z, REDO as Y
F.pyte.graphics.TEXT[2] = "+blink"   # (pyte has no dim: here SGR 2, dim, reads as blink, which fw never uses)
S = F.use_store("t/lock.json", clean=True)
import fw_migrate as M
SRC, S1, S2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
ME, X, QO, QL, ZZ = [f"20261001T100000-c00{i}" for i in range(5)]
DEEP, D1 = "20261001T100000-b000", "20261001T100000-b001"
CSRC, C1, CT, T1, QN, T2 = [f"20261001T100000-d00{i}" for i in range(6)]
CASC, QC = "20261001T100000-e000", "20261001T100000-e001"
OUT, O1, QI = "20261001T100000-f000", "20261001T100000-f001", "20261001T100000-f002"
OUTER, QU = "20261001T100000-f100", "20261001T100000-f101"
SENTER, CENTER, SLEFT = "\x1b[13;2u", "\x1b[13;5u", "\x1b[1;2D"
COPY, CUT, PASTE, CTRL_T, CTRL_K, CTRL_L, CTRL_O, CTRL_E = "\x03", "\x18", "\x16", "\x14", "\x0b", "\x0c", "\x0f", "\x05"
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}

def fresh(lock=False):
    F.write_store([blk(SRC, [S1, S2], "src"), blk(S1, "source one"), blk(S2, "source two"),
                   blk(ME, [X, QO, QL, ZZ], "mine"), blk(X, "my text"), blk(QO, {"quote": SRC}),
                   blk(QL, {"quote": SRC, **({"lock": True} if lock else {})}), blk(ZZ, "last"),
                   blk(DEEP, [D1], "deep"), blk(D1, "deep words"),
                   blk(CSRC, [C1, CT], "csrc"), blk(C1, "top words"), blk(CT, [T1, QN, T2]), blk(T1, "inner before"),
                   blk(QN, {"quote": DEEP}), blk(T2, "inner after"),
                   blk(CASC, [QC], "casc"), blk(QC, {"quote": CSRC, "lock": True}),
                   blk(OUT, [O1, QI], "out"), blk(O1, "outer text"), blk(QI, {"quote": DEEP, "lock": True}),
                   blk(OUTER, [QU], "outer"), blk(QU, {"quote": OUT})],
                  [SRC, ME, DEEP, CSRC, CASC, OUT, OUTER], version=9)
    S.cmd_migrate(None)
    open("t/mac.txt", "w").write("pasted")
    if os.path.exists(S.CLIP_PATH): os.remove(S.CLIP_PATH)
def B(): return S.index(S.load_data())
def text(i): return B()[i]["content"]
def locked(i): return S.quote_lock(B()[i])
def bar(t): return t.row(t.scr.lines - 1)
def open_(title, rows=40): return F.fw(title, rows=rows, cols=70, env=ENV)
def dim_at(t, words):
    y = t.find(words)
    return y is not None and t.cell(y, t.row(y).index(words)).blink
def rows_of(t, words): return [y for y in range(t.scr.lines - 1) if t.inside(y) == words]
def go(t, words, nth=0, at=0):
    """Click into the `nth` row showing `words`, `at` characters in (a click on a quote's text goes in)."""
    y = rows_of(t, words)[nth]
    x = t.row(y).index(words) + at
    t.key("\x1b[M" + chr(32) + chr(33 + x) + chr(33 + y) + "\x1b[M" + chr(35) + chr(33 + x) + chr(33 + y))
def where(t): return bar(t).split()[1]   # the bar's line:column
def png(path, w=4, h=4):
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(b"".join(b"\x00" + b"\x80" * w for _ in range(h))))
                           + chunk(b"IEND", b""))

# --- the shape: migration and schema
fresh()
d = json.load(open(os.environ["FW_DATA"]))
up = M.upgrade(copy.deepcopy({**d, "schemaVersion": 16}), now=S.now_local(), new_id=S.new_id)
check("v16 → v17: marked to be saved, the blocks as they were",
      M.SCHEMA_VERSION >= 17 and up["schemaVersion"] == M.SCHEMA_VERSION and M.behind({**d, "schemaVersion": 16}) and up["blocks"] == d["blocks"])
schema = S.load_schema()
check("the schema takes lock: true on a quote", not S.validate_instance(blk(QL, {"quote": SRC, "lock": True}), schema))
check("  only true (absent: unlocked)", S.validate_instance(blk(QL, {"quote": SRC, "lock": False}), schema)
      and S.validate_instance(blk(QL, {"quote": SRC, "lock": "yes"}), schema))
b = {"content": {"quote": SRC, "show": ["title"]}}; b = S.with_lock(b, True)
check("with_lock keeps the rest of the quote", b["content"] == {"quote": SRC, "show": ["title"], "lock": True}, b)
b = S.with_lock(b, False); check("  unlocking leaves no lock", b["content"] == {"quote": SRC, "show": ["title"]}, b)
lib = {QL: {"content": {"quote": SRC, "lock": True}}, QO: {"content": {"quote": SRC}}, QN: {"content": {"quote": DEEP}}}
same("locked_by: nothing open, writable", S.locked_by(lib, []), None)
same("  inside an unlocked quote, writable", S.locked_by(lib, [QO]), None)
same("  inside a locked one, locked by it", S.locked_by(lib, [QL]), QL)
same("  a quote inside a locked one: still locked by the outer (the cascade)", S.locked_by(lib, [QL, QN]), QL)
same("  a locked one inside an unlocked one: locked by the inner", S.locked_by(lib, [QO, QL]), QL)

# --- toggling it, from the menu: the label refreshes and it stays open; the top line marks it; dim
t = open_("mine")   # the cursor at the end of "last"
t.key(UP, MENU)
check("Ctrl+/ on a quote: Lock writing through, at the top level", "Lock writing through" in t.text(), t.text())
t.key("lock", ENTER); t.settle()
check("  locked: stored on the quote", locked(QL) and not locked(QO), (text(QL), text(QO)))
check("  the menu stays open, the label now Unlock", "Unlock writing through" in t.text(), t.text())
t.key(ESC)
check("  its top line: ⊘ (one column)", t.row(rows_of(t, "source one")[1] - 2).startswith("3 ┌─ ⊘ ──"), t.text())
ys = rows_of(t, "source one")
check("  its text dim; the other quote's not", len(ys) == 2 and not dim_at(t, "source one")
      and t.cell(ys[1], t.row(ys[1]).index("source one")).blink, t.text())
t.key(Z); t.settle()
check("^Z: unlocked again, one step", not locked(QL) and "⊘" not in t.text(), text(QL))
t.key(Y); t.settle()
check("^Y: locked again", locked(QL) and "⊘" in t.text(), text(QL))
t.key(CTRL_L); t.settle()
check("Ctrl+L on the quote selected: unlocks it", not locked(QL), text(QL))
t.key(CTRL_L); t.settle()
check("  and locks it", locked(QL), text(QL))

# --- through it: the cursor goes in and moves; every write is refused
before = (text(S1), text(S2), S.children(B()[SRC]))
go(t, "source two", 1, 3)
check("the cursor goes in", where(t) == "2:4", bar(t))
t.key(LEFT)
check("  and moves", where(t) == "2:3", bar(t))
check("  its text dim there too", t.cell(t.cursor()[0], t.cursor()[1]).blink, t.cursor())
for label, keys in [("typing", ("x",)), ("Backspace", (BS,)), ("Delete", (DEL,)), ("Enter", (ENTER,)),
                    ("Shift+Enter", (SENTER,)), ("Ctrl+Enter", (CENTER,)), ("a tab", ("\t",)),
                    ("paste", (PASTE,)), ("Turn into a quote (Ctrl+T)", (CTRL_T,)),
                    ("Backspace at a block's start (a join)", (HOME, BS)), ("/ (the insert menu)", (HOME, "/"))]:
    t.key(*keys); t.settle()
    check(f"  {label}: refused, the bar says locked", "locked" in bar(t) and (text(S1), text(S2), S.children(B()[SRC])) == before,
          (bar(t), text(S1), text(S2)))
check("  the cursor stayed in it", where(t) == "2:1", bar(t))
t.key(END, SLEFT, SLEFT, SLEFT)
t.key(CUT); t.settle()
check("  cut: refused", "locked" in bar(t) and text(S2) == "source two", (bar(t), text(S2)))
t.key(CTRL_K)
check("  a link (Ctrl+K): refused", "locked" in bar(t) and "link ›" not in t.text(), bar(t))
t.key(END, SLEFT, SLEFT, SLEFT, COPY)
check("  copying works", open("t/mac.txt").read() == "two" and "copied" in bar(t), (open("t/mac.txt").read(), bar(t)))
t.key(MENU)
menu = t.text()
check("  the menu: no Turn into…, Paraphrase it or links; the quote's own Unlock, mask and top line stay",
      "Turn into" not in menu and "Paraphrase" not in menu and "Link" not in menu and "Unlock writing through" in menu
      and "Create mask" in menu and "Its top line…" in menu, menu)
t.key(ESC, ESC)
check("Esc: the block selected whole", "block" in bar(t), bar(t))
t.key("x"); t.settle()
check("  typing on it: refused", "locked" in bar(t) and text(S2) == "source two", (bar(t), text(S2)))
t.key(BS); t.settle()
check("  Backspace on it: refused", "locked" in bar(t) and S.children(B()[SRC]) == [S1, S2], (bar(t), S.children(B()[SRC])))
t.key(CUT); t.settle()
check("  cut: refused", "locked" in bar(t) and S.children(B()[SRC]) == [S1, S2], bar(t))
t.key(COPY)
check("  copy: works", "copied" in bar(t), bar(t))
png("t/pic.png")
t.key(LEFT, END, PASTE_START + os.path.abspath("t/pic.png") + PASTE_END); t.settle()
check("dropping a picture into it: refused", "locked" in bar(t) and S.children(B()[SRC]) == [S1, S2], (bar(t), S.children(B()[SRC])))
t.key(Z); t.settle()
check("^Z inside: nothing written through it to undo", "nothing to undo" in bar(t) and (text(S1), text(S2)) == before[:2]
      and locked(QL), (bar(t), text(S2), text(QL)))

# --- the quote's own properties, from inside: top line, mask, lock
t.key(MENU, "title", ENTER, ESC); t.settle()
check("inside: Show its title works (the quote's own)", S.quote_show(B()[QL]) == ["title"] and "─ ⊘ src ─" in t.text(), (text(QL), t.text()))
t.key(CTRL_E)
check("  Ctrl+E: masking mode", "masking" in bar(t), bar(t))
t.key(HOME, "]", ESC); t.settle()
check("  a mask made on it, its source untouched", S.quoted(B()[QL])[1] is not None and (text(S1), text(S2)) == before[:2],
      (text(QL), text(S1), text(S2)))
t.key(Z); t.settle()
check("  ^Z: the mask edit undone, one step", S.quoted(B()[QL])[1] is None and locked(QL), text(QL))
t.key(Y); t.settle()
check("  ^Y: back", S.quoted(B()[QL])[1] is not None, text(QL))
t.key(MENU, "remove mask", ENTER); t.settle()
check("  Remove mask works too", S.quoted(B()[QL])[1] is None and "lock" in text(QL), text(QL))
t.key(MENU, "unlock", ENTER, ESC); t.settle()
check("inside: Unlock writing through", not locked(QL), text(QL))
t.key("y"); t.settle()
check("  then typing goes through", "y" in text(S1) + text(S2) and "locked" not in bar(t), (text(S1), text(S2)))
t.key(MENU, "lock w", ENTER, ESC); t.settle()
check("  locking it again from inside", locked(QL), text(QL))
t.key("n"); t.settle()
check("  refused again", "locked" in bar(t) and (text(S1), text(S2)) == ("source oney", "source two"), (text(S1), text(S2)))
t.key(Z); t.settle()
check("  ^Z unlocks it (one step)", not locked(QL) and "y" in text(S1) + text(S2), (text(QL), text(S1), text(S2)))
t.key(Z); t.settle()
check("  ^Z again: the typing undone, now it's unlocked", (text(S1), text(S2)) == before[:2], (text(S1), text(S2)))
t.key(CTRL_L); t.settle()
check("Ctrl+L inside: locks the quote you're in", locked(QL), text(QL))
t.close()

# --- another quote of the same source stays writable; Open it edits the source
fresh(lock=True)
t = open_("mine")
go(t, "source two", 0, 3)
t.key("z"); t.settle()
check("another quote of the same source: writable", text(S2) == "souzrce two" and "locked" not in bar(t), (bar(t), text(S2)))
t.key(Z); t.settle()
go(t, "source two", 1, 3)
t.key(CTRL_O); t.settle()
check("Open it inside a locked quote: its source, as the pericope", "title      src" in t.text() and "my text" not in t.text(), t.text())
t.key("!"); t.settle()
check("  editable there as usual", text(S2) == "sou!rce two" and "locked" not in bar(t), (text(S2), bar(t)))
t.key(Z); t.settle()
t.close()

# --- deleting the locked quote itself, selected from outside, works; copy/paste keeps the lock
fresh(lock=True)
t = open_("mine")
t.key(UP, COPY)
check("copying the locked quote, selected", "copied" in bar(t), bar(t))
t.key(DOWN, END, PASTE); t.settle()
new = [k for k in S.subtree(B(), ME) if S.quoted(B()[k]) and k not in (QO, QL)]
check("  ^V: a live quote of it, locked too", len(new) == 1 and S.quoted(B()[new[0]])[0] == SRC and locked(new[0]),
      [text(k) for k in S.children(B()[ME])])
t.key(Z); t.settle()
check("  ^Z: gone again", S.children(B()[ME]) == [X, QO, QL, ZZ], S.children(B()[ME]))
go(t, "last")
t.key(UP, BS); t.settle()
check("Backspace on the locked quote selected from outside: it goes (the quote, not its source)",
      S.children(B()[ME]) == [X, QO, ZZ] and text(S2) == "source two", S.children(B()[ME]))
t.key(Z); t.settle()
check("  ^Z: back, still locked", S.children(B()[ME]) == [X, QO, QL, ZZ] and locked(QL), S.children(B()[ME]))
t.close()

# --- the cascade: what shows through a locked quote is locked, at any depth: blocks in a container, a quote in it
fresh()
t = open_("casc")
check("the cascade: all of it dim, the quote inside it too", dim_at(t, "top words") and dim_at(t, "inner before")
      and dim_at(t, "deep words"), t.text())
check("  only the locked quote marked", t.text().count("⊘") == 1, t.text())
go(t, "inner after", 0, 2)
t.key("q"); t.settle()
check("  a block in a container inside it: locked", "locked" in bar(t) and text(T2) == "inner after", (bar(t), text(T2)))
t.key(UP)
check("  the quote inside it, selected", where(t) == "3:1" and "deep" in bar(t), bar(t))
t.key(MENU)
check("  on the quote inside it: no lock toggle, no top line, no Turn into text (they'd be its source's)",
      "writing through" not in t.text() and "Its top line" not in t.text() and "Turn into text" not in t.text()
      and "Open it" in t.text(), t.text())
t.key(ESC, CTRL_L)
check("  Ctrl+L on it: locked", "locked" in bar(t) and not locked(QN), bar(t))
t.key(BS); t.settle()
check("  Backspace on it: refused (it's its source's block)", "locked" in bar(t) and QN in S.children(B()[CT]), bar(t))
go(t, "deep words", 0, 2)
t.key("q"); t.settle()
check("  inside the quote inside it: locked too", "locked" in bar(t) and text(D1) == "deep words", (bar(t), text(D1)))
t.key(MENU)
check("    its menu: no lock toggle there either", "writing through" not in t.text() and "Create mask" not in t.text(), t.text())
t.key(ESC, CTRL_E)
check("    nor its mask (Ctrl+E): locked", "locked" in bar(t), bar(t))
t.close()

# --- a locked quote inside an unlocked one locks itself and what's under it
t = open_("outer")
check("a locked quote inside an unlocked one: its text dim, the outer's not", dim_at(t, "deep words") and not dim_at(t, "outer text"), t.text())
go(t, "outer text", 0, 2)
t.key("w"); t.settle()
check("  the outer quote's own text: writable", text(O1) == "ouwter text", text(O1))
go(t, "deep words", 0, 2)
t.key("w"); t.settle()
check("  inside the locked one: refused", "locked" in bar(t) and text(D1) == "deep words", (bar(t), text(D1)))
t.key(MENU)
check("  its menu there: Unlock writing through (its holder is writable)", "Unlock writing through" in t.text(), t.text())
t.key(ESC, CTRL_L); t.settle()
check("  Ctrl+L from inside it unlocks it", not locked(QI), text(QI))
t.key("w"); t.settle()
check("  then writing goes through", text(D1) == "dewep words", text(D1))
t.close()
F.report("LOCK")
