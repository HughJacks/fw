import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, DOWN, ESC, MENU, QUIT as Q
S = F.use_store("t/menu.json", clean=True)
HOST, CH = "20261001T100000-b000", "20261001T100000-b001"
F.write_store([blk(HOST, [CH], "host"), blk(CH, "host text")], [HOST])

t = F.fw("host")
t.key(MENU)
check("rows show names; the selected one's note at the bottom", "Turn into a quote" in t.text() and "this block to a pericope of its own" in t.text()
      and "and step into it" not in t.text(), t.text())
check("  and each command's key, on the right", "ctrl+t" in t.text() and "ctrl+shift+t" in t.text(), t.text())
t.key(DOWN)
check("  the note follows the selection", "and step into it" in t.text() and "this block to a pericope" not in t.text(), t.text())
t.key(ESC, Q, ESC); t.done()

sys.path.insert(0, F.DEV)
import fw_keys, fw_menu
cmd = fw_menu.Command("open", "Open it", "its source")
check("a command shows the key bound to its method", fw_menu.shortcut(cmd) == "ctrl+o", fw_menu.shortcut(cmd))
del fw_keys.KEYMAP["text"]["ctrl+o"]
check("  none bound: no key shown", fw_menu.shortcut(cmd) == "", fw_menu.shortcut(cmd))
F.report("MENU")
