#!/usr/bin/env python3
"""fw_keys — every key fw handles, as data.

    python3 fw_keys.py > KEYS.md

Two layers. `decode` turns what the terminal sends into a key name such as
`ctrl+z`, `alt+left` or `shift+enter` (a typed character stays itself), and
hides how each terminal spells it: curses codes, xterm sequences, Option sent
as Esc, the kitty keyboard protocol. `bind` turns a key name into an action in
a context, through KEYMAP. A context lists only what it changes and falls back
to the text's bindings; a typed character types unless a context binds it.
What an action does, and when (Backspace joins mask spans only on a bracket),
is up to the code that runs it.

KEYS.md is generated from this file, so the list can't drift: change a key
here, then regenerate it.
"""

import curses
import re

# context -> {key name: action}; each falls back to "text"
KEYMAP = {
    "text": {
        "enter": "newline",
        "shift+enter": "line_break", "alt+enter": "line_break",
        "ctrl+enter": "nest_in",
        "backspace": "backspace", "shift+backspace": "backspace",
        "alt+backspace": "delete_word", "ctrl+backspace": "delete_word",
        "delete": "delete",
        "tab": "tab",
        "left": "left", "right": "right", "up": "up", "down": "down",
        "alt+left": "word_left", "ctrl+left": "word_left", "meta+left": "word_left", "alt+b": "word_left",
        "alt+right": "word_right", "ctrl+right": "word_right", "meta+right": "word_right", "alt+f": "word_right",
        "home": "home", "end": "end",
        "page_up": "page_up", "page_down": "page_down",
        "shift+left": "select_left", "shift+right": "select_right",
        "shift+up": "select_up", "shift+down": "select_down",
        "alt+shift+left": "select_word_left", "ctrl+shift+left": "select_word_left",
        "shift+meta+left": "select_word_left",
        "alt+shift+right": "select_word_right", "ctrl+shift+right": "select_word_right",
        "shift+meta+right": "select_word_right",
        "shift+home": "select_home", "shift+end": "select_end",
        "shift+page_up": "select_page_up", "shift+page_down": "select_page_down",
        "ctrl+a": "select_all",
        "ctrl+c": "copy", "ctrl+x": "cut", "ctrl+v": "paste", "ctrl+shift+v": "paste_static",
        "ctrl+z": "undo", "ctrl+y": "redo",
        "ctrl+q": "quit",
        "ctrl+[": "go_back", "ctrl+]": "go_forward",  # (Ctrl+[ apart from Esc only with the kitty protocol, which fw asks for)
        "ctrl+/": "palette", "alt+/": "palette",
        "esc": "escape",
        # the menu's commands (named by the method they run), where the menu would offer them
        "ctrl+e": "edit_mask", "ctrl+shift+e": "show_all",
        "ctrl+t": "pop_out", "ctrl+shift+t": "pop_out_open", "alt+t": "detach",
        "ctrl+o": "open_source",
        "ctrl+k": "link_entry", "ctrl+shift+k": "remove_link",
        "ctrl+l": "toggle_lock",
        "ctrl+d": "delete_entry",
    },
    "mask": {
        "[": "open_bracket", "]": "close_bracket",
        "tab": "next_bracket", "shift+tab": "prev_bracket",
        "esc": "done", "enter": "done",
    },
    "blocks": {},  # blocks selected whole: the text's keys, acting on whole blocks (fw_blocks)
    "header": {
        "down": "next_field", "enter": "open_field", "tab": "next_field",
        "up": "prev_field",
        "esc": "leave_field",
    },
    "kinds": {  # the header's kinds line: the block's kinds as tokens, and a + at the end
        "down": "next_field", "tab": "next_field", "up": "prev_field", "esc": "leave_field",
        "left": "prev_kind", "right": "next_kind",
        "enter": "confirm_kind", "ctrl+o": "open_kind",
        "backspace": "remove_kind", "delete": "remove_kind",
    },
    "review": {  # a kind's maybe, open to be answered (from the kind's maybes line); arrows move, nothing types
        "enter": "review_yes", "backspace": "review_no", "delete": "review_no",
        "tab": "review_skip", "ctrl+z": "review_back", "ctrl+q": "review_stop",
    },
    "picker": {
        "enter": "pick", "tab": "pick", "shift+enter": "pick_masked",
        "right": "show_blocks", "left": "hide_blocks",
        "esc": "cancel",
        "ctrl+d": "delete_entry",
        "ctrl+g": "toggle_view",
    },
}
# not keys, but they arrive the same way
EVENTS = {"mouse", "paste_start", "paste_end"}


def bind(key: str | None, context: str = "text") -> str | None:
    """The action `key` does in `context` (a typed character types, unless the
    context binds it)."""
    if key is None:
        return None
    action = KEYMAP[context].get(key) or KEYMAP["text"].get(key)
    if action:
        return action
    return key if len(key) == 1 or key in EVENTS else None


# ---------------------------------------------------------------- decoding

MODS = ("ctrl", "alt", "shift", "meta")  # the order they're written in
BITS = {"shift": 1, "alt": 2, "ctrl": 4, "meta": 8}  # xterm's modifier bits (the parameter is 1 + these)


def named(bits: int, base: str) -> str:
    """e.g. (2, "left") -> "alt+left"."""
    return "+".join([m for m in MODS if bits & BITS[m]] + [base])


def char_key(c: str) -> str | None:
    """A character as a key: printable ones are themselves, control ones their name."""
    if c in ("\r", "\n"):
        return "enter"
    if c in ("\x7f", "\x08"):
        return "backspace"
    if c == "\t":
        return "tab"
    if c == "\x1f":
        return "ctrl+/"
    if c == "\x1d":
        return "ctrl+]"
    if "\x01" <= c <= "\x1a":
        return "ctrl+" + chr(ord(c) + 96)
    return c if c >= " " else None


CURSES = {
    curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right", curses.KEY_UP: "up", curses.KEY_DOWN: "down",
    curses.KEY_PPAGE: "page_up", curses.KEY_NPAGE: "page_down",
    curses.KEY_HOME: "home", curses.KEY_END: "end",
    curses.KEY_BACKSPACE: "backspace", curses.KEY_DC: "delete", curses.KEY_BTAB: "shift+tab",
    curses.KEY_ENTER: "enter",
    curses.KEY_SLEFT: "shift+left", curses.KEY_SRIGHT: "shift+right",
    curses.KEY_SR: "shift+up", curses.KEY_SF: "shift+down",
    curses.KEY_SHOME: "shift+home", curses.KEY_SEND: "shift+end",
    curses.KEY_SPREVIOUS: "shift+page_up", curses.KEY_SNEXT: "shift+page_down",
}
# ncurses names for modified keys, e.g. kLFT3 (Option-Left); no digit means Shift
CURSES_NAME_RE = re.compile(rb"k(LFT|RIT|UP|DN|HOM|END|PRV|NXT|DC)(\d*)")
CURSES_BASE = {b"LFT": "left", b"RIT": "right", b"UP": "up", b"DN": "down", b"HOM": "home",
               b"END": "end", b"PRV": "page_up", b"NXT": "page_down", b"DC": "delete"}

# after ESC: CSI / SS3 sequences, e.g. "[A", "[1;3D" (Option-Left), "[5~"
LETTERS = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}
TILDES = {1: "home", 7: "home", 4: "end", 8: "end", 3: "delete", 5: "page_up", 6: "page_down"}
LETTER_RE = re.compile(r"(?:\[(?:1;(\d+))?|O)([ABCDHF])")
TILDE_RE = re.compile(r"\[(\d+)(?:;(\d+))?~")
CODE_RE = re.compile(r"\[(\d+)(?:;(\d+))?u")       # kitty: CSI code;modifiers u
OTHER_RE = re.compile(r"\[27;(\d+);(\d+)~")       # xterm modifyOtherKeys: CSI 27;modifiers;code ~
SPECIAL = {"[Z": "shift+tab", "[200~": "paste_start", "[201~": "paste_end", "": "esc"}


def code_key(code: int, bits: int) -> str | None:
    """A key reported by its code (kitty, modifyOtherKeys)."""
    base = {13: "enter", 27: "esc", 127: "backspace", 8: "backspace", 9: "tab"}.get(code)
    if base is None:
        if code < 32:
            return None
        if not bits & ~BITS["shift"]:
            return chr(code)  # just typed
        base = chr(code)
    return named(bits, base)


def escape_key(seq: str) -> str | None:
    """The key for what followed an ESC."""
    if seq in SPECIAL:
        return SPECIAL[seq]
    if m := LETTER_RE.fullmatch(seq):
        return named(int(m.group(1) or 1) - 1, LETTERS[m.group(2)])
    if m := TILDE_RE.fullmatch(seq):
        base = TILDES.get(int(m.group(1)))
        return named(int(m.group(2) or 1) - 1, base) if base else None
    if m := CODE_RE.fullmatch(seq):
        return code_key(int(m.group(1)), int(m.group(2) or 1) - 1)
    if m := OTHER_RE.fullmatch(seq):
        return code_key(int(m.group(2)), int(m.group(1)) - 1)
    if len(seq) == 1:  # Option as Meta: ESC then the key
        k = char_key(seq)
        return "alt+" + k if k else None
    return None


def read_escape(scr) -> str:
    """After ESC: read the rest of the sequence, e.g. "[A" or "b"."""
    scr.timeout(30)
    seq = ""
    while True:
        try:
            c = scr.get_wch()
        except curses.error:
            break
        if not isinstance(c, str):
            break
        seq += c
        if not seq.startswith(("[", "O")) or (len(seq) > 1 and (c.isalpha() or c == "~")):
            break
    scr.timeout(-1)
    return seq


def decode(scr, key, prev_cr: bool = False) -> str | None:
    """What curses read -> a key name, a typed character, or an event.
    `prev_cr`: the key before was a CR (so this LF is a pasted CRLF's)."""
    if isinstance(key, int):
        if key == curses.KEY_MOUSE:
            return "mouse"
        if key in CURSES:
            return CURSES[key]
        m = CURSES_NAME_RE.fullmatch(curses.keyname(key))
        return named(int(m.group(2) or 2) - 1, CURSES_BASE[m.group(1)]) if m else None
    if key == "\x1b":
        return escape_key(read_escape(scr))
    if key == "\n" and prev_cr:
        return None  # CRLF from a paste is one break
    return char_key(key)


# ------------------------------------------------------------------- KEYS.md

SECTIONS = {
    "text": ("In the text", "Arrows stop on a quote, selected whole, on the way in and out; one more "
             "press goes inside, or past."),
    "blocks": ("Blocks selected whole", "Esc selects the block you're in; a selection that reaches another "
               "block takes whole blocks. The edge at the moving end is heavy, the text cursor hides, and a ghost "
               "shows where ↓ or ↑ from that edge lands."),
    "mask": ("Masking mode (Create mask / Edit mask)", "No typing: the text stays as it is. Arrows move, into a box "
             "inside too, to mask that quote as seen through this one (anything its source hides is a locked …)."),
    "header": ("The header", "Moving, deleting, pasting and typing edit the field, as in the text. "
               "A kind's title is its name: changed as you leave it."),
    "kinds": ("The kinds line", "In the header, above the title: what the block is, a token per kind "
              "(a yes white on blue, a no \"not …\" muted), then a model's guesses, dim blue with a ?, "
              "\"poem?\". Typing opens the kinds picker with it typed."),
    "review": ("Reviewing a kind's maybes", "Enter on a kind's maybes line (in its header: the blocks a model "
               "guesses might be one, from 50% up, likeliest first) opens each in turn, where it lives, the bar "
               "saying \"poem? 93% · 3 of 12\". Arrows and the wheel move and scroll; nothing types."),
    "picker": ("Menus and search", "The `/` menu, Quote a block, the kinds picker, and home. Typing filters; "
               "↑ ↓ choose."),
}
# what each action does, per context. An action listed for a context it
# isn't bound in is the text's, described for that context
DOES = {
    "text": {
        "newline": "new block at the cursor; on a selected quote, a new block below it; in a paraphrase, a block inside it",
        "line_break": "line break inside the block",
        "nest_in": "a block inside this one: it splits at the cursor, a level down; Enter on an empty one inside steps back out",
        "backspace": "deletes back; at a block's start, merges it into the one above; on a selected quote, removes it",
        "delete_word": "deletes the word before",
        "delete": "deletes forward; on a selected quote, removes it",
        "tab": "types a tab",
        "left": "move", "right": "move", "down": "move",
        "up": "move; from the first row, into the header; from a quote's first row, out of it",
        "word_left": "move a word", "word_right": "move a word",
        "home": "start of line", "end": "end of line",
        "page_up": "move a screen", "page_down": "move a screen",
        "select_left": "extend the selection", "select_right": "extend the selection",
        "select_up": "extend the selection (reaching another block: whole blocks)",
        "select_down": "extend the selection (reaching another block: whole blocks)",
        "select_word_left": "extend the selection a word", "select_word_right": "extend the selection a word",
        "select_home": "extend the selection", "select_end": "extend the selection",
        "select_page_up": "extend the selection", "select_page_down": "extend the selection",
        "select_all": "select all (with more than one block: all of them, whole)",
        "copy": "copy (system clipboard); on a selected quote, it whole", "cut": "cut; on a selected quote, it whole",
        "paste": "paste; blocks copied whole come back as live quotes of them (cut ones: moved), inside the block you're in, split at the cursor",
        "paste_static": "paste blocks copied whole as static copies: plain blocks, a quote as the text it showed",
        "undo": "undo a whole action, store included; after Open it, once nothing's left, steps back", "redo": "redo",
        "quit": "go home; after Open it, step back",
        "go_back": "back: as ^Q (a step back along the Open it trail, or home), and what you left can be gone forward to again",
        "go_forward": "forward again, to where you went back from (at the place you were); from home too; anything opened anew clears what's ahead",
        "palette": "the menu of actions on the block you're in, anywhere",
        "escape": "selects the block you're in whole (inside a quote too); again, the quote around it",
        "edit_mask": "Create mask / Edit mask, on the quote selected or the one you're in",
        "show_all": "Remove mask",
        "pop_out": "Turn into a quote: this block to a pericope of its own (a selection: just it, nested here)",
        "pop_out_open": "Turn into a quote and open it",
        "detach": "Turn into text: the quote selected, a plain copy",
        "open_source": "Open it: the quote selected or the one you're in, or the link the cursor's on, as the pericope",
        "link_entry": "Link to a pericope: the selection (in one block) points to a pericope you pick, or a new one",
        "remove_link": "Remove link: the one the cursor's on (the text stays)",
        "toggle_lock": "Lock / Unlock writing through: the quote selected or the one you're in (through a locked one, what writes says locked)",
        "delete_entry": "delete this pericope (asks first; quotes of it keep their text)",
    },
    "blocks": {
        "escape": "back to the text, the cursor where it was; inside a quote, the quote around them, selected",
        "select_up": "one block more above (or one fewer)", "select_down": "one block more below (or one fewer)",
        "up": "from the heavy top: out to the block above; of several selected, just the top one",
        "down": "from the heavy top: inside, where the ghost is; of several, just the bottom one",
        "left": "back to the text, at the start of the first block", "right": "back to the text, at the end of the last",
        "copy": "copy the blocks (the system clipboard gets their text, a blank line apart)", "cut": "cut the blocks",
        "paste": "blocks copied whole: before them from the heavy top, after them from the heavy bottom; text: in their place",
        "paste_static": "blocks copied whole, as static copies, before or after them as paste puts them",
        "backspace": "removes the blocks", "delete": "removes the blocks",
        "newline": "replaces them with a new, empty block",
        "pop_out": "with several selected: not here (a command acts on one block)",
    },
    "mask": {
        "open_bracket": "an opener, its partner inferred; with a selection, show exactly it",
        "close_bracket": "a closer, its partner inferred; with a selection, hide it",
        "next_bracket": "next bracket", "prev_bracket": "previous bracket",
        "backspace": "on a bracket, joins the spans either side",
        "delete": "on a bracket, joins the spans either side",
        "done": "done",
        "palette": "nothing (finish the mask first)",
    },
    "header": {"next_field": "the field below, or back to the text from the last one",
               "open_field": "on backlinks: the list of the blocks pointing here, Enter opens one; on a kind's maybes: review them, one block at a time; elsewhere as next_field",
               "prev_field": "the field above", "leave_field": "back to the text",
               "paste": "paste its first line"},
    "kinds": {"next_field": "the field below", "prev_field": "the field above", "leave_field": "back to the text",
              "prev_kind": "the kind before", "next_kind": "the kind after, then the + at the end",
              "confirm_kind": "on a guess: confirm it (it is one, a yes); on a kind: open it (^Q comes back); on the +: the kinds picker",
              "open_kind": "on a kind or a guess: open it (^Q comes back); on the +: the kinds picker",
              "remove_kind": "on a kind: take that answer back; on a guess: deny it (it isn't one, a no: \"not …\"); on the +: onto the last kind"},
    "review": {"review_yes": "it is one (a yes), on to the next", "review_no": "it isn't (a no), on to the next",
               "review_skip": "no answer, on to the next", "review_back": "back to the one before, its answer taken back",
               "review_stop": "stop: back to the kind (each answer one ^Z there)"},
    "picker": {"pick": "run it / open it / quote it / it is one, in the kinds picker (+ new kind: makes it; on home, a proposed kind: makes it and reviews its members) (a block inside a pericope: home opens the pericope at it; Quote a block makes it a pericope of its own, quoted here and where it was; a place that quotes a match: home opens it at the quote, Quote a block quotes the match)",
               "pick_masked": "Quote a block, on a block inside a pericope: quote its pericope, masked to just that block; the kinds picker: it isn't one (a no)",
               "show_blocks": "home and Quote a block, on a pericope: list all the blocks inside it, under it",
               "hide_blocks": "home and Quote a block: hide them again (from the pericope or one of its blocks)",
               "cancel": "close (the `/` menu leaves what you typed, as text; home quits)",
               "backspace": "with nothing typed: closes the menu; in Quote a block, back to the menu",
               "quit": "home: quit",
               "toggle_view": "home's garden: cards in a grid, or a list (a row each), and back",
               "go_forward": "home: forward again, to the pericope you went back from",
               "delete_entry": "home: delete the pericope selected (asks first; quotes of it keep their text); on a proposed kind's row (\"? a kind: …\"), dismiss it (asks first)"},
}
# keys that aren't bindings: typed characters with a meaning in one place, and the mouse
NOTES = {
    "text": [("a character", "types it"),
             ("`/` at a line's start or after a space", "the menu of blocks to put in (mid-text, nested there)"),
             ("Space on a red `…`", "edit the mask there"),
             ("click", "place the cursor (a header line: edit that field); in the menu, closes it first"),
             ("wheel", "scroll")],
    "blocks": [("a character", "replaces them with a new block holding it"),
               ("click", "back to the text, where you clicked")],
}
COMMANDS = ("Commands in the menu, shown only where they fit, each with its key: Quote a block · "
            "Create mask / Edit mask (masking mode: brackets only, no typing; arrow into a box inside to mask "
            "it as seen through this quote) · Remove mask · Open it · Its top line… (Show / Hide its title, date, "
            "last update, word count; found by search too, and the menu stays open to toggle more) · "
            "Lock writing through / Unlock writing through (stays open) · Turn into text · Turn into a quote (with a selection, just it, nested where it was) · Turn into a quote "
            "and open it · Link to a pericope · Remove link. A command's key does nothing "
            "where the menu wouldn't offer it.")


def keys_of(action: str, context: str) -> list:
    """Every key that does `action` in `context`, own bindings first."""
    own = [k for k, a in KEYMAP[context].items() if a == action]
    inherited = [k for k, a in KEYMAP["text"].items() if a == action and k not in KEYMAP[context]]
    return own + inherited if context != "text" else own


def markdown() -> str:
    out = ["# fw — keys", "",
           "Generated from `fw_keys.py` (`python3 fw_keys.py > KEYS.md`); change keys there.", "",
           "A key name is what a key config will use: `ctrl+`, `alt+` (Option), `shift+`, `meta+`, then",
           "the key. Each context lists what it changes; everything else does what it does in the text.", ""]
    for ctx, (title, intro) in SECTIONS.items():
        out += [f"## {title}", "", intro, "", "| keys | action | does |", "|---|---|---|"]
        actions = list(dict.fromkeys(KEYMAP[ctx].values())) + [a for a in DOES[ctx] if a not in KEYMAP[ctx].values()]
        for a in actions:
            keys = ", ".join(f"`{k}`" for k in keys_of(a, ctx))
            out.append(f"| {keys} | `{a}` | {DOES[ctx].get(a, '')} |")
        for keys, does in NOTES.get(ctx, []):
            out.append(f"| {keys} | | {does} |")
        out.append("")
        if ctx == "picker":
            out += [COMMANDS, ""]
    return "\n".join(out)


if __name__ == "__main__":
    print(markdown(), end="")
