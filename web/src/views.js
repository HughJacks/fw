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

/** A date as the headers show it ("Nov 19, 2026, 11:00 PM"). */
export function prettyDate(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}

/** A quote's top line: a mini header, in the main header's style (the user, 2026-11-19), of what it shows of its source
 * (its `show`): a line of facts (the lock, its words, made, last update), then its title; empty, nothing shown. And a
 * way to open it. */
function topLine(q, open) {
  const top = el("div", "fw-top");
  const show = q.show || [], facts = [];
  if (q.lock) facts.push("⊘");
  if (show.includes("words")) facts.push(`words ${q.words ?? 0}`);
  if (show.includes("created") && q.created) facts.push(`made ${prettyDate(q.created)}`);
  if (show.includes("updated") && q.updated) facts.push(`updated ${prettyDate(q.updated)}`);
  const label = el("span", "fw-top-label");   // (left empty, no whitespace, when there's nothing: the CSS hides it)
  if (facts.length) label.appendChild(el("div", "fw-mini-facts", facts.join(" · ")));
  if (show.includes("title")) label.appendChild(el("div", "fw-mini-title", q.title));
  top.appendChild(label);
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
    else if (item.t === "image" && item.file) {   // (in a block's box, as a picture anywhere: at the text's column, 2026-11-19)
      const pic = el("div", "fw-image"), img = el("img", "fw-pic");
      img.src = `/images/${item.file}`;
      pic.appendChild(img);
      box.appendChild(pic);
    } else if (item.t === "quote") box.appendChild(quoteEl(item, open, true));
    else box.appendChild(el("div", "fw-note", item.text || ""));
  }
}

/** A quote's box: its top line, then what it shows. */
export function quoteEl(q, open, inner = false) {
  const box = el("div", inner ? "fw-quote fw-inner" : "fw-quote");
  if (q.home || q.target) box.dataset.pericope = q.home || q.target;   // (where Open it goes: motion.js steps from or to it)
  if (q.target) box.dataset.target = q.target;   // (what it quotes: the pericope, or a block in it, a step arrives at)
  if (q.lock) box.classList.add("fw-locked");
  box.appendChild(topLine(q, inner ? null : open));
  const body = el("div", "fw-body");
  drawBody(body, q.body, open);
  box.appendChild(body);
  return box;
}
