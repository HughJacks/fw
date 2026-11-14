# home's search is the quote search: blocks inside pericopes found under where they live, Enter opens
# there, at the block; places that quote a match listed below it; a paraphrase family shown together
import os, struct, sys, zlib
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, ESC, BS, ENTER, QUIT as Q
S = F.use_store("t/homesearch.json", clean=True)
NOTES, N1, N2, N3 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002", "20261001T100000-a003"
SIDE, S1, QB = "20261002T100000-b000", "20261002T100000-b001", "20261002T100000-b002"
PARA, P1 = "20261003T100000-c000", "20261003T100000-c001"
LATER, L1 = "20261004T100000-d000", "20261004T100000-d001"

def png(path, w, h):
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
png("t/pic.png", 20, 10)
F.write_store([blk(NOTES, [N1, N2, N3], "notes"), blk(N1, "first idea"), blk(N2, "the aura of the room"), blk(N3, "x"),
               blk(SIDE, [S1, QB], "sidebar"), blk(S1, "intro words"), blk(QB, {"quote": N2}),
               blk(PARA, [P1], "para"), blk(P1, "a glow in the room"),
               blk(LATER, [L1], "later"), blk(L1, "the room hums")], [NOTES, SIDE, PARA, LATER], version=9)
S.cmd_migrate(None)
name = S.add_image("t/pic.png")
def setup(data, blocks):
    blocks[N3]["content"] = {"image": name}
    blocks[P1]["paraphrases"] = N2   # P1 says N2 another way, and L1 says P1: one family of three
    blocks[L1]["paraphrases"] = P1
S.transact(setup)
B = S.index(S.load_data())
same("families: the paraphrase marks joined, both ways, transitively", S.families(B).get(L1), [N2, P1, L1])
same("  a block in none has no family", S.families(B).get(N1), None)

def bar(t): return t.row(t.scr.lines - 1)
def rows(t): return [l[3:].rstrip(" │") for l in t.text().splitlines()]
def at(t, text): return next((n for n, l in enumerate(rows(t)) if l.startswith(text)), None)
def home():
    return F.fw("open", rows=30, env={"FW_PICTURES": "0"})
def select(t, text):
    """Move the selection down from the first result onto the row starting with `text`."""
    for _ in range(12):
        y = next((n for n, l in enumerate(t.text().splitlines()) if text in l), None)
        if y is not None and t.cell(y, 3).reverse:
            return True
        t.key(DOWN)
    return False

t = home()
check("home with nothing typed lists pericopes only", "notes" in t.text() and "the aura of the room" not in t.text(), t.text())
check("  and counts them as pericopes", "4 pericopes" in t.text() and "+ new pericope" in t.text(), t.row(0))
t.key(*"aura")
check("typing shows a matching block, indented under where it lives", "notes" in t.text() and "  · the aura of the room" in t.text(), t.text())
check("  its paraphrase family right under it, ≈", at(t, "    ≈ a glow in the room") == at(t, "  · the aura of the room") + 1
      and at(t, "    ≈ the room hums") == at(t, "  · the aura of the room") + 2, t.text())
check("  the place that quotes it, below the original", (at(t, "  “the aura of the room” quoted in sidebar") or 0) > at(t, "    ≈ the room hums"), t.text())
select(t, "· the aura of the room")
check("  the bottom line says Enter opens it where it lives", "open it where it lives" in t.text(), t.text())
t.key("\x04")
check("  ^D on a block inside a pericope deletes nothing", "delete '" not in t.text() and len(S.entry_ids(S.load_data())) == 4, bar(t))
t.key(ENTER)
check("Enter on it opens the pericope it lives in", t.until(lambda: "first idea" in t.text()) and "· notes" not in bar(t), t.text())
check("  the cursor at the block", " 2:1" in bar(t), bar(t))
t.key(Q)
check("^Q: home again", t.until(lambda: "open ›" in t.text()), t.text())
t.key(*"aura")
check("  a place that quotes it, selected, says Enter opens it at the quote", select(t, "quoted in sidebar") and "at the quote" in t.text(), t.text())
t.key(ENTER)
check("Enter on the place opens it, at the quote", t.until(lambda: "intro words" in t.text()) and " 2:" in bar(t), bar(t))
t.key(Q); t.until(lambda: "open ›" in t.text())
t.key(*"aura")
select(t, "≈ the room hums"); t.key(ENTER)
check("Enter on a paraphrase sibling opens where it lives", t.until(lambda: "the room hums" in t.text() and "open ›" not in t.text()) and " 1:1" in bar(t), bar(t))
t.key(Q); t.until(lambda: "open ›" in t.text())
t.key(*"glow")
check("a match on another member shows the same family, it first", at(t, "  · a glow in the room") is not None
      and at(t, "    ≈ the aura of the room") == at(t, "  · a glow in the room") + 1, t.text())
t.key(BS, BS, BS, BS, *"pict")
check("a picture is found, under where it lives", "  · picture" in t.text(), t.text())
select(t, "· picture"); t.key(ENTER)
check("  Enter opens its pericope at it", t.until(lambda: "first idea" in t.text()) and " 3:" in bar(t), bar(t))
t.key(Q); t.until(lambda: "open ›" in t.text())
t.key(ESC); t.done()

# the quote search shows the same rows; a place quoting a match quotes the match
t = F.fw("later", rows=30)
t.key(ENTER, "/", ENTER, *"aura")
check("the quote search: the same family and places", "  · the aura of the room" in t.text() and "≈ a glow in the room" in t.text()
      and "quoted in sidebar" in t.text(), t.text())
select(t, "quoted in sidebar")
check("  on a place, Enter quotes what it quotes", "quote what it quotes" in t.text(), t.text())
t.key(ESC, ESC, Q, ESC); t.done()
F.report("HOMESEARCH")
