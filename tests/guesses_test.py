# a model's guesses at kinds (kinds, step 2): a model outside fw writes kind-guesses.json, {model, guesses:
# {kind id: {block id: [p, kind's updated, block's updated]}}}; a model outside fw writes it beside the store; fw reads
# it (store.load_guesses, at the edge) and keeps the guesses that count (fw_block.guessed: unanswered, current, p ≥ 0.9,
# kinds that exist). Shown dim blue on the header's kinds line ("poem?"): Enter confirms one (a yes), Backspace denies
# it (a no), each one undo step; Ctrl+O opens the kind. Typing a kind's name in a search: the kind, the blocks said to
# be one, then the guessed ones, dim. Never stored.
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, UP, ESC, ENTER, QUIT as Q, UNDO as Z, REDO as Y
F.pyte.graphics.TEXT[2] = "+blink"   # (pyte has no dim: here SGR 2, dim, reads as blink, which fw never uses)
S = F.use_store("t/guesses.json", clean=True)
from fw_picker import Picker, blocks_inside

MINE, M1, M2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
OTHER, O1 = "20261002T100000-b000", "20261002T100000-b001"
POEM, PD = "20261004T100000-d000", "20261004T100000-d001"   # a kind, and a block of its description
LET = "20261005T100000-e000"                                 # another kind
HOST, H1 = "20261003T100000-c000", "20261003T100000-c001"
CTRL_O = "\x0f"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}
T, T2 = "2026-10-01T10:00:00-04:00", "2026-10-02T10:00:00-04:00"
GUESSES = os.path.join(os.path.dirname(os.environ["FW_DATA"]), "kind-guesses.json")
BLUE, BLUE_SOFT, BLUE_BG = "5fafff", "5f5f87", "005faf"

def blk(i, content, title=None, entry=False, **more):
    return {"id": i, "title": title, **({"entry": True} if entry else {}), "content": content, "words": 0,
            "created": T, "updated": T, **more}
def fresh():
    """mine: M1 (a poem, said so) and M2; other: O1; host: H1; the kinds poem (described) and letter."""
    blocks = [blk(MINE, [M1, M2], "mine", True), blk(M1, "roses are red\nviolets are blue", kinds={POEM: True}),
              blk(M2, "buy milk"), blk(OTHER, [O1], "other", True), blk(O1, "an old pond"),
              blk(HOST, [H1], "host", True), blk(H1, "host text"),
              blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True), blk(PD, "a short piece in lines"),
              blk(LET, {"kind": "letter", "blocks": []}, entry=True)]
    json.dump({"schemaVersion": 17, "blocks": blocks}, open(os.environ["FW_DATA"], "w"))
    S.cmd_migrate(None)
    for f in ("t/mac.txt", S.CLIP_PATH, GUESSES):
        if os.path.exists(f): os.remove(f)
def B(): return S.index(S.load_data())
def g(p, kind_at=T, block_at=T): return [p, kind_at, block_at]
def write_guesses(guesses, model="qwen/p2"):
    tmp = GUESSES + ".tmp"
    json.dump({"model": model, "guesses": guesses}, open(tmp, "w")); os.replace(tmp, GUESSES)
def bar(t): return t.row(t.scr.lines - 1)
def row_of(t, text): return next((y for y in range(t.scr.lines) if text in t.row(y)), None)
def cell(t, text, dx=1):
    y = row_of(t, text)
    return None if y is None else t.cell(y, t.row(y).index(text) + dx)
def kinds_row(t): return t.row(row_of(t, "kinds"))
def on(t):
    """The kinds line's token under the cursor."""
    y, x = t.cursor()
    row = t.row(y)
    return row[x:].split("  ")[0].strip() if row[x:x + 1] == " " else None

# --- pure: the guesses that count ------------------------------------------------------------------------------------
fresh()
b = B()
data = {"model": "m", "guesses": {
    POEM: {M1: g(0.99), M2: g(0.95), O1: g(0.89), OTHER: g(0.9), PD: g(0.97, block_at=T2)},
    LET: {M2: g(0.97, kind_at=T2), O1: g(1.0)},
    "20261009T100000-gone": {M2: g(0.99)},     # a kind that's gone
    M2: {O1: g(0.99)},                          # not a kind
}}
same("guessed: unanswered, current, p ≥ 0.9, kinds that exist; each block's kinds oldest first",
     S.guessed(data, b), {M2: {POEM: 0.95}, OTHER: {POEM: 0.9}, O1: {LET: 1.0}})
check("  M1's poem guess dropped: it's answered (answers win, a guess never shows over one)", M1 not in S.guessed(data, b))
check("  stale: the block changed since (its updated) or the kind did", PD not in S.guessed(data, b) and LET not in S.guessed(data, b).get(M2, {}))
same("  the threshold is a constant: 0.9", S.GUESS_AT, 0.9)
same("  works on the editor's library alike", S.guessed(data, S.build_library(S.load_data())), S.guessed(data, b))
same("  a block that's gone: nothing", S.guessed({"guesses": {POEM: {"20261009T100000-x": g(0.99)}}}, b), {})
same("  anything malformed counts for nothing",
     [S.guessed(x, b) for x in (None, {}, [], {"guesses": []}, {"guesses": {POEM: []}},
                                 {"guesses": {POEM: {M2: [0.99, T]}}}, {"guesses": {POEM: {M2: ["0.99", T, T]}}},
                                 {"guesses": {POEM: {M2: {"p": 0.99}}}})], [{}] * 8)
same("merge_kinds: a guess that counts is a yes, under the answers", S.merge_kinds({POEM: False}, {POEM: 0.99, LET: 0.95}),
     {POEM: False, LET: True})
same("of_kind with them: said, and guessed", S.of_kind(b, POEM, S.guessed(data, b)), [M1, M2, OTHER])

# --- I/O at the edge: the file beside the store ----------------------------------------------------------------------
same("no file: no guesses", S.load_guesses(), {})
open(GUESSES, "w").write('{"model": "m", "guesses": {')
same("a broken file: no guesses", S.load_guesses(), {})
write_guesses({POEM: {M2: g(0.95)}})
same("the file read (again, when it changes)", S.guessed(S.load_guesses(), B()), {M2: {POEM: 0.95}})
open(GUESSES, "w").write("[1, 2]")
same("  JSON, but not an object: none", S.load_guesses(), {})
os.remove(GUESSES)

# --- the kinds line: a guess from 0.9 is applied (poem·); Enter confirms it, Backspace denies, each an undo step ---------------------------------
fresh()
write_guesses({POEM: {OTHER: g(0.97)}, LET: {OTHER: g(0.95)}})
t = F.fw("other", rows=30, cols=70, env=ENV)
check("the kinds line shows the guesses, 'poem·'", " poem· " in kinds_row(t) and " letter· " in kinds_row(t), t.text())
c = cell(t, " poem· ")
check("  applied (0.9 up: a pericope's too, 2026-11-18): drawn as a yes, with its mark", c is not None and c.bg == BLUE_BG, (c and (c.fg, c.bg)))
t.key(UP, UP, F.HOME)
same("onto the kinds line, ← home: on the first guess", on(t), "poem·")
t.key(ENTER); t.settle()
same("Enter on a guess confirms it: an answer, yes", S.kinds_of(B()[OTHER]), {POEM: True})
c = cell(t, " poem ")
check("  drawn as a yes, white on blue; the guess gone", c is not None and c.bg == BLUE_BG and c.fg == "white" and " poem· " not in kinds_row(t),
      kinds_row(t))
same("  the cursor on what it became", on(t), "poem")
check("  not an edit: the block's updated stays (so the other guess is still current)",
      B()[OTHER]["updated"] == T and " letter· " in kinds_row(t), kinds_row(t))
t.key(F.RIGHT)
same("→ onto the next guess", on(t), "letter·")
t.key(F.BS); t.settle()
same("Backspace on a guess denies it: an answer, no", S.kinds_of(B()[OTHER]), {POEM: True, LET: False})
c = cell(t, " not letter ")
check("  drawn 'not letter', muted blue", c is not None and c.fg == BLUE_SOFT and " letter· " not in kinds_row(t), kinds_row(t))
same("  the cursor on it", on(t), "not letter")
t.key(Z); t.settle()
same("^Z: the no taken back, the guess shows again", (S.kinds_of(B()[OTHER]), " letter· " in kinds_row(t)), ({POEM: True}, True))
t.key(Z); t.settle()
same("^Z: the yes taken back, both guesses again", (S.kinds_of(B()[OTHER]), " poem· " in kinds_row(t)), ({}, True))
t.key(Y); t.settle()
same("^Y: confirmed again", S.kinds_of(B()[OTHER]), {POEM: True})
t.key(Y); t.settle()
same("^Y: denied again", S.kinds_of(B()[OTHER]), {POEM: True, LET: False})
t.key(Z, Z); t.settle()
t.key(F.HOME, F.DEL); t.settle()
same("Delete on a guess denies it too", S.kinds_of(B()[OTHER]), {POEM: False})
t.key(Z); t.settle()
t.key(F.HOME, CTRL_O)
check("Ctrl+O on a guess opens the kind, on the trail", t.until(lambda: "other ›" in bar(t)) and "kind: poem" in t.row(0), t.text())
same("  and answers nothing", S.kinds_of(B()[OTHER]), {})
t.key(Q)
check("  ^Q comes back", t.until(lambda: "other ›" not in bar(t)) and "an old pond" in t.text(), t.text())
write_guesses({POEM: {OTHER: g(0.97)}})
check("the file rewritten (by the model, say): the line follows", t.until(lambda: " letter· " not in kinds_row(t)) and " poem· " in kinds_row(t),
      kinds_row(t))
write_guesses({POEM: {OTHER: g(0.97, block_at=T2)}})
check("  a stale guess (the block changed since): gone", t.until(lambda: " poem· " not in kinds_row(t)), kinds_row(t))
open(GUESSES, "w").write("{broken")
t.pump(0.4)
check("  a broken file: no guesses, nothing else wrong", "(none)" in kinds_row(t) and "an old pond" in t.text(), kinds_row(t))
t.key(Q, ESC); t.done()
check("never stored: the store has no guesses", all("guess" not in json.dumps(x) for x in json.load(open(os.environ["FW_DATA"]))["blocks"]))

fresh()
t = F.fw("other", rows=30, cols=70, env=ENV)
check("no file: the kinds line as ever", "(none)" in kinds_row(t), kinds_row(t))
t.key(Q, ESC); t.done()

# --- search: the kind, the blocks said to be one, then the guessed ones, dim -----------------------------------------
fresh()
write_guesses({POEM: {OTHER: g(0.96), M2: g(0.5)}})  # (a pericope: a guess about a block inside one is applied, review_test)
lib = S.build_library(S.load_data())
refs = sorted((r for r, e in lib.items() if e["entry"]), reverse=True)
p = Picker(lib, refs, inside=blocks_inside(lib, refs), guesses=S.guessed(S.load_guesses(), lib))
p.query = "poem"
same("a kind's name typed: the kind, the block said to be one, then the guessed one (0.9 up: applied, so not dim)",
     [(r[0], r[1], r[3:]) for r in p.rows()[:3]], [(POEM, "poem", ()), (M1, "  · roses are red", ()), (OTHER, "  · other", ())])
check("  each once; under 0.9 not listed with them", [r[0] for r in p.rows()].count(OTHER) == 1 and M2 not in [r[0] for r in p.rows()[:4]], p.rows())
plain = Picker(lib, refs, inside=blocks_inside(lib, refs))
plain.query = "poem"
check("  without guesses: only the said", OTHER not in [r[0] for r in plain.rows()], plain.rows())
t = F.fw("open", rows=30, env=ENV)
t.key(*"poem")
y = row_of(t, "· other")
check("home: the guessed block under the poem said, applied (not dim)", y is not None and "roses are red" in t.row(y - 1) and "poem" in t.row(y - 2)
      and not t.cell(y, t.row(y).index("· other") + 2).blink, t.text())
t.key(ESC); t.done()
t = F.fw("host", rows=30, cols=70, env=ENV)
t.key(ENTER, "/", ENTER, *"poem")
y = row_of(t, "· other")
check("the quote search too", y is not None and "roses are red" in t.row(y - 1) and not t.cell(y, t.row(y).index("· other") + 2).blink, t.text())
t.key(ESC, ESC, Q, ESC); t.done()

check("the store validates throughout", not S.invalid(S.load_data(), S.load_schema()), S.invalid(S.load_data(), S.load_schema()))
F.report("GUESSES")
