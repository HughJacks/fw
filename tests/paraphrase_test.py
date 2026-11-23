# paraphrases: a block of its own, like a quote ({paraphrase: the original, text: your words}, schema v18), made from a
# block of text (Paraphrases…, Not a paraphrase) or in a quote's place (Paraphrase it); drawn red, "≈ source"
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, ENTER, ESC, MENU, QUIT as Q, UNDO as Z
S = F.use_store("t/paraphrase.json", clean=True)
SRC, S1 = "20261001T100000-5000", "20261001T100000-5001"
ME, M1, M2, MQ = "20261002T100000-b000", "20261002T100000-b001", "20261002T100000-b002", "20261002T100000-b003"
PIC, M3 = "20261002T100000-b004", "20261002T100000-b005"
CTRL_O, CTRL_T = "\x0f", "\x14"
def fresh():
    F.write_store([blk(SRC, [S1], "src"), blk(S1, "the original idea"),
                   blk(ME, [MQ, M2, M1], "mine"), blk(M1, "my words about it"), blk(MQ, {"quote": SRC}), blk(M2, "other")],
                  [SRC, ME], version=9)
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())
def mark(i): return S.paraphrases(B().get(i))
def bar(t): return t.row(t.scr.lines - 1)
def to_m1(t): pass   # (fw opens at the end of the last block: "my words about it")

fresh()
t = F.fw("mine", rows=30)
to_m1(t); t.key(MENU)
check("Ctrl+/ on a block you wrote offers Paraphrases…", "Paraphrases…" in t.text(), t.text())
t.key("paraphrases", ENTER, "src", ENTER); t.settle()
same("picking its source marks it", mark(M1), SRC)
check("  drawn with its source on its top line", "≈ src" in t.text(), t.text())
check("  the words are untouched", S.text_of(B()[M1]) == "my words about it")
same("  the source's backlinks list it", sorted((x["kind"], x["home"]) for x in S.backlinks(B(), SRC)), [("paraphrase", ME), ("quote", ME)])
t.key(Z); t.settle()
same("^Z: not a paraphrase again", mark(M1), None)
t.key(MENU, "paraphrases", ENTER, "src", ENTER); t.settle()
t.key(CTRL_O)
check("Open it on a paraphrase: the block it paraphrases, on the trail", t.until(lambda: "mine ›" in bar(t)) and "the original idea" in t.text(), bar(t))
t.key(Q); t.settle()
t.key(MENU, "not a para", ENTER); t.settle()
same("Not a paraphrase: the mark goes", mark(M1), None)
check("  the words stay", B()[M1]["content"] == "my words about it" and "≈" not in t.text(), t.text())
t.key(UP, UP, MENU)   # up past "other", onto the quote
check("on a quote: no Paraphrases… (its content is a pointer already)", "Paraphrases…" not in t.text(), t.text())
t.key(ESC, Q, ESC); t.done()

try:
    S.set_paraphrase(MQ, SRC); refused = False
except S.StoreError:
    refused = True
check("the store refuses to mark a quote", refused)
try:
    S.set_paraphrase(M1, M1); refused = False
except S.StoreError:
    refused = True
check("  or a block as a paraphrase of itself", refused)
def add_pic(data, blocks):
    S.add_block(data, blocks, PIC, {"image": "0123456789abcdef.png"}); blocks[ME]["content"].append(PIC)
S.transact(S.editing(add_pic))
try:
    S.set_paraphrase(PIC, SRC); refused = False
except S.StoreError:
    refused = True
check("  or a picture (only a block of text: a paraphrase is words)", refused and mark(PIC) is None)
try:
    S.set_paraphrase(ME, SRC); refused = False
except S.StoreError:
    refused = True
check("  or a pericope (a paraphrase is a block inside one, as a quote is)", refused and mark(ME) is None)

fresh()
S.set_paraphrase(M1, SRC)
t = F.fw("mine", rows=30)
to_m1(t); t.key(CTRL_T); t.settle()
moved = [c for c in S.children(B()[S.quoted(B()[M1])[0]])] if S.quoted(B()[M1]) else []
check("Turn into a quote on a paraphrase: the mark goes with its words, not onto the quote",
      mark(M1) is None and moved and mark(moved[0]) == SRC, (B()[M1], moved))
t.key(Q, ESC); t.done()

fresh()
S.set_paraphrase(M1, SRC)
S.delete_entry(SRC)
same("its source's entry deleted: the mark goes, the words stay", (mark(M1), B()[M1]["content"]), (None, "my words about it"))
def kids(i):
    b = B()
    return [("quote", S.quoted(b[k])[0]) if S.quoted(b[k]) else ("para", S.text_of(b[k]), S.paraphrases(b[k]))
            if S.paraphrases(b[k]) else b[k]["content"] for k in S.children(b[i])]
fresh()
t = F.fw("mine", rows=30)
t.key(UP, UP, MENU, "paraphrase it", ENTER); t.settle()   # onto the quote of src
same("Paraphrase it on a quote: an empty paraphrase of what it quoted, in its place", kids(ME), [("para", "", SRC), "other", "my words about it"])
check("  the source dim inside it as a guide, its top line ≈ src", "the original idea" in t.text() and "≈ src" in t.text(), t.text())
t.key("take"); t.settle()
same("  writing in it: your words, still pointing", kids(ME)[0], ("para", "take", SRC))
check("  the guide gone", "the original idea" not in t.text(), t.text())
t.key(Z, Z); t.settle()
same("^Z ^Z: the quote back, as it was", kids(ME), [("quote", SRC), "other", "my words about it"])
t.key(Q, ESC); t.done()

fresh()
t = F.fw("mine", rows=30)
t.key(MENU, "paraphrase it", ENTER); t.settle()   # on "my words about it"
k = kids(ME)
moved = k[-1][2] if isinstance(k[-1], tuple) else None
check("Paraphrase it on a block you wrote: it moves to an entry of its own, an empty paraphrase of that in its place",
      isinstance(k[-1], tuple) and k[:2] == [("quote", SRC), "other"] and k[-1][:2] == ("para", "") and B()[moved].get("entry"), k)
same("  the entry holds your old words", [B()[c]["content"] for c in S.children(B()[moved])], ["my words about it"])
t.key(Q, ESC); t.done()
t = F.fw("mine", rows=30)
t.settle()
same("left empty and reopened: still there, still pointing", kids(ME)[-1], ("para", "", moved))
check("  its guide shows", "my words about it" in t.text(), t.text())
t.key("short"); t.settle()
t.key(Z); t.settle()
t.key(Q, ESC); t.done()
t = F.fw("mine", rows=30)
t.key(Z); t.settle()   # (a fresh session: nothing to undo)
t.key(Q, ESC); t.done()

fresh()
t = F.fw("mine", rows=30)
t.key(MENU, "paraphrase it", ENTER); t.settle()
t.key(Z); t.settle()
same("^Z right after: your words back, the new entry gone", (kids(ME), moved in B() if False else len([b for b in B().values() if b.get("entry")])),
     ([("quote", SRC), "other", "my words about it"], 2))
t.key(Q, ESC); t.done()

def pic_only(data, blocks):
    S.add_block(data, blocks, PIC, {"image": "0123456789abcdef.png"}); blocks[ME]["content"] = [PIC]
fresh(); S.transact(S.editing(pic_only))
t = F.fw("mine", rows=30, env={"FW_PICTURES": "0"})
t.key(UP, MENU, "paraphrase it", ENTER); t.settle()   # (the picture's a pericope of its own, quoted here: its quote)
k = kids(ME)
check("Paraphrase it on a picture's quote: an empty paraphrase (its description) of the picture in its place",
      len(k) >= 1 and isinstance(k[0], tuple) and k[0][:2] == ("para", "") and S.image_of(B()[k[0][2]]), (k, t.text()))
t.key(Q, ESC); t.done()
# (Enter in a paraphrase, Show its source: the terminal editor, deprecated, isn't updated for v18; the web editor's are in web/test)

fresh()
t = F.fw("mine", rows=30)
t.key(UP, UP, MENU, "paraphrase it", ENTER); t.settle()
t.key(ENTER, "below"); t.settle()
same("Enter on a paraphrase not written yet: a plain block after it", kids(ME)[:2], [("para", "", SRC), "below"])
t.key(Q, ESC); t.done()

P, C1, C2 = "20261001T100000-f000", "20261001T100000-f001", "20261001T100000-f002"
draft = f"{S.block_line(C1, (P,))}\n\n{S.block_line(C2, (P,))}\n"
same("a paraphrase grown, then emptied: its blank blocks kept, so it isn't lost",
     S.draft_items(draft, (), {P}), [("blocks", P, [("text", C1, ""), ("text", C2, "")])])
same("  any other block emptied: gone, as ever", S.draft_items(draft, ()), [])
QH, QA, QB, QC = "20261003T100000-c000", "20261003T100000-c001", "20261003T100000-c002", "20261003T100000-c003"
fresh(); S.set_paraphrase(M1, SRC)
def quoting(data, blocks):
    S.add_block(data, blocks, QH, [QA, QB], "quoter", entry=True)
    S.add_block(data, blocks, QA, {"quote": ME}); S.add_block(data, blocks, QB, {"quote": M1})
S.transact(S.editing(quoting))
t = F.fw("quoter", rows=40)
check("a paraphrase inside a quote is still one: its box inside the quote, ≈ src on top", t.text().count("≈ src") == 2, t.text())
check("  a quote of a paraphrase itself says so on its top line", any("≈ src" in r and "┏" not in r for r in t.text().split("\n")), t.text())
t.key(Q, ESC); t.done()
# the migration (v18): a v17 mark on a block of text becomes the block's content; on anything else it's dropped
def marked_v17():
    top = lambda b: {**b, "entry": True}
    json.dump({"schemaVersion": 17, "blocks": [top(blk(SRC, [S1], "src")), blk(S1, "the original idea"), top(blk(ME, [M1, M2], "mine")),
               {**blk(M1, "my words about it"), "paraphrases": SRC}, {**blk(M2, [M3]), "paraphrases": SRC}, blk(M3, "inside")]},
              open(os.environ["FW_DATA"], "w"))
    S.cmd_migrate(None)
marked_v17()
same("v17 → v18: a marked block of text is a paraphrase, its words its text", B()[M1]["content"], {"paraphrase": SRC, "text": "my words about it"})
check("  the mark itself gone, everywhere", not any("paraphrases" in b for b in B().values()), [b for b in B().values() if "paraphrases" in b])
same("  a mark on a block holding blocks: dropped, the block as it was", B()[M2]["content"], [M3])
F.report("PARAPHRASE")
