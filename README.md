# fw

A terminal free-writing app growing, slowly, into a block-and-live-quote
notebook. You write; fw saves as you type. Everything you write is made of
**blocks**, and a block can be:

- **quoted live** somewhere else (edit the quote, and the original changes too),
- **masked**: a quote that shows only the parts of the original you pick,
- **linked** from a span of text to another entry, with **backlinks** shown on the target,
- marked as a **paraphrase** of another block (the same thing said another way),
- said to be of a **kind** (a poem, a to-do list…), kinds being blocks too.

Home is a **garden**: cards of what you've been writing, mixed with what's
been slipping out of memory (worked out from when you last visited each).

It's an early personal project: things change, and some corners are rough.

## Requirements

- Python 3.10 or newer, and one package: [`loro`](https://loro.dev) (the store is a Loro
  document, so copies on several machines can merge)
- macOS or Linux, with `zsh` (for the `fw` launcher)
- Any terminal. Pictures draw only in iTerm2; elsewhere a picture shows as a
  `▣ picture W×H` line. Keys like `ctrl+shift+v` need a terminal that reports
  modified keys (iTerm2, kitty, WezTerm, foot, recent xterm); everything is
  also reachable from the `ctrl+/` menu.
- Copy and paste use the system clipboard: `pbcopy`/`pbpaste` on macOS,
  `wl-copy`/`wl-paste`, `xclip` or `xsel` on Linux. Without any of them fw
  keeps its own clipboard.

## Install

```sh
git clone https://github.com/HughJacks/fw.git
cd fw
python3 -m venv .venv && .venv/bin/pip install loro==1.17.1
./fw            # or put this folder on your PATH and run: fw
```

## Use

```
fw                 new entry; ^Q goes home, the garden (type to search; Esc quits)
fw -t [minutes]    with a writing timer (10 minutes unless given)
fw <title>         open or start the entry with that title
fw last            append to the most recent entry
fw open            start at home
fw list            list every entry
fw stop            cancel a running timer
fw help            all of the above
```

The main keys: `Enter` new block, `ctrl+enter` a block inside this one,
`/` at a line's start the menu of blocks to put in (quote a block, add a
picture…), `ctrl+/` the menu of actions on the block you're in, `ctrl+e`
mask a quote, `ctrl+k` link the selection to an entry, `ctrl+o` open the
quote or link under the cursor, `esc` select the whole block, `ctrl+z` /
`ctrl+y` undo / redo, `ctrl+q` home, `ctrl+[` / `ctrl+]` back and forward,
`ctrl+g` on home the garden as cards or a list. Every key is in [KEYS.md](KEYS.md).

## Your data

Everything lives in `freewrites.loro` beside the code, a Loro document,
with `freewrites.json` written beside it as a plain copy you can read (and
a `.bak` of that), pictures in `images/`. Set
`FW_DATA=/path/to/freewrites.json` to keep it somewhere else. It's created
on first run, and checked and migrated on every run. To bring in a copy
from another machine: `.venv/bin/python fw_store.py merge other/freewrites.loro`
(both sides' edits kept, the same in either order).

## Developing

`DESIGN.md` is the technical map. Tests: `tests/run.sh` (needs `pyte` and `loro`
in `tests/.venv`; the script says how).
