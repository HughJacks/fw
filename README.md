# fw

A writing app where everything is a block, and any block can be quoted live anywhere else.
It runs in your browser, saves as you type, and keeps everything on your machine.

```sh
curl -fsSL https://raw.githubusercontent.com/HughJacks/fw/main/install.sh | sh
fw
```

Needs macOS or Linux, Python 3.10+, Node 22+ (the installer uses Homebrew for them if it can).
Your writing lives in `~/fw/freewrites.loro`, a [Loro](https://loro.dev) document, with a readable
`freewrites.json` beside it. Update by running the same line again. `fw help` for the rest.

## What a block can be

Text, a picture, a **live quote** of another block (edit through it and the original changes), a
**masked** quote showing only the parts you pick, a **paraphrase** of another block, a **tag**, or an
**expression**: a small program in a dialect of [Hazel](https://hazel.org) that shows its value, live.
Spans of text can **link** to other pages, which list their **backlinks**. `⌘/` shows what you can do
with the block you're in; `⌘⇧,` lists every key.

## Code

```
bin/fw          the launcher: starts the local server, opens the page
fw/             the core (Python, stdlib + loro)
  block/          the block model: one recursive type, pure functions
  store/          the store on disk: a Loro document, read, validated, written
  web/            the local HTTP server the page talks to
  draft.py lens.py migrate.py search.py …
web/            the page (Svelte 5, ProseMirror, CodeMirror)
hazel-bridge/   fw's prelude and bridge for the Hazel engine (built into web/vendor/hazel.js)
tests/          run.sh runs every suite: the core's, then the page's in headless Chrome
```

Hazel is © its authors, MIT licensed (`web/vendor/HAZEL-LICENSE`).
