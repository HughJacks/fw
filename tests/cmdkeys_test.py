import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, ESC, QUIT as Q, UNDO as Z
S = F.use_store("t/cmdkeys.json", clean=True)
SRC, CS = "20261001T100000-5a00", "20261001T100000-5a01"
HOST, CH, QH = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
F.write_store([blk(SRC, [CS], "src"), blk(CS, "alpha beta"),
               blk(HOST, [CH, QH], "host"), blk(CH, "host text"), blk(QH, {"quote": SRC})], [SRC, HOST])
CTRL_E, CTRL_SE, CTRL_T, CTRL_ST, ALT_T, CTRL_O = "\x05", "\x1b[101;6u", "\x14", "\x1b[116;6u", "\x1b[116;3u", "\x0f"
def data(): return S.index(S.load_data())
def quote(): return data()[[k for k in S.children(data()[HOST]) if S.quoted(data().get(k))][0]]
def bar(t): return t.row(t.scr.lines - 1)

t = F.fw("host")
t.key(UP, CTRL_O)
check("ctrl+o on a selected quote: Open it", "host ›" in bar(t), bar(t))
t.key(Q, UP, CTRL_E)
check("ctrl+e on a selected quote: Create mask (masking mode)", "‹" in t.text(), t.text())
t.key(F.RIGHT, F.RIGHT, F.RIGHT, F.RIGHT, F.RIGHT, F.RIGHT, "[", ESC); t.settle()
check("  the mask is stored", S.quoted(quote())[1] is not None, quote())
t.key(CTRL_SE); t.settle()
check("ctrl+shift+e: Remove mask", S.quoted(quote())[1] is None, quote())
check("  from inside the quote, it shows all of it at once", "alpha beta" in t.text() and "…" not in t.text(), t.text())
t.key(ESC, ALT_T); t.settle()
check("alt+t on a selected quote: Turn into text", isinstance(quote := data()[QH]["content"], str) if QH in data() else False, data().get(QH))
t.key(Q, ESC); t.done()

t = F.fw("host")   # opens at the end of what's there: on the empty line below the quote
t.key("new words", CTRL_T); t.settle()
check("ctrl+t in a text block: Turn into a quote", "popped out" in bar(t), bar(t))
t.key(F.ENTER, "more", CTRL_ST)
check("ctrl+shift+t: Turn into a quote and open it", "host ›" in bar(t) and "more" in t.text(), t.text())
t.key(Q, F.ENTER, CTRL_E)
check("a key where its command isn't offered: not here", "not here" in bar(t), bar(t))
t.key(Q, ESC); t.done()
F.report("CMDKEYS")
