# paraphrases: a block of their own, like a quote ({paraphrase: the original, text: your words}, schema v18), made
# from a block of text (set_paraphrase) or in a quote's or block's place (paraphrase_it)
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("paraphrase")
SRC, S1 = "20261001T100000-5000", "20261001T100000-5001"
ME, M1, M2, MQ, PIC, M3 = ("20261002T100000-b000", "20261002T100000-b001", "20261002T100000-b002", "20261002T100000-b003",
                           "20261002T100000-b004", "20261002T100000-b005")
def fresh():
    F.store(blk(SRC, [S1], "src", entry=True), blk(S1, "the original idea"),
            blk(ME, [MQ, M2, M1], "mine", entry=True), blk(M1, "my words about it"), blk(MQ, {"quote": SRC}), blk(M2, "other"))
def mark(i): return S.paraphrases(F.blocks().get(i))

fresh()
record = S.set_paraphrase(M1, SRC)
same("marked a paraphrase of its source, the words untouched", (mark(M1), S.text_of(F.blocks()[M1])), (SRC, "my words about it"))
same("  the source's backlinks list it", sorted((x["kind"], x["home"]) for x in S.backlinks(F.blocks(), SRC)), [("paraphrase", ME), ("quote", ME)])
S.restore(record)
same("  undone: not a paraphrase again", mark(M1), None)
S.set_paraphrase(M1, SRC); S.set_paraphrase(M1, None)
same("Not a paraphrase: the mark goes, the words stay", (mark(M1), F.content(M1)), (None, "my words about it"))
F.edit(lambda d, b: (S.add_block(d, b, PIC, {"image": "0123456789abcdef.png"}), b[ME]["content"].append(PIC)))
for label, ref, src in (("a quote", MQ, SRC), ("a block as a paraphrase of itself", M1, M1), ("a pericope", ME, SRC)):
    check(f"refused: {label}", F.refused(S.set_paraphrase, ref, src) and mark(ref) is None)
check("  a picture (only words can be a paraphrase)", F.refused(S.set_paraphrase, PIC, SRC) and S.image_of(F.blocks()[PIC]))

fresh(); S.set_paraphrase(M1, SRC)
new, _, _ = S.pop_out(M1)
moved = S.children(F.blocks()[new])[0]
same("Turn into a quote on a paraphrase: the mark goes with its words, not onto the quote", (mark(M1), mark(moved)), (None, SRC))
fresh(); S.set_paraphrase(M1, SRC)
S.delete_entry(SRC)
same("its source deleted: the mark goes, the words stay", (mark(M1), F.content(M1)), (None, "my words about it"))

# Paraphrase it: an empty paraphrase in its place
fresh()
pid, record = S.paraphrase_it(MQ)
same("on a quote: an empty paraphrase of what it quoted, in its place", F.kids(ME), [("para", "", SRC), "other", "my words about it"])
S.commit(ME, S.block_draft(F.blocks(), ME).replace(S.block_line(pid) + "\n", S.block_line(pid) + "\ntake", 1), [])
same("  written in: your words, still pointing", F.kids(ME)[0], ("para", "take", SRC))
fresh(); pid, record = S.paraphrase_it(MQ); S.restore(record)
same("  undone: the quote back", F.kids(ME), [("quote", SRC), "other", "my words about it"])
fresh()
pid, record = S.paraphrase_it(M1)
k = F.kids(ME)
moved = k[-1][2]
check("on a block you wrote: it moves to a pericope of its own, an empty paraphrase of that in its place",
      k[:2] == [("quote", SRC), "other"] and k[-1][:2] == ("para", "") and F.blocks()[moved].get("entry"), k)
same("  that pericope holds your words", F.kids(moved), ["my words about it"])
S.commit(ME, S.block_draft(F.blocks(), ME), [])
same("  saved left empty: kept, still pointing", F.kids(ME)[-1], ("para", "", moved))
S.restore(record)
same("  undone: your words back, the new pericope gone", (F.kids(ME), moved in F.blocks()), ([("quote", SRC), "other", "my words about it"], False))
check("on nothing written: refused", F.refused(S.paraphrase_it, "20261002T100000-ffff") == "write something first")
fresh()
F.edit(lambda d, b: (S.add_block(d, b, PIC, {"image": "0123456789abcdef.png"}), b[ME].update(content=[PIC])))
S.paraphrase_it(S.children(F.blocks()[ME])[0])   # (the picture's a pericope of its own, quoted here)
k = F.kids(ME)
check("on a picture's quote: an empty paraphrase (its description) of the picture", k[0][:2] == ("para", "") and S.image_of(F.blocks()[k[0][2]]), k)

P, C1, C2 = "20261001T100000-f000", "20261001T100000-f001", "20261001T100000-f002"
draft = f"{S.block_line(C1, (P,))}\n\n{S.block_line(C2, (P,))}\n"
same("a paraphrase grown, then emptied: its blank blocks kept, so it isn't lost",
     S.draft_items(draft, (), {P}), [("blocks", P, [("text", C1, ""), ("text", C2, "")])])
same("  any other block emptied: gone, as ever", S.draft_items(draft, ()), [])

# the migration (v18): a v17 mark on a block of text becomes the block's content; on anything else it's dropped
F.store(blk(SRC, [S1], "src", entry=True), blk(S1, "the original idea"), blk(ME, [M1, M2], "mine", entry=True),
        {**blk(M1, "my words about it"), "paraphrases": SRC}, {**blk(M2, [M3]), "paraphrases": SRC}, blk(M3, "inside"))
same("v17 → v18: a marked block of text is a paraphrase, its words its text", F.content(M1), {"paraphrase": SRC, "text": "my words about it"})
check("  the mark itself gone, everywhere", not any("paraphrases" in b for b in F.blocks().values()))
same("  a mark on a block holding blocks: dropped, the block as it was", F.content(M2), [M3])
F.report()
