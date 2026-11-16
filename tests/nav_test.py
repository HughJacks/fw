# getting around: home kept as it was left (after a delete there, or coming back), the garden's first cards
# mixing recent and resurfacing, the garden as a list (Ctrl+G), and back and forward (Ctrl+[ and Ctrl+]: the
# breadcrumbs, no bar for them yet)
import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, RIGHT, UP, DOWN, HOME, ENTER, ESC, QUIT as Q
S = F.use_store("t/nav.json", clean=True)
BACK, FORWARD = "\x1b[91;5u", "\x1b[93;5u"   # Ctrl+[ and Ctrl+], as the kitty protocol reports them
NOW, DAY = 29_920_000, 1440
open("t/clock", "w").write(str(NOW * 60))
ENV = {"FW_PICTURES": "0", "FW_CLOCK": os.path.abspath("t/clock")}
def bar(t): return t.row(t.scr.lines - 1)
def selected(t, text):
    y = next((n for n in range(t.scr.lines) if text in t.row(n)), None)
    return y is not None and t.cell(y, t.row(y).index(text)).reverse

# --- the garden's first cards: recent and resurfacing in turn
def visited(minutes_ago, total=1, flags="ow"):
    return {"total": total, "first": NOW - minutes_ago, "recent": [[NOW - minutes_ago, flags]]}
blocks, refs = {}, []
for n in range(5):   # five recent
    i = f"2026110{n}T100000-r000"; blocks[i] = {"id": i, "content": "x", "visits": visited((n + 1) * 60)}; refs.append(i)
for n in range(3):   # three faded
    i = f"2026060{n}T100000-f000"; blocks[i] = {"id": i, "content": "x", "visits": visited((200 + n) * DAY)}; refs.append(i)
order = S.garden(blocks, refs, NOW)
same("the first cards: a recent one, a resurfacing one, in turn, then the recent left",
     [w for _, w in order], ["recent", "resurfacing"] * 3 + ["recent"] * 2)
many = {f"2026110{n % 10}T1{n:05d}-r000": {"content": "x", "visits": visited(n + 1)} for n in range(14)}
order = S.garden({**blocks, **many}, refs + list(many), NOW)
same("  only the first TOP mix: a busy week's recent come after", [w for _, w in order][:S.TOP].count("resurfacing"), 3)

# --- a store to get around in: Alpha quotes Beta; Gamma, Delta
A, AQ, AT, B, BT, G, D = ("20261101T100000-a000", "20261101T100000-a001", "20261101T100000-a002", "20261102T100000-b000",
                          "20261102T100000-b001", "20261103T100000-c000", "20261104T100000-d000")
def entry(i, title, content, when):
    b = blk(i, content, title, created=when); b["entry"] = True; b["updated"] = when; return b
def fresh():
    F.write_store([entry(A, "Alpha", [AQ, AT], "2026-11-01T10:00:00-04:00"), blk(AQ, {"quote": B}), blk(AT, "alpha text"),
                   entry(B, "Beta", [BT], "2026-11-02T10:00:00-04:00"), blk(BT, "beta body"),
                   entry(G, "Gamma", "gamma body", "2026-11-03T10:00:00-04:00"),
                   entry(D, "Delta", "delta body", "2026-11-04T10:00:00-04:00")], [A, B, G, D])
    S.cmd_migrate(None)

# --- home as it was left
fresh()
t = F.fw("open", cols=110, rows=34, env=ENV)
first = t.text()
t.key(RIGHT)
gone = next(x for x in ("Alpha", "Beta", "Gamma", "Delta") if selected(t, x))
order = [x for x in ("Delta", "Gamma", "Beta", "Alpha") if x in first]
nxt = sorted(order, key=first.index)[sorted(order, key=first.index).index(gone) + 1]
t.key("\x04", "y")
cards = "\n".join(t.text().splitlines()[:-1])   # (the bar says what was deleted)
check("a delete on home: the card after it selected, in its place", gone not in cards and selected(t, nxt), (gone, nxt, t.text()))
t.key(ENTER); t.until(lambda: "body" in t.text() and "┌─" not in t.row(1)); t.key(Q); t.until(lambda: "type to search" in t.text())
check("back from a pericope: the same place", any(selected(t, x) for x in order if x != gone), t.text())
t.key("\x07")
check("Ctrl+G: the garden as a list, a row each, no cards", "┌" not in t.text() and "^G grid" in bar(t)
      and all(x in t.text() for x in order if x != gone), t.text())
t.key(ENTER); t.until(lambda: "body" in t.text()); t.key(Q); t.until(lambda: "type to search" in t.text())
check("  still a list, coming back", "┌" not in t.text() and "^G grid" in bar(t), t.text())
t.key("\x07")
check("  Ctrl+G again: cards", "┌" in t.text() and "^G list" in bar(t), bar(t))
t.key(ESC); t.done()

# --- back and forward
fresh()
t = F.fw("Alpha", cols=80, rows=20, env=ENV)
t.key(UP, "\x0f")   # the quote of Beta, Open it
check("Open it: into Beta, Alpha on the trail", t.until(lambda: "beta body" in t.text() and "Alpha" in bar(t)), bar(t))
t.key(BACK)
check("Ctrl+[: back to Alpha", t.until(lambda: "alpha text" in t.text() and "Alpha ›" not in bar(t)), t.text())
t.key(FORWARD)
check("Ctrl+]: forward into Beta again, Alpha on the trail", t.until(lambda: "Alpha ›" in bar(t) and "beta body" in t.text()), bar(t))
t.key(Q); t.until(lambda: "alpha text" in t.text())
t.key(DOWN, HOME)
check("  (^Q steps back too)", " 2:1" in bar(t), bar(t))
t.key(BACK)
check("Ctrl+[ at the top: home", t.until(lambda: "type to search" in t.text()), t.text())
t.key(FORWARD)
check("Ctrl+] on home: Alpha again, where the cursor was", t.until(lambda: "alpha text" in t.text()) and " 2:1" in bar(t), bar(t))
t.key("\x1d")
check("  Ctrl+] as a plain control key too: Beta, gone back from before", t.until(lambda: "beta body" in t.text() and "Alpha ›" in bar(t)), bar(t))
t.key(FORWARD)
check("nothing further: the bar says so", "nothing to go forward to" in bar(t), bar(t))
t.key(Q, Q); t.until(lambda: "type to search" in t.text())
t.key(*"gamma", ENTER); t.until(lambda: "gamma body" in t.text())
t.key(Q); t.until(lambda: "type to search" in t.text() or "open ›" in t.text())
t.key(ESC)
t.done()
t = F.fw("Delta", cols=80, rows=20, env=ENV)
t.key(FORWARD)
check("a new session: nothing ahead", "nothing to go forward to" in bar(t), bar(t))
t.key(Q, ESC); t.done()

F.report("NAV")
