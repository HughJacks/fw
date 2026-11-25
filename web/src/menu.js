// menu.js — the / menu (the terminal's insert menu): a / at a line's start or after a space opens it at the
// cursor; what's typed after the / filters it (typing what matches no command leaves it as text); ↑↓ move,
// Enter runs, Esc closes. Its commands: Quote a block (a search, then the block quoted here) and Add a
// picture from a link. A picture file dropped or pasted on the page is quoted the same way.
import { Plugin, PluginKey, TextSelection, NodeSelection } from "prosemirror-state";
import { schema } from "./schema.js";
import { codeMark, codeRuns, icodeKey } from "./inlinecode.js";
import { api } from "./api.js";
import { float } from "./float.svelte.js";
import SearchBox from "./SearchBox.svelte";
import PictureLink from "./PictureLink.svelte";
import SlashList from "./SlashList.svelte";

const key = new PluginKey("slash");
const COMMANDS = [
  { name: "quote", label: "Quote a block", note: "find a block, quoted here" },
  { name: "image", label: "Add a picture from a link", note: "downloaded into fw, kept here" },
  { name: "expr", label: "Expression", note: "a program: the block shows what it works out to · ⌘⇧X its code" },
];
/** An expression block put in at `at` (in place of an empty block, else after the text there), its code open to
 * write in (the expr branch). */
function insertExpr(editor, at) {
  const view = editor.view;
  const node = schema.nodes.expr.create({ id: null, source: "" });
  let tr = view.state.tr.setSelection(TextSelection.create(view.state.doc, at));
  const { $from } = tr.selection;
  const empty = $from.parent.type.name === "text_block" && $from.parent.content.size === 0;
  if (empty) tr.replaceWith($from.before(), $from.after(), node); else tr.replaceSelectionWith(node);
  let pos = null;
  tr.doc.descendants((n, p) => { if (pos === null && n.type.name === "expr" && !n.attrs.id) pos = p; });
  if (pos === null) return;
  if (!(tr.doc.nodeAt(pos + node.nodeSize)?.type.name === "text_block")) tr.insert(pos + node.nodeSize, schema.nodes.text_block.create());
  tr.setSelection(NodeSelection.create(tr.doc, pos));
  view.dispatch(tr.scrollIntoView());
  setTimeout(() => view.nodeDOM(view.state.selection.from)?.fwExpr?.toggle());   // (its code open: write it)
}
/** A quote of block `target` put in at the cursor: in place of an empty block, else after the text there
 * (split); the cursor in a block below it. Returns where the quote went. */
export async function insertQuote(editor, target, at = null) {
  const r = await api(`/api/quote?target=${encodeURIComponent(target)}${editor.quoteHere()}`);
  if (!r.ok) { editor.message = r.body.error || "can't quote that"; editor.status(); return null; }
  const view = editor.view;
  const node = schema.nodes.quote.create({ id: null, target, data: r.body });
  let tr = view.state.tr;
  if (at !== null) tr.setSelection(TextSelection.create(tr.doc, at));
  const { $from } = tr.selection;
  const empty = $from.parent.type.name === "text_block" && $from.parent.content.size === 0;
  if (empty) tr.replaceWith($from.before(), $from.after(), node);   // an empty block: the quote in its place
  else tr.replaceSelectionWith(node);                                  // else at the cursor (the text split there)
  let pos = null;   // where it went: the one quote with no id yet (ids come after this transaction)
  tr.doc.descendants((n, p) => { if (pos === null && n.type.name === "quote" && !n.attrs.id) pos = p; });
  if (pos === null) return null;
  const after = pos + node.nodeSize;
  if (!(tr.doc.nodeAt(after)?.type.name === "text_block")) tr.insert(after, schema.nodes.text_block.create());
  tr.setSelection(TextSelection.create(tr.doc, after + 1));
  view.dispatch(tr.scrollIntoView());
  view.focus();
  return pos;
}

/** A search box at document position `pos` of `view` (SearchBox.svelte: the home search's rows, the search service's answers
 * mixed in after a pause): `prompt`; `keep(row)` which rows to offer; `foot(row)` what Enter will do; `onPick(row,
 * shift, query)` once one's picked (the box gone). Esc closes it. */
export function searchBox(view, pos, { prompt, keep = () => true, foot, onPick }) {
  return float(SearchBox, view.coordsAtPos(pos), { prompt, keep, foot, onPick }, () => view.focus());
}

/** @ in a line: fw's search; a pick puts `$@id$` in place of the @ (an inline expression, drawn as its chip), a new
 * pericope titled with what's typed made first; Esc leaves the @ as it is. */
function mentionSearch(editor, pos) {
  const view = editor.view;
  searchBox(view, pos, {
    prompt: "@ › ",
    keep: (r) => r.key === "new" || !r.dim,
    foot: (it) => (it.key === "new" ? "↵ a new pericope, referred to here" : "↵ refer to it here"),
    onPick: async (it, _, typed) => {
      let id = it.source || it.key;
      if (it.key === "new") {
        const r = await api("/api/pericope", { method: "POST", body: JSON.stringify({ title: typed || null }) });
        if (!r.ok) return;
        id = r.body.id;
      }
      const at = view.state.doc.textBetween(pos, Math.min(pos + 1, view.state.doc.content.size)) === "@" ? pos : null;
      const code = `$@${id}$`, node = schema.text(code, [codeMark()]);
      const start = at ?? view.state.selection.from;
      let tr = at !== null ? view.state.tr.replaceWith(at, at + 1, node) : view.state.tr.replaceSelectionWith(node, false);
      tr = tr.setSelection(TextSelection.create(tr.doc, Math.min(start + code.length, tr.doc.content.size)));
      view.dispatch(tr.scrollIntoView());
      view.focus();
    },
  });
}

/** Stage two of Quote a block: a search, then Enter quotes. */
function quoteSearch(editor, pos, enterNew) {   // (enterNew(at): into the quote at `at`)
  const view = editor.view;
  searchBox(view, pos, {
    prompt: "quote › ",
    foot: (it) => (it.key === "new" ? "↵ a new pericope, quoted here, and into it"
      : it.inside ? "↵ a pericope of its own, quoted here and where it was · ⇧↵ its pericope, masked to it"
      : it.source !== it.key ? "↵ quote what it quotes" : "↵ quote it"),
    onPick: async (it, masked, typed) => {
      if (it.key === "new") {
        const r = await api("/api/pericope", { method: "POST", body: JSON.stringify({ title: typed || null }) });
        if (!r.ok) return;
        const at = await insertQuote(editor, r.body.id);
        if (at !== null) { await editor.save(); enterNew(at); }
        return;
      }
      if (it.inside && masked) {   // its pericope, masked to just it
        const at = await insertQuote(editor, it.open);
        if (at === null) return;
        await editor.save();
        const qid = view.state.doc.nodeAt(at)?.attrs.id;
        const r = await api("/api/maskto", { method: "POST", body: JSON.stringify({ quote: qid, block: it.key }) });
        if (r.ok) editor.setQuote(qid, r.body);
        return;
      }
      if (it.inside) {   // a pericope of its own, quoted here and where it was
        await editor.save();
        const r = await api("/api/popout", { method: "POST", body: JSON.stringify({ block: it.key }) });
        if (!r.ok) { editor.message = r.body.error; editor.status(); return; }
        await insertQuote(editor, r.body.id);
        editor.message = "a pericope of its own now, quoted here and where it was";
        editor.status();
        return;
      }
      await insertQuote(editor, it.source || it.key);
    },
  });
}

/** Stage two of Add a picture from a link (PictureLink.svelte): the address, then it's downloaded and quoted here. */
function pictureLink(editor, pos) {
  const view = editor.view;
  const box = float(PictureLink, view.coordsAtPos(pos), {
    add: async (url) => {
      const r = await api("/api/picture", { method: "POST", body: JSON.stringify({ url }) });
      if (!r.ok) return r.body.error || "couldn't add it";
      box.dismiss(false);
      await insertQuote(editor, r.body.id);
      editor.message = "picture added";
      editor.status();
      return null;
    },
  }, () => view.focus());
}

/** A picture file (dropped or pasted): a picture pericope, quoted at `pos`. */
export async function addPictureFile(editor, file, pos) {
  const r = await api("/api/picture", { method: "POST", body: file, headers: { "Content-Type": file.type, "X-Name": file.name || "a picture" } });
  if (!r.ok) { editor.message = r.body.error || "couldn't add it"; editor.status(); return; }
  await insertQuote(editor, r.body.id, pos);   // (where it was dropped)
  editor.message = "picture added";
  editor.status();
}

/** The / menu, as a ProseMirror plugin over `editor` (a BlockEditor); `enterNew()`: into the quote just
 * made (a new pericope's). */
export function slashMenu(editor, enterNew) {
  let box = null, sel = 0;   // (box: SlashList.svelte, floated while the menu's open)
  const shown = (state) => {
    const s = key.getState(state);
    if (!s) return null;
    const q = state.doc.textBetween(s.from + 1, state.selection.head, "\n").toLowerCase();
    return { ...s, q, cmds: COMMANDS.filter((c) => c.label.toLowerCase().includes(q) || c.name.startsWith(q)) };
  };
  const close = (view) => view.dispatch(view.state.tr.setMeta(key, { close: true }));
  const run = (view, m, cmd) => {
    const from = m.from;
    view.dispatch(view.state.tr.delete(from, view.state.selection.head).setMeta(key, { close: true }));
    if (cmd.name === "quote") quoteSearch(editor, from, enterNew);
    else if (cmd.name === "image") pictureLink(editor, from);
    else if (cmd.name === "expr") insertExpr(editor, from);
  };
  return new Plugin({
    key,
    state: {
      init: () => null,
      apply(tr, s, _, state) {
        const meta = tr.getMeta(key);
        if (meta && meta.close) return null;
        if (meta && meta.open !== undefined) return { from: meta.open };
        if (!s) return null;
        const from = tr.mapping.map(s.from);
        const head = state.selection.head;
        if (state.doc.textBetween(from, from + 1) !== "/" || head <= from || state.selection.$head.parent !== state.doc.resolve(from).parent) return null;
        return { from };
      },
    },
    props: {
      handleTextInput(view, from, to, text) {
        if (text === "$" && !editor.readOnly) {   // (TYPE.md "Inline": $ in an empty block makes it an expression; \$ a dollar sign)
          const $at = view.state.doc.resolve(from);
          if ($at.parent.type.name !== "text_block" || $at.parent.attrs.para) return false;
          if (from === to && $at.parent.textBetween(Math.max(0, $at.parentOffset - 1), $at.parentOffset) === "\\") {
            view.dispatch(view.state.tr.insertText("$", from - 1, to));
            return true;
          }
          if ($at.parent.content.size === 0) { insertExpr(editor, from); return true; }
          // (in an inline expression: its closing $ steps out of it, any other $ is nothing: Hazel has none)
          const run = codeRuns(view.state.doc).find((r) => r.source !== null && r.from < from && from < r.to);
          if (run) {
            if (from === run.to - 1) view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, run.to)));
            return true;
          }
          // (mid-text: an inline expression, two dollar signs, the caret between them)
          const mark = codeMark(), tr = view.state.tr.replaceWith(from, to, schema.text("$$", [mark]));
          view.dispatch(tr.setSelection(TextSelection.create(tr.doc, from + 1)).setMeta(icodeKey, { open: mark.attrs.key }));   // (typed: open)
          return true;
        }
        if (text === "@" && !editor.readOnly) {   // (TYPE.md "Inline": @ is sugar for $@p$, a reference in the line, its chip)
          const $at = view.state.doc.resolve(from);
          if ($at.parent.type.name !== "text_block" || $at.parent.attrs.para) return false;
          if (codeRuns(view.state.doc).some((r) => r.from < from && from < r.to)) return false;   // (in code: an @ reference, typed as is)
          if (from === to && $at.parent.textBetween(Math.max(0, $at.parentOffset - 1), $at.parentOffset) === "\\") {   // (\@: an @, no search)
            view.dispatch(view.state.tr.insertText("@", from - 1, to));
            return true;
          }
          const before = $at.parent.textBetween(0, $at.parentOffset);
          if (before && !/\s$/.test(before)) return false;   // (only at a line's start or after a space: an address stays text)
          view.dispatch(view.state.tr.insertText("@", from, to));
          mentionSearch(editor, from);
          return true;
        }
        if (text !== "/" || editor.readOnly) return false;
        const $at = view.state.doc.resolve(from);
        if ($at.parent.type.name !== "text_block") return false;
        const before = $at.parent.textBetween(0, $at.parentOffset);
        if (before && !/\s$/.test(before)) return false;   // (only at a line's start or after a space, as the terminal's)
        view.dispatch(view.state.tr.insertText("/", from, to).setMeta(key, { open: from }));
        sel = 0;
        return true;
      },
      handleKeyDown(view, e) {
        const m = shown(view.state);
        if (!m) return false;
        if (e.key === "ArrowDown") { sel = Math.min(m.cmds.length - 1, sel + 1); draw(view); return true; }
        if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(view); return true; }
        if (e.key === "Escape") { close(view); return true; }
        if (e.key === "Enter" && m.cmds[sel]) { run(view, m, m.cmds[sel]); return true; }
        return false;
      },
      handleDrop(view, e) {
        const file = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
        if (!file || editor.readOnly) return false;
        const at = view.posAtCoords({ left: e.clientX, top: e.clientY });
        addPictureFile(editor, file, at ? at.pos : null);
        return true;
      },
      handlePaste(view, e) {
        const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
        if (!file || editor.readOnly) return false;
        addPictureFile(editor, file, null);
        return true;
      },
    },
    view: () => ({
      update: (view) => draw(view),
      destroy: () => { box?.dismiss(false); box = null; },
    }),
  });

  function draw(view) {
    const m = shown(view.state);
    if (m && !m.cmds.length && m.q) { setTimeout(() => close(view)); }   // (matches nothing: it's just text)
    if (!m || !m.cmds.length) { box?.dismiss(false); box = null; return; }
    sel = Math.min(sel, m.cmds.length - 1);
    const runIt = (c) => { const now = shown(view.state); if (now) run(view, now, c); };
    if (!box) box = float(SlashList, view.coordsAtPos(m.from), { cmds: m.cmds, sel, run: runIt });
    else { box.props.cmds = m.cmds; box.props.sel = sel; }
  }
}
