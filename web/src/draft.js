// draft.js — pure: the core's JSON tree <-> the editor's document (ProseMirror JSON) -> fw's draft format.
//
// The page never sees the store. It's given a pericope as a tree of nodes (fw_web.node_json: text,
// container, quote, image) and saves it back as a draft in fw's own format (fw_draft): each block of text
// after a marker line naming it, {{block <id> <its containers, innermost first>}}, each quote one line,
// {{quote <target> <quote id> <its containers>}}. The core's commit does the rest, as for the terminal.
// No DOM here: `npm test` runs it.

const pad = (n, w = 2) => String(n).padStart(w, "0");

/** A new block id, as fw makes them: the time, and four hex digits. */
export function newId(now = new Date(), rand = Math.random) {
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}T` +
    `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `${stamp}-${Math.floor(rand() * 0x10000).toString(16).padStart(4, "0")}`;
}

/** A block of text's content: its lines, a hard break between each; its hyperlinks (`links`: [{to, at:
 * [start, end], title}], offsets into the text, a line break one) as link marks over their spans. */
export function inline(text, links = []) {
  const out = [];
  text = text || "";
  const cuts = new Set([0, text.length]);
  for (const l of links) for (const x of l.at) if (x >= 0 && x <= text.length) cuts.add(x);
  for (let i = 0; i < text.length; i++) if (text[i] === "\n") { cuts.add(i); cuts.add(i + 1); }
  const points = [...cuts].sort((a, b) => a - b);
  for (let k = 0; k + 1 < points.length; k++) {
    const [a, b] = [points[k], points[k + 1]];
    const piece = text.slice(a, b);
    if (piece === "\n") { out.push({ type: "hard_break" }); continue; }
    if (!piece) continue;
    const link = links.find((l) => l.at[0] <= a && b <= l.at[1]);
    out.push(link ? { type: "text", text: piece, marks: [{ type: "link", attrs: { to: link.to, title: link.title || "" } }] }
                  : { type: "text", text: piece });
  }
  return out;
}

/** One node of the core's tree -> a ProseMirror node (JSON). */
export function pmNode(node) {
  switch (node.t) {
    case "text": return { type: "text_block", attrs: { id: node.id, own: !!node.own, para: node.para || null }, content: inline(node.text, node.links) };
    case "container": return { type: "container", attrs: { id: node.id, para: node.para || null },
      content: node.children.length ? node.children.map(pmNode) : [{ type: "text_block", attrs: { id: null } }] };
    case "quote": return { type: "quote", attrs: { id: node.id, target: node.target, data: node } };
    case "image": return { type: "image", attrs: { id: node.id, file: node.file } };
    case "expr": return { type: "expr", attrs: { id: node.id, source: node.source || "" } };
    default: return { type: "text_block", attrs: { id: null }, content: inline(node.text || "") };
  }
}

/** A pericope's blocks (the core's tree) -> the editor's document (JSON). */
export function pmDoc(children) {
  const content = (children || []).map(pmNode);
  return { type: "doc", content: content.length ? content : [{ type: "text_block", attrs: { id: null } }] };
}

/** A block of text's text (JSON): its lines. */
function textOf(node) {
  return (node.content || []).map((c) => (c.type === "hard_break" ? "\n" : c.text || "")).join("");
}

const within = (ids) => ids.map((c) => " " + c).join("");

/** The editor's document (JSON) -> fw's draft. A picture (a picture pericope's own) isn't in it. A block
 * of text that's the block being saved itself (`own`: a quote of a block of text, an old one-text pericope)
 * is its text alone, no marker. */
export function draftOf(doc) {
  const lines = [];
  const walk = (nodes, outer) => {
    for (const n of nodes || []) {
      if (n.type === "text_block" && n.attrs.own) {
        lines.push(textOf(n));
      } else if (n.type === "text_block") {
        lines.push(`{{block ${n.attrs.id}${within(outer)}}}`, textOf(n));
      } else if (n.type === "container") {
        walk(n.content, [n.attrs.id, ...outer]);
      } else if (n.type === "quote") {
        lines.push(`{{quote ${n.attrs.target} ${n.attrs.id}${within(outer)}}}`);
      } else if (n.type === "expr") {   // (its source as a JSON string: one line, fw_draft.EXPR_RE)
        lines.push(`{{expr ${n.attrs.id}${within(outer)} ${JSON.stringify(n.attrs.source || "")}}}`);
      }
    }
  };
  walk(doc.content, []);
  return lines.join("\n");
}

/** The editor's document (JSON), or one node of it, as the expression engine reads a block (the snapshot's node, as
 * fw_web.snap_node makes them from the store): text, a paraphrase, a quote, a picture, an expression, or blocks. */
export function snapNode(n) {
  const id = n.attrs?.id || "";
  switch (n.type) {
    case "doc": {
      const kids = n.content || [];
      if (kids.length === 1 && kids[0].type === "text_block" && kids[0].attrs.own) return snapNode(kids[0]);   // (a pericope that's one text)
      return { id, t: "blocks", children: kids.map(snapNode) };
    }
    case "text_block": return n.attrs.para ? { id, t: "paraphrase", target: n.attrs.para.id, text: textOf(n) } : { id, t: "text", text: textOf(n), links: linksOf(n) };
    case "container": return { id, t: "blocks", children: (n.content || []).map(snapNode) };
    case "quote": return { id, t: "quote", target: n.attrs.target };
    case "image": return { id, t: "picture", target: id };
    case "expr": return { id, t: "expr", source: n.attrs.source || "" };
    default: return { id, t: "unknown" };
  }
}

/** A block of text's (JSON) links: [{to, at: [start, end]}], offsets into its text (a line break one), runs joined. */
function linksOf(node) {
  const out = [];
  let at = 0;
  for (const c of node.content || []) {
    const len = c.type === "hard_break" ? 1 : (c.text || "").length;
    const to = (c.marks || []).find((m) => m.type === "link")?.attrs.to;
    const last = out[out.length - 1];
    if (to && last && last.to === to && last.at[1] === at) last.at[1] = at + len;
    else if (to) out.push({ to, at: [at, at + len] });
    at += len;
  }
  return out;
}

/** Ids a document needs: every block of text, container and quote with one, none twice (an Enter splits
 * a block: the new half gets one; a pasted quote becomes a new quote of the same block). `blocks` are
 * {type, id} in document order; returns a Map of index -> the new id to give it. */
export function freshIds(blocks, make = newId) {
  const seen = new Set(), out = new Map();
  blocks.forEach(({ type, id }, n) => {
    if (!["text_block", "container", "quote", "expr"].includes(type)) return;
    if (id && !seen.has(id)) { seen.add(id); return; }
    let fresh = make();
    while (seen.has(fresh)) fresh = make();
    seen.add(fresh);
    out.set(n, fresh);
  });
  return out;
}

/** A masked quote's view (the core's lens segments) -> a document: each block of text its shown text, each
 * hidden stretch (`hole`, the view's mark) a hole; a kept line a rawline. */
export function pmLens(segments, hole) {
  const content = segments.map((seg) => {
    if (seg.t === "line") return { type: "rawline", attrs: { line: seg.line, title: seg.title, data: seg.data || null } };
    const inl = [];
    seg.text.split(hole).forEach((piece, n) => {
      if (n) inl.push({ type: "hole" });
      inl.push(...inline(piece));
    });
    return { type: "text_block", attrs: { id: seg.id, marker: seg.marker, empty: seg.empty }, content: inl };
  });
  return { type: "doc", content: content.length ? content : [{ type: "text_block", attrs: {} }] };
}

/** The document written through a masked quote -> its view's text, as the lens's put takes it back: each block
 * its marker line (as it was), then its text, each hole the view's mark again. */
export function lensOf(doc, hole) {
  const lines = [];
  for (const n of doc.content || []) {
    if (n.type === "rawline") { lines.push(n.attrs.line); continue; }
    const text = (n.content || []).map((c) => (c.type === "hole" ? hole : c.type === "hard_break" ? "\n" : c.text || "")).join("");
    if (n.attrs.marker) lines.push(n.attrs.marker);
    if (!(n.attrs.empty && text === "")) lines.push(text);
  }
  return lines.join("\n");
}

const TITLE_MAX = 60;   // (fw_block.TITLE_MAX_CHARS)
/** A title from the text, as fw_block.derive_title: its first real line, minus leading markup and quotes,
 * clipped at a word to 60 characters; null with nothing to name it by. */
export function deriveTitle(text) {
  for (const raw of text.split(/\r\n|\r|\n/)) {
    const line = raw.trim().replace(/^[#>\-*\s]+/, "").trim().replace(/^["'“”]+|["'“”]+$/g, "");
    if (!line || /^-{2,}/.test(raw.trim())) continue;
    const trim = (s) => s.replace(/[.,;:—\- ]+$/, "");
    if (line.length <= TITLE_MAX) return trim(line);
    const cut = line.slice(0, TITLE_MAX), at = cut.lastIndexOf(" ");
    const clipped = trim(at >= 0 ? cut.slice(0, at) : cut);
    return (clipped || cut.trimEnd()) + "…";
  }
  return null;
}
