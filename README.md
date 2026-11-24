# fw

A free-writing app growing, slowly, into a block-and-live-quote notebook.
You write in your browser; fw saves as you type, to a file on your own
machine. Nothing leaves it: there's no account, no server but the small one
fw runs on 127.0.0.1, and no model. Everything you write is made of
**blocks**, and a block can be:

- **quoted live** somewhere else (edit the quote, and the original changes too),
- **masked**: a quote that shows only the parts of the original you pick,
- **linked** from a span of text to another entry, with **backlinks** shown on the target,
- marked as a **paraphrase** of another block (the same thing said another way),
- **tagged** (a poem, a letter, a class you're taking…), tags being blocks too,
- or an **expression**: a small program that shows what it works out to, live,
  from the blocks around it or from anything you've written (`/` → Expression,
  ⌘⇧X for its code). Quote one and it's worked out where the quote sits.

Home has an empty pericope waiting in the middle: start typing and it's
yours. Below it are the search and the **garden** (cards of what you've been
writing, mixed with what's been slipping out of memory, worked out from when
you last visited each), and below that everything you've written.

The web editor is the default. The original terminal editor is still there
(`fw term`), deprecated.

It's an early personal project: things change, and some corners are rough.

## Try it

On a Mac (Linux works too), in Terminal:

1. **Get the two things fw needs**, Python and Node. With [Homebrew](https://brew.sh):

   ```sh
   brew install python node
   ```

2. **Download fw and set it up** (a minute or two):

   ```sh
   git clone https://github.com/HughJacks/fw.git ~/fw
   ~/fw/install.sh
   ```

3. **Start writing:**

   ```sh
   fw
   ```

   Your browser opens on fw's home. Just start typing in the empty page in
   the middle: it saves as you type. (If `fw` isn't found, the installer
   printed one line to add to `~/.zshrc`; or run `~/fw/fw`.)

**A few keys to start with** (⌘ is Ctrl on Linux): `Enter` a new block,
`⌘/` what you can do with the block you're in, `/` at the start of a line
to quote another block, `⌘⇧Enter` done with this page (saved, back home),
`⌘[` back. Every key, and changing them: `⌘⇧,`.

**Your writing** stays on your computer, in `~/fw/freewrites.loro` (with a
readable copy, `freewrites.json`, beside it). Nothing is sent anywhere.

**To update:** `cd ~/fw && git pull && ./install.sh`. To stop fw's little
background server: `pkill -f fw_web.py` (the next `fw` starts it again).

## Requirements

- Python 3.10 or newer, and one package: [`loro`](https://loro.dev) (the store is a Loro
  document, so copies on several machines can merge)
- [Node](https://nodejs.org) 22 or newer, once, to build the page (`npm ci`,
  `npm run build`): the browser loads it from `web/dist/`, nothing from the internet
- macOS or Linux, with `zsh` (for the `fw` launcher)
- A browser. The web editor's tests drive Google Chrome (`$CHROME` names another
  Chromium); without it they're skipped.
- For the terminal editor only: any terminal. Pictures draw only in iTerm2; elsewhere a picture shows as a
  `▣ picture W×H` line. Keys like `ctrl+shift+v` need a terminal that reports
  modified keys (iTerm2, kitty, WezTerm, foot, recent xterm); everything is
  also reachable from the `ctrl+/` menu.
- Copy and paste use the system clipboard: `pbcopy`/`pbpaste` on macOS,
  `wl-copy`/`wl-paste`, `xclip` or `xsel` on Linux. Without any of them fw
  keeps its own clipboard.

## Install

`./install.sh` does all of this (and links `fw` into `~/.local/bin`). By hand:

```sh
git clone https://github.com/HughJacks/fw.git
cd fw
python3 -m venv .venv && .venv/bin/pip install loro==1.17.1
(cd web && npm ci && npm run build)
./fw            # or put this folder on your PATH and run: fw
```

`fw` starts the core (`fw_web.py`, on http://127.0.0.1:8020; `FW_WEB_PORT`
picks another port) if it isn't running and opens the page. After a
`git pull`, the running core notices: it rebuilds the page, restarts itself,
and the open tab reloads.

## Use

```
fw                 the web editor, in your browser (also: fw open, fw web)
fw list            list every entry
fw help            all of it

fw term            the terminal editor: a new entry; ^Q goes home
fw term open       the terminal editor, starting at home
fw -t [minutes]    the terminal editor with a writing timer (10 minutes unless given)
fw <title>         the terminal editor, on the entry with that title (started if missing)
fw last            the terminal editor, appending to the most recent entry
fw stop            cancel a running timer
```

The web editor's keys are Mac-style (⌘ is Ctrl elsewhere): `Enter` a new
block, `⇧Enter` a line break, `⌘Enter` a block inside this one, `/` at a
line's start the menu of blocks to put in (quote a block, add a picture…),
`⌘/` the actions on the block you're in, `⌘O` open the quote or link
you're in, `⌘[` / `⌘]` back and forward, `⌘⇧Enter` send the pericope away
(saved, and home), `⌘Z` / `⌘⇧Z` undo and redo, `⌘⇧H` home. Every key, and
changing them: the keys page, `⌘⇧,` (your bindings are kept in
`web-keys.json` beside your writing).

The terminal editor's main keys: `Enter` new block, `ctrl+enter` a block inside this one,
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
when first needed, and checked and migrated on every run. To bring in a copy
from another machine: `.venv/bin/python fw_store.py merge other/freewrites.loro`
(both sides' edits kept, the same in either order).

Search by meaning is optional and off: fw has no model. If you run a
search service that answers `GET /search?q=…&n=…` with
`{"results": [[block id, …], …]}`, set `FW_MEANING_URL` to it and fw mixes
its answers into the search.

## Developing

`DESIGN.md` is the technical map; `TYPE.md` is the theory of blocks and
expressions. Expressions are written in fw's dialect of
[Hazel](https://github.com/hazelgrove/hazel) (MIT; its licence is in
`web/vendor/HAZEL-LICENSE`): `web/vendor/hazel.js` is Hazel's engine compiled to
JavaScript with fw's prelude and bridge (their sources in `hazel-bridge/`). Tests: `tests/run.sh` (needs `pyte` and `loro`
in `tests/.venv`; the script says how). Its suite "web" builds the page, runs
`npm test` and the browser suite (`web/test/e2e.mjs`, headless Chrome).
