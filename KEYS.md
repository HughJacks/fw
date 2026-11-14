# fw — keys

Generated from `fw_keys.py` (`python3 fw_keys.py > KEYS.md`); change keys there.

A key name is what a key config will use: `ctrl+`, `alt+` (Option), `shift+`, `meta+`, then
the key. Each context lists what it changes; everything else does what it does in the text.

## In the text

Arrows stop on a quote, selected whole, on the way in and out; one more press goes inside, or past.

| keys | action | does |
|---|---|---|
| `enter` | `newline` | new block at the cursor; on a selected quote, a new block below it; in a paraphrase, a block inside it |
| `shift+enter`, `alt+enter` | `line_break` | line break inside the block |
| `ctrl+enter` | `nest_in` | a block inside this one: it splits at the cursor, a level down; Enter on an empty one inside steps back out |
| `backspace`, `shift+backspace` | `backspace` | deletes back; at a block's start, merges it into the one above; on a selected quote, removes it |
| `alt+backspace`, `ctrl+backspace` | `delete_word` | deletes the word before |
| `delete` | `delete` | deletes forward; on a selected quote, removes it |
| `tab` | `tab` | types a tab |
| `left` | `left` | move |
| `right` | `right` | move |
| `up` | `up` | move; from the first row, into the header; from a quote's first row, out of it |
| `down` | `down` | move |
| `alt+left`, `ctrl+left`, `meta+left`, `alt+b` | `word_left` | move a word |
| `alt+right`, `ctrl+right`, `meta+right`, `alt+f` | `word_right` | move a word |
| `home` | `home` | start of line |
| `end` | `end` | end of line |
| `page_up` | `page_up` | move a screen |
| `page_down` | `page_down` | move a screen |
| `shift+left` | `select_left` | extend the selection |
| `shift+right` | `select_right` | extend the selection |
| `shift+up` | `select_up` | extend the selection (reaching another block: whole blocks) |
| `shift+down` | `select_down` | extend the selection (reaching another block: whole blocks) |
| `alt+shift+left`, `ctrl+shift+left`, `shift+meta+left` | `select_word_left` | extend the selection a word |
| `alt+shift+right`, `ctrl+shift+right`, `shift+meta+right` | `select_word_right` | extend the selection a word |
| `shift+home` | `select_home` | extend the selection |
| `shift+end` | `select_end` | extend the selection |
| `shift+page_up` | `select_page_up` | extend the selection |
| `shift+page_down` | `select_page_down` | extend the selection |
| `ctrl+a` | `select_all` | select all (with more than one block: all of them, whole) |
| `ctrl+c` | `copy` | copy (system clipboard); on a selected quote, it whole |
| `ctrl+x` | `cut` | cut; on a selected quote, it whole |
| `ctrl+v` | `paste` | paste; blocks copied whole come back as live quotes of them (cut ones: moved), inside the block you're in, split at the cursor |
| `ctrl+shift+v` | `paste_static` | paste blocks copied whole as static copies: plain blocks, a quote as the text it showed |
| `ctrl+z` | `undo` | undo a whole action, store included; after Open it, once nothing's left, steps back |
| `ctrl+y` | `redo` | redo |
| `ctrl+q` | `quit` | go home; after Open it, step back |
| `ctrl+/`, `alt+/` | `palette` | the menu of actions on the block you're in, anywhere |
| `esc` | `escape` | selects the block you're in whole (inside a quote too); again, the quote around it |
| `ctrl+e` | `edit_mask` | Create mask / Edit mask, on the quote selected or the one you're in |
| `ctrl+shift+e` | `show_all` | Remove mask |
| `ctrl+t` | `pop_out` | Turn into a quote: this block to a pericope of its own (a selection: just it, nested here) |
| `ctrl+shift+t` | `pop_out_open` | Turn into a quote and open it |
| `alt+t` | `detach` | Turn into text: the quote selected, a plain copy |
| `ctrl+o` | `open_source` | Open it: the quote selected or the one you're in, or the link the cursor's on, as the pericope |
| `ctrl+k` | `link_entry` | Link to a pericope: the selection (in one block) points to a pericope you pick, or a new one |
| `ctrl+shift+k` | `remove_link` | Remove link: the one the cursor's on (the text stays) |
| `ctrl+d` | `delete_entry` | delete this pericope (asks first; quotes of it keep their text) |
| a character | | types it |
| `/` at a line's start or after a space | | the menu of blocks to put in (mid-text, nested there) |
| Space on a red `…` | | edit the mask there |
| click | | place the cursor (a header line: edit that field); in the menu, closes it first |
| wheel | | scroll |

## Blocks selected whole

Esc selects the block you're in; a selection that reaches another block takes whole blocks. The edge at the moving end is heavy, the text cursor hides, and a ghost shows where ↓ or ↑ from that edge lands.

| keys | action | does |
|---|---|---|
| `esc` | `escape` | back to the text, the cursor where it was; inside a quote, the quote around them, selected |
| `shift+up` | `select_up` | one block more above (or one fewer) |
| `shift+down` | `select_down` | one block more below (or one fewer) |
| `up` | `up` | from the heavy top: out to the block above; of several selected, just the top one |
| `down` | `down` | from the heavy top: inside, where the ghost is; of several, just the bottom one |
| `left` | `left` | back to the text, at the start of the first block |
| `right` | `right` | back to the text, at the end of the last |
| `ctrl+c` | `copy` | copy the blocks (the system clipboard gets their text, a blank line apart) |
| `ctrl+x` | `cut` | cut the blocks |
| `ctrl+v` | `paste` | blocks copied whole: before them from the heavy top, after them from the heavy bottom; text: in their place |
| `ctrl+shift+v` | `paste_static` | blocks copied whole, as static copies, before or after them as paste puts them |
| `backspace`, `shift+backspace` | `backspace` | removes the blocks |
| `delete` | `delete` | removes the blocks |
| `enter` | `newline` | replaces them with a new, empty block |
| `ctrl+t` | `pop_out` | with several selected: not here (a command acts on one block) |
| a character | | replaces them with a new block holding it |
| click | | back to the text, where you clicked |

## Masking mode (Create mask / Edit mask)

No typing: the text stays as it is. Arrows move, into a box inside too, to mask that quote as seen through this one (anything its source hides is a locked …).

| keys | action | does |
|---|---|---|
| `[` | `open_bracket` | an opener, its partner inferred; with a selection, show exactly it |
| `]` | `close_bracket` | a closer, its partner inferred; with a selection, hide it |
| `tab` | `next_bracket` | next bracket |
| `shift+tab` | `prev_bracket` | previous bracket |
| `esc`, `enter` | `done` | done |
| `backspace`, `shift+backspace` | `backspace` | on a bracket, joins the spans either side |
| `delete` | `delete` | on a bracket, joins the spans either side |
| `ctrl+/`, `alt+/` | `palette` | nothing (finish the mask first) |

## The header

Moving, deleting, pasting and typing edit the field, as in the text.

| keys | action | does |
|---|---|---|
| `down`, `tab` | `next_field` | the field below, or back to the text from the last one |
| `enter` | `open_field` | on backlinks: the list of the blocks pointing here, Enter opens one; elsewhere as next_field |
| `up` | `prev_field` | the field above |
| `esc` | `leave_field` | back to the text |
| `ctrl+v` | `paste` | paste its first line |

## Menus and search

The `/` menu, Quote a block, and home. Typing filters; ↑ ↓ choose.

| keys | action | does |
|---|---|---|
| `enter`, `tab` | `pick` | run it / open it / quote it (a block inside a pericope: home opens the pericope at it; Quote a block makes it a pericope of its own, quoted here and where it was; a place that quotes a match: home opens it at the quote, Quote a block quotes the match) |
| `shift+enter` | `pick_masked` | Quote a block, on a block inside a pericope: quote its pericope, masked to just that block |
| `right` | `show_blocks` | home and Quote a block, on a pericope: list all the blocks inside it, under it |
| `left` | `hide_blocks` | home and Quote a block: hide them again (from the pericope or one of its blocks) |
| `esc` | `cancel` | close (the `/` menu leaves what you typed, as text; home quits) |
| `ctrl+d` | `delete_entry` | home: delete the pericope selected (asks first; quotes of it keep their text) |
| `backspace`, `shift+backspace` | `backspace` | with nothing typed: closes the menu; in Quote a block, back to the menu |
| `ctrl+q` | `quit` | home: quit |

Commands in the menu, shown only where they fit, each with its key: Quote a block · Create mask / Edit mask (masking mode: brackets only, no typing; arrow into a box inside to mask it as seen through this quote) · Remove mask · Open it · Its top line… (Show / Hide its title, date, last update, word count; found by search too, and the menu stays open to toggle more) · Turn into text · Turn into a quote (with a selection, just it, nested where it was) · Turn into a quote and open it · Link to a pericope · Remove link. A command's key does nothing where the menu wouldn't offer it.
