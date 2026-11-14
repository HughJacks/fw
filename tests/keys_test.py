import curses, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import same as check
sys.path.insert(0, "dev"); import fw_keys as keys
curses.setupterm("xterm-256color")
class Scr:  # what follows an ESC, read back one character at a time
    def __init__(s, rest): s.q = list(rest)
    def timeout(s, n): pass
    def get_wch(s):
        if not s.q: raise curses.error
        return s.q.pop(0)
def key(*sent): return keys.decode(Scr(sent[1:] and sent[1]), sent[0])

check("KEYS.md is what fw_keys.py generates", open("dev/KEYS.md").read() == keys.markdown(), True)
undescribed = [(c, a) for c, m in keys.KEYMAP.items() for a in m.values() if a not in keys.DOES[c]]
check("every bound action is described", undescribed, [])
check("one action, many spellings: Option-Left (xterm, Terminal.app)", {keys.bind(key("\x1b", "[1;3D")), keys.bind(key("\x1b", "b"))}, {"word_left"})
check("  xterm, Terminal.app and kitty Shift+Enter", {key("\x1b", "[27;2;13~"), key("\x1b", "[13;2u")}, {"shift+enter"})
check("  a control character and kitty Ctrl+Z", {key("\x1a"), key("\x1b", "[122;5u")}, {"ctrl+z"})
check("  Option-Backspace, as Esc+ and kitty", {key("\x1b", "\x7f"), key("\x1b", "[127;3u")}, {"alt+backspace"})
check("a lone Esc", key("\x1b"), "esc")
check("typing stays itself", [key("a"), key("["), key(" ")], ["a", "[", " "])
check("a context falls back to the text", keys.bind("ctrl+z", "mask"), "undo")
check("  and overrides it", (keys.bind("esc", "mask"), keys.bind("esc")), ("done", "escape"))
check("a typed character types unless bound", (keys.bind("[", "text"), keys.bind("[", "mask")), ("[", "open_bracket"))
F.report("KEYS")
