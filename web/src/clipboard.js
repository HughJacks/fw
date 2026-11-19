// clipboard.js — the rich clipboard (the terminal's): blocks selected whole, copied, paste back as live quotes of
// them; cut, they paste back as themselves (moved, the same ids: the store keeps a cut block while the clipboard
// holds it, store.clip_holds); ⌘⇧V (paste and match style) is a plain copy of their text. What fw clipped is kept by
// the core (.fw-clip.json, shared with the terminal), and used when what's pasted is still the text it clipped.
// Anything else pastes as ProseMirror pastes it.
import { Plugin, NodeSelection, TextSelection } from "prosemirror-state";
import { Fragment, Slice } from "prosemirror-model";
import { schema } from "./schema.js";
import { pmNode } from "./draft.js";
import { api } from "./api.js";
import { BlockSelection, removeSelected } from "./blocks.js";

let clip = null;   // what fw last clipped, as the core keeps it ({text, blocks, cut})
const norm = (s) => (s || "").replace(/\r\n/g, "\n").trim();
export async function readClip() { const r = await api("/api/clip"); clip = r.ok && r.body.blocks ? r.body : clip; }

/** The blocks selected whole: [{node, pos}], or null (a text selection: ProseMirror's own copy). */
function picked(state) {
  const sel = state.selection;
  if (sel instanceof BlockSelection) return sel.blocks();
  if (sel instanceof NodeSelection && sel.node.isBlock) return [{ node: sel.node, pos: sel.from }];
  return null;
}

/** A block's text, as it goes on the system clipboard. */
function textOf(node) {
  if (node.type.name === "quote") return (node.attrs.data?.body || []).map((b) => b.text || "").join("\n");
  if (node.type.name === "image") return "";
  return node.textBetween(0, node.content.size, "\n\n", "\n");
}

/** The plugin, over `editor` (a BlockEditor). */
export function clipboardPlugin(editor) {
  const copy = (view, e, cut) => {
    const blocks = picked(view.state);
    if (!blocks || editor.readOnly || editor.lens) return false;
    const ids = blocks.map(({ node }) => (node.attrs.own ? editor.id : node.attrs.id)).filter(Boolean);
    const text = blocks.map(({ node }) => textOf(node)).join("\n\n");
    e.clipboardData.setData("text/plain", text);
    e.preventDefault();
    (async () => {
      await editor.save();   // (each block in the store, by its id)
      clip = { text, blocks: ids.map((id) => ({ id })), cut };
      await api("/api/clip", { method: "POST", body: JSON.stringify({ ids, cut, text }) });
      if (cut) { removeSelected(view.state, view.dispatch); editor.message = "cut"; }
      else editor.message = `copied ${ids.length} block${ids.length === 1 ? "" : "s"}`;
      editor.status();
    })();
    return true;
  };
  return new Plugin({
    props: {
      handleDOMEvents: { copy: (view, e) => copy(view, e, false), cut: (view, e) => copy(view, e, true) },
      handlePaste(view, e) {
        if (editor.staticPaste || editor.readOnly || editor.lens) return false;   // (⌘⇧V: the plain text)
        const text = e.clipboardData?.getData("text/plain");
        if (!clip || !clip.blocks?.length || norm(text) !== norm(clip.text)) return false;
        const held = clip;
        (async () => {
          let nodes;
          if (held.cut) {   // moved: the blocks themselves, as the store has them
            const r = await api(`/api/blocks?ids=${held.blocks.map((u) => u.id).join(",")}`);
            nodes = (r.body.blocks || []).map((b) => schema.nodeFromJSON(pmNode(b)));
            clip = { ...held, cut: false };   // (a second paste: quotes of them)
            await api("/api/clip", { method: "POST", body: JSON.stringify({ ids: held.blocks.map((u) => u.id), cut: false, text: held.text }) });
          } else {   // live quotes of them (a quote copied: another quote of what it quotes)
            nodes = [];
            for (const u of held.blocks) {
              const target = u.quote ? u.quote.quote : u.id;
              const r = await api(`/api/quote?target=${encodeURIComponent(target)}${editor.quoteHere()}`);
              if (r.ok) nodes.push(schema.nodes.quote.create({ id: null, target, data: r.body }));
              else { editor.message = r.body.error || "can't quote that here"; editor.status(); }
            }
          }
          if (!nodes.length) return;
          const state = view.state, { $from } = state.selection;
          let tr = state.tr;
          if ($from.parent.type.name === "text_block" && $from.parent.content.size === 0 && state.selection.empty) {
            tr.replaceWith($from.before(), $from.after(), Fragment.fromArray(nodes));   // (an empty block: they go in its place)
          } else {
            tr.replaceSelection(new Slice(Fragment.fromArray(nodes), 0, 0));
          }
          // the cursor in a block of text just below them, as a quote put in from the / menu leaves it (one there, or
          // a new one): never a selection the browser's caret isn't at (the browser's stale caret then wins: a key
          // pressed next acted at the top of the page, 2026-11-18)
          const end = Math.min(tr.mapping.map(state.selection.to), tr.doc.content.size);
          const $end = tr.doc.resolve(end);
          const after = $end.depth === 0 ? end : $end.after(1);
          if (tr.doc.nodeAt(after)?.type.name !== "text_block") tr.insert(after, schema.nodes.text_block.create());
          tr.setSelection(TextSelection.create(tr.doc, after + 1));
          view.dispatch(tr.scrollIntoView());
          editor.message = held.cut ? "moved here" : `pasted ${nodes.length} live quote${nodes.length === 1 ? "" : "s"} · ⌘⇧V a plain copy`;
          editor.status();
        })();
        return true;
      },
    },
  });
}
