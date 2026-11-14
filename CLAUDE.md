# fw

A terminal free-writing app growing slowly into a block-and-live-quote PKM. **Read `DESIGN.md` first.** It's the technical map: principles, files, where changes go, the data model (schema v15), the architecture, and working on it. Every key is in `KEYS.md`.

- **Build it slowly and without bloat.** Build only what's asked; never build or plan stretch goals unprompted.
- **Functional principles in the code too:** a block is a recursive option type, pure functions, I/O at the edges. Standard library only.
- **Keys live in `fw_keys.py`** (`KEYMAP`, and what each action does). After changing them, regenerate `KEYS.md` with `python3 fw_keys.py > KEYS.md`; `tests/keys_test.py` fails if you forget.
- **Menu commands follow one pattern:** each is a `Command` in `fw_menu.commands`. Decide two things for every new one: does it **close the menu** after it runs (one-shot actions: Open it, Turn into …) or **stay open** (`stays=True`: toggles and anything you'd do a few of in a row; its label refreshes)? And does it belong **in a submenu** (`group=`, with a `group:<name>` entry that opens it) to keep the top level short? Nested commands still show up when you search for them.
- **Where a change goes:** a new menu command in `fw_menu.py` (a `Command` in `commands`, its method named in `run_command`); mask editing in `fw_mask_ui.py`; blocks selected whole in `fw_blocks.py`; how things are laid out and drawn in `fw_layout.py`; keys in `fw_keys.py`; pure block/draft/mask logic in `fw_block.py`, `fw_draft.py`, `fw_lens.py`; pictures (format, size, the terminal escape) in `fw_image.py`; store writes in `fw_store.py`; a schema change's migration as a step in `fw_migrate.py`; the app loop and the Open it trail in `fw_app.py`; state a mode owns as a field of its record in `fw_state.py` (not a new loose attribute or dict key). New suites use `tests/fwtest.py` (see its docstring).
- **Everything is a block.** Any block type added (text, image, whatever comes next) must work with every block operation: Quote a block (found in the search), Turn into a quote (and open it), Open it, selected whole, copy/cut/paste, undo. Write those operations over the content cases generically (`store.pop_out` takes any content but a quote's; `fw_block.is_whole` names the blocks with nothing to write in), and test a new case through all of them.
- **Undo must revert an action completely,** including whatever it changed in the store.
- **Before installing a change:**
  1. Run `tests/run.sh`.
  2. Make sure no fw session is open: `pgrep -fl "fw_app|fw_edit"`.
  3. Back up your store (`freewrites.json`, its `images/`).
  4. Install, then run `python3 fw_store.py migrate` and check the store.
- **`freewrites.json` is your real writing.** Tests use throwaway stores (`FW_DATA`); never write to the real one in tests.
