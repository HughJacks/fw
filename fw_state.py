"""fw_state — the editor's modes, named, and the state each one owns.

The editor (fw_edit.Editor, with its mixins fw_mask_ui and fw_menu) is
always in one mode, read off its state by `Editor.mode`, and each key goes to
that mode's handler (`Editor.key_<mode>`), which passes what it doesn't
handle on to a more general one (masking and view to quote, quote to text):

    "menu"     the / menu over any of the below    `palette`: a Menu
    "header"   editing a header field             `field` (an index), `fedit`: a FieldEdit
    "masking"  choosing what a quote shows         `medit`: a Masking
    "view"     inside a masked quote: typing goes
               through its mask                    `vmode`: a View
    "blocks"   blocks selected whole (fw_blocks)  `picked`: a Picked
    "review"   a kind's maybe, open to be answered `review`: a Review
    "quote"    inside a quote: typing edits it
    "text"     writing in the entry

Inside a quote (and so in "view" and "masking"), `self.lines` is that
block's text, and each block around it waits on `stack` as a Frame. What
every mode shares lives on the editor itself: the buffer (`lines`, `bids`),
the cursor (`cy`, `cx`), the undo stacks. These records are the rest: what
belongs to one mode, written down, so the mixins depend on named fields
rather than on dict keys that happen to match.
"""

from dataclasses import dataclass, field


@dataclass
class View:
    """A masked quote's view, being edited ("view"): the buffer is what the
    quote shows, its hidden stretches drawn as … ."""
    qid: str                   # the quote block whose view this is
    opened: int | None         # the hidden stretch laid open, if any
    silent: set                # blocks whose marker is hidden in the view (no marker of their own)


@dataclass
class Frame:
    """A block waiting on the stack while a quote inside it is edited (or,
    while masking, while the cursor is in a quote inside the one being masked)."""
    id: str                    # the block
    lines: list                # its buffer, as it was left
    bids: list
    saved: tuple               # its snapshot as last saved
    anchor: int                # the line of the quote that's open
    undo: list                 # its undo and redo, kept for when it's back
    redo: list
    vmode: View | None         # its view, if it's a masked quote's
    nest: dict = field(default_factory=dict)  # its nesting (fw_draft.parse_nest)
    meta: list | None = None   # while masking: how each line is drawn (fw_mask_ui.render)
    silent: set = field(default_factory=set)  # while masking: as View.silent


@dataclass
class FieldEdit:
    """A header field being edited ("header"): which, where the cursor is in
    it, and its text as typed, which can be empty (a derived title shows
    again only once you leave it empty)."""
    index: int                 # which field (into Editor.editable)
    x: int                     # the cursor's column in it (on the kinds line: which token, len for the +)
    text: str                  # what's in the field now
    start: str                 # what it showed when you came in (a derived title, or what's written)
    was: str                   # its value when you came in ("" for a derived one)
    anchor: int | None = None  # the selection's other end (^A), if any


@dataclass
class Masking:
    """Masking mode ("masking"): one mask over the flow of the quote being
    masked and every quote inside it (fw_mask_ui)."""
    qid: str                   # the quote being masked (its masks are stored on it)
    start: int                 # where its steps start on the undo stack (one step, once done)
    depth: int                 # its level on the stack
    keys: list                 # the segments the cursor's in, outermost first: [()] at the quote itself
    flow: dict                 # fw_mask_ui.build_flow: the stream, its segments
    mask: list                 # the one mask, over the stream
    meta: list | None = None   # how each line of the buffer is drawn (fw_mask_ui.render)
    silent: set = field(default_factory=set)  # as View.silent, for the buffer


@dataclass
class Menu:
    """The / menu ("menu"): commands to pick from (stage "command"), the
    entry to quote (stage "block") or to link to (stage "link"), or a kind
    (stage "kinds", from the header's kinds line), with its Picker, or a
    picture's web address, typed (stage "url", in `query`)."""
    stage: str                 # "command", "block", "link", "url", "backlinks", "paraphrase" or "kinds"
    query: str = ""
    sel: int = 0
    commands: list = field(default_factory=list)  # fw_menu.Command, as they fit where the cursor is
    slash: bool = False        # opened by typing / (closing it types what was typed)
    group: str | None = None   # the submenu it's in
    used: bool = False         # a command ran and it stayed open: closing it types nothing
    picker: object = None      # stage "block", "link", "backlinks" or "kinds": the fw_picker.Picker
    mark: str | None = None    # stage "paraphrase": the block to mark as a paraphrase of the one picked
    found: list = field(default_factory=list)  # stage "backlinks": fw_block.backlinks, its rows' keys indexes into it
    span: tuple | None = None  # stage "link": (the text block, its text, [start, end]) to link
    fetch: dict | None = None  # stage "url": the download under way, {"result": None, then (ok, bytes or why)}
    note: str = ""             # stage "url": why the last one didn't work


@dataclass
class Picked:
    """Blocks selected whole ("blocks", fw_blocks): the entry's numbered
    blocks from `anchor` to `at`, as indexes into fw_blocks.units()."""
    anchor: int                # the block the selection began on
    at: int                    # the block at its moving end
    edge: str                  # "top" or "bottom": `at`'s heavy edge (↑/↓ from it goes in, the other way out)
    back: tuple                # (line, col) of the cursor before: Esc puts it back
    text: tuple | None = None  # began as a text selection: its anchor (back in that block, it's text again)


@dataclass
class Review:
    """Going through a kind's maybes (fw_block.maybes), one block at a time:
    begun on the kind's maybes line, each block opened in turn by fw_app,
    its editor in mode "review" (Enter it is one, Backspace it isn't, Tab
    skip, ^Z back, ^Q stop); then back to the kind."""
    kind: str                  # the kind
    queue: list                # [(block id, p)] still to see, the one open first
    total: int                 # how many there were
    done: list = field(default_factory=list)  # [(block id, p, True | False | None (skipped), set_kind's undo record or None)], in order
    stop: bool = False         # ^Q: back to the kind, the rest left


@dataclass
class Visits:
    """Not a mode: what the editor notes of the visits it sees, in every mode
    (fw_block.attend; written by Editor.flush_visits)."""
    live: dict = field(default_factory=dict)     # the visits under way: {block id: (minute it began, last attention, s)}
    pending: dict = field(default_factory=dict)  # not yet in the store: {block id: {minute: flags}}
    here: tuple | None = None                    # the block the cursor's in: (id, since, counted yet?, it and its containers)


@dataclass
class Home:
    """Home between visits (fw_app.home), so coming back to it, after a delete
    there or from a pericope, finds it as it was left: the view, what was
    typed, which card or row was selected, grid or list."""
    search: bool = False       # the search showing (else the garden)
    query: str = ""            # what was typed in it
    sel: int | None = None     # the garden's selected card (None: the first pericope's)
    picked: int | None = None  # the search's selected row
    grid: bool = True          # the garden as cards, or a list (Ctrl+G)
    forward: list = field(default_factory=list)  # [(entry, its draft offset)] gone back from, the newest last: Ctrl+] opens them again
