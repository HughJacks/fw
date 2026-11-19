// schema.js — the editor's document: what a pericope holds, as fw's blocks are.
//   text_block   a block of text (its lines split by hard breaks: Shift+Enter)
//   container    a block holding blocks (nested, to any depth)
//   quote        a live quote of another block, drawn read only for now (what it shows comes from the core)
//   image        a picture (only a picture pericope's own: a picture elsewhere is a quote of one)
import { Schema } from "prosemirror-model";

/** A block's DOM attributes: a paraphrase (its `para`: what it paraphrases) drawn red, "≈ its source" on top. */
const paraAttrs = (n, cls) => (n.attrs.para ? { class: `${cls} fw-para`, "data-para": `≈ ${n.attrs.para.title}` } : { class: cls });

export const schema = new Schema({
  nodes: {
    doc: { content: "block+" },
    text_block: {
      group: "block", content: "inline*",
      attrs: { id: { default: null }, own: { default: false }, marker: { default: null }, empty: { default: false }, para: { default: null } },
      parseDOM: [{ tag: "div.fw-text" }, { tag: "p" }],
      toDOM: (n) => ["div", paraAttrs(n, "fw-text"), 0],
    },
    container: {
      group: "block", content: "block+", attrs: { id: { default: null }, para: { default: null } }, defining: true,
      parseDOM: [{ tag: "div.fw-container" }],
      toDOM: (n) => ["div", paraAttrs(n, "fw-container"), 0],
    },
    quote: {
      group: "block", atom: true, selectable: true, draggable: false,
      attrs: { id: { default: null }, target: {}, data: { default: null } },
      toDOM: () => ["div", { class: "fw-quote" }],
    },
    image: {
      group: "block", atom: true, selectable: true,
      attrs: { id: { default: null }, file: {} },
      toDOM: (n) => ["div", { class: "fw-image" }, ["img", { src: `/images/${n.attrs.file}` }]],
    },
    // through a masked quote (the lens): a hidden stretch, "…" (never removed: put needs every one back), and a
    // line kept exactly as the view has it (a quote or picture inside, drawn read only)
    hole: {
      inline: true, group: "inline", atom: true, selectable: false,
      toDOM: () => ["span", { class: "fw-hole", contenteditable: "false" }, "…"],
    },
    rawline: {
      group: "block", atom: true, selectable: false, attrs: { line: {}, title: { default: "" }, data: { default: null } },
      toDOM: (n) => ["div", { class: "fw-rawline", contenteditable: "false" }, `❝ ${n.attrs.title}`],
    },
    text: { group: "inline" },
    hard_break: {
      inline: true, group: "inline", selectable: false,
      parseDOM: [{ tag: "br" }], toDOM: () => ["br"],
    },
  },
  marks: {
    // a hyperlink: a span of a block of text pointing at a pericope (the store's `links`; drawn red, underlined, ↗)
    link: {
      attrs: { to: {}, title: { default: "" } }, inclusive: false,
      parseDOM: [{ tag: "span.fw-link", getAttrs: (d) => ({ to: d.dataset.to, title: d.title }) }],
      toDOM: (m) => ["span", { class: "fw-link", "data-to": m.attrs.to, title: m.attrs.title ? `→ ${m.attrs.title}` : "" }, 0],
    },
  },
});
