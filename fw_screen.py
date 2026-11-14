"""fw_screen — the terminal under the editor and home: character widths,
soft wrap, word steps, drawing a line or a box, the terminal's modes, and
(for tests only) saying when fw is about to wait for a key.
"""

import curses
import fcntl
import os
import sys
import termios
import unicodedata
from contextlib import contextmanager
from typing import NamedTuple

TAB_WIDTH = 4


# old ncurses (as on macOS) has no BUTTON5 and reports wheel-down as this bit
WHEEL_DOWN = getattr(curses, "BUTTON5_PRESSED", curses.REPORT_MOUSE_POSITION)


# tests only: with $FW_SYNC set, before each wait for a key fw says how many
# keys it has read, how often it has woken idle, whether there's unsaved
# writing and how many bytes of input are still unread, as an OSC terminals
# ignore, so a test can wait on that instead of sleeping. Without it nothing
# changes
SYNC = bool(os.environ.get("FW_SYNC"))


SEEN = {"keys": 0, "wakes": 0}


def cwidth(ch: str) -> int:
    if ch == "\t":
        return TAB_WIDTH
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def swidth(s: str) -> int:
    return sum(cwidth(c) for c in s)


def wrap(line: str, width: int) -> list[tuple[int, int]]:
    """Split one line into screen rows, as (start, end) index pairs.

    Breaks after the last space that fits. A space landing exactly at the edge
    hangs in the spare column; a word longer than the row is cut."""
    rows, start, n = [], 0, len(line)
    while True:
        w, i, brk = 0, start, -1
        while i < n:
            cw = cwidth(line[i])
            if w + cw > width:
                break
            w += cw
            i += 1
            if line[i - 1] == " ":
                brk = i
        if i >= n:
            rows.append((start, n))
            return rows
        if line[i] == " ":
            end = i + 1
        elif brk > start:
            end = brk
        else:
            end = max(i, start + 1)
        rows.append((start, end))
        start = end


def word_left(line: str, col: int) -> int:
    while col > 0 and line[col - 1].isspace():
        col -= 1
    while col > 0 and not line[col - 1].isspace():
        col -= 1
    return col


def word_right(line: str, col: int) -> int:
    n = len(line)
    while col < n and line[col].isspace():
        col += 1
    while col < n and not line[col].isspace():
        col += 1
    return col


def put(scr, y: int, x: int, text: str, attr: int = 0) -> None:
    try:
        scr.addstr(y, x, text, attr)
    except curses.error:
        pass  # writing the bottom-right cell always "fails"; harmless


def draw_box(scr, y0: int, x0: int, bw: int, prompt: str, note: str, rows: list, sel: int,
             first: int, footer: str = "") -> tuple[int, int]:
    """A search box: the prompt line, then `rows` of (key, left, right[,
    dim]) from `first` on, `sel` highlighted, then a dim `footer` line if there is one.
    Returns where the cursor goes."""
    inner = bw - 4
    put(scr, y0, x0, "┌" + "─" * (bw - 2) + "┐", curses.A_DIM)
    put(scr, y0 + 1, x0, "│ " + prompt[:inner].ljust(inner) + " │")
    if note and swidth(prompt) + len(note) + 1 < inner:
        put(scr, y0 + 1, x0 + 2 + inner - len(note), note, curses.A_DIM)
    for n, (_, left, right, *dim) in enumerate(rows):
        right = right[:max(inner - len(left) - 2, 0)]  # short of room: the note gives way, not the name
        text = left[:max(inner - len(right) - 2, 1)].ljust(max(inner - len(right), 1)) + right
        put(scr, y0 + 2 + n, x0, "│ ", curses.A_DIM)
        put(scr, y0 + 2 + n, x0 + 2, text[:inner].ljust(inner),
            (curses.A_REVERSE if first + n == sel else 0) | (curses.A_DIM if dim and dim[0] else 0))
        put(scr, y0 + 2 + n, x0 + 2 + inner, " │", curses.A_DIM)
    if not rows:
        put(scr, y0 + 2, x0, "│ " + "no matches".ljust(inner) + " │", curses.A_DIM)
    y = y0 + len(rows or [None]) + 2
    if footer:
        put(scr, y, x0, "│ " + footer[:inner].ljust(inner) + " │", curses.A_DIM)
        y += 1
    put(scr, y, x0, "└" + "─" * (bw - 2) + "┘", curses.A_DIM)
    return y0 + 1, x0 + 2 + min(swidth(prompt), inner)


class Ink(NamedTuple):
    """The attributes fw draws with (setup makes them once curses starts;
    these defaults stand in before, and with no colours)."""
    red: int = curses.A_BOLD          # a quote's box while bright, a link, a …
    tag: int = curses.A_BOLD          # white on red: a quote's number and title, bright
    ghost: int = curses.A_UNDERLINE   # white underline: where one more arrow press lands
    soft: int = curses.A_DIM          # a quote's box at rest: muted red
    faint: int = curses.A_DIM         # a block of text's box: a quiet grey


def setup(scr) -> Ink:
    """Terminal modes for the editor; returns what it draws with (quiet greys
    and a muted red where there are 256 colours)."""
    curses.raw()   # so ^S, ^Q, ^Z reach us instead of the terminal
    curses.nonl()  # keep Enter as \r, so a pasted \r\n is one break
    scr.keypad(True)
    curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED
                     | curses.BUTTON4_PRESSED | WHEEL_DOWN)
    curses.mouseinterval(0)  # report presses at once instead of waiting to see if it's a click
    try:
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(3, curses.COLOR_WHITE, -1)
        many = curses.COLORS >= 256
        curses.init_pair(4, 95 if many else curses.COLOR_RED, -1)
        curses.init_pair(5, 239 if many else curses.COLOR_WHITE, -1)
        quiet = 0 if many else curses.A_DIM
        return Ink(curses.color_pair(1), curses.color_pair(2) | curses.A_BOLD, curses.color_pair(3) | curses.A_UNDERLINE,
                   curses.color_pair(4) | quiet, curses.color_pair(5) | quiet)
    except curses.error:  # no colours: bold, underlined and dim
        return Ink()


@contextmanager
def keyboard_modes():
    """Ask for modified keys reported distinctly (kitty keyboard protocol, so
    Shift+Enter isn't Enter) and for pastes to be marked; terminals that
    don't know these ignore them."""
    sys.stdout.write("\x1b[>1u\x1b[?2004h")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\x1b[<u\x1b[?2004l")
        sys.stdout.flush()


def ready(scr, dirty: bool = False) -> None:
    """About to wait for a key: tell a test (only with $FW_SYNC)."""
    if SYNC:
        scr.refresh()
        unread = int.from_bytes(fcntl.ioctl(sys.stdin.fileno(), termios.FIONREAD, bytes(4)), sys.byteorder)
        os.write(sys.stdout.fileno(), f"\x1b]777;fw;{SEEN['keys']};{SEEN['wakes']};{int(dirty)};{unread}\x07".encode())
