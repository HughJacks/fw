import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import same as check, blk
S = F.use_store("t/mask.json")
E, Q, P = S.ELLIPSIS, S.CLOSE, S.OPEN
A, CA, CB, ME, QM, T = "20261001T100000-aaaa", "20261001T100000-c0a0", "20261001T100000-c0b0", "20261021T230000-0000", "20261021T230000-9999", "20261021T230000-c001"
def fresh(mask=None, a_text=("the quick brown fox", "jumps over the lazy dog")):
    q = {"quote": A} if mask is None else {"quote": A, "mask": mask}
    json.dump({"schemaVersion": 5, "entries": [A, ME], "blocks": [
        blk(A, [CA, CB], "Alpha"), blk(CA, a_text[0]), blk(CB, a_text[1]),
        blk(ME, [T, QM], "mine"), blk(T, "my own words"), blk(QM, q)]}, open("t/mask.json", "w"))
    return S.block_draft(S.index(S.load_data()), A)
def draft(): return S.block_draft(S.index(S.load_data()), A)
def mask(): return S.quoted(S.index(S.load_data())[QM])[1]
def shown(): return [i for i in S.block_items(S.index(S.load_data()), ME)]

d = fresh()
quick = d.index("quick"); brown_end = d.index("brown") + 5; lazy = d.index("lazy")
m = [quick, brown_end]
check("view: an ellipsis on each side of the shown part", S.view(d, m).count(E), 2)
v = S.view(d, m)
check("  reads …quick brown…", v.split("\n")[-1] if "\n" in v else v, f"{E}quick brown{E}")
check("put(view) unchanged = the same draft and mask", S.put(d, m, v), (d, m))
nd, nm = S.put(d, m, v.replace("quick brown", "quick red-brown"))
check("put an edit: hidden text kept, range grows", nd.split("\n")[1], "the quick red-brown fox")
check("  the mask covers the edited text", nd[nm[0]:nm[1]], "quick red-brown")
nd, nm = S.put(d, m, v.replace(f"{E}quick", f"{E}very quick"))
check("typing at an anchor joins the shown part", nd[nm[0]:nm[1]], "very quick brown")
check("normalize: one range over everything is no mask", S.normalize(d, [0, len(d)]), None)
check("normalize: nothing shown is []", S.normalize(d, []), [])
two = [quick, brown_end, lazy, lazy + 4]
check("two ranges in two blocks: …quick brown… / …lazy…, each block its own …", S.view(d, two).count(E), 4)
check("  the blocks kept apart: the second's marker shows, hidden text never runs them together", S.view(d, two), d[:d.index("the quick")] + E + "quick brown" + E + d[d.index("\n{{block", quick):lazy - len("jumps over the ")] + E + "lazy" + E)
check("normalize merges ranges with nothing between", S.normalize(d, [quick, quick + 5, quick + 5, brown_end]), [quick, brown_end])
check("snap keeps anchors out of marker lines", S.snap(d, 3, True) == d.index("the quick"), True)
last = len(S.pieces(d, m)[0]) - 1   # the hole after "brown" (the first is before A's kept marker)
op = S.view(d, m, opened=last)
check("opened: the hole laid open between CLOSE and OPEN", P not in op and Q in op and op.endswith(d[brown_end:]), True)
nd, nm = S.put(d, m, op.replace(Q + " fox", " fox" + Q), opened=last)
check("moving CLOSE right (in the opened view) shows more", nd[nm[0]:nm[1]], "quick brown fox")
old = d; new = d.replace("the quick", "THE quick")
check("rebase: an edit before the range shifts it", new[S.rebase(old, new, m)[0]:S.rebase(old, new, m)[1]], "quick brown")
new = d.replace("quick brown", "quick and brown")
r = S.rebase(old, new, m)
check("rebase: an edit inside grows with it", new[r[0]:r[1]], "quick and brown")
new = d.replace("brown fox", "brownish fox")
r = S.rebase(old, new, m)
check("rebase: typing right at the close anchor joins the range", new[r[0]:r[1]], "quick brownish")

# --- through the store
fresh(m)
words = S.word_count(S.full_text(S.index(S.load_data()), ME))
check("words count only the shown part (3 own + 2 shown)", words, 5)
S.commit(A, d.replace("the quick", "oh the quick"), [])
check("editing the source elsewhere keeps the mask on the same words", draft()[mask()[0]:mask()[1]], "quick brown")
h = S.commit_view(QM, S.view(draft(), mask()).replace("quick brown", "quick, quick brown"))
check("commit_view puts the edit into the source", S.own_text(S.index(S.load_data()), A), "oh the quick, quick brown fox\njumps over the lazy dog")
check("  and the mask still shows exactly the shown part", draft()[mask()[0]:mask()[1]], "quick, quick brown")
check("  returns new hashes for the source and the quote's holder", sorted(h), sorted([A, ME]))
fresh()
dd = draft(); S.set_quote_mask(QM, dd, [dd.index("lazy"), dd.index("lazy") + 8])
check("set_quote_mask from the editor's draft", draft()[mask()[0]:mask()[1]], "lazy dog")
S.set_quote_mask(QM, None, None)
check("show all again", mask(), None)
fresh([quick, brown_end])
text, _, _ = S.detach(QM)
B = S.index(S.load_data())
check("detach: the quote becomes its shown text, … for what was hidden", (text, B[QM]["content"]), ("…quick brown…", "…quick brown…"))
check("  and A is no longer reached through it", S.quoted(B[QM]), None)
fresh()
entry, _, _ = S.pop_out(T)
B = S.index(S.load_data())
check("pop out: the block becomes a quote of a new entry", (S.quoted(B[T])[0] == entry, entry in S.entry_ids(S.load_data())), (True, True))
check("  which holds the text, titled from its first line", (S.own_text(B, entry), S.display_title(B, entry)), ("my own words", "my own words"))
check("  and the entry still shows the same text", S.full_text(B, ME), "my own words\nthe quick brown fox\njumps over the lazy dog")
fresh(m)
S.commit(ME, S.block_draft(S.index(S.load_data()), ME), [])
check("saving the quoting entry keeps the quote's mask", mask(), m)
fresh(m)
dme = S.block_draft(S.index(S.load_data()), ME)
S.commit(ME, dme + "\n" + S.quote_line(A, QM), [])
B = S.index(S.load_data())
qs = [k for k in S.children(B[ME]) if S.quoted(B[k])]
check("a second copy of the same quote line gets its own block, mask copied", (len(qs), S.quoted(B[qs[1]])[1]), (2, m))
# --- editing a mask: brackets as an interval set
d10, L = "0123456789", 10
check("[ in hidden text shows to the end", S.open_at([], 4, L), [4, 10])
check("] in hidden text shows from the start", S.close_at([], 4, L), [0, 4])
check("[ in hidden text runs up to the next span (touching, kept apart)", S.open_at([6, 8], 2, L), [2, 6, 6, 8])
check("] in shown text hides to the span's end", S.close_at([0, 10], 4, L), [0, 4])
check("[ in shown text hides from the span's start", S.open_at([0, 10], 4, L), [4, 10])
check("[ then ] make an isolated span in a gap", S.close_at(S.open_at([0, 2, 8, 10], 4, L), 6, L), [0, 2, 4, 6, 8, 10])
check("touching spans join when the edit is done", S.normalize(d10, [0, 3, 3, 5]), [0, 5])
check("wrap inside a shown span narrows it to the selection", S.wrap([0, 10], 3, 6), [3, 6])
check("wrap in hidden text adds a span", S.wrap([0, 2], 5, 7), [0, 2, 5, 7])
check("hide a selection splits a span", S.minus([0, 10], 3, 5), [0, 3, 5, 10])
check("drop an opener: joins the gap before", S.drop_anchor([0, 2, 5, 8], 2, L), [0, 8])
check("drop the last closer: runs to the end", S.drop_anchor([0, 2, 5, 8], 3, L), [0, 2, 5, 10])
check("restore's inverse brings back blocks made under it", "subtree" in dir(S), True)

# a hidden stretch that spans a line break keeps it, after its …
db = "{{block a}}\nA quote is a window.\n{{block b}}\nhidden line\nQuotes edit through.\n{{block c}}\nlast"
mb = [db.index("A quote"), db.index("window.") + 7, db.index("Quotes"), len(db)]
check("a hidden stretch across lines: … then the break", S.view(db, mb), "{{block a}}\nA quote is a window." + E + "\nQuotes edit through.\n{{block c}}\nlast")
check("  within a line: no break", S.view("{{block a}}\none two three", [12, 15, 20, 26]), "{{block a}}\none" + E + "three")
check("  put takes the break back out", S.put(db, mb, S.view(db, mb))[0], db)
check("  text typed after the … joins the shown text after it", S.put(db, mb, S.view(db, mb).replace(E + "\n", E + "X\n"))[0], db.replace("Quotes", "XQuotes"))
import random
random.seed(7)
fails = []
for _ in range(2000):   # every mask: put(view) is the draft, and every view position maps into it
    mk = S.normalize(db, sorted(random.sample(range(len(db) + 1), 4)))
    if mk and (S.put(db, mk, S.view(db, mk))[0] != db or not all(0 <= S.view_to_draft(db, mk, v) <= len(db) for v in range(len(S.view(db, mk)) + 1))):
        fails.append(mk)
check("  2000 random masks round-trip", fails, [])

# on disk a mask is per block, like links: what shows of each block, in its own text
d = fresh([quick, brown_end, lazy, lazy + 4])
S.cmd_migrate(None)
raw = next(b for b in json.load(open("t/mask.json"))["blocks"] if b["id"] == QM)["content"]
check("on disk: per block, spans of each block's own text", raw["mask"], {CA: [[4, 15]], CB: [[15, 19]]})
check("  read back as anchors into the whole draft, the same as before", mask(), [quick, brown_end, lazy, lazy + 4])
d = fresh([quick, lazy + 4])   # one span across the boundary
S.cmd_migrate(None)
raw = next(b for b in json.load(open("t/mask.json"))["blocks"] if b["id"] == QM)["content"]
check("a span across two blocks is split between them", raw["mask"], {CA: [[4, 19]], CB: [[0, 19]]})
check("  and joins up again in memory", mask(), [quick, lazy + 4])
d = fresh([])
S.cmd_migrate(None)
raw = next(b for b in json.load(open("t/mask.json"))["blocks"] if b["id"] == QM)["content"]
check("showing nothing: no block listed", (raw["mask"], mask()), ({}, []))
blocks = {b["id"]: b for b in S.masks_out(S.load_data()["blocks"])}
check("a block a mask doesn't list shows nothing of it", S.flat_mask(S.regions(blocks, A, draft()), draft(), {CB: [[0, 5]]}), [d.index("jumps"), d.index("jumps") + 5])
check("  a quote inside, listed, shows: [[0, 1]] is the whole quote line", S.per_block([(QM, 10, 20, True)], [5, 25]), {QM: [[0, 1]]})
d = fresh(); regs = S.regions(S.index(S.load_data()), A, d); fails = []
for _ in range(2000):
    mk = S.normalize(d, sorted(random.sample(range(len(d) + 1), random.choice([2, 4, 6]))))
    once = S.flat_mask(regs, d, S.per_block(regs, mk))
    if mk is not None and S.flat_mask(regs, d, S.per_block(regs, once)) != once:
        fails.append(mk)
check("  2000 random masks: to disk and back is stable", fails, [])
F.report("MASK")
