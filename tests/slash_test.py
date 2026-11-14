# the / menu puts blocks in (at a line's start or after a space; mid-text they nest), Ctrl+/ acts on the block
import json, os, struct, sys, zlib
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, HOME, END, RIGHT, ENTER, ESC, MENU, QUIT as Q, UNDO as Z
S = F.use_store("t/slash.json", clean=True)
HOST, H1, X, SRC, S1 = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002", "20261001T100000-5000", "20261001T100000-5001"
def fresh():
    F.write_store([blk(HOST, [H1, X], "host"), blk(H1, "hello world"), blk(X, "end"), blk(SRC, [S1], "src"), blk(S1, "source text")],
                  [HOST, SRC], version=9)
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())
def kids(i, b=None):
    b = b or B()
    return [("quote", S.quoted(b[k])[0]) if S.quoted(b[k]) else ("image",) if S.image_of(b[k]) else kids(k, b) if S.children(b[k])
            else b[k]["content"] for k in S.children(b[i])]
def snap(): return json.dumps(sorted((b["id"], b["content"], b.get("entry", False)) for b in S.load_data()["blocks"]), default=str)
def open_(): return F.fw("host", rows=30, cols=60)
def at_hello(t): t.key(UP, HOME, RIGHT * 6)   # "hello |world"

fresh()
t = open_()
t.key(MENU)
check("Ctrl+/ acts on the block: Turn into a quote, no Quote a block", "Turn into a quote" in t.text() and "Quote a block" not in t.text(), t.text())
t.key(ESC, ENTER, MENU)
check("  on an empty line, nothing to act on", "nothing to do here" in t.text(), t.text())
t.key("/")
check("the / menu puts things in: Quote a block, Add a picture, no actions", "Quote a block" in t.text() and "Add a picture" in t.text()
      and "Turn into" not in t.text(), t.text())
t.key(ESC); t.key("and/or "); t.settle()
same("a / after a letter is just a slash", kids(HOST)[-1], "/and/or ")
t.key("/")
check("  after a space it opens the menu", "Quote a block" in t.text(), t.text())
t.key("usr"); t.settle()
same("  typing what no command is: it was writing, typed in", kids(HOST)[-1], "/and/or /usr")
t.key(Q, ESC); t.done()

fresh(); before = snap()
t = open_()
at_hello(t); t.key("/", ENTER, "src", ENTER); t.settle()
same("a quote put mid-text nests there, the text either side", kids(HOST), [["hello ", ("quote", SRC), "world"], "end"])
check("  the block keeps its id", S.children(B()[HOST])[0] == H1)
t.key("!"); t.settle()
same("  the cursor after it, at the rest of the text", kids(HOST), [["hello ", ("quote", SRC), "!world"], "end"])
t.key(Z, Z); t.settle()
same("^Z the typing, ^Z the quote: the store as it was", snap(), before)
t.key(Q, ESC); t.done()

fresh()
t = open_()
t.key(UP, END, " /", ENTER, "src", ENTER); t.settle()
same("at a block's end: the quote goes below it, no nesting", kids(HOST), ["hello world ", ("quote", SRC), "end"])
t.key(Q, ESC); t.done()
fresh()
t = open_()
t.key(UP, HOME, "/", ENTER, "src", ENTER); t.settle()
same("at its start: above it", kids(HOST), [("quote", SRC), "hello world", "end"])
t.key(Q, ESC); t.done()

fresh(); before = snap()
t = open_()
at_hello(t); t.key("/", ENTER, "a new thought", ENTER); t.settle()
check("+ new entry mid-text: in the new entry", "a new thought" in t.text(), t.text())
t.key(Q); t.settle()
k = kids(HOST)
check("  back: it's quoted where the cursor was, nested", k[0][0] == "hello " and k[0][1][0] == "quote" and k[0][2] == "world", k)
t.key(Z); t.settle()
same("  one ^Z: the quote, the nesting and the new entry gone, the store as it was", snap(), before)
t.key(Q, ESC); t.done()

def png(path, w, h):
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
PIC = os.path.abspath("t/pic.png"); png(PIC, 40, 20)
fresh(); before = snap()
t = F.fw("host", rows=30, cols=60, env={"FW_PICTURES": "0"})
at_hello(t); t.key("\x1b[200~" + PIC + "\x1b[201~"); t.settle()
same("a picture dropped mid-text nests there too", kids(HOST), [["hello ", ("image",), "world"], "end"])
t.key(Z); t.settle()
same("  one ^Z: the store as it was (but the picture's file)", snap(), before)
t.key(Q, ESC); t.done()
F.report("SLASH")
