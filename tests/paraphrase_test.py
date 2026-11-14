# paraphrases: any block but a quote marked as pointing at another (Paraphrases…, Not a paraphrase); drawn red, "≈ source"
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, ENTER, ESC, MENU, QUIT as Q, UNDO as Z
S = F.use_store("t/paraphrase.json", clean=True)
SRC, S1 = "20261001T100000-5000", "20261001T100000-5001"
ME, M1, M2, MQ = "20261002T100000-b000", "20261002T100000-b001", "20261002T100000-b002", "20261002T100000-b003"
PIC = "20261002T100000-b004"
CTRL_O, CTRL_T = "\x0f", "\x14"
def fresh():
    F.write_store([blk(SRC, [S1], "src"), blk(S1, "the original idea"),
                   blk(ME, [MQ, M2, M1], "mine"), blk(M1, "my words about it"), blk(MQ, {"quote": SRC}), blk(M2, "other")],
                  [SRC, ME], version=9)
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())
def mark(i): return B().get(i, {}).get("paraphrases")
def bar(t): return t.row(t.scr.lines - 1)
def to_m1(t): pass   # (fw opens at the end of the last block: "my words about it")

fresh()
t = F.fw("mine", rows=30)
to_m1(t); t.key(MENU)
check("Ctrl+/ on a block you wrote offers Paraphrases…", "Paraphrases…" in t.text(), t.text())
t.key("paraphrases", ENTER, "src", ENTER); t.settle()
same("picking its source marks it", mark(M1), SRC)
check("  drawn with its source on its top line", "≈ src" in t.text(), t.text())
check("  the words are untouched", B()[M1]["content"] == "my words about it")
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
S.transact(add_pic)
S.set_paraphrase(PIC, SRC)
same("a picture can be one (an illustration of it)", mark(PIC), SRC)

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
    return [("quote", S.quoted(b[k])[0]) if S.quoted(b[k]) else ("para", b[k]["content"], b[k].get("paraphrases"))
            if b[k].get("paraphrases") else b[k]["content"] for k in S.children(b[i])]
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
fresh(); S.transact(pic_only)
t = F.fw("mine", rows=30, env={"FW_PICTURES": "0"})
t.key(MENU, "paraphrase it", ENTER); t.settle()
k = kids(ME)
check("Paraphrase it on a picture: it moves out, an empty paraphrase (its description) in its place",
      len(k) >= 1 and isinstance(k[0], tuple) and k[0][:2] == ("para", "") and S.image_of(B()[S.children(B()[k[0][2]])[0]]), (k, t.text()))
t.key(Q, ESC); t.done()
fresh(); S.set_paraphrase(M1, SRC)
t = F.fw("mine", rows=34)   # at the end of "my words about it", a paraphrase
t.key(ENTER, "second"); t.settle()
same("Enter in a paraphrase grows it: a block inside it, the mark on the whole", kids(ME)[-1][2], SRC)
same("  holding both", [B()[c]["content"] for c in S.children(B()[M1])], ["my words about it", "second"])
check("  one box, ≈ src on top", t.text().count("≈ src") == 1, t.text())
t.key(ENTER, ENTER, "after"); t.settle()
same("Enter on an empty one inside: out, a plain block after it", kids(ME)[-1], "after")
same("  the paraphrase as it was", (B()[M1].get("paraphrases"), [B()[c]["content"] for c in S.children(B()[M1])]),
     (SRC, ["my words about it", "second"]))
t.key(UP, MENU, "show its source", ENTER, ESC); t.settle()
check("Show its source: its text, dim, inside it", t.text().count("the original idea") == 2, t.text())
t.key(MENU)
check("  the command now hides it", "Hide its source" in t.text(), t.text())
t.key("hide", ENTER, ESC); t.settle()
check("  hidden again", t.text().count("the original idea") == 1, t.text())
t.key(Q, ESC); t.done()

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
S.transact(quoting)
t = F.fw("quoter", rows=40)
check("a paraphrase inside a quote is still one: its box inside the quote, ≈ src on top", t.text().count("≈ src") == 2, t.text())
check("  a quote of a paraphrase itself says so on its top line", any("≈ src" in r and "┏" not in r for r in t.text().split("\n")), t.text())
t.key(Q, ESC); t.done()
F.report("PARAPHRASE")
