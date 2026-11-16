# reviewing a kind's maybes (kinds, step 2): a kind's header has a maybes line, the pericopes a model guesses might be
# one (fw_block.maybes: unanswered, current, p ≥ 0.5, likeliest first; a guess about a block inside a pericope is
# applied at 0.9 instead, never reviewed, as a learned kind's is: fw_block.is_applied). Enter on it opens each in turn,
# the bar saying "poem? 95% · 1 of 3": Enter it is one, Backspace it isn't, Tab skip (each on to the next), ^Z back to
# the one before (its answer taken back), ^Q stop. Nothing types. Back on the kind, each answer is one ^Z.
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, UP, ENTER, BS, TAB, QUIT as Q, UNDO as Z, REDO as Y
S = F.use_store("t/review.json", clean=True)

MINE, M1, M2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
OTHER, O1 = "20261002T100000-b000", "20261002T100000-b001"
THIRD, T1 = "20261003T100000-c000", "20261003T100000-c001"
POEM, PD = "20261004T100000-d000", "20261004T100000-d001"
LET = "20261005T100000-e000"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}
T, T2 = "2026-10-01T10:00:00-04:00", "2026-10-02T10:00:00-04:00"
GUESSES = os.path.join(os.path.dirname(os.environ["FW_DATA"]), "kind-guesses.json")

def blk(i, content, title=None, entry=False, **more):
    return {"id": i, "title": title, **({"entry": True} if entry else {}), "content": content, "words": 0,
            "created": T, "updated": T, **more}
def fresh():
    """mine: M1 (a poem, said so) and M2; other: O1; the kinds poem (described) and letter."""
    blocks = [blk(MINE, [M1, M2], "mine", True), blk(M1, "roses are red", kinds={POEM: True}), blk(M2, "buy milk"),
              blk(OTHER, [O1], "other", True), blk(O1, "an old pond"),
              blk(THIRD, [T1], "third", True), blk(T1, "a third thing"),
              blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True), blk(PD, "a short piece in lines"),
              blk(LET, {"kind": "letter", "blocks": []}, entry=True)]
    json.dump({"schemaVersion": 17, "blocks": blocks}, open(os.environ["FW_DATA"], "w"))
    S.cmd_migrate(None)
    for f in ("t/mac.txt", S.CLIP_PATH, GUESSES):
        if os.path.exists(f): os.remove(f)
def B(): return S.index(S.load_data())
def g(p, kind_at=T, block_at=T): return [p, kind_at, block_at]
def write_guesses(guesses, learned=()):
    sources = {k: {"source": "learned", "yes": 10, "no": 0} for k in learned}
    json.dump({"model": "m", "guesses": guesses, "sources": sources}, open(GUESSES + ".tmp", "w")); os.replace(GUESSES + ".tmp", GUESSES)
def bar(t): return t.row(t.scr.lines - 1)
def row_of(t, text): return next((y for y in range(t.scr.lines) if text in t.row(y)), None)
def maybes_row(t):
    y = row_of(t, "maybes")
    return None if y is None else t.row(y)
def to_maybes(t):
    for _ in range(6):
        if "maybes" in bar(t): return True
        t.key(UP)
    return "maybes" in bar(t)

# --- pure: the maybes ------------------------------------------------------------------------------------------------
fresh()
b = B()
data = {"guesses": {POEM: {M1: g(0.99), M2: g(0.95), O1: g(0.7), MINE: g(0.95), OTHER: g(0.6), PD: g(0.8, block_at=T2),
                           LET: g(0.97), POEM: g(0.99)},
                    LET: {MINE: g(0.99)}}}
same("maybes: pericopes, unanswered, current, p ≥ 0.5, likeliest first", S.maybes(data, b, POEM), [(LET, 0.97), (MINE, 0.95), (OTHER, 0.6)])
check("  never a block inside a pericope (M2, O1)", not {M2, O1} & {i for i, _ in S.maybes(data, b, POEM)})
same("  from 0.5 up (the 0.9 of the dim guesses on blocks stays)", (S.MAYBE_AT, S.GUESS_AT), (0.5, 0.9))
same("  under 0.5: not a maybe", S.maybes({"guesses": {POEM: {MINE: g(0.49)}}}, b, POEM), [])
same("  ties: the oldest first", S.maybes({"guesses": {POEM: {OTHER: g(0.8), MINE: g(0.8)}}}, b, POEM), [(MINE, 0.8), (OTHER, 0.8)])
same("  another kind's: its own", S.maybes(data, b, LET), [(MINE, 0.99)])
same("is_applied: a guess about a block inside a pericope, or a learned kind's; a pericope's, otherwise, asked",
     [S.is_applied(b, M2, POEM, set()), S.is_applied(b, MINE, POEM, set()), S.is_applied(b, MINE, POEM, {POEM}),
      S.is_applied(S.build_library(S.load_data()), O1, LET, set())], [True, False, True, True])
same("  nothing malformed counts", [S.maybes(x, b, POEM) for x in (None, {}, {"guesses": {POEM: []}})], [[]] * 3)

# --- the maybes line: only a kind's ----------------------------------------------------------------------------------
fresh()
write_guesses({POEM: {MINE: g(0.95), OTHER: g(0.7), THIRD: g(0.6), M1: g(0.99), O1: g(0.5)}})
t = F.fw("mine", rows=30, cols=80, env=ENV)
check("a pericope's header has no maybes line", maybes_row(t) is None, t.text())
t.key(Q); t.close()
t = F.fw("letter", rows=30, cols=80, env=ENV)
check("a kind with none: 'none'", maybes_row(t) is not None and "none" in maybes_row(t), t.text())
check("  reached with ↑", to_maybes(t), bar(t))
t.key(ENTER)
check("  Enter: says there's nothing to review, stays", "no maybes" in bar(t) and "maybes" in maybes_row(t), bar(t))
t.key(Q); t.close()

# --- reviewing them, one at a time -------------------------------------------------------------------------------------
t = F.fw("poem", rows=30, cols=80, env=ENV)
check("a kind's header: maybes, 3 to review", maybes_row(t) is not None and "3 · ↵ review them" in maybes_row(t), t.text())
check("  reached with ↑ (above the kinds line and the title)", to_maybes(t), bar(t))
t.key(ENTER)
check("Enter: the likeliest opens, the bar asking", "poem? 95% · 1 of 3" in bar(t) and "buy milk" in t.text(),
      bar(t) + "\n" + t.text())
check("  the bar's keys", "↵ yes" in bar(t) and "⌫ no" in bar(t) and "⇥ skip" in bar(t) and "^Q stop" in bar(t), bar(t))
check("  on the trail, under the kind", "poem ›" in bar(t), bar(t))
t.key("x")
same("nothing types", B()[M2]["content"], "buy milk")
check("  the bar says what to press", "↵ it is one" in bar(t), bar(t))
t.key(ENTER); t.settle()
same("Enter: it is one (a yes)", S.kinds_of(B()[MINE]), {POEM: True})
check("  on to the next", "poem? 70% · 2 of 3" in bar(t) and "an old pond" in t.text(), bar(t))
check("  not an edit: the block's updated stays", B()[MINE]["updated"] == T, B()[MINE].get("updated"))
t.key(BS); t.settle()
same("Backspace: it isn't (a no)", S.kinds_of(B()[OTHER]), {POEM: False})
check("  on to the last", "poem? 60% · 3 of 3" in bar(t) and "a third thing" in t.text(), bar(t))
t.key(Z); t.settle()
same("^Z: back to the one before, its answer taken back", S.kinds_of(B()[OTHER]), {})
check("  it's open again, 2 of 3", "poem? 70% · 2 of 3" in bar(t), bar(t))
t.key(TAB); t.settle()
same("Tab: skipped, no answer", S.kinds_of(B()[OTHER]), {})
check("  on to the last", "3 of 3" in bar(t), bar(t))
t.key(Q); t.settle()
check("^Q: stop, back on the kind, the bar says how it went",
      "reviewed: 1 yes, 0 no, 1 skipped · 1 left" in bar(t) and "maybes" in t.text(), bar(t))
check("  the maybes line counts what's left: the skipped one and the one not reached", "2 · ↵ review them" in maybes_row(t), maybes_row(t))
t.key(Z); t.settle()
same("back on the kind, ^Z takes an answer back", S.kinds_of(B()[MINE]), {})
check("  a maybe again", "3 · ↵ review them" in maybes_row(t), maybes_row(t))
t.key(Y); t.settle()
same("  ^Y: the yes again", S.kinds_of(B()[MINE]), {POEM: True})
check("to the end: back on the kind by itself", to_maybes(t), bar(t))
t.key(ENTER)
check("  the two left, the likeliest first", "poem? 70% · 1 of 2" in bar(t), bar(t))
t.key(ENTER); t.settle(); t.key(ENTER); t.settle()
check("  back on the kind", "reviewed: 2 yes, 0 no" in bar(t) and "left" not in bar(t), bar(t))
same("  both answered", (S.kinds_of(B()[OTHER]), S.kinds_of(B()[THIRD])), ({POEM: True}, {POEM: True}))
check("  none left", "none" in maybes_row(t), maybes_row(t))
t.key(Q); t.close()

# --- a maybe that's gone by the time it's reached is passed over ---------------------------------------------------------
fresh()
write_guesses({POEM: {MINE: g(0.95), OTHER: g(0.7)}})
t = F.fw("poem", rows=30, cols=80, env=ENV)
to_maybes(t); t.key(ENTER)
S.delete_entry(OTHER)
t.key(ENTER); t.settle()
check("a maybe deleted meanwhile: passed over, back on the kind", "reviewed: 1 yes, 0 no, 1 skipped" in bar(t), bar(t))
t.key(Q); t.close()

# --- a learned kind's guesses that count are applied: like a yes, marked ·; under 0.9 still maybes ----------------------
fresh()
b = B()
data = {"guesses": {POEM: {MINE: g(0.95), OTHER: g(0.7)}, LET: {MINE: g(0.97)}}, "sources": {POEM: {"source": "learned"}, LET: {"source": "qwen"}}}
same("learned: the kinds whose source is learned", S.learned(data), {POEM})
same("  anything malformed: none", [S.learned(x) for x in (None, {}, {"sources": []}, {"sources": {POEM: "learned"}})], [set()] * 4)
same("a learned kind's maybes: only under 0.9 (over it, applied)", S.maybes(data, b, POEM), [(OTHER, 0.7)])
same("  another kind's: from 0.5 up, as before", S.maybes(data, b, LET), [(MINE, 0.97)])
write_guesses({POEM: {MINE: g(0.95)}, LET: {MINE: g(0.97)}}, learned=[POEM])
t = F.fw("mine", rows=30, cols=80, env=ENV)
y = row_of(t, "kinds")
check("on the block: the applied kind 'poem·', the other guess 'letter?'", " poem· " in t.row(y) and " letter? " in t.row(y), t.row(y))
c = t.cell(y, t.row(y).index(" poem· ") + 1)
check("  applied: white on blue, like a yes", c.bg == "005faf" and c.fg == "white", (c.fg, c.bg))
same("  never stored", S.kinds_of(B()[MINE]), {})
for _ in range(5):
    if "kinds" in bar(t): break
    t.key(UP)
t.key(F.HOME); t.key(ENTER); t.settle()
same("Enter on it: your yes", S.kinds_of(B()[MINE]), {POEM: True})
check("  drawn as yours, the mark gone", " poem " in t.row(row_of(t, "kinds")) and "poem·" not in t.text(), t.row(row_of(t, "kinds")))
t.key(Z); t.settle()
same("^Z: applied again", (S.kinds_of(B()[MINE]), " poem· " in t.row(row_of(t, "kinds"))), ({}, True))
t.key(F.BS); t.settle()
same("Backspace on it: a no", S.kinds_of(B()[MINE]), {POEM: False})
t.key(Q); t.close()
fresh()
write_guesses({POEM: {MINE: g(0.95), OTHER: g(0.7)}}, learned=[POEM])
t = F.fw("poem", rows=30, cols=80, env=ENV)
check("the kind's maybes line: the maybes, and how many are applied", "1 · ↵ review them · 1 applied" in (maybes_row(t) or ""), maybes_row(t))
t.key(Q); t.close()
write_guesses({POEM: {M2: g(0.95), O1: g(0.92), T1: g(0.7), OTHER: g(0.7)}})
t = F.fw("poem", rows=30, cols=80, env=ENV)
check("  a kind not learned: its guesses about blocks inside pericopes applied (≥ 0.9), not reviewed",
      "1 · ↵ review them · 2 applied" in (maybes_row(t) or ""), maybes_row(t))
t.key(Q); t.close()
from fw_picker import Picker, blocks_inside
lib = S.build_library(S.load_data())
def kind_rows(applied):
    refs = sorted(r for r, e in lib.items() if e["entry"])
    p = Picker(lib, refs, inside=blocks_inside(lib, refs), guesses={MINE: {POEM: 0.95}}, applied=applied)
    for ch in "poem": p.key(ch)
    return [r for r in p.rows() if r[0] in (POEM, MINE)]
rows = kind_rows({POEM})
check("search for a learned kind: its applied blocks listed as the said ones, not dim",
      [r[0] for r in rows[:2]] == [POEM, MINE] and len(rows[1]) == 3, rows[:2])
check("  a kind that isn't learned: its guessed pericopes dim, as before", len(kind_rows(set())[1]) == 4, kind_rows(set())[:2])
refs = sorted(r for r, e in lib.items() if e["entry"])
p = Picker(lib, refs, inside=blocks_inside(lib, refs), guesses={M2: {POEM: 0.95}}, applied=set())
for ch in "poem": p.key(ch)
r = next((r for r in p.rows() if r[0] == M2), None)
check("  a block inside a pericope: applied, not dim, whichever kind", r is not None and len(r) == 3, p.rows())

F.report("REVIEW")
