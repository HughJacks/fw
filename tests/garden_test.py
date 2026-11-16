# home starts as the garden: a grid of cards (recent, then resurfacing by an
# FSRS-style memory read from visits, then the rest); typing hands over to the search
import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, DOWN, RIGHT, LEFT, BS, ENTER, ESC, QUIT as Q
S = F.use_store("t/garden.json", clean=True)

NOW = 29_920_000              # minutes since the epoch (mid-Nov 2026)
DAY = 1440
open("t/clock", "w").write(str(NOW * 60))

# --- the pure parts
fresh = {"created": "2026-11-15T10:00:00-05:00", "visits": {"total": 1, "first": NOW - 2 * DAY, "recent": [[NOW - 2 * DAY, "ow"]]}}
s1, r1 = S.memory(fresh, NOW)
check("one visit 2 days ago: S is a day, R about .8", abs(s1 - 1) < 1e-9 and 0.8 < r1 < 0.85, (s1, r1))
spaced = {"visits": {"total": 4, "first": NOW - 200 * DAY,
                     "recent": [[NOW - 200 * DAY, "ow"], [NOW - 190 * DAY, "oc"], [NOW - 150 * DAY, "ow"], [NOW - 60 * DAY, "oc"]]}}
crammed = {"visits": {"total": 4, "first": NOW - 200 * DAY,
                      "recent": [[NOW - 200 * DAY, "ow"], [NOW - 200 * DAY + 30, "oc"], [NOW - 200 * DAY + 60, "ow"], [NOW - 60 * DAY, "oc"]]}}
check("spaced visits build more stability than crammed ones", S.memory(spaced, NOW)[0] > S.memory(crammed, NOW)[0],
      (S.memory(spaced, NOW), S.memory(crammed, NOW)))
w = {"visits": {"total": 2, "first": NOW - 30 * DAY, "recent": [[NOW - 30 * DAY, "ow"], [NOW - 20 * DAY, "ow"]]}}
o = {"visits": {"total": 2, "first": NOW - 30 * DAY, "recent": [[NOW - 30 * DAY, "ow"], [NOW - 20 * DAY, "o"]]}}
check("writing in it counts for more than a glance", S.memory(w, NOW)[0] > S.memory(o, NOW)[0])
check("no visits: its writing stands for the first", S.memory({"created": "2026-11-01T10:00:00-05:00"}, NOW)[1] < 1)
same("ago", [S.ago(NOW - n, NOW) for n in (0, 5, 120, 3 * DAY, 70 * DAY, 400 * DAY)],
     ["just now", "5m ago", "2h ago", "3d ago", "2mo ago", "1y ago"])
same("last action: the last visit's strongest flag", S.last_action(w)[0], "written")
same("  a glance", S.last_action(o)[0], "opened")
same("  none, never changed: made", S.last_action({"created": "2026-11-01T10:00:00-05:00",
                                                  "updated": "2026-11-01T10:00:00-05:00"})[0], "made")

# --- the order
RECENT, FADED, FADED2, FRESHOLD, PLAIN = ("2026110%dT100000-a000" % n for n in range(1, 6))
def entry(i, title, visits=None, created="2026-06-01T10:00:00-04:00", updated=None):
    b = blk(i, title + " body text that goes on for a while so the preview has something to show", title, created=created)
    b["updated"] = updated or created
    b["entry"] = True
    if visits:
        b["visits"] = visits
    return b
blocks = [
    entry(RECENT, "recent one", {"total": 1, "first": NOW - DAY, "recent": [[NOW - DAY, "ow"]]}),
    entry(FADED, "faded much", {"total": 3, "first": NOW - 300 * DAY,
                                "recent": [[NOW - 300 * DAY, "ow"], [NOW - 299 * DAY, "oc"], [NOW - 200 * DAY, "oc"]]}),
    entry(FADED2, "faded once", {"total": 1, "first": NOW - 100 * DAY, "recent": [[NOW - 100 * DAY, "o"]]}),
    entry(FRESHOLD, "steady", {"total": 6, "first": NOW - 400 * DAY,
                               "recent": [[NOW - 400 * DAY, "ow"], [NOW - 390 * DAY, "ow"], [NOW - 370 * DAY, "ow"],
                                          [NOW - 330 * DAY, "ow"], [NOW - 250 * DAY, "ow"], [NOW - 30 * DAY, "ow"]]}),
    entry(PLAIN, "plain"),
]
F.write_store(blocks, [b["id"] for b in blocks], version=14)
S.cmd_migrate(None)
B = S.index(S.load_data())
order = S.garden(B, [b["id"] for b in blocks], NOW)
same("recent first", order[0], (RECENT, "recent"))
why = dict(order)
check("faded ones resurface", why[FADED] == "resurfacing" and why[FADED2] == "resurfacing", order)
same("  well rehearsed, seen a month ago: still in mind, not resurfaced", why[FRESHOLD], "")
check("  the more rehearsed first", [i for i, w in order].index(FADED) < [i for i, w in order].index(FADED2), order)
same("everything once", sorted(i for i, _ in order), sorted(b["id"] for b in blocks))

# --- the screen
def home():
    return F.fw("open", cols=110, rows=34, env={"FW_PICTURES": "0", "FW_CLOCK": os.path.abspath("t/clock")})
t = home()
txt = t.text()
check("fw open starts as the garden: cards with their titles", "recent one" in txt and "faded much" in txt and "┌" in txt, txt)
check("  a card says why it's there", " recent " in txt and " resurfacing " in txt, txt)
check("  and what last happened, when", "written 1d ago" in txt, txt)
check("  and the start of what it says", "body text" in txt, txt)
check("  + new pericope is a card too", "+ new pericope" in txt, txt)
check("  the hint says typing searches", "type to search" in F.__dict__.get("bar", lambda t: t.row(t.scr.lines - 1))(t), t.row(t.scr.lines - 1))
t.key("plai")
check("typing hands over to the search, what's typed kept", "open › plai" in t.text() and "plain" in t.text(), t.text())
t.key(BS, BS, BS, BS)
t.key(BS)
check("Backspace with nothing typed: the garden again", " recent " in t.text(), t.text())
t.key(ENTER)
check("Enter opens the selected card (the most recent)", "recent one" in t.text() and "┌" not in t.row(1)[:1], t.text())
t.key(Q)
t.close()

t = home()
t.key(RIGHT, ENTER)
check("→ moves to the next card; Enter opens it", "faded much" in t.text(), t.text())
t.key(Q)
t.close()
F.report("GARDEN")
