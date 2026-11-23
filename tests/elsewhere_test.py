# written elsewhere (another session, another machine merged in): home follows the store, a pericope
# deleted while open takes you back (along the trail, or home), and migrate leaves a just-started empty
# pericope alone (it may be open on another machine, whose drafts this one can't see)
import os, sys, time
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, ESC, QUIT as Q
S = F.use_store("t/elsewhere.json", clean=True)
def bar(t): return t.row(t.scr.lines - 1)
A, AQ, AT, B, BT, G = ("20261101T100000-a000", "20261101T100000-a001", "20261101T100000-a002", "20261102T100000-b000",
                       "20261102T100000-b001", "20261103T100000-c000")
def entry(i, title, content, when):
    b = blk(i, content, title, created=when); b["entry"] = True; b["updated"] = when; return b
def fresh():
    F.write_store([entry(A, "Alpha", [AQ, AT], "2026-11-01T10:00:00-04:00"), blk(AQ, {"quote": B}), blk(AT, "alpha text"),
                   entry(B, "Beta", [BT], "2026-11-02T10:00:00-04:00"), blk(BT, "beta body"),
                   entry(G, "Gamma", "gamma body", "2026-11-03T10:00:00-04:00")], [A, B, G])
    S.cmd_migrate(None)

# --- home follows the store
fresh()
t = F.fw("open", cols=110, rows=30)
check("home shows Gamma", "Gamma" in t.text(), t.text())
S.delete_entry(G)
check("deleted elsewhere: gone from home by itself", t.until(lambda: "Gamma" not in t.text()), t.text())
ref, tmp, _ = S.stage(None, "Zeta"); S.drop_draft(tmp)
check("  and one started elsewhere appears", t.until(lambda: "Zeta" in t.text()), t.text())
t.key("\x07")
S.delete_entry(ref)
check("  the list too, still a list", t.until(lambda: "Zeta" not in t.text()) and "^G grid" in bar(t), t.text())
t.key(ESC); t.done()

# --- deleted while open: out, home
fresh()
t = F.fw("Gamma", cols=80, rows=20)
t.until(lambda: "gamma body" in t.text())
S.delete_entry(G)
check("an open pericope deleted elsewhere: out of it, home, saying so",
      t.until(lambda: "type to search" in t.text() and "'Gamma' was deleted elsewhere" in bar(t)), t.text())
check("  and nothing brought it back", G not in S.index(S.load_data()))
t.key(ESC); t.done()

# --- deleted while open, with a trail: back to where you stepped in from
fresh()
t = F.fw("Alpha", cols=80, rows=20)
t.key(UP, "\x0f")
check("Open it: into Beta", t.until(lambda: "beta body" in t.text() and "Alpha" in bar(t)), bar(t))
S.delete_entry(B)
check("Beta deleted elsewhere: back in Alpha, saying so",
      t.until(lambda: "alpha text" in t.text() and "'Beta' was deleted elsewhere" in bar(t)), t.text())
t.key(Q, ESC); t.done()

# --- migrate and empty pericopes
fresh()
ref, tmp, _ = S.stage(None, None); S.drop_draft(tmp)   # just started, empty, untitled, open nowhere here
S.cmd_migrate(None)
check("migrate leaves a just-started empty pericope alone", ref in S.index(S.load_data()))
open("t/clock", "w").write(str(time.time() + 2 * 3600)); os.environ["FW_CLOCK"] = os.path.abspath("t/clock")
S.cmd_migrate(None)
check("  once it's sat untouched an hour, it's cleared", ref not in S.index(S.load_data()))
del os.environ["FW_CLOCK"]

# --- a sync while fw is open: another machine's document (the mini's, say) merged in under the
# editor, which follows it like any other session's save, and its own writing afterwards keeps the mini's
import shutil, subprocess
fresh()
mini = os.path.abspath("t/mini"); shutil.rmtree(mini, ignore_errors=True); os.makedirs(mini)
shutil.copy(S.LORO_PATH, f"{mini}/freewrites.loro")   # one shared history, the mini its own peer
def on_mini(code):
    env = {**os.environ, "FW_DATA": f"{mini}/freewrites.json"}
    r = subprocess.run([sys.executable, "-c", "import fw_store as S\n" + code], env=env, cwd=F.DEV, capture_output=True, text=True)
    check("  (written on the mini)", r.returncode == 0, r.stderr)
on_mini("S.cmd_migrate(None)")
t = F.fw("Alpha", cols=80, rows=20)
t.until(lambda: "alpha text" in t.text())
on_mini(f"S.transact(S.editing(lambda d, b: b[{BT!r}].update(content='beta from the mini')))")
S.merge_file(f"{mini}/freewrites.loro")
check("merged while open: the quote shows the mini's edit", t.until(lambda: "beta from the mini" in t.text()), t.text())
on_mini(f"S.transact(S.editing(lambda d, b: b[{AT!r}].update(content='alpha from the mini')))")
S.merge_file(f"{mini}/freewrites.loro")
check("  the block open here, edited there: followed", t.until(lambda: "alpha from the mini" in t.text()), t.text())
t.key(F.END, " and the laptop"); t.settle()
blocks = S.index(S.load_data())
same("  typed here after: saved over the mini's text, not instead of it",
     (blocks[AT]["content"], blocks[BT]["content"]), ("alpha from the mini and the laptop", "beta from the mini"))
check("  nothing refused", "changed in another session" not in bar(t), bar(t))
t.key(Q, ESC); t.done()

F.report("ELSEWHERE")
