# the layout's pure parts, without a terminal: rows, gaps, box edges, widths, masking colours
import sys, curses
sys.path.insert(0, "."); import fwtest as F
from fwtest import same as check
F.use_store("t/layout.json")
import fw_layout as L

R, D = L.Row, L.Drawn
rows = [R(None, 0, 0, L.edge(0, "top"), 0), R(0, 0, 5, None, 0), R(None, 0, 0, L.edge(0, "bottom"), 0),
        R(None, 0, 0, L.edge(0, "top"), 0), R(1, 0, 3, None, 0), R(None, 0, 0, L.edge(0, "bottom"), 0),
        R(2, 0, 0, L.edge(1, "top", "Alpha"), 1), R(2, 0, 0, D(1, "quoted", "text"), 1), R(2, 0, 0, L.edge(1, "bottom"), 1)]
check("a text block's top and bottom are gaps", [L.is_gap(r) for r in rows], [True, False, True, True, False, True, False, False, False])
check("  a quote's edges aren't: they're the quote", L.is_edge(rows[6].drawn) and not L.is_gap(rows[6]), True)
check("past the gaps going down: two edges in a row skipped", L.past_gaps(rows, 2, 1), 4)
check("  going up", L.past_gaps(rows, 3, -1), 1)
check("  turning back at the start", L.past_gaps(rows, 0, -1), 1)
check("a row is named and still a tuple", rows[1].line == rows[1][0] == 0 and tuple(rows[1]) == (0, 0, 5, None, 0), True)
check("drawn wraps a line into rows (a space may hang past the edge)", [d.text for d in L.drawn(1, "aaaa bbbb cccc", 9)], ["aaaa bbbb ", "cccc"])
check("  with each row's own codes", [d.codes for d in L.drawn(1, "ab cd", 3, "mask", "sshhh")], [("s", "s", "h"), ("h", "h")])
check("box edges: a thin top", L.box_edge(6, "top", False), "┌────┐")
check("  a heavy bottom", L.box_edge(6, "bottom", True), "┗━━━━┛")
check("a label too long is cut with …", L.fit("A description of this tool", 10), "A descrip…")
check("  one that fits is left alone", L.fit("Alpha", 10), "Alpha")
check("text width: room for 3 boxes either side and the cursor", L.text_width(60, 2), 60 - 2 - 6 - 3)
check("  and one column for all text", L.text_column(2), 6)
cells = L.masking_cells("a‹b›c", "hosch", red=1)
check("masking colours: hidden dim, a typed bracket red and bold", [a for _, a in cells],
      [curses.A_DIM, 1 | curses.A_BOLD, 0, 1 | curses.A_BOLD, curses.A_DIM])
check("  an implied one dim", L.masking_cells("‹", "O", red=1)[0][1], 1 | curses.A_DIM)
F.report("LAYOUT")
