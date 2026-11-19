# emptying the original of a masked quote: undo puts the quote's mask back with the text (undo is total), and
# a span whose text was all deleted stays as an empty place, so text typed there shows again
import sys
sys.path.insert(0, ".")
exec(open("maskui_test.py").read().split("# --- checks")[0])   # fresh(), Term, ids, helpers
from fwtest import REDO as Y, DEL, same

def edit_alpha():  # the editor on the original, Alpha
    F.write_meta(A, "t/a.meta.json"); open("t/a.txt", "w").write(adraft())
    return F.editor("t/a.txt", "--meta", "t/a.meta.json")
def select_quick_brown(t):  # on "the quick brown fox": "quick brown" selected
    t.key(HOME, RIGHT * 4, *[SRIGHT] * 11)

# --- undo is total: the mask comes back with the text
fresh([qk, br]); before = state()
t = edit_alpha(); select_quick_brown(t); t.key(DEL); t.settle()
check("the shown text deleted from the original", "quick" not in adraft(), adraft())
t.key(Z); t.settle()
check("^Z in the original: the text back, and the quote's mask with it", state() == before, diff(before, state()))
check("  the quote shows what it showed", shown() == ["quick brown"], shown())
t.key(Y); t.settle()
check("^Y: deleted again", "quick" not in adraft(), adraft())
t.key(Z); t.settle()
check("  ^Z once more: as it was", state() == before, diff(before, state()))
t.close()

# a span's edge moved by an edit, not emptied: undo puts the edge back too (not grown over what was hidden)
fresh([qk, br]); before = state()
t = edit_alpha(); t.key(HOME, RIGHT * 14, *[SRIGHT] * 3, DEL); t.settle()   # "own f" -> deletes "n f" across the span's end
t.key(Z); t.settle()
check("an edit across a span's end, then ^Z: the mask exactly as it was", state() == before, diff(before, state()))
t.close()

# --- an emptied range stays as an empty place: text typed there shows
import json
def on_disk(): return next(b["content"].get("mask") for b in json.load(open("t/store.json"))["blocks"] if b["id"] == QM)
fresh([qk, br])
t = edit_alpha(); select_quick_brown(t); t.key(DEL); t.settle()
check("the shown text deleted: the quote shows nothing", shown() == [], (mask(), adraft()))
same("  its place kept on disk, an empty range where the text was", on_disk(), {CA: [[4, 4]]})
p = adraft().index("the ") + 4
same("  and read back from the Loro document", S.raw_mask(B()[QM]), [p, p])
S.set_quote_mask(QM, adraft(), [p - 4, p - 1])
same("  masking anew keeps it where it's still hidden", S.raw_mask(B()[QM]), [p - 4, p - 1, p, p])
S.set_quote_mask(QM, adraft(), [])
t.key("slow "); t.settle()
same("text typed there shows in the quote", shown(), ["slow "])
t.close()

fresh([qk, br])
t = edit_alpha(); select_quick_brown(t); t.key(DEL); t.settle()
t.key(LEFT, LEFT, "a"); t.settle()
check("typed elsewhere: still hidden, the place still kept", shown() == [] and on_disk() == {CA: [[5, 5]]}, (shown(), on_disk()))
t.close()

# --- drawn: a quote whose text was all deleted says so; one masked to hide everything is a …
fresh([qk, br])
t = edit_alpha(); select_quick_brown(t); t.key(DEL); t.settle(); t.close()
t = Term()
check("where it's quoted: (nothing here now), not a lone …", "(nothing here now)" in t.text() and "…" not in t.text(), t.text())
t.close()
fresh([qk, br]); S.set_quote_mask(QM, adraft(), [])
t = Term()
check("a mask that hides it all on purpose: still a …", "…" in t.text() and "nothing here now" not in t.text(), t.text())
t.close()

F.report("EMPTIED")
