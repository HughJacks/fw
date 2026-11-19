// views.js — how a quote and a picture are drawn in the editor (ProseMirror node views), and what a
// quote shows (the core's items: text, pictures, quotes inside, notes), read only for now.

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

/** Text as the page shows it: each … (a hidden stretch of a masked quote) marked. */
function textEl(text) {
  const d = el("div", "fw-qtext");
  for (const part of text.split(/(…)/)) {
    d.appendChild(part === "…" ? el("span", "fw-hidden", "…") : document.createTextNode(part));
  }
  return d;
}

/** A quote's top line: what it shows of its source (its `show`), the lock, a way to open it. */
function topLine(q, open) {
  const top = el("div", "fw-top");
  const words = [];
  if (q.lock) words.push("⊘");
  if (q.show && q.show.includes("title")) words.push(q.title);
  top.appendChild(el("span", "fw-top-label", words.join(" ")));
  if (open && q.target) {
    const go = el("button", "fw-open", "↗");
    go.title = "Open it (^O)";
    go.addEventListener("mousedown", (e) => { e.preventDefault(); open(q); });
    top.appendChild(go);
  }
  return top;
}

/** What a quote shows, drawn into `box`. */
export function drawBody(box, items, open) {
  for (const item of items || []) {
    if (item.t === "text") box.appendChild(textEl(item.text));
    else if (item.t === "image" && item.file) {
      const img = el("img", "fw-pic");
      img.src = `/images/${item.file}`;
      box.appendChild(img);
    } else if (item.t === "quote") box.appendChild(quoteEl(item, open, true));
    else box.appendChild(el("div", "fw-note", item.text || ""));
  }
}

/** A quote's box: its top line, then what it shows. */
export function quoteEl(q, open, inner = false) {
  const box = el("div", inner ? "fw-quote fw-inner" : "fw-quote");
  if (q.home || q.target) box.dataset.pericope = q.home || q.target;   // (where Open it goes: motion.js zooms from or to it)
  if (q.lock) box.classList.add("fw-locked");
  box.appendChild(topLine(q, inner ? null : open));
  const body = el("div", "fw-body");
  drawBody(body, q.body, open);
  box.appendChild(body);
  return box;
}

/** The node view of a quote in the document: drawn from its data, never edited here. */
export class QuoteView {
  constructor(node, open) {
    this.dom = quoteEl(node.attrs.data || { target: node.attrs.target, body: [] }, open);
    this.dom.contentEditable = "false";
  }
  stopEvent() { return false; }
  ignoreMutation() { return true; }
}
