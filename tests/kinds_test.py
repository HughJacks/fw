# kinds (schema v16): what a block is (a poem, a to-do). A kind is a block, content {kind, blocks}: a name and
# a description of child blocks, a pericope of its own; a block carries the user's answers, kinds: {kind id: bool},
# set in the header's kinds field (a new name makes a new kind). Everything is a block: a kind works with search,
# Quote a block, Turn into a quote (and open it), Open it, selected whole, copy/cut/paste, undo, backlinks, the
# draft, word counts. Drawn blue.
import copy, importlib.machinery, importlib.util, json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, UP, DOWN, ESC, ENTER, MENU, BS, QUIT as Q, UNDO as Z, REDO as Y
S = F.use_store("t/kinds.json", clean=True)
import fw_migrate as M
from fw_picker import Picker, blocks_inside

MINE, M1, M2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
OTHER, O1 = "20261002T100000-b000", "20261002T100000-b001"
HOST, H1 = "20261003T100000-c000", "20261003T100000-c001"
POEM, PD = "20261004T100000-d000", "20261004T100000-d001"   # a kind, and a block of its description
CTRL_O, CTRL_T, CTRL_ST = "\x0f", "\x14", "\x1b[116;6u"
SUP, COPY, CUT, PASTE = "\x1b[1;2A", "\x03", "\x18", "\x16"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}  # never the real clipboard
T = "2026-10-01T10:00:00-04:00"

def blk(i, content, title=None, entry=False, **more):
    return {"id": i, "title": title, **({"entry": True} if entry else {}), "content": content, "words": 0,
            "created": T, "updated": T, **more}
def fresh(kinds=True):
    """mine: two blocks of text (mine a poem, when `kinds`); other: one; host: one; and the kind poem, described."""
    blocks = [blk(MINE, [M1, M2], "mine", True), blk(M1, "roses are red\nviolets are blue"), blk(M2, "buy milk"),
              blk(OTHER, [O1], "other", True), blk(O1, "an old pond"),
              blk(HOST, [H1], "host", True), blk(H1, "host text")]
    if kinds:
        blocks += [blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True), blk(PD, "a short piece in lines")]
        blocks[0]["kinds"] = {POEM: True}
    json.dump({"schemaVersion": 16, "blocks": blocks}, open(os.environ["FW_DATA"], "w"))
    S.cmd_migrate(None)
    for f in ("t/mac.txt", S.CLIP_PATH):
        if os.path.exists(f): os.remove(f)
def B(): return S.index(S.load_data())
def bar(t): return t.row(t.scr.lines - 1)
def open_(title, rows=30): return F.fw(title, rows=rows, cols=70, env=ENV)
def row_of(t, text): return next((y for y in range(t.scr.lines) if text in t.row(y)), None)
def fg(t, text, dx=0):
    """The colour (and bold) of the first character of `text` on screen, dx columns on."""
    y = row_of(t, text)
    if y is None: return None
    c = t.cell(y, t.row(y).index(text) + dx)
    return c.fg, c.bold
BLUE, BLUE_SOFT, BLUE_BG = "5fafff", "5f5f87", "005faf"   # (xterm-256 75, 60 and 25, as fw_screen.setup has them)
SENTER = "\x1b[13;2u"

# --- the shape: migration and schema ---------------------------------------------------------------------
fresh(kinds=False)
d = json.load(open(os.environ["FW_DATA"]))
v15 = {**d, "schemaVersion": 15}
up = M.upgrade(copy.deepcopy(v15), now=S.now_local(), new_id=S.new_id)
check("v15 → v16 (and on): marked to be saved, the blocks as they were (no kinds yet)",
      M.SCHEMA_VERSION >= 16 and up["schemaVersion"] == M.SCHEMA_VERSION and M.behind(v15) and up["blocks"] == d["blocks"]
      and not any("kinds" in b for b in up["blocks"]))
v18 = {"schemaVersion": 18, "blocks": [blk(MINE, [M1, M2], "mine", True, kinds={POEM: False}), blk(M1, "x", kinds={POEM: True, OTHER: True}),
       blk(M2, "y", kinds={HOST: False}), blk(OTHER, [O1], "other", True), blk(O1, "z", kinds={POEM: True})]}
up = {b["id"]: b for b in M.upgrade(v18, now=None, new_id=None)["blocks"]}
same("v18 → v19: only a pericope has kinds: a yes inside carried up, the pericope's own answer winning, the rest gone",
     [up[i].get("kinds") for i in (MINE, M1, M2, OTHER, O1)], [{POEM: False, OTHER: True}, None, None, {POEM: True}, None])
schema = S.load_schema()
good = blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True, kinds={OTHER: False})
same("the schema takes a Kind, and kinds on a block", S.validate_instance(good, schema), [])
check("  and refuses a nameless kind, or an answer that isn't yes or no",
      S.validate_instance(blk(POEM, {"kind": " ", "blocks": []}), schema)
      and S.validate_instance(blk(M1, "x", kinds={POEM: "yes"}), schema))
check("  kinds is a header field the user writes (not readOnly)", "kinds" in S.editable_keys(schema))

# --- pure: answers, the merge point for a model's guesses, the header's text --------------------------------
same("parse_kinds: commas apart, 'not' before a no, a name once (the last word wins)",
     S.parse_kinds(" Poem,  not  letter , poem, ,to-do"), [("letter", False), ("poem", True), ("to-do", True)])
same("merge_kinds: guesses under your answers, which win", S.merge_kinds({POEM: False}, {POEM: True, OTHER: True}),
     {POEM: False, OTHER: True})
fresh()
b = B()
same("of_kind: the blocks you said are one", S.of_kind(b, POEM), [MINE])
same("  with a model's guesses merged under them (a later step's)", S.of_kind(b, POEM, {OTHER: {POEM: True}, MINE: {POEM: False}}),
     [MINE, OTHER])
same("kind_named: case and spacing aside", (S.kind_named(b, " POEM "), S.kind_named(b, "letter")), (POEM, None))
same("kind_of and display_title: its name", (S.kind_of(b[POEM]), S.display_title(b, POEM), S.kind_of(b[M1])), ("poem", "poem", None))

# --- the store: the header's kinds, made and undone ------------------------------------------------------------
fresh(kinds=False)
rec = S.set_kinds(MINE, "Poem, not letter")
b = B()
made = S.kind_ids(b)
same("set_kinds: each new name a new kind, an entry of its own, empty", sorted((S.kind_of(b[k]), b[k].get("entry"), S.children(b[k])) for k in made),
     [("Poem", True, []), ("letter", True, [])])
same("  the block's answers, yes and no", S.kinds_text(b, b[MINE]), "Poem, not letter")
check("  not an edit: the block's updated stays", b[MINE]["updated"] == T, b[MINE]["updated"])
rec2 = S.set_kinds(OTHER, "POEM")
same("  an existing name, any case: that kind, no new one", (len(S.kind_ids(B())), S.of_kind(B(), S.kind_named(B(), "poem"))), (2, [MINE, OTHER]))
redo = S.restore(rec2)
same("undo (restore its record): the answers as they were", S.kinds_of(B()[OTHER]), {})
S.restore(rec)
same("  and the kinds it made, gone: completely as before", (S.kinds_of(B()[MINE]), S.kind_ids(B())), ({}, []))
fresh()
try: S.set_kinds(POEM, "poem"); refused = False
except S.StoreError: refused = True
check("a kind can't be a kind of itself", refused)
S.set_kinds(MINE, "")
same("set_kinds '': its answers go, the kind stays", (S.kinds_of(B()[MINE]), S.kind_ids(B())), ({}, [POEM]))

# --- everything is a block: draft, words, backlinks, empty, delete ------------------------------------------------
fresh()
b = B()
same("the draft: a kind is drafted as its description's blocks", S.block_draft(b, POEM), f"{{{{block {PD}}}}}\na short piece in lines")
same("words: its description's (not its name)", b[POEM]["words"], 5)
_, tmp, _ = S.stage(POEM)
draft = open(tmp).read() + f"\n{{{{block}}}}\nwith a turn"
S.commit(POEM, draft, json.load(open(S.meta_path(tmp)))["fields"], final=True); S.drop_draft(tmp)
b = B()
same("  edited through the draft (as the editor saves): still a kind, a block added",
     (S.kind_of(b[POEM]), len(S.children(b[POEM])), S.own_text(b, POEM)), ("poem", 2, "a short piece in lines\nwith a turn"))
same("  and its words follow", b[POEM]["words"], 8)
fields = {f["key"]: f for f in json.load(open(S.meta_path(S.stage(MINE)[1])))["fields"]}
same("the header: kinds by name, editable; a kind's title stands in as its name",
     (fields["kinds"]["value"], fields["kinds"]["editable"]), ("poem", True))
found = S.backlinks(B(), POEM)
same("backlinks of a kind: the blocks of that kind", [(x["kind"], x["by"], x["home"]) for x in found], [("kind", MINE, MINE)])
same("  summed up", S.backlink_summary(found), "1 · 1 block of this kind")
S.set_kinds(OTHER, "not poem")
same("  a no isn't one", len(S.backlinks(B(), POEM)), 1)
check("an empty kind isn't 'empty': kept (it has its name)", not S.is_empty_untitled({POEM: blk(POEM, {"kind": "x", "blocks": []})}, POEM))
fresh()
S.set_kinds(MINE, "")
S.transact(S.editing(lambda data, blocks: blocks[POEM]["content"].update(blocks=[])))
S.cmd_migrate(None)
check("  migrate keeps an empty kind", POEM in B() and B()[POEM].get("entry"))
fresh()
S.delete_entry(POEM)
same("deleting a kind drops the answers about it", (POEM in B(), S.kinds_of(B()[MINE])), (False, {}))

# --- only a pericope has kinds; Turn into a quote leaves them where they were; a kind's own blocks too ---------------
fresh()
try: S.set_kinds(M1, "poem"); refused = False
except S.StoreError: refused = True
check("set_kinds on a block inside a pericope: refused (only a pericope has kinds)", refused)
try: S.set_kind(M1, POEM, True); refused = False
except S.StoreError: refused = True
check("  set_kind too", refused)
S.transact(S.editing(lambda data, blocks: blocks[M1].update(kinds={POEM: False})))
same("  a block moved inside one (as a paste might) loses its answers on the write", S.kinds_of(B()[M1]), {})
entry, _, rec = S.pop_out(M1)
b = B()
same("Turn into a quote inside a poem: the pericope still a poem, the new one not",
     (S.kinds_of(b[MINE]), S.kinds_of(b[entry]), S.quoted(b[M1])[0]), ({POEM: True}, {}, entry))
S.restore(rec)
entry, _, _ = S.pop_out(PD)
same("  a block of a kind's description: quoted there, the kind still a kind",
     (S.kind_of(B()[POEM]), S.quoted(B()[PD])[0]), ("poem", entry))
try: S.pop_out(POEM); refused = False
except S.StoreError: refused = True
check("  a kind itself can't be: it's a pericope of its own already", refused)

# --- two machines (the store a Loro document): answers merge kind by kind; a kind's description as a container -------
L2, K2 = "20261005T100000-e000", "20261005T100000-e001"
base = blk(M1, "same", kinds={POEM: True})
lap, mini = copy.deepcopy(base), copy.deepcopy(base)
lap["kinds"] = {POEM: True, L2: True}
mini["kinds"] = {K2: False}   # (the mini took back "poem" and said "not K2")
same("merged: each side's answers kept, kind by kind", F.loro_merge(base, lap, mini)["kinds"], {L2: True, K2: False})
kb = blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True)
kl = {**copy.deepcopy(kb), "content": {"kind": "poem", "blocks": [PD, L2]}, "updated": "2026-11-01T10:00:00-04:00"}
km = {**copy.deepcopy(kb), "content": {"kind": "poem", "blocks": [K2, PD]}, "updated": "2026-11-02T10:00:00-04:00"}
same("  a kind's description both sides added to: merged, still a kind", F.loro_merge(kb, kl, km)["content"],
     {"kind": "poem", "blocks": [K2, PD, L2]})

# --- search: a kind's name brings the kind first, then its blocks ------------------------------------------------
fresh()
S.set_kinds(OTHER, "poem")
lib = S.build_library(S.load_data())
refs = sorted((r for r, e in lib.items() if e["entry"]), reverse=True)
p = Picker(lib, refs, inside=blocks_inside(lib, refs))
same("nothing typed: a kind's row, just its name (drawn blue)", [r[1] for r in p.rows() if r[0] == POEM], ["poem"])
p.query = "Poem"
same("its name typed (any case): the kind first, the blocks of that kind under it, oldest first",
     [(r[0], r[1]) for r in p.rows()[:3]], [(POEM, "poem"), (MINE, "  · mine"), (OTHER, "  · other")])
check("  each once", [r[0] for r in p.rows()].count(MINE) == 1, p.rows())
p.query = "poe"
check("  a part of it: an ordinary search (no blocks of that kind)", MINE not in [r[0] for r in p.rows()], p.rows())
link = Picker(lib, refs)
link.query = "poem"
check("  Link to an entry (not a search over blocks): no kind-first rows", [r[0] for r in link.rows()] == [POEM], link.rows())

# --- the kinds line: tokens, the kinds picker, one undo each -------------------------------------------------
fresh()
S.set_kinds(HOST, "letter"); S.set_kinds(HOST, "")   # a kind "letter", no block of it
LET = S.kind_named(B(), "letter")
t = open_("other")   # one block: the cursor on its first line of text
t.key(UP)
check("Up from the text: the title first, as ever", t.cursor()[0] == row_of(t, "title"), (t.cursor(), t.text()))
t.key(UP)
y = row_of(t, "kinds")
check("  up again: the kinds line, above it; a + on it to add one", t.cursor()[0] == y and " + " in t.row(y), (t.cursor(), t.text()))
t.key(*"po")
check("typing opens the kinds picker, filtered by it", "kinds › po" in t.text() and row_of(t, "poem") is not None, t.text())
same("  a kind's row blue", fg(t, "poem")[0], BLUE)
t.key(ENTER); t.settle()
same("Enter on a kind: it is one", S.kinds_of(B()[OTHER]), {POEM: True})
y = row_of(t, "kinds")
x = t.row(y).find(" poem ")
check("  a token on the kinds line, white on blue", x > 0 and t.cell(y, x + 1).bg == BLUE_BG and t.cell(y, x + 1).fg == "white",
      (t.row(y), x > 0 and (t.cell(y, x + 1).fg, t.cell(y, x + 1).bg)))
check("  the picker closed, the cursor on the + to add another", "kinds ›" not in t.text() and t.cursor() == (y, t.row(y).find(" + ")),
      (t.cursor(), t.row(y)))
t.key(ENTER, *"letter", SENTER); t.settle()
same("Enter on the +, then Shift+Enter on a kind: it isn't one (a no)", S.kinds_of(B()[OTHER]), {POEM: True, LET: False})
same("  drawn 'not letter', muted blue", fg(t, "not letter"), (BLUE_SOFT, False))
t.key(*"sonnet")
check("a name no kind has: + new kind, selected", "+ new kind “sonnet”" in t.text(), t.text())
t.key(ENTER); t.settle()
SON = S.kind_named(B(), "sonnet")
check("  Enter makes it a kind (a pericope of its own) and says it is one",
      SON and B()[SON].get("entry") and S.kinds_of(B()[OTHER]) == {POEM: True, LET: False, SON: True}, S.kinds_of(B()[OTHER]))
check("  its token drawn", " sonnet " in t.row(row_of(t, "kinds")), t.text())
t.key(F.LEFT, F.BS); t.settle()
same("← onto its token, Backspace: that answer taken back (the kind stays)",
     (S.kinds_of(B()[OTHER]), SON in B()), ({POEM: True, LET: False}, True))
check("  its token gone", " sonnet " not in t.row(row_of(t, "kinds")), t.text())
t.key(Z); t.settle()
same("^Z: the answer back", S.kinds_of(B()[OTHER]), {POEM: True, LET: False, SON: True})
t.key(Z); t.settle()
same("^Z: + new kind taken back whole, the kind it made too", (S.kinds_of(B()[OTHER]), SON in B()), ({POEM: True, LET: False}, False))
t.key(Z); t.settle()
same("^Z: the no taken back", S.kinds_of(B()[OTHER]), {POEM: True})
t.key(Z); t.settle()
same("^Z: the yes taken back, as before", S.kinds_of(B()[OTHER]), {})
check("  the line shows it: no tokens", " poem " not in t.row(row_of(t, "kinds")), t.text())
t.key(Y); t.settle()
same("^Y: made again", S.kinds_of(B()[OTHER]), {POEM: True})
t.key(F.HOME, ENTER)
check("Enter on a token: that kind opens, on the trail", t.until(lambda: "other ›" in bar(t)) and "kind: poem" in t.row(0), t.text())
t.key(Q)
check("  ^Q comes back", t.until(lambda: "other ›" not in bar(t)) and "an old pond" in t.text(), t.text())
t.key(UP, UP, F.HOME, CTRL_O)
check("Ctrl+O on a token too", t.until(lambda: "other ›" in bar(t)) and "kind: poem" in t.row(0), t.text())
t.key(Q); t.until(lambda: "other ›" not in bar(t))
t.key(Q, ESC); t.done()
check("the answers kept", S.kinds_of(B()[OTHER]) == {POEM: True})

fresh()
t = open_("poem")
t.key(UP, UP, *"Poem")
check("a kind's own kinds picker doesn't list it", row_of(t, "+ new kind “Poem”") is not None and fg(t, "  poem") is None, t.text())
t.key(ENTER); t.settle()
check("+ new kind with its own name: refused, said why", "itself" in bar(t) and S.kinds_of(B()[POEM]) == {} and len(S.kind_ids(B())) == 1,
      bar(t))
t.key(Q, ESC); t.done()

# --- renaming a kind: its title field is its name --------------------------------------------------------------
fresh()
S.set_kinds(HOST, "letter")
rec = S.rename_kind(POEM, "  Free   verse ")
same("rename_kind: the name, its spacing tidied", S.kind_of(B()[POEM]), "Free verse")
check("  everything reads it: the title, the answers' text, a search", S.display_title(B(), POEM) == "Free verse"
      and S.kinds_text(B(), B()[MINE]) == "Free verse" and S.kind_named(B(), "free verse") == POEM)
S.restore(rec)
same("  undone (restore): its old name", S.kind_of(B()[POEM]), "poem")
for name, why in (("  ", "a kind needs a name"), ("LETTER", "there's a kind called letter already")):
    try: S.rename_kind(POEM, name); got = None
    except S.StoreError as e: got = str(e)
    same(f"  refused: {name!r}", got, why)
S.rename_kind(POEM, "Poem")
same("  its own name in another case: fine", S.kind_of(B()[POEM]), "Poem")
fresh()
S.set_kinds(HOST, "letter"); S.set_kinds(OTHER, "poem")
S.transact(S.editing(lambda data, blocks: (S.add_block(data, blocks, "20261003T100000-c002", {"quote": POEM}),
                                 blocks[HOST]["content"].append("20261003T100000-c002"))))
t = open_("poem")
t.key(UP)
y = row_of(t, "title")
check("a kind's title field: its name, as written (not dim)", "poem" in t.row(y) and not t.cell(y, t.row(y).index("poem")).bold
      and t.cursor()[0] == y, t.text())
t.key("\x01", *"verse", DOWN); t.settle()
check("changed and left: renamed, its header follows", S.kind_of(B()[POEM]) == "verse" and "kind: verse" in t.row(0)
      and B()[POEM]["title"] is None, (S.kind_of(B()[POEM]), t.row(0)))
t.key(Z); t.settle()
check("^Z: one step, its old name", S.kind_of(B()[POEM]) == "poem" and "kind: poem" in t.row(0), t.row(0))
t.key(Y); t.settle()
same("^Y: renamed again", S.kind_of(B()[POEM]), "verse")
t.key(UP, "\x01", F.BS, DOWN); t.settle()
check("emptied: refused, said in the bar, the name stays", "needs a name" in bar(t) and S.kind_of(B()[POEM]) == "verse"
      and "verse" in t.row(row_of(t, "title")), (bar(t), t.text()))
t.key(UP, "\x01", *"Letter", ESC); t.settle()
check("another kind's name (any case): refused, said why", "already" in bar(t) and S.kind_of(B()[POEM]) == "verse", bar(t))
t.key(Q, ESC); t.done()
t = open_("other")
check("everything follows: a poem's token shows the new name", " verse " in t.row(row_of(t, "kinds")), t.text())
t.key(Q, ESC); t.done()
t = open_("host")
check("  a quote of it, its top line", "kind: verse" in t.text(), t.text())
t.key(ENTER, "/", ENTER, *"verse")
check("  the quote search, by its new name (no prefix)", row_of(t, "· mine") is not None
      and "verse" in t.row(row_of(t, "· mine") - 1), t.text())
t.key(ESC, ESC, Q, ESC); t.done()

# --- every pericope's header says its type -----------------------------------------------------------------
same("block_type over the content cases", [S.block_type(blk(M1, c)) for c in
     ("text", [], {"image": "a.png"}, {"quote": M1}, {"kind": "poem", "blocks": []})], ["text", "block", "image", "quote", "kind"])
same("type_label: a kind's says which", [S.type_label(blk(M1, c)) for c in ({"kind": "poem", "blocks": []}, [PD])], ["kind: poem", "block"])
b = B()
same("  a pericope's, given the blocks: its one block's type, else 'pericope'",
     [S.type_label(b[MINE], b), S.type_label(b[OTHER], b), S.type_label({**b[OTHER], "content": []}, b), S.type_label(b[M1], b)],
     ["pericope", "text", "pericope", "text"])
fresh()
TX, QT = "20261006T100000-f000", "20261006T100000-f001"
S.transact(S.editing(lambda data, blocks: (S.add_block(data, blocks, TX, "just text", "tx", entry=True),
                                 S.add_block(data, blocks, QT, {"quote": OTHER}, "qt", entry=True))))
for title, label in (("mine", " block "), ("poem", " kind: poem "), ("tx", " text "), ("qt", " quote ")):
    t = open_(title)
    check(f"{title}: its header's top line says {label.strip()}", label in t.row(0), t.row(0))
    t.key(Q, ESC); t.done()

# --- a kind's own pericope ----------------------------------------------------------------------------------
fresh()
t = open_("poem")
check("fw poem opens the kind (by its name): 'kind: poem' on its header's top line, its name standing in as its title",
      "kind: poem" in t.row(0) and "poem" in t.inside(row_of(t, "title")), t.text())
same("  its header boxed blue, muted at rest", fg(t, "┌")[0], BLUE_SOFT)
check("  its description, ordinary blocks, to write in", "a short piece in lines" in t.text())
t.key(*" that rhymes"); t.settle()
same("writing in it: its description", (S.kind_of(B()[POEM]), S.own_text(B(), POEM)), ("poem", "a short piece in lines that rhymes"))
check("  the backlinks field counts the blocks of this kind", "1 · 1 block of this kind" in t.text(), t.text())
t.key(Q, ESC); t.done()
check("quit: still a kind, still a pericope", S.kind_of(B()[POEM]) == "poem" and B()[POEM].get("entry"))
S.transact(S.editing(lambda data, blocks: blocks[POEM]["content"].update(blocks=[])))
t = open_("poem"); t.key(Q, ESC); t.done()
check("  an empty kind opened and left: kept (not an empty pericope)", POEM in B() and B()[POEM].get("entry"))

# --- Quote a block: the quote search finds it first; a quote of a kind, blue -------------------------------------
fresh()
t = open_("host")
t.key(ENTER, "/", ENTER, *"poem")
y = row_of(t, "· mine")
check("the quote search: its name typed, the kind first, its blocks under it",
      y is not None and t.row(y - 1).split("│")[1].strip().startswith("poem") and "kind:" not in t.row(y - 1), t.text())
same("  the kind's row blue, no prefix", t.cell(y - 1, t.row(y - 1).index("poem")).fg, BLUE)
t.key(ENTER); t.settle()
qs = [k for k in S.children(B()[HOST]) if S.quoted(B()[k])]
check("Enter: a quote of the kind, here", [S.quoted(B()[k])[0] for k in qs] == [POEM], S.children(B()[HOST]))
check("  its top line says what it is", "kind: poem" in t.text() and "a short piece in lines" in t.text(), t.text())
same("  its box blue, muted at rest", fg(t, "kind: poem", -2), (BLUE_SOFT, False))
t.key(UP)   # (from the line below it: onto it, selected)
same("  bright while it's selected", fg(t, "kind: poem", -2), (BLUE, True))
t.key(UP, F.END)   # inside: editing through it edits the kind's description
t.key(*"!"); t.settle()
same("typing inside the quote writes the kind's description", S.own_text(B(), POEM), "a short piece in lines!")
check("  it's still a kind", S.kind_of(B()[POEM]) == "poem")
t.key(ESC, ESC)   # the block inside, whole; then the quote, selected
t.key(CTRL_O)
check("Open it on the quote: the kind's own pericope, on the trail", t.until(lambda: "host ›" in bar(t)) and "kind: poem" in t.row(0), t.text())
t.key(Q); t.settle()
check("  ^Q comes back", "host ›" not in bar(t), bar(t))
t.key(Q, ESC); t.done()

# --- selected whole, copy, paste, cut, and undo ---------------------------------------------------------------
fresh()
S.transact(S.editing(lambda data, blocks: (S.add_block(data, blocks, "20261003T100000-c002", {"quote": POEM}),
                                 blocks[HOST]["content"].append("20261003T100000-c002"))))
QK = "20261003T100000-c002"
t = open_("host")
t.key(UP)   # (from the end, onto the quote of the kind)
t.key(ESC, SUP)
check("the quote of a kind selected whole with the block above it", "blocks 1–2" in bar(t), bar(t))
t.key(COPY)
t.key(DOWN, DOWN, ENTER, PASTE); t.settle()
qs = [S.quoted(B()[k])[0] for k in S.children(B()[HOST]) if S.quoted(B()[k])]
same("^V: a live quote of each, the kind's too", qs.count(POEM), 1 + 1)
t.key(Z); t.settle()
same("^Z takes the paste back out", [S.quoted(B()[k])[0] for k in S.children(B()[HOST]) if S.quoted(B()[k])], [POEM])
t.key(Q, ESC); t.done()

fresh()
t = open_("mine")   # the cursor at the end of "buy milk"; the poem above it
t.key(UP, UP, ESC, CUT); t.settle()
t.key(Q); t.until(lambda: "pericope" in t.text())
t.key(*"host", ENTER)   # home: open host
t.until(lambda: "host text" in t.text())
t.key(PASTE); t.settle()
same("a block cut from a poem and pasted elsewhere: it moves, the poem's kinds stay with the poem",
     (M1 in S.children(B()[HOST]) or any(M1 in S.subtree(B(), k) for k in S.children(B()[HOST])), S.kinds_of(B()[M1]),
      S.kinds_of(B()[MINE]), S.kinds_of(B()[HOST])), (True, {}, {POEM: True}, {}))
t.key(Q, ESC); t.done()

# --- home: the kind and its blocks first; Enter opens -------------------------------------------------------
fresh()
t = F.fw("open", rows=30, env=ENV)
check("home lists a kind by its name, blue (no prefix)", "kind:" not in t.text() and fg(t, "poem")[0] == BLUE, t.text())
t.key(*"poem")
y = row_of(t, "· mine")
check("its name typed: the kind first, the poem under it", y is not None and "poem" in t.row(y - 1), t.text())
t.key(DOWN, ENTER)
check("Enter on the poem: opens where it lives", t.until(lambda: "buy milk" in t.text()) and "title      mine" in t.text(), t.text())
t.key(Q); t.until(lambda: "pericope" in t.text())
t.key(BS, BS, BS, BS, *"poem", ENTER)   # (home as it was left: the search for poem, typed again from the top)
check("Enter on the kind: its own pericope", t.until(lambda: "kind: poem" in t.row(0)), t.text())
t.key(Q, ESC); t.done()

check("the store validates throughout", not S.invalid(S.load_data(), S.load_schema()), S.invalid(S.load_data(), S.load_schema()))
F.report("KINDS")
