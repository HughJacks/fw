// actions.js — the Ctrl+/ menu (the terminal's actions menu): what can be done where the cursor is, each a
// store function through the core (POST /api/act). It opens at the cursor; typing filters it (nested
// commands still found); ↑↓ move, Enter runs, → opens a submenu, ← or Esc goes back. A command either
// closes the menu (one-shot: Open it, Turn into …) or stays open (toggles: the top line, the lock). Each also
// has its key, as the terminal's. Each action's undo record is kept: ^Z, once what's typed is undone, takes the
// actions back, latest first; ^Y does them again.
import { api } from "./api.js";
import { searchBox } from "./menu.js";
import { startMasking } from "./masking.js";
import { splitSelection } from "./blocks.js";
import { newId } from "./draft.js";
import { keyOf, pretty } from "./keys.js";
import { ask } from "./ask.js";
import { float } from "./float.svelte.js";
import ActionsMenu from "./ActionsMenu.svelte";

const SHOWABLE = [["title", "title"], ["created", "date"], ["updated", "last update"], ["words", "word count"]];

/** The commands that fit `ctx` (BlockEditor.context()) in `editor`: [{name, label, note, key, stays, group}]. */
export function commands(editor, ctx) {
  const q = ctx.quote, shows = q || ctx.within, out = [];
  if (shows && !shows.data?.locked) out.push({ name: "mask", label: shows.data?.masked ? "Edit mask" : "Create mask", key: pretty(keyOf("mask")),
    note: "choose what it shows, with [ ]" });
  const para = !q && ctx.block?.para;
  if (q || ctx.link || para || ctx.para || editor.exit) out.push({ name: "open", label: "Open it", key: pretty(keyOf("open")),
    note: q ? "its source, as the pericope you're in" : ctx.link ? "the pericope it links to" : (para || ctx.para) ? "the block it paraphrases"
      : "the quote you're in, as the pericope, here" });
  if (para && !editor.lens) out.push({ name: "peek", label: editor.peeking.has(ctx.block.id) ? "Hide its source" : "Show its source",
    note: "its source's text, dim, inside it", stays: true });
  if (shows && shows.data?.masked) out.push({ name: "showall", label: "Remove mask", key: pretty(keyOf("showall")), note: "show all of it again" });
  if (shows) {
    out.push({ name: "group:topline", label: "Its top line…", note: "show its title, date, …" });
    for (const [k, said] of SHOWABLE) {
      const on = (shows.data?.show || []).includes(k);
      out.push({ name: `show:${k}`, label: `${on ? "Hide" : "Show"} its ${said}`, note: "in its top line", group: "topline", stays: true });
    }
    out.push(shows.data?.lock
      ? { name: "lock", label: "Unlock writing through", key: pretty(keyOf("lock")), note: "what it shows can be changed here again", stays: true }
      : { name: "lock", label: "Lock writing through", key: pretty(keyOf("lock")), note: "what it shows can't be changed from here", stays: true });
  }
  if (editor.lens) return out;   // (through a masked quote: only its text is written there)
  if (ctx.span && !editor.readOnly) out.push({ name: "link", label: "Link to a pericope", key: pretty(keyOf("link")), note: "the selection points to a pericope" });
  if (ctx.link && !editor.readOnly) out.push({ name: "unlink", label: "Remove link", key: pretty(keyOf("unlink")), note: "the text stays as it is" });
  if (q && !editor.readOnly) out.push({ name: "paraphrase_it", label: "Paraphrase it", note: "your words in its place" });
  else if (ctx.block && !ctx.block.para && !editor.readOnly && !(ctx.block.own && !editor.exit)) {
    if (ctx.block.text) out.push({ name: "paraphrase_it", label: "Paraphrase it", note: "it moves out; your words in its place" });
    out.push({ name: "paraphrase", label: "Paraphrases…", note: "mark this block as a paraphrase of another" });
  }
  if (para && !editor.readOnly) out.push({ name: "unparaphrase", label: "Not a paraphrase", note: "your words stay, no longer pointing" });
  if (q) out.push({ name: "detach", label: "Turn into text", key: pretty(keyOf("detach")), note: "a plain copy, no longer live" });
  else if (ctx.span && !editor.readOnly) {
    out.push({ name: "popout", label: "Turn into a quote", key: pretty(keyOf("popout")), note: "the selection to a pericope of its own, nested here" });
    out.push({ name: "popopen", label: "Turn into a quote and open it", key: pretty(keyOf("popopen")), note: "…and step into it" });
  } else if (ctx.block && ctx.block.text && !editor.readOnly && !(ctx.block.own && !editor.exit)) {
    out.push({ name: "popout", label: "Turn into a quote", key: pretty(keyOf("popout")), note: "this block to a pericope of its own" });
    out.push({ name: "popopen", label: "Turn into a quote and open it", key: pretty(keyOf("popopen")), note: "…and step into it" });
  }
  if (!editor.exit && !editor.holder) out.push({ name: "delete", label: "Delete this pericope", key: pretty(keyOf("delete")), note: "asked first; quotes of it elsewhere keep its last text" });
  return out;
}

/** The ⌘/ menu (the terminal's Ctrl+/ menu) and its actions for a page: `root()` the page's editor, `reload(selectQuote)` the page
 * drawn again from the store, `go(hash)`, `gone()` (the pericope deleted: leave without saving). Returns
 * act(editor, name), what the editors' keys call. */
export function actions({ root, reload, go, gone, title }) {
  // the store actions taken here, to undo (each its record: store.restore puts it back) and to redo (their
  // inverses). ^Z takes what's typed back first (ProseMirror's history), then these, latest first.
  const done = [], undone = [];
  let box = null;

  const post = async (body) => {
    await root().saveAll();
    const r = await api("/api/act", { method: "POST", body: JSON.stringify(body) });
    if (!r.ok) { root().message = r.body.error || "couldn't"; root().status(); return null; }
    if (r.body.record) { done.push(r.body.record); undone.length = 0; }
    return r.body;
  };
  /** A record put back (store.restore): its inverse onto `to`, the page drawn again. */
  const putBack = async (from, to, said) => {
    const record = from.pop();
    await root().saveAll();
    const r = await api("/api/restore", { method: "POST", body: JSON.stringify({ record }) });
    if (!r.ok) { say(r.body.error || "couldn't"); return; }
    to.push(r.body.record);
    await reload();
    say(said);
  };
  const say = (text) => { root().message = text; root().status(); };

  async function run(editor, name, ctx) {
    const q = ctx.quote, shows = q || ctx.within;
    switch (name) {
      case "open":
        if (q) editor.open({ ...(q.data || { target: q.target }), whole: !ctx.within });
        else if (ctx.link) editor.open({ target: ctx.link.to });
        else if (ctx.para || ctx.block?.para) { const p = ctx.para || ctx.block.para; editor.open({ target: p.id, home: p.home }); }
        else if (editor.exit) editor.open({ target: editor.id, at: ctx.block && ctx.block.id });
        return false;
      case "detach":
        if (!q) return false;
        if (await post({ do: "detach", quote: q.id })) { await reload(); say("turned into text"); }
        return false;
      case "popout":
      case "popopen": {
        if (!ctx.block || !ctx.block.text) return false;
        let block = ctx.block.own ? editor.id : ctx.block.id;
        if (ctx.span) {   // a selection: split out to a block of its own (the block a container around it), then that moved
          const split = splitSelection(editor.view.state, newId);
          if (!split) return false;
          editor.view.dispatch(split.tr);
          block = split.id;
        }
        const got = await post({ do: "popout", block });
        if (!got) return false;
        const at = await reload();   // (the cursor kept, through the quote now)
        // … and open it: from there, as Open it does from inside a quote, a step into it (the same pop out, then the
        // same step: 2026-11-19); the cursor not in it (the page left meanwhile), just opened
        if (name === "popopen") { if (!at?.openHere?.()) go(`#/p/${got.id}`); return false; }
        say("a pericope of its own now, quoted here");
        return false;
      }
      case "link": {   // the selection: a hyperlink to a pericope (or a new one, titled with what's typed)
        const span = ctx.span;
        if (!span) return false;
        searchBox(editor.view, span.from, {
          prompt: "link › ",
          keep: (r) => r.key === "new" || (r.key === r.open && !r.dim),   // (pericopes: a link points at one)
          foot: (it) => (it.key === "new" ? "↵ a new pericope, the selection linked to it" : "↵ link to it"),
          onPick: async (it, _, typed) => {
            const got = await post({ do: "link", block: editor.storeId(span), text: span.text, at: span.at,
              to: it.key === "new" ? null : it.key, title: it.key === "new" ? (typed || null) : null });
            if (!got) return;
            await reload();   // (drawn from the store: the link there; what's typed before it stays before it in undo)
            say(`linked to ${got.title}`);
          },
        });
        return false;
      }
      case "unlink": {
        const link = ctx.link;
        if (!link || !(await post({ do: "unlink", block: editor.storeId(link), to: link.to, at: link.at }))) return false;
        await reload();
        say("link removed");
        return false;
      }
      case "mask": {   // masking mode, in the quote's own box (masking.js)
        if (!shows) return false;
        const box = q ? editor.view.nodeDOM(editor.view.state.selection.from) : editor.holder?.dom;
        if (!box) return false;
        await root().saveAll();
        await startMasking(box, shows.id, {
          finish: async (draft, mask) => {
            if (await post({ do: "setmask", quote: shows.id, draft, mask })) { await reload(shows.id); say("masked · ^Z takes it back"); }
          },
          cancel: () => editor.view.focus(),
        });
        return false;
      }
      case "paraphrase_it": {   // your words in its place: an empty paraphrase of it, the cursor in it
        const ref = q ? q.id : ctx.block && editor.storeId(ctx.block);
        const got = ref && (await post({ do: "paraphrase_it", block: ref }));
        if (!got) return false;
        await reload();
        root().place(got.id);
        say("paraphrase it: your words in its place");
        return false;
      }
      case "paraphrase": {   // mark this block as a paraphrase of another, picked
        const b = ctx.block;
        if (!b) return false;
        searchBox(editor.view, editor.view.state.selection.from, {
          prompt: "paraphrases › ", keep: (r) => r.key !== "new",
          foot: () => "↵ this block says it another way",
          onPick: async (it) => {
            if (await post({ do: "paraphrase", block: editor.storeId(b), source: it.source || it.key })) { await reload(); say("marked as a paraphrase"); }
          },
        });
        return false;
      }
      case "unparaphrase":
        if (ctx.block?.para && (await post({ do: "paraphrase", block: editor.storeId(ctx.block), source: null }))) { await reload(); say("not a paraphrase"); }
        return false;
      case "peek":
        if (!ctx.block?.para) return false;
        if (editor.peeking.has(ctx.block.id)) editor.peeking.delete(ctx.block.id); else editor.peeking.add(ctx.block.id);
        editor.view.dispatch(editor.view.state.tr.setMeta("peek", true));   // (drawn again)
        return true;
      case "showall":
        if (shows && (await post({ do: "showall", quote: shows.id }))) { await reload(shows.id); say("all of it shown"); }
        return false;
      case "lock":
        return (shows && (await post({ do: "lock", quote: shows.id, on: !shows.data?.lock })) && (await reload(null, { focus: false }))) || true;
      case "delete": {
        if (editor !== root()) return false;
        if (!(await ask(`delete “${title()}”? quotes of it elsewhere keep its last text. this can't be undone.`))) { editor.view.focus(); return false; }
        const got = await post({ do: "delete", pericope: root().id });
        if (got) { gone(); go("#/"); }
        return false;
      }
      default:
        if (name.startsWith("show:") && shows) {
          const k = name.slice(5), now = shows.data?.show || [];
          const show = now.includes(k) ? now.filter((x) => x !== k) : [...now, k];
          // (the menu stays open: the cursor kept where it was, the focus left in the menu; the editor it's in back)
          return ((await post({ do: "show", quote: shows.id, show })) && (await reload(null, { focus: false }))) || true;
        }
        return false;
    }
  }

  function menu(editor) {   // ActionsMenu.svelte, at the cursor
    box?.dismiss(false);
    const view = editor.view;
    let at = editor;   // (where the focus goes back to: where it opened, or after a toggle, the editor the cursor's in now)
    box = float(ActionsMenu, view.coordsAtPos(view.state.selection.from), { editor, commands, run, root, moved: (e) => { at = e; } },
      () => (at.view.dom.isConnected ? at : root()).view.focus());   // (back there, if that's still there)
  }

  /** What an editor's key calls: the menu, an action, or ^Z on an action just taken. Returns whether it was handled. */
  return function act(editor, name) {
    if (name === "menu") { menu(editor); return true; }
    if (name === "changed") { undone.length = 0; return false; }
    if (name === "undo") { if (!done.length) return false; putBack(done, undone, "taken back · ^Y does it again"); return true; }
    if (name === "redo") { if (!undone.length) return false; putBack(undone, done, "done again"); return true; }
    const ctx = editor.context();
    if (!commands(editor, ctx).some((c) => c.name === name)) return false;   // (it doesn't fit here)
    run(editor, name, ctx);
    return true;
  };
}

